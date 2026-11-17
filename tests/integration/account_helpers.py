"""Fixtures for isolated PostgreSQL integration tests; no authentication bypass."""

import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from api_sentinel.auth import digest
from api_sentinel.auth_models import AuthSession, EmailAction, Invitation, User
from api_sentinel.models import (
    Alert,
    Execution,
    Incident,
    Monitor,
    MonitorEvent,
    NotificationChannel,
    StatusPage,
    now,
)
from api_sentinel.passwords import Passwords


async def create_identity(db):
    key, token = uuid4(), secrets.token_urlsafe(32)
    async with db.sessions.begin() as session:
        session.add(
            User(
                id=key,
                username="test-" + key.hex,
                password_hash=Passwords().hash("test only passphrase 1234"),
                is_admin=False,
            )
        )
        await session.flush()
        session.add(
            AuthSession(
                token_hash=digest(token), user_id=key, expires_at=now() + timedelta(hours=1)
            )
        )
    return key, token


async def remove_identity(db, key):
    async with db.sessions.begin() as session:
        monitors = select(Monitor.id).where(Monitor.owner_id == key)
        channels = list(
            (
                await session.scalars(
                    select(NotificationChannel.id).where(NotificationChannel.owner_id == key)
                )
            ).all()
        )
        await session.execute(
            delete(Alert).where(
                Alert.incident_id.in_(select(Incident.id).where(Incident.monitor_id.in_(monitors)))
                | Alert.channel.in_([f"discord:{c}" for c in channels])
            )
        )
        for model in (MonitorEvent, Execution, Incident):
            await session.execute(delete(model).where(model.monitor_id.in_(monitors)))
        for model in (Monitor, NotificationChannel, StatusPage):
            await session.execute(delete(model).where(model.owner_id == key))
        await session.execute(delete(EmailAction).where(EmailAction.user_id == key))
        await session.execute(delete(AuthSession).where(AuthSession.user_id == key))
        await session.execute(delete(Invitation).where(Invitation.created_by == key))
        await session.execute(delete(User).where(User.id == key))
