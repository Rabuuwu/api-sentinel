"""Email recovery with real DB transactions and a fake HTTPS mail provider only."""

import asyncio
import json
import os
from datetime import timedelta

import httpx
import pytest
from account_helpers import create_identity, remove_identity
from sqlalchemy import delete, select, update
from sqlalchemy.engine import make_url

from api_sentinel.app import create_app
from api_sentinel.auth import digest
from api_sentinel.auth_models import AuthBudget, EmailAction, MailDelivery, User
from api_sentinel.config import Settings
from api_sentinel.mailer import cipher, send_mail_pending
from api_sentinel.models import now

pytestmark = pytest.mark.integration
PASSWORD = "test only passphrase 1234"


def test_email_verification_reset_and_outbox(tmp_path):
    url = os.getenv("SENTINEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires isolated migrated localhost sentinel_test")
    parsed = make_url(url)
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database == "sentinel_test"
    settings = Settings(
        url,
        "x" * 40,
        secrets_dir=str(tmp_path),
        webhook_encryption_key="ab" * 32,
        gmail_client_id="test-client",
        gmail_client_secret="test-secret",
        gmail_refresh_token="test-refresh",
        mail_from="sender@gmail.com",
        public_app_url="https://example.com/sentinel/",
    )

    async def run():
        app = create_app(settings)
        db = app.state.db
        uid, token = await create_identity(db)
        guest_id = None
        async with db.sessions.begin() as session:
            await session.execute(delete(AuthBudget))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:

            async def request(path, data=None, auth=False):
                return await client.post(
                    "/api/v1/auth" + path,
                    json=data,
                    headers={"Authorization": "Bearer " + token} if auth else {},
                )

            async def queued(purpose):
                from urllib.parse import parse_qs, urlsplit

                async with db.sessions() as session:
                    action = await session.scalar(
                        select(EmailAction).where(
                            EmailAction.user_id == uid, EmailAction.purpose == purpose
                        )
                    )
                    delivery = await session.scalar(
                        select(MailDelivery).where(MailDelivery.action_hash == action.token_hash)
                    )
                    payload = json.loads(cipher(settings).decrypt(delivery.ciphertext.encode()))
                    query = parse_qs(urlsplit(payload["link"]).fragment.split("?")[1])
                    secret = query["token"][0]
                    assert secret not in delivery.ciphertext and action.token_hash == digest(secret)
                    return secret, delivery.id

            try:
                assert (
                    await request(
                        "/email", {"email": "alice@example.com", "current_password": PASSWORD}, True
                    )
                ).status_code == 202
                verify_token, delivery_id = await queued("verify")
                assert (
                    await request("/password-reset/request", {"email": "alice@example.com"})
                ).status_code == 202
                async with db.sessions() as session:
                    assert not await session.scalar(
                        select(EmailAction).where(EmailAction.purpose == "reset")
                    )

                def fake_google(r):
                    if r.url.host == "oauth2.googleapis.com":
                        return httpx.Response(200, json={"access_token": "fake-access"})
                    return httpx.Response(200, json={"id": "fake-message"})

                def busy_google(r):
                    if r.url.host == "oauth2.googleapis.com":
                        return httpx.Response(200, json={"access_token": "fake-access"})
                    return httpx.Response(429, json={"error": "quota"})

                await send_mail_pending(db, settings, httpx.MockTransport(busy_google))
                async with db.sessions.begin() as session:
                    delivery = await session.get(MailDelivery, delivery_id)
                    assert delivery.state == "PENDING" and delivery.attempts == 1
                    assert delivery.ciphertext and delivery.next_attempt_at > now()
                    delivery.next_attempt_at = now() - timedelta(seconds=1)
                await send_mail_pending(db, settings, httpx.MockTransport(fake_google))
                async with db.sessions() as session:
                    delivery = await session.get(MailDelivery, delivery_id)
                    assert delivery.state == "SENT" and delivery.ciphertext is None
                # Wrong-purpose action cannot change a password.
                assert (
                    await request(
                        "/password-reset/confirm",
                        {"token": verify_token, "new_password": "new test passphrase 5678"},
                    )
                ).status_code == 400
                assert (await request("/email/verify", {"token": verify_token})).status_code == 200
                assert (await request("/email/verify", {"token": verify_token})).status_code == 400
                async with db.sessions() as session:
                    user = await session.get(User, uid)
                    username = user.username
                    assert user.email == "alice@example.com" and user.pending_email is None
                assert (
                    await client.get(
                        "/api/v1/auth/me", headers={"Authorization": "Bearer " + token}
                    )
                ).status_code == 401
                login_before_reset = await request(
                    "/login", {"username": username, "password": PASSWORD}
                )
                active_token = login_before_reset.json()["token"]
                # Existing and unknown addresses produce exactly the same response.
                existing = await request("/password-reset/request", {"email": "alice@example.com"})
                unknown = await request("/password-reset/request", {"email": "unknown@example.com"})
                assert existing.status_code == unknown.status_code == 202
                assert existing.json() == unknown.json()
                reset_token, _ = await queued("reset")
                assert (await request("/email/verify", {"token": reset_token})).status_code == 400
                response = await request(
                    "/password-reset/confirm",
                    {"token": reset_token, "new_password": "new test passphrase 5678"},
                )
                assert response.status_code == 200, response.text
                assert (
                    await client.get(
                        "/api/v1/auth/me", headers={"Authorization": "Bearer " + active_token}
                    )
                ).status_code == 401
                assert (
                    await request(
                        "/password-reset/confirm",
                        {"token": reset_token, "new_password": "new test passphrase 5678"},
                    )
                ).status_code == 400
                assert (
                    await request("/login", {"username": username, "password": PASSWORD})
                ).status_code == 401
                login = await request(
                    "/login", {"username": username, "password": "new test passphrase 5678"}
                )
                assert login.status_code == 200
                # Expiration enforced by the API, independently of the worker's cleanup.
                async with db.sessions.begin() as session:
                    await session.execute(delete(AuthBudget))
                assert (
                    await request("/password-reset/request", {"email": "alice@example.com"})
                ).status_code == 202
                expired, _ = await queued("reset")
                async with db.sessions.begin() as session:
                    await session.execute(
                        update(EmailAction)
                        .where(EmailAction.token_hash == digest(expired))
                        .values(expires_at=now() - timedelta(seconds=1))
                    )
                assert (
                    await request(
                        "/password-reset/confirm",
                        {"token": expired, "new_password": "new test passphrase 9999"},
                    )
                ).status_code == 400
                # New accounts cannot log in until their mailbox has been confirmed.
                async with db.sessions.begin() as session:
                    await session.execute(delete(AuthBudget))
                    await session.execute(update(User).where(User.id == uid).values(is_admin=True))
                admin_login = await request(
                    "/login", {"username": username, "password": "new test passphrase 5678"}
                )
                token = admin_login.json()["token"]
                invitation = await request("/invitations", auth=True)
                registration = await request(
                    "/register",
                    {
                        "username": "mail-guest",
                        "password": PASSWORD,
                        "email": "guest@example.com",
                        "invitation": invitation.json()["invitation"],
                    },
                )
                assert registration.status_code == 201, registration.text
                assert registration.json()["verification_required"]
                assert "token" not in registration.json()
                async with db.sessions() as session:
                    guest = await session.scalar(select(User).where(User.username == "mail-guest"))
                    guest_id = guest.id
                    old_action = await session.scalar(
                        select(EmailAction).where(EmailAction.user_id == guest_id)
                    )
                    old_hash = old_action.token_hash
                assert (
                    await request("/login", {"username": "mail-guest", "password": PASSWORD})
                ).status_code == 403
                assert (
                    await request(
                        "/email/resend", {"username": "mail-guest", "email": "guest@example.com"}
                    )
                ).status_code == 202
                async with db.sessions() as session:
                    assert await session.get(EmailAction, old_hash) is None
                    delivery = await session.scalar(
                        select(MailDelivery)
                        .join(EmailAction)
                        .where(EmailAction.user_id == guest_id)
                    )
                    payload = json.loads(cipher(settings).decrypt(delivery.ciphertext.encode()))
                    from urllib.parse import parse_qs, urlsplit

                    guest_token = parse_qs(urlsplit(payload["link"]).fragment.split("?")[1])[
                        "token"
                    ][0]
                assert (await request("/email/verify", {"token": guest_token})).status_code == 200
                assert (
                    await request("/login", {"username": "mail-guest", "password": PASSWORD})
                ).status_code == 200
            finally:
                if guest_id:
                    await remove_identity(db, guest_id)
                await remove_identity(db, uid)
                async with db.sessions.begin() as session:
                    await session.execute(delete(AuthBudget))
                await db.close()

    asyncio.run(run())
