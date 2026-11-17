"""One-instance hosted launcher: migrate, then supervise API and scheduler separately."""

import asyncio
import logging
import signal
import sys

from api_sentinel.config import Settings, environment_values
from api_sentinel.config_errors import ConfigurationError, env_integer
from api_sentinel.vault import EncryptedVault

logger = logging.getLogger("sentinel")


async def stop_processes(processes):
    for process in processes:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
    if not processes:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*(process.wait() for process in processes)), timeout=20
        )
    except TimeoutError:
        for process in processes:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
        await asyncio.gather(*(process.wait() for process in processes))


async def supervise(commands, stop, spawn=None):
    spawn = spawn or asyncio.create_subprocess_exec
    processes = []
    waits = []
    try:
        for command in commands:
            if stop.is_set():
                return 0
            processes.append(await spawn(*command))
        waits = [asyncio.create_task(process.wait()) for process in processes]
        stopping = asyncio.create_task(stop.wait())
        waits.append(stopping)
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        # Even an unexpected child exit(0) is a failed service, not a healthy API-only instance.
        return 0 if stop.is_set() else 1
    finally:
        await stop_processes(processes)
        for task in waits:
            task.cancel()
        await asyncio.gather(*waits, return_exceptions=True)


async def run():
    settings = Settings.from_env()
    if settings.webhook_encryption_key:
        EncryptedVault(settings.webhook_encryption_key)  # Fail before migration if unavailable.
    port = env_integer("PORT", "8000", environment_values())
    if not 1 <= port <= 65535:
        raise ConfigurationError("PORT must be between 1 and 65535")
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    migration = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "alembic", "upgrade", "head"
    )
    migration_wait = asyncio.create_task(migration.wait())
    stop_wait = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait(
            [migration_wait, stop_wait], timeout=300, return_when=asyncio.FIRST_COMPLETED
        )
        if stop.is_set():
            return 0
        if migration_wait not in done or migration.returncode != 0:
            raise RuntimeError("Database migration failed or timed out")
    finally:
        await stop_processes([migration])
        for task in (migration_wait, stop_wait):
            task.cancel()
        await asyncio.gather(migration_wait, stop_wait, return_exceptions=True)
    return await supervise(
        [
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api_sentinel.app:create_app",
                "--factory",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
                "--no-access-log",
            ],
            [sys.executable, "-m", "api_sentinel.worker"],
        ],
        stop,
    )


def main():
    logging.basicConfig(level=logging.INFO)
    try:
        code = asyncio.run(run())
    except ConfigurationError as error:
        logger.error("Hosted configuration invalid: %s", error)
        code = 1
    except Exception as error:
        # Config/DB/secret exceptions must not reveal credentials in provider logs.
        logger.error("Hosted startup failed (%s)", type(error).__name__)
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
