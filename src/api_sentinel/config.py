import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from dotenv import load_dotenv


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

    def __post_init__(self):
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        if len(self.api_key) < 32 or self.api_key.startswith("replace-with"):
            raise ValueError("SENTINEL_API_KEY must contain at least 32 random characters")
        if not 1 <= self.check_concurrency <= 100:
            raise ValueError("CHECK_CONCURRENCY must be between 1 and 100")
        if not 1 <= self.max_monitors <= 10000 or not 1 <= self.retention_days <= 365:
            raise ValueError("Invalid monitor or retention limit")
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
        return cls(
            database_url=os.environ.get("DATABASE_URL", ""),
            api_key=os.environ.get("SENTINEL_API_KEY", ""),
            check_concurrency=int(os.getenv("CHECK_CONCURRENCY", "10")),
            max_monitors=int(os.getenv("MAX_MONITORS", "100")),
            retention_days=int(os.getenv("RETENTION_DAYS", "30")),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
            allowed_hosts=tuple(os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")),
            secrets_dir=os.getenv("SECRETS_DIR", ".local/secrets"),
            frontend_dir=os.getenv("FRONTEND_DIR", "frontend/dist"),
        )
