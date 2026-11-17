"""Configuration diagnostics containing field names, never supplied values."""

import os
from collections.abc import Mapping
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Only static, secret-free messages may be passed to this exception."""


def env_integer(name: str, default: str, values: Mapping[str, str] | None = None) -> int:
    try:
        return int((os.environ if values is None else values).get(name, default))
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer") from None


def config_url(value: str, field: str):
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return parsed
    except ValueError:
        raise ConfigurationError(f"{field} contains an invalid URL or port") from None
