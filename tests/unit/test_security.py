import asyncio
import socket

import pytest
from pydantic import ValidationError

from api_sentinel.schemas import MonitorInput
from api_sentinel.security import UnsafeTarget, public_ip, resolve_public


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://10.0.0.1",
        "http://169.254.169.254",
        "http://[::1]",
        "http://[fc00::1]",
        "http://[::ffff:8.8.8.8]",
        "ftp://example.com",
        "https://user:password@example.com",
        "https://example.com:22",
        "https://example.com?a=secret",
        "https://example.com/#fragment",
        "http://224.0.0.1",
        "http://0.0.0.0",
        "http://100.64.0.1",
        "https://example.com\r\nHost: localhost",
        "http://[64:ff9b::7f00:1]",
        "https://bad_host.example",
        "https://-bad.example",
        "https://example..com",
        "http://%31%32%37.0.0.1",
        'https://bad"host.example',
    ],
)
def test_rejects_unsafe_targets(url):
    with pytest.raises(ValidationError):
        MonitorInput(name="test", url=url)


@pytest.mark.parametrize(
    "fields",
    [
        {"interval_seconds": 59},
        {"timeout_seconds": 31},
        {"failure_threshold": 0},
        {"expected_status_min": 500, "expected_status_max": 200},
        {"method": "POST"},
        {"mode": "sleep_aware"},
        {"name": " "},
        {"extra": "field"},
    ],
)
def test_configuration_limits(fields):
    with pytest.raises(ValidationError):
        MonitorInput.model_validate({"name": "test", "url": "https://example.com", **fields})


def test_public_address_policy():
    assert public_ip("8.8.8.8")
    assert public_ip("2606:4700:4700::1111")
    assert not public_ip("192.168.1.1")


def test_mixed_dns_answers_block_entire_target(monkeypatch):
    async def run():
        async def answers(*args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
                for ip in ["8.8.8.8", "127.0.0.1"]
            ]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", answers)
        with pytest.raises(UnsafeTarget):
            await resolve_public("example.com", 443)

    asyncio.run(run())
