from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.schemas.api import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HealthOut:
    await session.connection()
    dialect = "sqlite" if settings.database_url.startswith("sqlite") else "postgresql"
    return HealthOut(
        status="ok",
        env=settings.app_env,
        database=dialect,
    )
