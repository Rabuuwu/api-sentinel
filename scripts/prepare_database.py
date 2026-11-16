"""Create only the dedicated local database; refuse arbitrary database URLs."""

import asyncio
import os
import subprocess
import sys
from urllib.parse import urlsplit

import asyncpg
from dotenv import dotenv_values


async def main():
    values = {**dotenv_values(".env"), **os.environ}
    url = urlsplit(values.get("DATABASE_URL", ""))
    if (
        url.hostname != "127.0.0.1"
        or url.port != 54329
        or url.path != "/sentinel"
        or url.username != "sentinel"
    ):
        raise SystemExit("Native setup only accepts sentinel@127.0.0.1:54329/sentinel")
    if "--validate-only" in sys.argv:
        return
    connection = await asyncpg.connect(
        host="127.0.0.1", port=54329, user="sentinel", password=url.password, database="postgres"
    )
    try:
        if not await connection.fetchval("SELECT 1 FROM pg_database WHERE datname='sentinel'"):
            await connection.execute('CREATE DATABASE "sentinel"')
    finally:
        await connection.close()
    subprocess.run([".venv/bin/alembic", "upgrade", "head"], check=True)


if __name__ == "__main__":
    asyncio.run(main())
