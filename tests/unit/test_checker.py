import asyncio
import socket
import ssl

import httpcore
import httpx
import pytest

from api_sentinel import checker
from api_sentinel.checker import PublicBackend, PublicTransport, check
from api_sentinel.schemas import MonitorInput
from api_sentinel.security import UnsafeTarget


def test_success_records_status_and_latency():
    result = asyncio.run(
        check(
            MonitorInput(name="test", url="https://example.com"),
            httpx.MockTransport(lambda request: httpx.Response(200)),
        )
    )
    assert result.result == "SUCCESS"
    assert result.http_status == 200
    assert result.latency_ms >= 0


def test_redirect_is_not_followed():
    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})

    result = asyncio.run(
        check(MonitorInput(name="test", url="https://example.com"), httpx.MockTransport(response))
    )
    assert result.result == "HTTP_ERROR"
    assert calls == ["https://example.com"]


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (httpx.ReadTimeout("sensitive"), "TIMEOUT"),
        (socket.gaierror("sensitive"), "DNS_ERROR"),
        (ssl.SSLError("sensitive"), "TLS_ERROR"),
        (httpcore.ConnectError("sensitive"), "NETWORK_ERROR"),
        (UnsafeTarget("sensitive"), "BLOCKED_TARGET"),
    ],
)
def test_error_classification_without_sensitive_details(exception, expected):
    def fail(request):
        raise exception

    result = asyncio.run(
        check(MonitorInput(name="test", url="https://example.com"), httpx.MockTransport(fail))
    )
    assert result.result == expected
    assert result.http_status is None
    assert "sensitive" not in repr(result)


def test_transport_uses_original_host_and_streams_headers_only():
    backend = httpcore.AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\nContent-Length: 999999999\r\n\r\n",
        ]
    )
    result = asyncio.run(
        check(MonitorInput(name="test", url="https://example.com"), PublicTransport(backend))
    )
    assert result.result == "SUCCESS"


def test_dns_pinning_connects_only_to_validated_literal(monkeypatch):
    calls = []

    async def resolve(host, port):
        calls.append(("resolve", host, port))
        return "8.8.8.8"

    class Backend:
        async def connect_tcp(self, host, port, *args):
            calls.append(("connect", host, port))
            return object()

    monkeypatch.setattr(checker, "resolve_public", resolve)
    backend = PublicBackend()
    backend.backend = Backend()
    asyncio.run(backend.connect_tcp("example.com", 443))
    assert calls == [("resolve", "example.com", 443), ("connect", "8.8.8.8", 443)]


def test_total_deadline_includes_dns(monkeypatch):
    async def slow(*args):
        await asyncio.sleep(10)

    monkeypatch.setattr(checker, "resolve_public", slow)
    result = asyncio.run(
        check(MonitorInput(name="test", url="https://example.com", timeout_seconds=2))
    )
    assert result.result == "TIMEOUT"


def test_original_tls_sni_and_host_survive_pinning():
    seen = {}

    class Stream(httpcore.AsyncMockStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            seen["sni"] = server_hostname
            return self

        async def write(self, buffer, timeout=None):
            seen.setdefault("wire", bytearray()).extend(buffer)

    class Backend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            return Stream([b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"])

    result = asyncio.run(
        check(MonitorInput(name="test", url="https://example.com"), PublicTransport(Backend()))
    )
    assert result.result == "SUCCESS"
    assert seen["sni"] == "example.com"
    assert b"Host: example.com\r\n" in seen["wire"]


def test_slow_success_uses_the_configuration_at_execution_time():
    async def response(request):
        await asyncio.sleep(0.01)
        return httpx.Response(200)

    result = asyncio.run(
        check(
            MonitorInput(name="slow", url="https://example.com", degraded_latency_ms=1),
            httpx.MockTransport(response),
        )
    )
    assert result.result == "DEGRADED"
    assert result.http_status == 200
    assert result.latency_ms >= 1
