import asyncio
import json
import logging
import signal

from sqlalchemy import text

from api_sentinel.alerts import send_pending
from api_sentinel.checker import check
from api_sentinel.config import Settings
from api_sentinel.db import Database
from api_sentinel.service import housekeeping, record, recover_abandoned, reserve

logger = logging.getLogger("sentinel")
WORKER_LOCK = 71424001


async def run(settings: Settings):
    db = Database(settings)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        async with db.engine.connect() as lock:
            deadline = asyncio.get_running_loop().time() + settings.worker_lock_wait_seconds
            while True:
                acquired = await lock.scalar(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}
                )
                await lock.commit()
                if acquired:
                    break
                if stop.is_set():
                    return
                if asyncio.get_running_loop().time() >= deadline:
                    raise RuntimeError("Another API Sentinel worker already owns the scheduler")
                # Render may start a replacement before stopping the old deployment.
                try:
                    await asyncio.wait_for(stop.wait(), timeout=2)
                except TimeoutError:
                    pass
            await recover_abandoned(db)
            channel = "discord" if settings.discord_webhook_url else "console"

            async def execute(execution_id, monitor):
                result = await check(monitor)
                await record(db, execution_id, result, channel)
                logger.info(
                    json.dumps(
                        {
                            "event": "check",
                            "execution_id": str(execution_id),
                            "result": result.result,
                        }
                    )
                )

            async def wait_for_stop():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=5)
                except TimeoutError:
                    pass

            async def sender():
                while not stop.is_set():
                    await send_pending(db, settings, stop=stop)
                    await wait_for_stop()

            async def scheduler():
                while not stop.is_set():
                    # A lost lock connection terminates the process; never silently reconnect.
                    await lock.execute(text("SELECT 1"))
                    await lock.commit()
                    await housekeeping(db, settings.retention_days)
                    work = await reserve(db, settings.check_concurrency)
                    async with asyncio.TaskGroup() as group:
                        for execution_id, monitor in work:
                            group.create_task(execute(execution_id, monitor))
                    await wait_for_stop()

            try:
                async with asyncio.TaskGroup() as tasks:
                    tasks.create_task(sender())
                    tasks.create_task(scheduler())
            finally:
                if not lock.invalidated:
                    await lock.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK}
                    )
                    await lock.commit()
    finally:
        await db.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # httpx logs full webhook URLs at INFO; never allow that in application logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        asyncio.run(run(Settings.from_env()))
    except Exception as exc:
        logger.error(json.dumps({"event": "worker_stopped", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
