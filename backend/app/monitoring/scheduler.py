from __future__ import annotations

import asyncio
from datetime import timedelta

from app.core.config import Settings, get_settings
from app.core.db import as_utc, get_session_factory, utcnow
from app.core.logging import get_logger
from app.ingestion.pipeline import ingest_offers
from app.monitoring.metrics import get_or_create_checkpoint
from app.publishing.telegram import publish_opportunity
from app.sources.pelando import PelandoSource
from app.sources.shopee import ShopeeSource
from app.sources.base import SourceAuthError, SourceBlocked, SourceConnector, SourceError

log = get_logger("scheduler")


def build_connectors(settings: Settings) -> list[SourceConnector]:
    return [
        PelandoSource(settings),
        ShopeeSource(settings),
    ]


async def poll_source(connector: SourceConnector, settings: Settings) -> None:
    factory = get_session_factory()
    async with factory() as session:
        checkpoint = await get_or_create_checkpoint(session, connector.name)
        now = utcnow()
        circuit_until = as_utc(checkpoint.circuit_open_until)
        locked_until = as_utc(checkpoint.locked_until)
        if circuit_until and circuit_until > now:
            log.warning("circuit_open", source=connector.name, until=str(circuit_until))
            return
        if locked_until and locked_until > now:
            return
        checkpoint.locked_until = now + timedelta(seconds=max(connector.poll_seconds - 1, 3))
        checkpoint.last_poll_at = now
        await session.commit()

    try:
        offers = await connector.poll(now=now)
        async with factory() as session:
            checkpoint = await get_or_create_checkpoint(session, connector.name)
            checkpoint.requests_total += 1
            checkpoint.offers_received += len(offers)
            result = await ingest_offers(session, offers, settings, now=now)
            checkpoint.offers_new += result.created
            checkpoint.offers_duplicate += result.duplicates
            checkpoint.offers_provisional += result.provisional
            checkpoint.offers_historically_validated += result.historically_validated
            checkpoint.offers_rejected += result.rejected
            checkpoint.last_success_at = utcnow()
            checkpoint.last_error = None
            log.info(
                "poll_ok",
                source=connector.name,
                received=len(offers),
                novas=result.created,
                duplicatas=result.duplicates,
            )
            if settings.enable_telegram_publish:
                for opp in result.opportunities:
                    await publish_opportunity(session, opp, settings)
            await session.commit()
    except SourceBlocked as exc:
        await _fail(connector.name, str(exc), disable=True)
    except SourceAuthError as exc:
        await _fail(connector.name, str(exc), disable=True)
    except SourceError as exc:
        await _fail(connector.name, str(exc), disable=exc.disable, rate_limit="429" in str(exc))
    except Exception as exc:
        await _fail(connector.name, str(exc), disable=False)


async def _fail(source: str, message: str, *, disable: bool, rate_limit: bool = False) -> None:
    log.error("source_failed", source=source, error=message, disable=disable)
    factory = get_session_factory()
    async with factory() as session:
        checkpoint = await get_or_create_checkpoint(session, source)
        checkpoint.requests_failed += 1
        checkpoint.last_error = message[:2000]
        if rate_limit:
            checkpoint.rate_limit_events += 1
        if disable:
            checkpoint.enabled = False
            checkpoint.circuit_open_until = utcnow() + timedelta(minutes=30)
        await session.commit()


async def run_scheduler(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    connectors = [c for c in build_connectors(settings) if c.is_enabled()]
    log.info("scheduler_start", sources=[c.name for c in connectors])
    try:
        while True:
            for connector in connectors:
                if not connector.is_enabled():
                    continue
                try:
                    await poll_source(connector, settings)
                except Exception as exc:
                    log.exception("poll_crash", source=connector.name, error=str(exc))
                await asyncio.sleep(0)
            await asyncio.sleep(1)
    finally:
        for connector in connectors:
            await connector.close()
