import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
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
        mid = uuid4()
        page_id = None
        try:
            async with db.sessions.begin() as session:
                session.add(
                    Monitor(
                        id=mid,
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
                client.headers["X-API-Key"] = config.api_key
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
            await db.close()

    asyncio.run(run())
