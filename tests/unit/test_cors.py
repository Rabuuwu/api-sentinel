import pytest
from fastapi.testclient import TestClient

from api_sentinel.app import create_app
from api_sentinel.config import Settings

ORIGIN = "https://rabuuwu.github.io"


def client(origins=()):
    return TestClient(
        create_app(
            Settings(
                "postgresql+asyncpg://localhost/sentinel_test",
                "x" * 40,
                allowed_hosts=("testserver",),
                cors_origins=origins,
            )
        )
    )


def test_allowed_pages_preflight_and_unauthorized_response():
    with client((ORIGIN,)) as http:
        response = http.options(
            "/api/v1/monitors",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert "access-control-allow-credentials" not in response.headers
        response = http.get("/api/v1/monitors", headers={"Origin": ORIGIN})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == ORIGIN


def test_other_origins_and_default_local_mode_are_not_allowed():
    for origins, origin in [((), ORIGIN), ((ORIGIN,), "https://untrusted.example")]:
        with client(origins) as http:
            response = http.options(
                "/api/v1/monitors",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.github.io",
        "http://example.com",
        "https://rabuuwu.github.io/api-sentinel/",
        "https://user:password@example.com",
        "null",
    ],
)
def test_origin_configuration_rejects_unsafe_or_misleading_values(origin):
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings("postgresql+asyncpg://localhost/test", "x" * 40, cors_origins=(origin,))
