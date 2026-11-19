"""Password authentication. No API-key bypass; bearer tokens remain browser-memory only."""

import asyncio
import hashlib
import hmac
import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import delete, func, select, text, update

from api_sentinel.auth_models import AuthBudget, AuthSession, EmailAction, Invitation, User
from api_sentinel.email_auth import EmailAccounts
from api_sentinel.mail_config import normalize_email
from api_sentinel.models import Monitor, NotificationChannel, StatusPage, now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def owner(session):
    # Fail closed if a protected query accidentally uses the public dependency.
    return session.info["user_id"]


def owned_monitors(session):
    return select(Monitor.id).where(Monitor.owner_id == owner(session))


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: SecretStr = Field(min_length=15, max_length=128)

    @field_validator("username")
    @classmethod
    def canonical(cls, value):
        return value.lower()


class EmailCredentials(Credentials):
    email: str | None = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return normalize_email(value) if value is not None else None


class Registration(EmailCredentials):
    invitation: SecretStr = Field(min_length=32, max_length=128)


class Bootstrap(EmailCredentials):
    setup_key: SecretStr = Field(min_length=32, max_length=256)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=15, max_length=128)


def public_user(user):
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


def install_auth(app, db, settings):
    from api_sentinel.passwords import Passwords

    hasher = Passwords()
    dummy_hash = hasher.hash(secrets.token_urlsafe(32))
    hashing = asyncio.Semaphore(2)

    async def hash_password(password):
        async with hashing:
            return await asyncio.to_thread(hasher.hash, password)

    async def verify(encoded, password):
        async with hashing:
            return await asyncio.to_thread(hasher.verify, encoded, password)

    async def budget(label, namespace="auth", minutes=5, total=60, individual=8):
        # Committed separately, including failed attempts. Global limit bounds table growth
        # and hashing CPU; per-login limit survives restarts and ignores spoofed proxy IPs.
        denied = False
        async with db.sessions.begin() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(71424003)"))
            await session.execute(delete(AuthBudget).where(AuthBudget.expires_at <= now()))
            for key, limit in (
                (namespace + ":global", total),
                (namespace + ":subject:" + label, individual),
            ):
                hashed = digest(key)
                row = await session.get(AuthBudget, hashed)
                if row is None:
                    row = AuthBudget(
                        key=hashed, count=0, expires_at=now() + timedelta(minutes=minutes)
                    )
                    session.add(row)
                row.count += 1
                if row.count > limit:
                    denied = True
                    break
        if denied:
            raise HTTPException(429, "Too many attempts; please try again later")

    async def authenticate(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer ") or not 40 <= len(authorization[7:]) <= 128:
            raise HTTPException(401, "Sign in to your account")
        token_hash = digest(authorization[7:])
        async with db.sessions.begin() as session:
            record = await session.get(AuthSession, token_hash)
            if (
                record is None
                or record.expires_at <= now()
                or record.last_seen <= now() - timedelta(minutes=30)
            ):
                raise HTTPException(401, "Session expired; sign in again")
            user = await session.get(User, record.user_id)
            if user is None or user.requires_verification:
                raise HTTPException(401, "Sign in to your account")
            record.last_seen = now()
            return user

    emails = EmailAccounts(db, settings, budget)
    app.state.authenticate = authenticate
    Auth = Depends(authenticate)
    router = APIRouter(prefix="/api/v1/auth", tags=["Accounts"])

    async def issue(session, user):
        await session.execute(
            delete(AuthSession).where(
                (AuthSession.expires_at <= now())
                | (AuthSession.last_seen <= now() - timedelta(minutes=30))
            )
        )
        # Bound active sessions to five per user, including concurrent logins (user row locked).
        records = list(
            (
                await session.scalars(
                    select(AuthSession)
                    .where(AuthSession.user_id == user.id)
                    .order_by(AuthSession.expires_at.desc())
                )
            ).all()
        )
        for record in records[4:]:
            await session.delete(record)
        token = secrets.token_urlsafe(32)
        expires = now() + timedelta(hours=8)
        session.add(AuthSession(token_hash=digest(token), user_id=user.id, expires_at=expires))
        return {"token": token, "expires_at": expires, "user": public_user(user)}

    @router.get("/setup")
    async def setup_status():
        async with db.sessions() as session:
            return {
                "setup_required": not bool(await session.scalar(select(User.id).limit(1))),
                "mail_enabled": settings.mail_enabled,
            }

    @router.post("/bootstrap", status_code=201)
    async def bootstrap(data: Bootstrap):
        await budget("bootstrap", namespace="bootstrap")
        if not hmac.compare_digest(
            data.setup_key.get_secret_value().encode(), settings.api_key.encode()
        ):
            raise HTTPException(401, "Invalid setup credentials")
        if settings.mail_enabled:
            if not data.email:
                raise HTTPException(422, "Email address is required")
            await emails.mail_budget(data.email)
        encoded = await hash_password(data.password.get_secret_value())
        async with db.sessions.begin() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(71424004)"))
            if await session.scalar(select(User.id).limit(1)):
                raise HTTPException(409, "Initial account already exists")
            user = User(username=data.username, password_hash=encoded, is_admin=True)
            session.add(user)
            await session.flush()
            for model in (Monitor, NotificationChannel, StatusPage):
                await session.execute(
                    update(model).where(model.owner_id.is_(None)).values(owner_id=user.id)
                )
            if settings.mail_enabled:
                user.pending_email, user.requires_verification = data.email, True
                await emails.queue(session, user, data.email, "verify")
                return {
                    "verification_required": True,
                    "message": "Check your email to activate your account.",
                }
            return await issue(session, user)

    @router.post("/register", status_code=201)
    async def register(data: Registration):
        await budget(data.username, namespace="registration")
        if settings.mail_enabled:
            if not data.email:
                raise HTTPException(422, "Email address is required")
            await emails.mail_budget(data.email)
        encoded = await hash_password(data.password.get_secret_value())
        async with db.sessions.begin() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(71424004)"))
            if (await session.scalar(select(func.count()).select_from(User))) >= 100:
                raise HTTPException(409, "Account limit reached")
            invite = await session.scalar(
                select(Invitation)
                .where(Invitation.token_hash == digest(data.invitation.get_secret_value()))
                .with_for_update()
            )
            if invite is None or invite.expires_at <= now():
                raise HTTPException(400, "Invalid or expired invitation")
            if await session.scalar(select(User.id).where(User.username == data.username)):
                raise HTTPException(409, "Unable to create account with these details")
            user = User(username=data.username, password_hash=encoded, is_admin=False)
            session.add(user)
            await session.flush()
            await session.delete(invite)
            if settings.mail_enabled:
                user.pending_email, user.requires_verification = data.email, True
                await emails.queue(session, user, data.email, "verify")
                return {
                    "verification_required": True,
                    "message": "Check your email to activate your account.",
                }
            return await issue(session, user)

    @router.post("/login")
    async def login(data: Credentials):
        await budget(data.username)
        async with db.sessions.begin() as session:
            user = await session.scalar(
                select(User).where(User.username == data.username).with_for_update()
            )
            valid = await verify(
                user.password_hash if user else dummy_hash, data.password.get_secret_value()
            )
            if user is None or not valid:
                raise HTTPException(401, "Invalid username or password")
            if user.requires_verification:
                raise HTTPException(403, "Confirm your email before signing in")
            if hasher.check_needs_rehash(user.password_hash):
                user.password_hash = await hash_password(data.password.get_secret_value())
            return await issue(session, user)

    @router.get("/me")
    async def me(user=Auth):
        return {
            **public_user(user),
            "email": user.email,
            "pending_email": user.pending_email,
            "mail_enabled": settings.mail_enabled,
        }

    @router.post("/logout", status_code=204)
    async def logout(user=Auth, authorization: str = Header()):
        async with db.sessions.begin() as session:
            await session.execute(
                delete(AuthSession).where(
                    AuthSession.token_hash == digest(authorization[7:]),
                    AuthSession.user_id == user.id,
                )
            )

    @router.post("/logout-all", status_code=204)
    async def logout_all(user=Auth):
        async with db.sessions.begin() as session:
            await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))

    @router.post("/password", status_code=204)
    async def change_password(data: PasswordChange, user=Auth):
        await budget(user.username, namespace="account-settings")
        async with db.sessions.begin() as session:
            current = await session.scalar(select(User).where(User.id == user.id).with_for_update())
            if not await verify(current.password_hash, data.current_password.get_secret_value()):
                raise HTTPException(400, "Invalid current password")
            current.password_hash = await hash_password(data.new_password.get_secret_value())
            current.pending_email = None
            await session.execute(delete(EmailAction).where(EmailAction.user_id == user.id))
            await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))

    @router.post("/invitations", status_code=201)
    async def invite(user=Auth):
        if not user.is_admin:
            raise HTTPException(403, "Administrator access required")
        await budget(user.username, namespace="account-settings")
        async with db.sessions.begin() as session:
            await session.execute(delete(Invitation).where(Invitation.expires_at <= now()))
            if (await session.scalar(select(func.count()).select_from(Invitation))) >= 20:
                raise HTTPException(409, "Invitation limit reached")
            token = secrets.token_urlsafe(32)
            expires = now() + timedelta(hours=24)
            session.add(
                Invitation(token_hash=digest(token), created_by=user.id, expires_at=expires)
            )
            return {"invitation": token, "expires_at": expires}

    @router.get("/users")
    async def users(user=Auth):
        if not user.is_admin:
            raise HTTPException(403, "Administrator access required")
        async with db.sessions() as session:
            return [
                public_user(u)
                for u in (
                    await session.scalars(select(User).order_by(User.created_at).limit(100))
                ).all()
            ]

    @router.delete("/users/{user_id}/sessions", status_code=204)
    async def revoke_user(user_id: UUID, user=Auth):
        if not user.is_admin:
            raise HTTPException(403, "Administrator access required")
        async with db.sessions.begin() as session:
            await session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))

    emails.routes(router, Auth, hash_password, verify)
    app.include_router(router)
    return authenticate
