import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from dotenv import dotenv_values

from api_sentinel.config_errors import ConfigurationError, config_url, env_integer
from api_sentinel.database_url import connection_options


def environment_values() -> dict[str, str]:
    # Never mutate os.environ: subsequent Settings reads and child processes must
    # not inherit a lower-priority production URL over an explicit test URL.
    layers: list[Mapping[str, str | None]] = [
        dotenv_values(".env"),
        dotenv_values(".env.local"),
        dict(os.environ),
    ]
    values = {k: v for layer in layers for k, v in layer.items() if v is not None}
    for layer in reversed(layers):
        database = layer.get("DATABASE_URL_UNPOOLED") or layer.get("DATABASE_URL")
        if database:
            values["SENTINEL_RESOLVED_DATABASE_URL"] = database
            break
    return values


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    api_key: str = field(repr=False)
    check_concurrency: int = 10
    max_monitors: int = 100
    retention_days: int = 30
    discord_webhook_url: str = field(default="", repr=False)
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "[::1]")
    secrets_dir: str = field(default=".local/secrets", repr=False)
    frontend_dir: str = "frontend/dist"
    cors_origins: tuple[str, ...] = ()
    hosted: bool = False
    webhook_encryption_key: str = field(default="", repr=False)
    worker_lock_wait_seconds: int = 0

    def __post_init__(self):
        connection_options(self.database_url, self.hosted)
        if self.webhook_encryption_key and not re.fullmatch(
            r"[0-9a-fA-F]{64}", self.webhook_encryption_key
        ):
            raise ConfigurationError("WEBHOOK_ENCRYPTION_KEY must be 64 hexadecimal characters")
        if self.hosted and not self.webhook_encryption_key:
            raise ConfigurationError("Hosted mode requires WEBHOOK_ENCRYPTION_KEY")
        if not 0 <= self.worker_lock_wait_seconds <= 300:
            raise ConfigurationError("WORKER_LOCK_WAIT_SECONDS must be between 0 and 300")
        if len(self.api_key) < 32 or self.api_key.startswith("replace-with"):
            raise ConfigurationError("SENTINEL_API_KEY must contain at least 32 random characters")
        if not 1 <= self.check_concurrency <= 100:
            raise ConfigurationError("CHECK_CONCURRENCY must be between 1 and 100")
        if not 1 <= self.max_monitors <= 10000 or not 1 <= self.retention_days <= 365:
            raise ConfigurationError(
                "MAX_MONITORS must be 1..10000 and RETENTION_DAYS must be 1..365"
            )
        for origin in self.cors_origins:
            parsed = config_url(origin, "CORS_ORIGINS")
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ConfigurationError(
                    "CORS_ORIGINS must contain exact HTTPS origins without paths"
                )
        if self.discord_webhook_url:
            url = config_url(self.discord_webhook_url, "DISCORD_WEBHOOK_URL")
            if (
                url.scheme != "https"
                or url.hostname != "discord.com"
                or not url.path.startswith("/api/webhooks/")
                or url.username
                or url.port not in (None, 443)
            ):
                raise ConfigurationError("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook")

    @classmethod
    def from_env(cls):
        values = environment_values()
        hosts = values.get("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
        external_host = values.get("RENDER_EXTERNAL_HOSTNAME", "")
        if external_host:
            hosts.append(external_host)
        return cls(
            database_url=values.get("SENTINEL_RESOLVED_DATABASE_URL", ""),
            api_key=values.get("SENTINEL_API_KEY", ""),
            check_concurrency=env_integer("CHECK_CONCURRENCY", "10", values),
            max_monitors=env_integer("MAX_MONITORS", "100", values),
            retention_days=env_integer("RETENTION_DAYS", "30", values),
            discord_webhook_url=values.get("DISCORD_WEBHOOK_URL", ""),
            allowed_hosts=tuple(host.strip() for host in hosts if host.strip()),
            secrets_dir=values.get("SECRETS_DIR", ".local/secrets"),
            frontend_dir=values.get("FRONTEND_DIR", "frontend/dist"),
            hosted=values.get("RENDER", "").lower() == "true",
            webhook_encryption_key=values.get("WEBHOOK_ENCRYPTION_KEY", ""),
            worker_lock_wait_seconds=env_integer("WORKER_LOCK_WAIT_SECONDS", "0", values),
            cors_origins=tuple(
                origin.strip()
                for origin in values.get("CORS_ORIGINS", "").split(",")
                if origin.strip()
            ),
        )
