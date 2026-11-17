"""Remove only known E2E fixture accounts from an explicitly isolated local test DB."""

import asyncio
import os

from account_helpers import remove_identity
from sqlalchemy import select
from sqlalchemy.engine import make_url

from api_sentinel.auth_models import User
from api_sentinel.config import Settings
from api_sentinel.db import Database


async def main():
    url = os.environ["SENTINEL_TEST_DATABASE_URL"]
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or parsed.database != "sentinel_test":
        raise SystemExit("Refusing E2E cleanup outside localhost sentinel_test")
    db = Database(Settings(url, "isolated-test-only-key-" + "x" * 32))
    try:
        async with db.sessions() as session:
            ids = list(
                (
                    await session.scalars(
                        select(User.id).where(
                            (User.username == "e2e-owner") | User.username.startswith("guest-e2e-")
                        )
                    )
                ).all()
            )
        for key in ids:
            await remove_identity(db, key)
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
