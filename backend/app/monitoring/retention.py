from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.inbox.media import media_path
from app.models.entities import (
    InboxMessage,
    Opportunity,
    PriceObservation,
    Product,
    PublicationLog,
    SourceMetricSample,
)

log = get_logger("retention")

_MEDIA_MARKER = "/inbox/media/"


def _media_name(url: str | None) -> str | None:
    if not url or _MEDIA_MARKER not in url:
        return None
    name = url.rsplit("/", 1)[-1].strip()
    return name or None


def _unlink_media(names: set[str]) -> int:
    removed = 0
    for name in names:
        path = media_path(name)
        if path is None:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


async def purge_stale_promos(
    session: AsyncSession,
    *,
    days: int,
    now: datetime | None = None,
) -> dict[str, int]:
    cutoff = (now or utcnow()) - timedelta(days=max(1, days))

    inbox_urls = (
        await session.execute(
            select(InboxMessage.image_url).where(InboxMessage.posted_at < cutoff)
        )
    ).scalars().all()
    doomed_media = {name for url in inbox_urls if (name := _media_name(url))}

    opportunities = (
        await session.execute(delete(Opportunity).where(Opportunity.updated_at < cutoff))
    ).rowcount or 0
    observations = (
        await session.execute(
            delete(PriceObservation).where(
                PriceObservation.observed_at < cutoff,
                ~exists().where(Opportunity.observation_id == PriceObservation.id),
            )
        )
    ).rowcount or 0
    products = (
        await session.execute(
            delete(Product).where(
                ~exists().where(PriceObservation.product_id == Product.id),
                ~exists().where(Opportunity.product_id == Product.id),
            )
        )
    ).rowcount or 0
    inbox = (
        await session.execute(delete(InboxMessage).where(InboxMessage.posted_at < cutoff))
    ).rowcount or 0
    publications = (
        await session.execute(
            delete(PublicationLog).where(PublicationLog.published_at < cutoff)
        )
    ).rowcount or 0
    metrics = (
        await session.execute(
            delete(SourceMetricSample).where(SourceMetricSample.recorded_at < cutoff)
        )
    ).rowcount or 0

    kept_urls = (await session.execute(select(InboxMessage.image_url))).scalars().all()
    kept_media = {name for url in kept_urls if (name := _media_name(url))}
    media = _unlink_media(doomed_media - kept_media)
    session.expire_all()

    return {
        "opportunities": opportunities,
        "observations": observations,
        "products": products,
        "inbox": inbox,
        "publications": publications,
        "metrics": metrics,
        "media": media,
        "days": days,
    }


async def run_retention(
    settings: Settings | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    days = settings.promo_retention_days
    if days <= 0:
        return {"skipped": 1}
    factory = get_session_factory()
    async with factory() as session:
        stats = await purge_stale_promos(session, days=days, now=now)
        await session.commit()
    log.info("retention_ok", **stats)
    return stats
