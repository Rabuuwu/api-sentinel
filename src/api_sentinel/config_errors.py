"""Configuration diagnostics containing field names, never supplied values."""

import os
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Only static, secret-free messages may be passed to this exception."""


def env_integer(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer") from None


def config_url(value: str, field: str):
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return parsed
    except ValueError:
        raise ConfigurationError(f"{field} contains an invalid URL or port") from None
