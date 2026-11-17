import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from api_sentinel import auth_models  # noqa: F401
from api_sentinel.config import Settings
from api_sentinel.database_url import connection_options
from api_sentinel.models import Base


def configure(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    settings = Settings.from_env()
    url, options = connection_options(settings.database_url, settings.hosted)
    engine = create_async_engine(url, connect_args=options)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url="postgresql+asyncpg://",
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
