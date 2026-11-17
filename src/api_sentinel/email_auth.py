"""Verified recovery addresses and atomic, purpose-bound one-time actions."""

import asyncio
import secrets
import time
from datetime import timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import delete, func, select

from api_sentinel.auth_models import AuthSession, EmailAction, MailDelivery, User
from api_sentinel.mail_config import normalize_email
from api_sentinel.mailer import queue_mail
from api_sentinel.models import now

GENERIC = {"message": "If the details match an eligible account, an email will arrive shortly."}


class EmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return normalize_email(value)


class BindEmail(EmailInput):
    current_password: SecretStr = Field(min_length=1, max_length=128)


class ResendEmail(EmailInput):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")


class ActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: SecretStr = Field(min_length=40, max_length=128)


class ResetInput(ActionInput):
    new_password: SecretStr = Field(min_length=15, max_length=128)


class EmailAccounts:
    def __init__(self, db, settings, budget):
        self.db, self.settings, self.budget = db, settings, budget

    def enabled(self):
        if not self.settings.mail_enabled:
            raise HTTPException(503, "Email recovery is not configured")

    async def mail_budget(self, email):
        self.enabled()
        await self.budget(email, namespace="mail", minutes=60, total=30, individual=3)

    async def queue(self, session, user, email, purpose):
        from api_sentinel.auth import digest

        await session.execute(
            delete(EmailAction).where(
                EmailAction.user_id == user.id, EmailAction.purpose == purpose
            )
        )
        token = secrets.token_urlsafe(32)
        action = EmailAction(
            token_hash=digest(token),
            user_id=user.id,
            purpose=purpose,
            email=email,
            expires_at=now() + timedelta(minutes=60 if purpose == "verify" else 15),
        )
        session.add(action)
        await session.flush()
        await queue_mail(session, self.settings, action, token)

    async def consume(self, session, token, purpose):
        from api_sentinel.auth import digest

        key = digest(token)
        # All writers lock User before EmailAction, including password changes and resend.
        candidate = await session.get(EmailAction, key)
        if candidate is None:
            raise HTTPException(400, "Invalid or expired link")
        user = await session.scalar(
            select(User).where(User.id == candidate.user_id).with_for_update()
        )
        action = await session.scalar(
            select(EmailAction)
            .where(EmailAction.token_hash == key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            user is None
            or action is None
            or action.purpose != purpose
            or action.expires_at <= now()
            or (purpose == "verify" and action.email != user.pending_email)
            or (purpose == "reset" and action.email != user.email)
        ):
            raise HTTPException(400, "Invalid or expired link")
        return user, action

    def routes(self, router, Auth, hash_password, verify):
        @router.post("/email", status_code=202)
        async def bind_email(data: BindEmail, user=Auth):
            await self.budget(user.username)
            await self.mail_budget(data.email)
            async with self.db.sessions.begin() as session:
                current = await session.scalar(
                    select(User).where(User.id == user.id).with_for_update()
                )
                if not await verify(
                    current.password_hash, data.current_password.get_secret_value()
                ):
                    raise HTTPException(400, "Invalid current password")
                current.pending_email = data.email
                await self.queue(session, current, data.email, "verify")
            return GENERIC

        @router.post("/email/resend", status_code=202)
        async def resend(data: ResendEmail):
            await self.mail_budget(data.email)
            started = time.monotonic()
            async with self.db.sessions.begin() as session:
                user = await session.scalar(
                    select(User)
                    .where(User.username == data.username.lower(), User.pending_email == data.email)
                    .with_for_update()
                )
                if user:
                    await self.queue(session, user, data.email, "verify")
            await asyncio.sleep(max(0, 0.5 - (time.monotonic() - started)))
            return GENERIC

        @router.post("/email/verify")
        async def confirm(data: ActionInput):
            self.enabled()
            await self.budget("email-confirm")
            async with self.db.sessions.begin() as session:
                user, action = await self.consume(session, data.token.get_secret_value(), "verify")
                # Serialize address claims so duplicates produce a safe generic error.
                from sqlalchemy import text

                await session.execute(text("SELECT pg_advisory_xact_lock(71424007)"))
                if await session.scalar(
                    select(User.id).where(User.email == action.email, User.id != user.id)
                ):
                    raise HTTPException(400, "This address cannot be assigned; contact the owner")
                user.email, user.pending_email = action.email, None
                user.requires_verification = False
                await session.execute(delete(EmailAction).where(EmailAction.user_id == user.id))
                await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
            return {"message": "Email confirmed. Sign in again."}

        @router.post("/password-reset/request", status_code=202)
        async def request_reset(data: EmailInput):
            await self.mail_budget(data.email)
            started = time.monotonic()
            async with self.db.sessions.begin() as session:
                user = await session.scalar(
                    select(User)
                    .where(User.email == data.email, User.requires_verification.is_(False))
                    .with_for_update()
                )
                if user:
                    await self.queue(session, user, data.email, "reset")
            # Sending is asynchronous; pad the small lookup/write difference as well.
            await asyncio.sleep(max(0, 0.5 - (time.monotonic() - started)))
            return GENERIC

        @router.post("/password-reset/confirm")
        async def reset(data: ResetInput):
            self.enabled()
            await self.budget("reset-confirm")
            encoded = await hash_password(data.new_password.get_secret_value())
            async with self.db.sessions.begin() as session:
                user, _ = await self.consume(session, data.token.get_secret_value(), "reset")
                user.password_hash, user.pending_email = encoded, None
                await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                await session.execute(delete(EmailAction).where(EmailAction.user_id == user.id))
            return {"message": "Password updated. Sign in with your new password."}

        @router.get("/email/status")
        async def mail_status(user=Auth):
            if not user.is_admin:
                raise HTTPException(403, "Administrator access required")
            async with self.db.sessions() as session:
                counts = dict(
                    (
                        await session.execute(
                            select(MailDelivery.state, func.count()).group_by(MailDelivery.state)
                        )
                    ).all()
                )
                return {"enabled": self.settings.mail_enabled, "deliveries": counts}
