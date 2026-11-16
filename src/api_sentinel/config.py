import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from dotenv import load_dotenv

from api_sentinel.database_url import connection_options


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
            raise ValueError("WEBHOOK_ENCRYPTION_KEY must be 64 hexadecimal characters")
        if self.hosted and not self.webhook_encryption_key:
            raise ValueError("Hosted mode requires WEBHOOK_ENCRYPTION_KEY")
        if not 0 <= self.worker_lock_wait_seconds <= 300:
            raise ValueError("Invalid worker lock wait")
        if len(self.api_key) < 32 or self.api_key.startswith("replace-with"):
            raise ValueError("SENTINEL_API_KEY must contain at least 32 random characters")
        if not 1 <= self.check_concurrency <= 100:
            raise ValueError("CHECK_CONCURRENCY must be between 1 and 100")
        if not 1 <= self.max_monitors <= 10000 or not 1 <= self.retention_days <= 365:
            raise ValueError("Invalid monitor or retention limit")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
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
                raise ValueError("CORS_ORIGINS must contain exact HTTPS origins without paths")
        if self.discord_webhook_url:
            url = urlsplit(self.discord_webhook_url)
            if (
                url.scheme != "https"
                or url.hostname != "discord.com"
                or not url.path.startswith("/api/webhooks/")
                or url.username
                or url.port not in (None, 443)
            ):
                raise ValueError("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook")

    @classmethod
    def from_env(cls):
        load_dotenv()
        hosts = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
        external_host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "")
        if external_host:
            hosts.append(external_host)
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            api_key=os.environ.get("SENTINEL_API_KEY", ""),
            check_concurrency=int(os.getenv("CHECK_CONCURRENCY", "10")),
            max_monitors=int(os.getenv("MAX_MONITORS", "100")),
            retention_days=int(os.getenv("RETENTION_DAYS", "30")),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
            allowed_hosts=tuple(host.strip() for host in hosts if host.strip()),
            secrets_dir=os.getenv("SECRETS_DIR", ".local/secrets"),
            frontend_dir=os.getenv("FRONTEND_DIR", "frontend/dist"),
            hosted=os.getenv("RENDER", "").lower() == "true",
            webhook_encryption_key=os.getenv("WEBHOOK_ENCRYPTION_KEY", ""),
            worker_lock_wait_seconds=int(os.getenv("WORKER_LOCK_WAIT_SECONDS", "0")),
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("CORS_ORIGINS", "").split(",")
                if origin.strip()
            ),
        )
