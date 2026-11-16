"""Normalize provider URLs without logging credentials; verify hosted TLS certificates."""

import ssl
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def connection_options(value: str, require_tls: bool = False):
    # libpq URL syntax is what Neon exposes; SQLAlchemy asyncpg needs driver options.
    value = value.replace("postgres://", "postgresql+asyncpg://", 1)
    value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlsplit(value)
    if parsed.scheme not in ("postgresql+asyncpg", "postgresql+psycopg"):
        raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
    params = dict(parse_qsl(parsed.query))
    mode = params.pop("sslmode", None)
    binding = params.pop("channel_binding", "prefer")
    if binding not in ("require", "prefer", "disable"):
        raise ValueError("Unsupported channel_binding option")
    if require_tls and mode in ("disable", "allow", "prefer"):
        raise ValueError("Hosted PostgreSQL requires verified TLS")
    if mode not in (None, "require", "verify-full", "verify-ca", "disable"):
        raise ValueError("Unsupported DATABASE_URL sslmode")
    if require_tls and "ssl" in params:
        raise ValueError("Use sslmode=require, not the ssl URL parameter")
    if "-pooler." in (parsed.hostname or ""):
        raise ValueError(
            "Use the direct Neon endpoint (disable connection pooling); worker uses session locks"
        )
    options: dict[str, Any] = {}
    # Preserve required SCRAM channel binding using libpq; asyncpg cannot enforce it.
    if binding == "require" or parsed.scheme == "postgresql+psycopg":
        if "ssl" in params or mode == "disable":
            raise ValueError("Channel-bound PostgreSQL requires verified TLS")
        params.update(sslmode="verify-full", sslrootcert="system", channel_binding=binding)
        url = urlunsplit(parsed._replace(scheme="postgresql+psycopg", query=urlencode(params)))
        return url, options

    if require_tls or mode in ("require", "verify-full", "verify-ca"):
        options["ssl"] = ssl.create_default_context()
    elif mode == "disable":
        options["ssl"] = False
    url = urlunsplit(parsed._replace(query=urlencode(params)))
    return url, options
