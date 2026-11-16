import pytest

from api_sentinel.config import Settings


def test_secrets_are_not_in_repr():
    settings = Settings("postgresql+asyncpg://secret", "a" * 40)
    assert "secret" not in repr(settings)
    assert "a" * 40 not in repr(settings)


@pytest.mark.parametrize("key", ["", "short", "replace-with-at-least-32-random-characters"])
def test_unsafe_keys_rejected(key):
    with pytest.raises(ValueError):
        Settings("postgresql+asyncpg://localhost/test", key)


def test_non_discord_webhook_rejected():
    with pytest.raises(ValueError):
        Settings(
            "postgresql+asyncpg://localhost/test",
            "a" * 40,
            discord_webhook_url="http://127.0.0.1/secret",
        )
