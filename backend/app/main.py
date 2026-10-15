from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.go import router as go_router
from app.api.health import router as health_router
from app.api.inbox import media_router as inbox_media_router
from app.api.inbox import router as inbox_router
from app.api.opportunities import router as opportunities_router
from app.api.ops_auth import require_ops
from app.api.products import router as products_router
from app.api.public import router as public_router
from app.api.sources import router as sources_router
from app.api.watchlist import router as watchlist_router
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging, get_logger
from app.inbox import run_telegram_inbox
from app.monitoring.retention import run_retention
from app.monitoring.scheduler import run_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()
    try:
        await run_retention(settings)
    except Exception as exc:
        get_logger("app").exception("retention_startup_failed", error=str(exc))
    tasks: list[asyncio.Task] = []
    if settings.enable_scheduler:
        tasks.append(asyncio.create_task(run_scheduler(settings)))
    if settings.enable_channel_inbox:
        print("telegram_inbox task_start", flush=True)
        tasks.append(asyncio.create_task(run_telegram_inbox(settings)))
    else:
        print("telegram_inbox skipped_flag_off", flush=True)
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PriceDev Bot", version="0.1.0", lifespan=lifespan)
    origins = settings.public_cors_origin_list or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    ops = [Depends(require_ops)]
    app.include_router(health_router)
    app.include_router(go_router)
    app.include_router(public_router, prefix="/api/public/v1")
    app.include_router(opportunities_router, prefix="/api/v1", dependencies=ops)
    app.include_router(products_router, prefix="/api/v1", dependencies=ops)
    app.include_router(sources_router, prefix="/api/v1", dependencies=ops)
    app.include_router(watchlist_router, prefix="/api/v1", dependencies=ops)
    app.include_router(inbox_router, prefix="/api/v1", dependencies=ops)
    return app


app = create_app()
