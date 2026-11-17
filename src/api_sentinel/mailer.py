"""Gmail HTTPS transport and durable delivery. No SMTP ports or message/token logs."""

import base64
import json
import logging
from datetime import timedelta
from email.message import EmailMessage
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

from api_sentinel.auth_models import EmailAction, MailDelivery
from api_sentinel.mail_config import normalize_email
from api_sentinel.models import now

logger = logging.getLogger("sentinel")


def cipher(settings):
    return Fernet(base64.urlsafe_b64encode(bytes.fromhex(settings.webhook_encryption_key)))


async def queue_mail(session, settings, action, token):
    key = uuid4()
    # Hash-router URL keeps the secret out of web server requests and referrers.
    link = settings.public_app_url.rstrip("/") + "/#/account-link?purpose=" + action.purpose
    link += "&token=" + token
    payload = json.dumps(
        {"id": str(key), "email": action.email, "purpose": action.purpose, "link": link}
    )
    session.add(
        MailDelivery(
            id=key,
            action_hash=action.token_hash,
            ciphertext=cipher(settings).encrypt(payload.encode()).decode(),
        )
    )


class MailError(Exception):
    def __init__(self, code, permanent=False):
        self.code, self.permanent = code, permanent
        super().__init__(code)


def oauth_failure_code(response):
    # Never log descriptions, response bodies or arbitrary provider-supplied values.
    known = {
        "invalid_grant",
        "invalid_client",
        "deleted_client",
        "unauthorized_client",
        "access_denied",
        "invalid_scope",
        "admin_policy_enforced",
    }
    try:
        body = response.json()
        reason = body.get("error") if isinstance(body, dict) else None
    except ValueError:
        reason = None
    if isinstance(reason, str) and reason in known:
        return "GMAIL_AUTH_" + reason.upper()
    return "GMAIL_AUTH_FAILED"


async def gmail_send(settings, payload, transport=None):
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = payload["email"]
    verify = payload["purpose"] == "verify"
    message["Subject"] = "API Sentinel — " + (
        "confirm your email" if verify else "reset your password"
    )
    message.set_content(
        ("Confirm your email address" if verify else "Set a new password")
        + " for API Sentinel:\n\n"
        + payload["link"]
        + "\n\nThis single-use link expires in "
        + ("60" if verify else "15")
        + " minutes.\n"
        + "If you did not request this message, ignore it. Never share this link.\n"
    )
    async with httpx.AsyncClient(
        timeout=15, trust_env=False, follow_redirects=False, transport=transport
    ) as client:
        try:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.gmail_client_id,
                    "client_secret": settings.gmail_client_secret,
                    "refresh_token": settings.gmail_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if response.status_code != 200:
                raise MailError(
                    oauth_failure_code(response), response.status_code in (400, 401, 403)
                )
            access = response.json().get("access_token")
            if not isinstance(access, str) or not access:
                raise MailError("GMAIL_AUTH_FAILED", True)
            response = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": "Bearer " + access},
                json={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()},
            )
            if response.status_code not in (200, 202):
                raise MailError("GMAIL_SEND_FAILED", response.status_code in (400, 401, 403, 404))
        except (httpx.HTTPError, ValueError):
            raise MailError("GMAIL_NETWORK_ERROR") from None


async def send_mail_pending(db, settings, transport=None):
    if not settings.mail_enabled:
        return
    async with db.sessions.begin() as session:
        await session.execute(delete(EmailAction).where(EmailAction.expires_at <= now()))
        ids = list(
            (
                await session.scalars(
                    select(MailDelivery.id)
                    .where(MailDelivery.state == "PENDING", MailDelivery.next_attempt_at <= now())
                    .limit(5)
                )
            ).all()
        )
    for key in ids:
        async with db.sessions() as session:
            row = await session.get(MailDelivery, key)
            if row is None:
                continue
            encoded = row.ciphertext
        error = None
        try:
            payload = json.loads(cipher(settings).decrypt(encoded.encode()).decode())
            if (
                payload["id"] != str(key)
                or payload["purpose"] not in ("verify", "reset")
                or normalize_email(payload["email"]) != payload["email"]
                or not payload["link"].startswith(
                    settings.public_app_url.rstrip("/") + "/#/account-link?purpose="
                )
            ):
                raise ValueError
        except Exception:
            error = MailError("MAIL_DECRYPT_FAILED", True)
        if error is None:
            try:
                await gmail_send(settings, payload, transport)
            except MailError as exc:
                error = exc
        async with db.sessions.begin() as session:
            row = await session.get(MailDelivery, key)
            if row is None:
                continue
            row.attempts += 1
            row.last_error = error.code if error else None
            if error is None:
                row.state, row.ciphertext = "SENT", None
            elif error.permanent or row.attempts >= 5:
                row.state, row.ciphertext = "FAILED", None
            else:
                row.next_attempt_at = now() + timedelta(seconds=min(600, 30 * 2**row.attempts))
            if error:
                logger.warning("mail_delivery_failed code=%s", error.code)
