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


def test_neon_unpooled_variable_wins(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@ep-x-pooler.neon.tech/db")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://user:pass@ep-x.neon.tech/db")
    monkeypatch.setenv("SENTINEL_API_KEY", "a" * 40)
    assert Settings.from_env().database_url == "postgresql://user:pass@ep-x.neon.tech/db"


def test_explicit_test_database_overrides_dotenv_neon(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/sentinel_test")
    monkeypatch.setenv("SENTINEL_API_KEY", "a" * 40)
    (tmp_path / ".env").write_text("DATABASE_URL_UNPOOLED=postgresql://host/production\n")
    assert Settings.from_env().database_url == "postgresql://localhost/sentinel_test"
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)


def test_dotenv_reads_do_not_poison_subsequent_test_settings(monkeypatch, tmp_path):
    import os
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL_UNPOOLED", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/sentinel_test")
    monkeypatch.setenv("SENTINEL_API_KEY", "x" * 40)
    (tmp_path / ".env").write_text("DATABASE_URL_UNPOOLED=postgresql://host/production\n")
    for _ in range(2):
        assert Settings.from_env().database_url == "postgresql://localhost/sentinel_test"
    assert "DATABASE_URL_UNPOOLED" not in os.environ
