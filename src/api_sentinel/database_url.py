"""Normalize provider URLs without logging credentials; verify hosted TLS certificates."""

import ssl
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def connection_options(value: str, require_tls: bool = False):
    # libpq URL syntax is what Neon exposes; SQLAlchemy asyncpg needs driver options.
    value = value.replace("postgres://", "postgresql+asyncpg://", 1)
    value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
    parsed = urlsplit(value)
    if parsed.scheme != "postgresql+asyncpg":
        raise ValueError("DATABASE_URL must be a PostgreSQL connection string")
    params = dict(parse_qsl(parsed.query))
    mode = params.pop("sslmode", None)
    # asyncpg does not implement libpq's channel_binding option. Never silently downgrade it.
    if params.pop("channel_binding", "prefer") == "require":
        raise ValueError(
            "Remove channel_binding=require from the asyncpg URL; "
            "TLS hostname verification remains required"
        )
    if require_tls and mode in ("disable", "allow", "prefer"):
        raise ValueError("Hosted PostgreSQL requires verified TLS")
    if mode not in (None, "require", "verify-full", "verify-ca", "disable"):
        raise ValueError("Unsupported DATABASE_URL sslmode")
    if require_tls and "ssl" in params:
        raise ValueError("Use sslmode=require, not the ssl URL parameter")
    if require_tls and "-pooler." in (parsed.hostname or ""):
        raise ValueError(
            "Use the direct Neon endpoint (disable connection pooling); worker uses session locks"
        )
    options: dict[str, ssl.SSLContext | bool] = {}
    if require_tls or mode in ("require", "verify-full", "verify-ca"):
        options["ssl"] = ssl.create_default_context()
    elif mode == "disable":
        options["ssl"] = False
    url = urlunsplit(parsed._replace(query=urlencode(params)))
    return url, options
