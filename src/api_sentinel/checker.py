import asyncio
import socket
import ssl
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpcore
import httpx

from api_sentinel.schemas import MonitorInput
from api_sentinel.security import UnsafeTarget, resolve_public, validate_url


class PublicBackend(httpcore.AsyncNetworkBackend):
    def __init__(self):
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ):
        address = await resolve_public(host, port)
        # TLS and Host still use the original hostname held by httpcore.
        return await self.backend.connect_tcp(address, port, timeout, local_address, socket_options)


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class PublicTransport(httpx.AsyncBaseTransport):
    def __init__(self, backend=None):
        self.pool = httpcore.AsyncConnectionPool(
            network_backend=backend or PublicBackend(),
            max_connections=1,
            max_keepalive_connections=0,
            retries=0,
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.pool.handle_async_request(
            httpcore.Request(
                method=request.method,
                url=httpcore.URL(
                    scheme=request.url.raw_scheme,
                    host=request.url.raw_host,
                    port=request.url.port,
                    target=request.url.raw_path,
                ),
                headers=request.headers.raw,
                content=request.stream,
                extensions=request.extensions,
            )
        )
        return httpx.Response(
            response.status,
            headers=response.headers,
            stream=ResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self):
        await self.pool.aclose()


@dataclass(frozen=True)
class CheckResult:
    result: str
    http_status: int | None = None
    latency_ms: float | None = None


async def check(monitor: MonitorInput, transport: httpx.AsyncBaseTransport | None = None):
    start = time.monotonic()
    try:
        validate_url(monitor.url)
        async with asyncio.timeout(monitor.timeout_seconds):
            async with httpx.AsyncClient(
                transport=transport or PublicTransport(),
                trust_env=False,
                follow_redirects=False,
                timeout=monitor.timeout_seconds,
                headers={"User-Agent": "API-Sentinel/0.1"},
            ) as client:
                # Stream only response headers. Never buffer/decompress a remote response body.
                async with client.stream(monitor.method, monitor.url) as response:
                    if sum(len(k) + len(v) for k, v in response.headers.raw) > 65536:
                        return CheckResult("RESPONSE_TOO_LARGE")
                    result = (
                        "SUCCESS"
                        if monitor.expected_status_min
                        <= response.status_code
                        <= monitor.expected_status_max
                        else "HTTP_ERROR"
                    )
                    latency = round((time.monotonic() - start) * 1000, 3)
                    if (
                        result == "SUCCESS"
                        and monitor.degraded_latency_ms is not None
                        and latency >= monitor.degraded_latency_ms
                    ):
                        result = "DEGRADED"
                    return CheckResult(result, response.status_code, latency)
    except (UnsafeTarget, httpx.InvalidURL):
        return CheckResult("BLOCKED_TARGET")
    except socket.gaierror:
        return CheckResult("DNS_ERROR")
    except (TimeoutError, httpx.TimeoutException, httpcore.TimeoutException):
        return CheckResult("TIMEOUT")
    except ssl.SSLError:
        return CheckResult("TLS_ERROR")
    except (httpx.NetworkError, httpcore.NetworkError) as exc:
        cause: BaseException | None = exc
        while cause:
            if isinstance(cause, ssl.SSLError):
                return CheckResult("TLS_ERROR")
            cause = cause.__cause__
        return CheckResult("NETWORK_ERROR")
    except (httpx.ProtocolError, httpcore.ProtocolError):
        return CheckResult("NETWORK_ERROR")
