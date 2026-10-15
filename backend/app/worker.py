from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging, get_logger
from app.inbox import run_telegram_inbox
from app.monitoring.retention import run_retention
from app.monitoring.scheduler import run_scheduler


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("worker")
    await init_db()
    try:
        await run_retention(settings)
    except Exception as exc:
        log.exception("retention_startup_failed", error=str(exc))
    tasks: list[asyncio.Task] = []
    if settings.enable_scheduler:
        tasks.append(asyncio.create_task(run_scheduler(settings)))
    if settings.enable_channel_inbox:
        tasks.append(asyncio.create_task(run_telegram_inbox(settings)))
    if not tasks:
        log.warning("worker_idle")
        while True:
            await asyncio.sleep(3600)
        return
    log.info(
        "worker_start",
        scheduler=settings.enable_scheduler,
        inbox=settings.enable_channel_inbox,
    )
    await asyncio.gather(*tasks)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
