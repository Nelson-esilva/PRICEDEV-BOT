from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.inbox import router as inbox_router
from app.api.opportunities import router as opportunities_router
from app.api.products import router as products_router
from app.api.sources import router as sources_router
from app.api.watchlist import router as watchlist_router
from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging
from app.inbox import run_telegram_inbox
from app.monitoring.scheduler import run_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()
    tasks: list[asyncio.Task] = []
    if settings.enable_scheduler:
        tasks.append(asyncio.create_task(run_scheduler(settings)))
    if settings.enable_channel_inbox:
        tasks.append(asyncio.create_task(run_telegram_inbox(settings)))
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
    app = FastAPI(title="PriceDev Bot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(opportunities_router, prefix="/api/v1")
    app.include_router(products_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(watchlist_router, prefix="/api/v1")
    app.include_router(inbox_router, prefix="/api/v1")
    return app


app = create_app()
