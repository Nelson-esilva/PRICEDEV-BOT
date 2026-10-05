from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.monitoring.metrics import get_or_create_checkpoint, latency_summary
from app.schemas.api import SourceStatusOut
from app.sources.registry import build_connectors

router = APIRouter()


@router.get("/sources", response_model=list[SourceStatusOut])
async def list_sources(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[SourceStatusOut]:
    return await _statuses(session, settings)


@router.get("/monitoring/status", response_model=list[SourceStatusOut])
async def monitoring_status(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[SourceStatusOut]:
    return await _statuses(session, settings)


async def _statuses(session: AsyncSession, settings: Settings) -> list[SourceStatusOut]:
    connectors = build_connectors(settings)
    out: list[SourceStatusOut] = []
    for connector in connectors:
        checkpoint = await get_or_create_checkpoint(session, connector.name)
        metrics = await latency_summary(session, connector.name)
        out.append(
            SourceStatusOut(
                source=connector.name,
                enabled=connector.is_enabled() and checkpoint.enabled,
                configured=connector.is_enabled(),
                last_poll_at=checkpoint.last_poll_at,
                last_success_at=checkpoint.last_success_at,
                last_error=checkpoint.last_error,
                circuit_open_until=checkpoint.circuit_open_until,
                requests_total=checkpoint.requests_total,
                requests_failed=checkpoint.requests_failed,
                rate_limit_events=checkpoint.rate_limit_events,
                offers_received=checkpoint.offers_received,
                offers_new=checkpoint.offers_new,
                offers_duplicate=checkpoint.offers_duplicate,
                offers_provisional=checkpoint.offers_provisional,
                offers_historically_validated=checkpoint.offers_historically_validated,
                offers_rejected=checkpoint.offers_rejected,
                poll_seconds=connector.poll_seconds,
                metrics=metrics,
            )
        )
    await session.commit()
    return out
