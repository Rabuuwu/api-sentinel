"""Real PostgreSQL checks. Never use DATABASE_URL; explicit test DB only."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("asyncpg")
from sqlalchemy import func, select, text, update
from sqlalchemy.engine import make_url

from api_sentinel.alerts import send_pending
from api_sentinel.app import create_app
from api_sentinel.checker import CheckResult
from api_sentinel.config import Settings
from api_sentinel.db import Database
from api_sentinel.models import Alert, Execution, Incident, Monitor, now
from api_sentinel.service import record, recover_abandoned, reserve

pytestmark = pytest.mark.integration


def settings():
    url = os.getenv("SENTINEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set SENTINEL_TEST_DATABASE_URL to an isolated migrated PostgreSQL database")
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or parsed.database != "sentinel_test":
        pytest.fail("Tests only accept a localhost database named sentinel_test")
    return Settings(
        url,
        "integration-test-key-" + "x" * 32,
        discord_webhook_url="https://discord.com/api/webhooks/test/test",
    )


def test_database_api_worker_lifecycle():
    config = settings()

    async def run():
        app = create_app(config)
        db: Database = app.state.db
        monitor_id = None
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                assert (await client.get("/api/v1/monitors")).status_code == 401
                client.headers["X-API-Key"] = config.api_key
                invalid = await client.post(
                    "/api/v1/monitors", json={"name": "private", "url": "http://127.0.0.1"}
                )
                assert invalid.status_code == 422
                created = await client.post(
                    "/api/v1/monitors", json={"name": "integration", "url": "https://example.com"}
                )
                assert created.status_code == 201, created.text
                monitor_id = created.json()["id"]
                from uuid import UUID

                mid = UUID(monitor_id)
                stats = (await client.get(f"/api/v1/monitors/{mid}/stats")).json()
                assert stats["success_rate_percent"] is None
                work = await reserve(db, 100)
                execution_id = next(key for key, data in work if data.name == "integration")
                await asyncio.gather(
                    *(
                        record(db, execution_id, CheckResult("HTTP_ERROR", 500), "discord")
                        for _ in range(2)
                    )
                )
                async with db.sessions() as session:
                    monitor = await session.get(Monitor, mid)
                    assert monitor.consecutive_failures == 1

                async def add_result(result):
                    async with db.sessions.begin() as session:
                        monitor = await session.get(Monitor, mid)
                        execution = Execution(
                            id=uuid4(),
                            monitor_id=mid,
                            generation=monitor.generation,
                            scheduled_for=now(),
                        )
                        session.add(execution)
                    await record(db, execution.id, result, "discord")

                for _ in range(2):
                    await add_result(CheckResult("HTTP_ERROR", 500))
                async with db.sessions() as session:
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(Incident)
                            .where(Incident.monitor_id == mid)
                        )
                        == 1
                    )
                assert (
                    await client.patch(
                        f"/api/v1/monitors/{mid}", json={"url": "https://other.example.com"}
                    )
                ).status_code == 409
                await client.post(f"/api/v1/monitors/{mid}/pause")
                async with db.sessions.begin() as session:
                    await session.execute(
                        update(Monitor)
                        .where(Monitor.id == mid)
                        .values(next_run_at=now() - timedelta(seconds=60))
                    )
                assert not await reserve(db, 100)
                await client.post(f"/api/v1/monitors/{mid}/resume")
                await add_result(CheckResult("SUCCESS", 200, 100))
                await add_result(CheckResult("SUCCESS", 200, 200))
                stats = (await client.get(f"/api/v1/monitors/{mid}/stats")).json()
                assert stats["completed_checks"] == 5
                assert stats["success_rate_percent"] == 40
                assert stats["latency_p50_ms"] == 150
                assert stats["open_incidents"] == 0
                # History cursor does not repeat rows even when timestamps tie.
                first = (await client.get(f"/api/v1/monitors/{mid}/checks?limit=2")).json()
                second = (
                    await client.get(
                        f"/api/v1/monitors/{mid}/checks",
                        params={"limit": 2, "cursor": first["next_cursor"]},
                    )
                ).json()
                assert not ({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]})
                # Transient Discord failure leaves both logical events retryable.
                await send_pending(db, config, httpx.MockTransport(lambda r: httpx.Response(503)))
                async with db.sessions() as session:
                    alerts = (
                        await session.scalars(
                            select(Alert).join(Incident).where(Incident.monitor_id == mid)
                        )
                    ).all()
                    assert len(alerts) == 2
                    assert all(a.delivery_state == "PENDING" and a.attempts == 1 for a in alerts)
                # Editing invalidates an in-flight check without losing its history.
                work = await reserve(db, 100)
                stale_id = next(key for key, data in work if data.name == "integration")
                assert (
                    await client.patch(f"/api/v1/monitors/{mid}", json={"name": "edited"})
                ).status_code == 200
                await record(db, stale_id, CheckResult("HTTP_ERROR", 500), "discord")
                async with db.sessions() as session:
                    assert (await session.get(Monitor, mid)).consecutive_failures == 0
                # Lost worker reservations are unknown, not target failures.
                await reserve(db, 100)
                await recover_abandoned(db)
                stats = (await client.get(f"/api/v1/monitors/{mid}/stats")).json()
                assert stats["aborted_checks"] == 1
                assert (await client.delete(f"/api/v1/monitors/{mid}")).status_code == 204
                assert (await client.get(f"/api/v1/monitors/{mid}")).status_code == 404
        finally:
            if monitor_id:
                async with db.sessions.begin() as session:
                    # Only remove this test's rows, never truncate a shared database.
                    await session.execute(
                        text(
                            "DELETE FROM alert_outbox WHERE incident_id IN "
                            "(SELECT id FROM incidents WHERE monitor_id=CAST(:id AS uuid))"
                        ),
                        {"id": monitor_id},
                    )
                    for table in ("monitor_events", "incidents", "check_executions"):
                        await session.execute(
                            text(f"DELETE FROM {table} WHERE monitor_id=CAST(:id AS uuid)"),
                            {"id": monitor_id},
                        )
                    await session.execute(
                        text("DELETE FROM monitors WHERE id=CAST(:id AS uuid)"), {"id": monitor_id}
                    )
            await db.close()

    asyncio.run(run())
