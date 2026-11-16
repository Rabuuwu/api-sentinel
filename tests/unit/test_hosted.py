import asyncio
import ssl
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api_sentinel.config import Settings
from api_sentinel.database_url import connection_options
from api_sentinel.hosted import supervise


def test_neon_url_uses_asyncpg_and_verified_tls():
    url, options = connection_options(
        "postgresql://user:encoded%40password@ep-example.eu-central-1.aws.neon.tech/sentinel?sslmode=require",
        True,
    )
    assert url.startswith("postgresql+asyncpg://user:encoded%40password@")
    assert "sslmode" not in url
    assert options["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert options["ssl"].check_hostname


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@ep-example-pooler.aws.neon.tech/db?sslmode=require",
        "postgresql://user:pass@host/db?sslmode=disable",
        "postgresql://user:pass@host/db?ssl=false",
        "postgresql://user:pass@host/db?channel_binding=invalid",
    ],
)
def test_hosted_rejects_unsafe_or_incompatible_db_options(url):
    with pytest.raises(ValueError):
        connection_options(url, True)


def test_local_database_still_needs_no_tls_option():
    url = "postgresql+asyncpg://localhost/sentinel_test"
    assert connection_options(url) == (url, {})


def test_hosted_requires_durable_secret_key():
    with pytest.raises(ValueError, match="WEBHOOK_ENCRYPTION_KEY"):
        Settings("postgresql://localhost/test", "a" * 40, hosted=True)
    settings = Settings(
        "postgresql://localhost/test", "a" * 40, hosted=True, webhook_encryption_key="b" * 64
    )
    assert "b" * 64 not in repr(settings)


class Child:
    def __init__(self):
        self.returncode = None
        self.done = asyncio.Event()
        self.terminated = False

    async def wait(self):
        await self.done.wait()
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15
        self.done.set()


@pytest.mark.parametrize("shutdown", [False, True])
def test_supervisor_stops_both_children_on_failure_or_shutdown(shutdown):
    async def scenario():
        stop = asyncio.Event()
        children = []

        async def spawn(*command):
            child = Child()
            children.append(child)
            if len(children) == 2:
                if shutdown:
                    stop.set()
                else:
                    child.returncode = 0  # Even unexpected exit(0) must fail the service.
                    child.done.set()
            return child

        code = await supervise([["api"], ["worker"]], stop, spawn)
        assert code == (0 if shutdown else 1)
        assert children[0].terminated
        assert all(p.returncode is not None for p in children)

    asyncio.run(scenario())


def test_supervisor_cleans_up_api_when_worker_cannot_start():
    async def scenario():
        api = Child()
        count = 0

        async def spawn(*command):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("start failed")
            return api

        with pytest.raises(OSError):
            await supervise([["api"], ["worker"]], asyncio.Event(), spawn)
        assert api.terminated

    asyncio.run(scenario())


def test_encrypted_secret_roundtrip_tampering_and_channel_binding():
    pytest.importorskip("cryptography", reason="Hosted encryption dependency is not installed")
    from api_sentinel.dashboard_schemas import ChannelOut
    from api_sentinel.models import now
    from api_sentinel.vault import EncryptedVault

    key, channel = "ab" * 32, uuid4()
    secret = "https://discord.com/api/webhooks/123/test-secret"
    value = EncryptedVault(key).encrypt(channel, secret)
    assert secret not in value
    assert EncryptedVault(key).decrypt(channel, value) == secret
    for vault, identifier, ciphertext in [
        (EncryptedVault("cd" * 32), channel, value),
        (EncryptedVault(key), uuid4(), value),
        (EncryptedVault(key), channel, value[:-4] + "xxxx"),
    ]:
        with pytest.raises(ValueError, match="cannot be decrypted"):
            vault.decrypt(identifier, ciphertext)
    output = ChannelOut.model_validate(
        SimpleNamespace(
            id=channel,
            name="Test",
            provider="discord",
            enabled=True,
            on_down=True,
            on_recovered=True,
            created_at=now(),
            webhook_ciphertext=value,
        )
    ).model_dump_json()
    assert value not in output
    assert "ciphertext" not in output


def test_neon_channel_binding_is_preserved():
    from urllib.parse import parse_qs, urlsplit

    url, _ = connection_options(
        "postgresql://user:p%40ss@ep-example.neon.tech/db?sslmode=require&channel_binding=require"
    )
    parsed = urlsplit(url)
    assert parsed.scheme == "postgresql+psycopg"
    assert parsed.password == "p%40ss"
    assert parse_qs(parsed.query) == {
        "sslmode": ["verify-full"], "sslrootcert": ["system"], "channel_binding": ["require"]
    }


def test_neon_pooler_rejected_even_outside_render():
    with pytest.raises(ValueError, match="direct Neon"):
        connection_options("postgresql://user:pass@ep-example-pooler.neon.tech/db")
