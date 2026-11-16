import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit


class UnsafeTarget(ValueError):
    pass


def public_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped or ip.sixtofour or ip.teredo:
            return False
        if ip in ipaddress.ip_network("64:ff9b::/96"):
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def validate_url(value: str) -> str:
    try:
        url = urlsplit(value)
        host = url.hostname
        if (
            url.scheme not in {"http", "https"}
            or not host
            or url.username is not None
            or url.password is not None
            or url.fragment
            or url.query
            or url.port not in (None, 80, 443)
            or "\\" in value
            or any(ord(c) < 33 or ord(c) == 127 for c in value)
        ):
            raise UnsafeTarget("Use HTTP(S), ports 80/443, without credentials, query or fragment")
        if host.rstrip(".").lower() == "localhost" or host.lower().endswith(".localhost"):
            raise UnsafeTarget("Private targets are not allowed")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            ascii_host = host.rstrip(".").encode("idna").decode("ascii")
            if len(ascii_host) > 253 or not all(
                re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in ascii_host.split(".")
            ):
                raise UnsafeTarget("Invalid DNS hostname") from None
        else:
            if not public_ip(host):
                raise UnsafeTarget("Private targets are not allowed")
    except (ValueError, UnicodeError) as exc:
        raise UnsafeTarget("Invalid or disallowed target URL") from exc
    return value


async def resolve_public(host: str, port: int) -> str:
    """Validate ALL answers; return a literal address for the actual TCP connection."""
    answers = await asyncio.get_running_loop().getaddrinfo(
        host,
        port,
        type=socket.SOCK_STREAM,
    )
    addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
    if not addresses or not all(public_ip(ip) for ip in addresses):
        raise UnsafeTarget("DNS returned a non-public address")
    return addresses[0]
