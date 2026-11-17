"""Real HTTP + PostgreSQL account isolation; explicit localhost test database only."""

import asyncio
import os
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from account_helpers import remove_identity
from sqlalchemy import delete, select, update
from sqlalchemy.engine import make_url

from api_sentinel.app import create_app
from api_sentinel.auth import digest
from api_sentinel.auth_models import AuthBudget, AuthSession, Invitation, User
from api_sentinel.config import Settings
from api_sentinel.models import Incident, Monitor, now

pytestmark = pytest.mark.integration
PASSWORD = "a test passphrase with sufficient length"


def test_accounts_ownership_sessions_and_registration(tmp_path):
    url = os.getenv("SENTINEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires isolated migrated localhost sentinel_test")
    parsed = make_url(url)
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database == "sentinel_test"

    async def run():
        settings = Settings(
            url,
            "test-setup-key-" + "x" * 40,
            secrets_dir=str(tmp_path),
            webhook_encryption_key="ab" * 32,
        )
        app = create_app(settings)
        db = app.state.db
        users = []
        legacy_id = uuid4()
        async with db.sessions.begin() as session:
            assert not await session.scalar(select(User.id).limit(1)), "Use an empty test database"
            await session.execute(delete(AuthBudget))
            session.add(Monitor(id=legacy_id, name="Existing monitor", url="https://example.com"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:

            async def request(method, path, token=None, body=None):
                return await client.request(
                    method,
                    "/api/v1" + path,
                    json=body,
                    headers={"Authorization": "Bearer " + token} if token else {},
                )

            async def register(username, invitation):
                response = await request(
                    "POST",
                    "/auth/register",
                    body={"username": username, "password": PASSWORD, "invitation": invitation},
                )
                assert response.status_code == 201, response.text
                data = response.json()
                users.append(UUID(data["user"]["id"]))
                return data["token"]

            try:
                assert (await request("GET", "/auth/setup")).json()["setup_required"]
                invalid = await request(
                    "POST",
                    "/auth/bootstrap",
                    body={"username": "owner", "password": PASSWORD, "setup_key": "wrong" * 10},
                )
                assert invalid.status_code == 401
                result = await request(
                    "POST",
                    "/auth/bootstrap",
                    body={"username": "Owner", "password": PASSWORD, "setup_key": settings.api_key},
                )
                assert result.status_code == 201, result.text
                data = result.json()
                admin = data["token"]
                users.append(UUID(data["user"]["id"]))
                assert data["user"]["username"] == "owner" and data["user"]["is_admin"]
                assert not (await request("GET", "/auth/setup")).json()["setup_required"]
                assert (await request("GET", f"/monitors/{legacy_id}", admin)).status_code == 200
                assert (
                    await client.get("/api/v1/monitors", headers={"X-API-Key": settings.api_key})
                ).status_code == 401
                assert (
                    await request(
                        "POST",
                        "/auth/bootstrap",
                        body={
                            "username": "intruder",
                            "password": PASSWORD,
                            "setup_key": settings.api_key,
                        },
                    )
                ).status_code == 409
                invite = (await request("POST", "/auth/invitations", admin)).json()["invitation"]
                alice = await register("alice", invite)
                assert (
                    await request(
                        "POST",
                        "/auth/register",
                        body={"username": "reuse", "password": PASSWORD, "invitation": invite},
                    )
                ).status_code == 400
                invite2 = (await request("POST", "/auth/invitations", admin)).json()["invitation"]
                bob = await register("bob", invite2)
                assert (await request("POST", "/auth/invitations", alice)).status_code == 403
                assert (await request("GET", "/auth/users", alice)).status_code == 403
                assert (await request("GET", "/monitors", alice)).json()["items"] == []
                assert (await request("GET", "/monitors", bob)).json()["items"] == []
                channel = await request(
                    "POST",
                    "/notifications",
                    alice,
                    {
                        "name": "Alice channel",
                        "webhook_url": "https://discord.com/api/webhooks/123/test-token",
                    },
                )
                assert channel.status_code == 201, channel.text
                cid = channel.json()["id"]
                assert "test-token" not in channel.text and "ciphertext" not in channel.text
                monitor = await request(
                    "POST",
                    "/monitors",
                    alice,
                    {
                        "name": "Alice private",
                        "url": "https://example.com/private",
                        "notification_channel_ids": [cid],
                    },
                )
                assert monitor.status_code == 201, monitor.text
                mid = monitor.json()["id"]
                iid = uuid4()
                async with db.sessions.begin() as session:
                    session.add(
                        Incident(
                            id=iid,
                            monitor_id=UUID(mid),
                            started_at=now(),
                            reason="HTTP_ERROR",
                            failure_count_at_open=3,
                        )
                    )
                page = await request(
                    "POST",
                    "/status-pages",
                    alice,
                    {
                        "name": "Alice status",
                        "slug": "alice-test",
                        "monitor_ids": [mid],
                        "published": True,
                    },
                )
                assert page.status_code == 201, page.text
                pid = page.json()["id"]
                for method, path, body in [
                    ("GET", f"/monitors/{mid}", None),
                    ("PATCH", f"/monitors/{mid}", {"name": "stolen"}),
                    ("DELETE", f"/monitors/{mid}", None),
                    ("POST", f"/monitors/{mid}/pause", None),
                    ("POST", f"/monitors/{mid}/resume", None),
                    *[
                        ("GET", f"/monitors/{mid}/{suffix}", None)
                        for suffix in ("checks", "incidents", "stats", "metrics", "timeline")
                    ],
                    ("GET", f"/incidents/{iid}", None),
                    ("PATCH", f"/notifications/{cid}", {"enabled": False}),
                    ("DELETE", f"/notifications/{cid}", None),
                    ("POST", f"/notifications/{cid}/test", None),
                    ("GET", f"/notifications/{cid}/deliveries", None),
                    (
                        "PUT",
                        f"/status-pages/{pid}",
                        {"name": "stolen", "slug": "stolen", "monitor_ids": [mid]},
                    ),
                    ("DELETE", f"/status-pages/{pid}", None),
                ]:
                    denied = await request(method, path, bob, body)
                    assert denied.status_code == 404, (method, path, denied.text)
                for path in ("/overview", "/incidents", "/notifications", "/status-pages"):
                    result = await request("GET", path, bob)
                    assert result.status_code == 200, result.text
                    assert "Alice" not in result.text and mid not in result.text
                overview = (await request("GET", "/overview", bob)).json()
                assert overview["summary"]["total"] == 0
                assert overview["summary"]["open_incidents"] == 0
                assert overview["summary"]["average_ms"] is None
                assert (
                    await request(
                        "POST",
                        "/monitors",
                        bob,
                        {
                            "name": "bad",
                            "url": "https://example.com",
                            "notification_channel_ids": [cid],
                        },
                    )
                ).status_code == 422
                assert (
                    await request(
                        "POST",
                        "/status-pages",
                        bob,
                        {"name": "bad", "slug": "bad", "monitor_ids": [mid]},
                    )
                ).status_code == 422
                public = await request("GET", "/public/status-pages/alice-test")
                assert public.status_code == 200
                assert "private" not in public.text.lower().replace("alice private", "")
                assert "owner_id" not in public.text and "reason" not in public.text
                async with db.sessions() as session:
                    row = await session.get(User, users[1])
                    assert (
                        row.password_hash.startswith("$argon2id$")
                        and PASSWORD not in row.password_hash
                    )
                    stored = await session.get(AuthSession, digest(alice))
                    assert stored is not None and stored.token_hash != alice
                    assert await session.get(Invitation, digest(invite)) is None
                assert (await request("POST", "/auth/logout", alice)).status_code == 204
                assert (await request("GET", "/auth/me", alice)).status_code == 401
                login = await request(
                    "POST", "/auth/login", body={"username": "ALICE", "password": PASSWORD}
                )
                alice = login.json()["token"]
                assert (
                    await request(
                        "POST",
                        "/auth/password",
                        alice,
                        {
                            "current_password": PASSWORD,
                            "new_password": "a new test passphrase 5678",
                        },
                    )
                ).status_code == 204
                assert (await request("GET", "/auth/me", alice)).status_code == 401
                assert (
                    await request(
                        "POST", "/auth/login", body={"username": "alice", "password": PASSWORD}
                    )
                ).status_code == 401
                assert (
                    await request(
                        "POST",
                        "/auth/login",
                        body={"username": "alice", "password": "a new test passphrase 5678"},
                    )
                ).status_code == 200
                async with db.sessions.begin() as session:
                    await session.execute(
                        update(AuthSession)
                        .where(AuthSession.token_hash == digest(bob))
                        .values(last_seen=now() - timedelta(minutes=31))
                    )
                assert (await request("GET", "/auth/me", bob)).status_code == 401
                async with db.sessions.begin() as session:
                    await session.execute(
                        update(AuthSession)
                        .where(AuthSession.token_hash == digest(admin))
                        .values(expires_at=now() - timedelta(seconds=1))
                    )
                assert (await request("GET", "/auth/me", admin)).status_code == 401
                for _ in range(8):
                    assert (
                        await request(
                            "POST",
                            "/auth/login",
                            body={"username": "missing", "password": PASSWORD},
                        )
                    ).status_code == 401
                assert (
                    await request(
                        "POST", "/auth/login", body={"username": "missing", "password": PASSWORD}
                    )
                ).status_code == 429
            finally:
                for user in reversed(users):
                    await remove_identity(db, user)
                async with db.sessions.begin() as session:
                    await session.execute(delete(Monitor).where(Monitor.id == legacy_id))
                    await session.execute(delete(AuthBudget))
                await db.close()

    asyncio.run(run())
