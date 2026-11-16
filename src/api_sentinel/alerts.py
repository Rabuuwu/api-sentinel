import asyncio
import json
import logging
import random
from datetime import timedelta
from uuid import UUID

import httpx
from sqlalchemy import select

from api_sentinel.config import Settings
from api_sentinel.db import Database
from api_sentinel.models import Alert, Incident, MonitorEvent, NotificationChannel, now
from api_sentinel.vault import EncryptedVault, SecretVault

logger = logging.getLogger("sentinel")


async def send_pending(db: Database, settings: Settings, transport=None, stop=None):
    async with db.sessions() as session:
        ids = list(
            (
                await session.scalars(
                    select(Alert.id)
                    .where(Alert.delivery_state == "PENDING", Alert.next_attempt_at <= now())
                    .order_by(Alert.created_at)
                    .limit(10)
                )
            ).all()
        )
    for alert_id in ids:
        if stop is not None and stop.is_set():
            break
        # Singleton worker owns delivery. Do not hold a DB transaction across network I/O.
        async with db.sessions() as session:
            alert = await session.get(Alert, alert_id)
            if alert is None:
                continue
            webhook = settings.discord_webhook_url
            channel_unavailable = False
            if alert.channel.startswith("discord:"):
                channel = await session.get(NotificationChannel, UUID(alert.channel.split(":")[1]))
                if channel is None or channel.deleted_at or not channel.enabled:
                    channel_unavailable = True
                else:
                    try:
                        if channel.webhook_ciphertext:
                            webhook = EncryptedVault(settings.webhook_encryption_key).decrypt(
                                channel.id, channel.webhook_ciphertext
                            )
                        else:
                            webhook = SecretVault(settings.secrets_dir).read(channel.id)
                    except (OSError, ValueError):
                        channel_unavailable = True
            payload = {
                "content": f"API Sentinel: {alert.event_type} | incident {alert.incident_id}",
                "allowed_mentions": {"parse": []},
            }
        success, permanent, error, delay = False, False, None, 0.0
        if channel_unavailable:
            error, permanent = "CHANNEL_UNAVAILABLE", True
        elif alert.channel == "console":
            logger.info(json.dumps({"event": "alert", "id": str(alert.id), **payload}))
            success = True
        elif not webhook:
            error = "WEBHOOK_NOT_CONFIGURED"
        else:
            try:
                async with asyncio.timeout(15):
                    async with httpx.AsyncClient(
                        timeout=10, trust_env=False, transport=transport
                    ) as client:
                        async with client.stream("POST", webhook, json=payload) as response:
                            success = 200 <= response.status_code < 300
                            permanent = (
                                400 <= response.status_code < 500 and response.status_code != 429
                            )
                            error = None if success else f"HTTP_{response.status_code}"
                            if response.status_code == 429:
                                try:
                                    delay = min(
                                        86400,
                                        max(0, float(response.headers.get("Retry-After", "0"))),
                                    )
                                except ValueError:
                                    pass
            except (httpx.HTTPError, TimeoutError):
                error = "DELIVERY_NETWORK_ERROR"
        async with db.sessions.begin() as session:
            current = await session.get(Alert, alert_id)
            if current is None:
                continue
            current.attempts += 1
            current.last_error_sanitized = error
            if success:
                current.delivery_state = "SENT"
                current.sent_at = now()
                if current.incident_id:
                    incident = await session.get(Incident, current.incident_id)
                    if incident:
                        session.add(
                            MonitorEvent(
                                monitor_id=incident.monitor_id,
                                action="NOTIFICATION_SENT",
                                information={
                                    "provider": current.channel.split(":")[0],
                                    "retry": current.attempts - 1,
                                    "event": current.event_type,
                                },
                            )
                        )
            elif permanent or current.attempts >= 10:
                current.delivery_state = "FAILED"
            else:
                current.next_attempt_at = now() + timedelta(
                    seconds=max(delay, min(3600, 2**current.attempts * 5) + random.uniform(0, 5))
                )
