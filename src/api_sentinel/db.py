from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api_sentinel.config import Settings


class Database:
    def __init__(self, settings: Settings):
        self.engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args={"server_settings": {"statement_timeout": "10000"}},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self):
        await self.engine.dispose()
