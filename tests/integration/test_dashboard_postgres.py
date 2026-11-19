import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from account_helpers import create_identity, remove_identity
from sqlalchemy import select, text, update
from sqlalchemy.engine import make_url

from api_sentinel.app import create_app
from api_sentinel.checker import CheckResult
from api_sentinel.config import Settings
from api_sentinel.metrics import metrics, percentile
from api_sentinel.models import Alert, Execution, Incident, Monitor, MonitorEvent, now
from api_sentinel.service import record

pytestmark = pytest.mark.integration


def test_real_metrics_events_and_public_redaction(tmp_path):
    url = os.getenv("SENTINEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires explicitly migrated isolated PostgreSQL sentinel_test")
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"} and parsed.database == "sentinel_test"
    config = Settings(url, "integration-key-" + "x" * 40, secrets_dir=str(tmp_path))

    async def run():
        app = create_app(config)
        db = app.state.db
        user_id, token = await create_identity(db)
        mid = uuid4()
        page_id = None
        try:
            async with db.sessions.begin() as session:
                session.add(
                    Monitor(
                        id=mid,
                        owner_id=user_id,
                        name="Dashboard test",
                        url="https://example.com/private",
                        degraded_latency_ms=250,
                        degraded_threshold=2,
                    )
                )
            for latency in [100, 200, 300, 400]:
                async with db.sessions.begin() as session:
                    execution = Execution(
                        id=uuid4(), monitor_id=mid, generation=0, scheduled_for=now()
                    )
                    session.add(execution)
                await record(db, execution.id, CheckResult("SUCCESS", 200, latency), "console")
            async with db.sessions() as session:
                data = await metrics(session, mid, "24h", now() + timedelta(seconds=1))
                assert data["summary"]["uptime"] == 100
                assert data["summary"]["degraded"] == 2
                for p in [50, 75, 90, 95, 99]:
                    assert data["summary"][f"p{p}"] == percentile([100, 200, 300, 400], p)
                assert len(data["buckets"]) == 60
                assert any(bucket["uptime"] is None for bucket in data["buckets"])
                assert (await session.get(Monitor, mid)).status == "DEGRADED"
                events = (
                    await session.scalars(
                        select(MonitorEvent).where(MonitorEvent.monitor_id == mid)
                    )
                ).all()
                assert [event.action for event in events] == ["MONITOR_DEGRADED"]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                client.headers["Authorization"] = "Bearer " + token
                page = await client.post(
                    "/api/v1/status-pages",
                    json={
                        "name": "Public test",
                        "slug": "test-" + mid.hex,
                        "monitor_ids": [str(mid)],
                        "published": True,
                    },
                )
                assert page.status_code == 201, page.text
                page_id = page.json()["id"]
                client.headers.clear()
                public = await client.get("/api/v1/public/status-pages/test-" + mid.hex)
                assert public.status_code == 200
                assert "example.com/private" not in public.text
                assert "url" not in public.json()["monitors"][0]
                async with db.sessions.begin() as session:
                    await session.execute(update(Monitor).where(Monitor.id == mid).values(
                        status="UP", last_checked_at=now()-timedelta(hours=1)))
                stale = await client.get("/api/v1/public/status-pages/test-" + mid.hex)
                item = stale.json()["monitors"][0]
                assert item["status"] == "UNKNOWN" and item["freshness"] == "STALE"
                assert item["last_observed_status"] == "UP"
                assert item["history"]["completed_checks"] == 4
                client.headers["Authorization"] = "Bearer " + token
                overview = await client.get("/api/v1/overview?status=UNKNOWN")
                assert overview.status_code == 200, overview.text
                assert str(mid) in [m["id"] for m in overview.json()["items"]]
                assert overview.json()["summary"]["operational"] == 0
                async with db.sessions() as session:
                    assert (await session.get(Monitor, mid)).status == "UP"
        finally:
            async with db.sessions.begin() as session:
                if page_id:
                    await session.execute(
                        text("DELETE FROM status_pages WHERE id=CAST(:id AS uuid)"), {"id": page_id}
                    )
                for model in (MonitorEvent, Execution):
                    await session.execute(model.__table__.delete().where(model.monitor_id == mid))
                await session.execute(
                    Alert.__table__.delete().where(
                        Alert.incident_id.in_(select(Incident.id).where(Incident.monitor_id == mid))
                    )
                )
                await session.execute(Incident.__table__.delete().where(Incident.monitor_id == mid))
                await session.execute(Monitor.__table__.delete().where(Monitor.id == mid))
            await remove_identity(db, user_id)
            await db.close()

    asyncio.run(run())


def test_encrypted_channel_survives_api_restart_without_local_files(tmp_path):
    url = os.getenv("SENTINEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires explicitly migrated isolated PostgreSQL sentinel_test")
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"} and parsed.database == "sentinel_test"
    pytest.importorskip("cryptography")
    from api_sentinel.models import NotificationChannel
    from api_sentinel.vault import EncryptedVault

    config = Settings(
        url,
        "integration-key-" + "x" * 40,
        secrets_dir=str(tmp_path),
        webhook_encryption_key="ab" * 32,
    )

    async def run():
        from uuid import UUID

        app = create_app(config)
        user_id, token = await create_identity(app.state.db)
        channel_id = None
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://localhost",
                headers={"Authorization": "Bearer " + token},
            ) as client:
                created = await client.post(
                    "/api/v1/notifications",
                    json={
                        "name": "Encrypted integration channel",
                        "webhook_url": "https://discord.com/api/webhooks/123/test-token",
                    },
                )
                assert created.status_code == 201
                channel_id = UUID(created.json()["id"])
                assert "test-token" not in created.text
                assert "ciphertext" not in created.text
            await app.state.db.close()
            app = create_app(config)
            async with app.state.db.sessions() as session:
                channel = await session.get(NotificationChannel, channel_id)
                assert channel.webhook_ciphertext
                assert (
                    EncryptedVault(config.webhook_encryption_key).decrypt(
                        channel.id, channel.webhook_ciphertext
                    )
                    == "https://discord.com/api/webhooks/123/test-token"
                )
            assert list(tmp_path.iterdir()) == []
        finally:
            if channel_id:
                async with app.state.db.sessions.begin() as session:
                    await session.execute(
                        NotificationChannel.__table__.delete().where(
                            NotificationChannel.id == channel_id
                        )
                    )
            await remove_identity(app.state.db, user_id)
            await app.state.db.close()

    asyncio.run(run())
