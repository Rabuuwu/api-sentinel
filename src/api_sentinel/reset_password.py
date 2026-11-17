"""Operator-only password recovery using direct DB access; never accepts secrets as arguments."""

import asyncio
import getpass
import sys

from sqlalchemy import delete, select

from api_sentinel.auth import Credentials
from api_sentinel.auth_models import AuthSession, User
from api_sentinel.config import Settings
from api_sentinel.db import Database
from api_sentinel.passwords import Passwords


async def reset(username: str, password: str):
    db = Database(Settings.from_env())
    try:
        async with db.sessions.begin() as session:
            user = await session.scalar(
                select(User).where(User.username == username).with_for_update()
            )
            if user is None:
                raise ValueError("Account not found")
            user.password_hash = await asyncio.to_thread(Passwords().hash, password)
            await session.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    finally:
        await db.close()


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Use an interactive terminal; passwords are never accepted as arguments")
    username = input("Username: ")
    password = getpass.getpass("New password (15–128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    try:
        data = Credentials.model_validate({"username": username, "password": password})
        asyncio.run(reset(data.username, data.password.get_secret_value()))
    except Exception:
        raise SystemExit(
            "Password reset failed; check username, password rules and DB access"
        ) from None
    print("Password updated; all sessions for this account revoked")


if __name__ == "__main__":
    main()
