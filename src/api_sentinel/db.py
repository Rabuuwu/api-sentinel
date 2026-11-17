from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api_sentinel import auth_models  # noqa: F401
from api_sentinel.config import Settings
from api_sentinel.database_url import connection_options


class Database:
    def __init__(self, settings: Settings):
        url, options = connection_options(settings.database_url, settings.hosted)
        if url.startswith("postgresql+psycopg://"):
            options["options"] = "-c statement_timeout=10000"
        else:
            options["server_settings"] = {"statement_timeout": "10000"}
        self.engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
            connect_args=options,
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self):
        await self.engine.dispose()
