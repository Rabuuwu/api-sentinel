import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from api_sentinel.alerts import send_pending
from api_sentinel.config import Settings
from api_sentinel.models import Alert, now


class Session:
    def __init__(self, alert):
        self.alert = alert

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def scalars(self, query):
        return SimpleNamespace(all=lambda: [self.alert.id])

    async def get(self, model, key):
        return self.alert


class Sessions:
    def __init__(self, alert):
        self.session = Session(alert)

    def __call__(self):
        return self.session

    def begin(self):
        return self.session


@pytest.mark.parametrize(
    ("status", "state"), [(204, "SENT"), (503, "PENDING"), (429, "PENDING"), (404, "FAILED")]
)
def test_discord_delivery_and_retry_after(status, state):
    before = now()
    alert = Alert(
        id=uuid4(),
        incident_id=None,
        channel="discord",
        event_type="TEST",
        attempts=0,
        delivery_state="PENDING",
        next_attempt_at=before,
    )
    db = SimpleNamespace(sessions=Sessions(alert))
    config = Settings(
        "postgresql+asyncpg://localhost/sentinel_test",
        "test-key-" + "x" * 40,
        discord_webhook_url="https://discord.com/api/webhooks/123/test-token",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, headers={"Retry-After": "90"})
    )
    asyncio.run(send_pending(db, config, transport))
    assert alert.delivery_state == state
    assert alert.attempts == 1
    if status == 429:
        assert alert.next_attempt_at >= before + timedelta(seconds=90)
    if status == 503:
        assert alert.next_attempt_at > before
    assert "test-token" not in (alert.last_error_sanitized or "")


def test_delivery_timeout_is_sanitized_and_retryable():
    alert = Alert(
        id=uuid4(),
        incident_id=None,
        channel="discord",
        event_type="TEST",
        attempts=0,
        delivery_state="PENDING",
        next_attempt_at=now(),
    )

    def timeout(request):
        raise httpx.ReadTimeout("sensitive webhook token")

    db = SimpleNamespace(sessions=Sessions(alert))
    config = Settings(
        "postgresql+asyncpg://localhost/sentinel_test",
        "test-key-" + "x" * 40,
        discord_webhook_url="https://discord.com/api/webhooks/123/test-token",
    )
    asyncio.run(send_pending(db, config, httpx.MockTransport(timeout)))
    assert alert.delivery_state == "PENDING"
    assert alert.last_error_sanitized == "DELIVERY_NETWORK_ERROR"
