import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from api_sentinel.app import create_app
from api_sentinel.config import Settings
from api_sentinel.dashboard_schemas import ChannelInput, ChannelOut, PublicPage, StatusPageInput
from api_sentinel.domain import Transition, transition
from api_sentinel.metrics import percentile, rate
from api_sentinel.vault import SecretVault, validate_webhook


@pytest.mark.parametrize(
    ("values", "p", "expected"),
    [
        ([], 50, None),
        ([100], 99, 100),
        ([100, 200], 50, 150),
        ([100, 200, 300, 400], 75, 325),
        ([100, 200, 300, 400], 90, 370),
        ([100, 200, 300, 400], 95, 385),
        ([100, 200, 300, 400], 99, 397),
    ],
)
def test_percentile_interpolation(values, p, expected):
    assert percentile(values, p) == expected


def test_no_data_is_not_perfect_uptime():
    assert rate(0, 0) is None
    assert rate(2, 5) == 40


def test_degraded_needs_consecutive_slow_checks_and_healthy_recovery():
    state = Transition("UP", 0, 0)
    for index in range(3):
        state = transition(
            state.status, state.failures, state.successes, True, 3, 2, True, state.degraded, 3
        )
        assert state.status == ("DEGRADED" if index == 2 else "UP")
    assert state.event == "MONITOR_DEGRADED"
    first = transition(state.status, state.failures, state.successes, True, 3, 2)
    assert first.status == "DEGRADED"
    second = transition(first.status, first.failures, first.successes, True, 3, 2)
    assert second.status == "UP"
    assert second.event == "MONITOR_RECOVERED"


def test_slow_success_does_not_recover_down_monitor_or_open_another_incident():
    state = transition("DOWN", 5, 1, True, 3, 2, True, 2, 3)
    assert state.status == "DOWN"
    assert state.successes == 0
    assert state.event is None
    state = transition("DEGRADED", 2, 0, False, 3, 2, False, 3, 3)
    assert state.status == "DOWN"
    assert state.event == "INCIDENT_OPENED"


def test_vault_and_channel_dto_do_not_expose_webhook(tmp_path):
    key = uuid4()
    secret = "https://discord.com/api/webhooks/12345/test-secret"
    vault = SecretVault(str(tmp_path / "vault"))
    vault.write(key, secret)
    assert vault.read(key) == secret
    assert (tmp_path / "vault" / str(key)).stat().st_mode & 0o777 == 0o600
    data = ChannelInput(name="Alerts", webhook_url=secret)
    assert "test-secret" not in repr(data)
    output = ChannelOut.model_validate(
        {
            "id": key,
            "name": "Alerts",
            "provider": "discord",
            "enabled": True,
            "on_down": True,
            "on_recovered": True,
            "created_at": datetime.now(UTC),
            "webhook_url": secret,
        }
    )
    assert secret not in output.model_dump_json()
    assert "webhook_url" not in output.model_dump()


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/1/a",
        "https://discord.com.evil.test/api/webhooks/1/a",
        "https://127.0.0.1/api/webhooks/1/a",
        "https://discord.com/api/webhooks/1/a?token=private",
        "https://discord.com/api/webhooks/../a",
    ],
)
def test_webhook_destination_is_restricted(url):
    with pytest.raises(ValueError):
        validate_webhook(url)


def test_public_page_contract_strips_private_fields():
    public = PublicPage.model_validate(
        {
            "name": "Services",
            "description": "",
            "updated_at": None,
            "monitors": [
                {
                    "name": "App",
                    "status": "UP",
                    "uptime": None,
                    "last_checked_at": None,
                    "url": "https://private.example/token",
                    "incidents": [],
                }
            ],
            "token": "secret",
        }
    )
    payload = public.model_dump_json()
    assert "private.example" not in payload and "token" not in payload


def test_status_page_slug_and_selection_validation():
    with pytest.raises(ValidationError):
        StatusPageInput(name="test", slug="../private", monitor_ids=[uuid4()])
    with pytest.raises(ValidationError):
        StatusPageInput(name="test", slug="services", monitor_ids=[])


@pytest.fixture
def app(tmp_path):
    return create_app(
        Settings(
            "postgresql+asyncpg://test:test@127.0.0.1:54328/sentinel_test",
            "unit-test-key-" + "x" * 40,
            secrets_dir=str(tmp_path),
        )
    )


@pytest.mark.parametrize(
    "path",
    [
        "/overview",
        "/incidents",
        "/notifications",
        "/status-pages",
        "/monitors/" + str(uuid4()) + "/metrics",
    ],
)
def test_new_admin_endpoints_require_key(app, path):
    with TestClient(app, base_url="http://localhost") as client:
        assert client.get("/api/v1" + path).status_code == 401


def test_openapi_exposes_new_contracts_without_secrets(app):
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get(
            "/api/v1/openapi.json", headers={"X-API-Key": "unit-test-key-" + "x" * 40}
        )
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/v1/monitors/{monitor_id}/metrics" in paths
        assert "/api/v1/public/status-pages/{slug}" in paths
        assert (
            "webhook_url"
            not in response.json()["components"]["schemas"]["ChannelOut"]["properties"]
        )


def test_commit_failure_cannot_return_false_success(app):
    session = Mock()
    session.scalar = AsyncMock(return_value=0)
    session.execute = AsyncMock()
    session.flush = AsyncMock()

    async def broken_transaction():
        yield session
        raise SQLAlchemyError("private database details")

    app.dependency_overrides[app.state.session_dependency] = broken_transaction
    with TestClient(app, base_url="http://localhost") as client:
        response = client.post(
            "/api/v1/monitors",
            headers={"X-API-Key": "unit-test-key-" + "x" * 40},
            json={"name": "Test", "url": "https://example.com"},
        )
        assert response.status_code == 503
        assert "private database details" not in json.dumps(response.json())
