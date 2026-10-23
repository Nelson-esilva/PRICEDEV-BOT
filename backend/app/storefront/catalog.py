from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.search import CATEGORY_KEYS
from app.models.entities import Opportunity, PublishedDeal
from app.storefront.taxonomy import category_of

log = get_logger("storefront")

PUBLIC_SOURCES = frozenset({"shopee", "mlhub"})
AFFILIATE_OK = frozenset({"converted", "official"})
STORE_BY_SOURCE = {
    "shopee": "shopee",
    "mlhub": "mercadolivre",
}
STORE_LABELS = {
    "shopee": "Shopee",
    "mercadolivre": "Mercado Livre",
    "kabum": "KaBuM!",
}


def slugify(name: str, short_id: str) -> str:
    folded = unicodedata.normalize("NFKD", name or "")
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()[:72]
    token = (short_id or "deal").replace("-", "")[:8]
    return f"{cleaned}-{token}" if cleaned else token


def store_of(opportunity: Opportunity) -> str:
    return STORE_BY_SOURCE.get(opportunity.source, opportunity.source)


def infer_category(product_name: str, declared: str | None) -> str | None:
    return category_of(product_name, declared)


def discount_of(opportunity: Opportunity) -> tuple[Decimal | None, str | None]:
    if opportunity.classification in {"HISTORICALLY_VALIDATED", "PRICE_ANOMALY_CANDIDATE"}:
        if opportunity.historical_discount_pct and opportunity.historical_discount_pct > 0:
            return opportunity.historical_discount_pct, "historical"
    if opportunity.announced_discount_pct and 5 <= opportunity.announced_discount_pct < 100:
        return opportunity.announced_discount_pct, "store"
    return None, None


def list_price_of(opportunity: Opportunity) -> Decimal | None:
    pct, basis = discount_of(opportunity)
    if basis == "store":
        # Mesma reconstrução do Telegram: preço anterior implícito no percentual da loja.
        if pct is None or pct >= 90:
            return None
        reconstructed = (opportunity.current_price / (Decimal("1") - pct / Decimal("100"))).quantize(Decimal("0.01"))
        return reconstructed if reconstructed > opportunity.current_price else None
    median = opportunity.historical_median
    if median is not None and median > opportunity.current_price:
        return median
    return None


def destination_of(opportunity: Opportunity) -> str | None:
    for candidate in (
        opportunity.affiliate_url,
        opportunity.final_purchase_url,
        opportunity.validated_purchase_url,
        opportunity.original_purchase_url,
    ):
        url = (candidate or "").strip()
        if url:
            return url
    return None


def qualifies(opportunity: Opportunity, settings: Settings) -> bool:
    if opportunity.source not in PUBLIC_SOURCES:
        return False
    if opportunity.status != "active":
        return False
    if opportunity.classification in {"REJECTED", "EXPIRED"}:
        return False
    if discount_of(opportunity)[0] is None and not (opportunity.coupon_code or "").strip():
        return False
    if opportunity.affiliate_status not in AFFILIATE_OK:
        return False
    if opportunity.acceptance_score < settings.storefront_min_score:
        return False
    return destination_of(opportunity) is not None


def _apply_snapshot(deal: PublishedDeal, opportunity: Opportunity, *, now: datetime, ttl: timedelta) -> None:
    deal.product_id = opportunity.product_id
    deal.source = opportunity.source
    deal.store = store_of(opportunity)
    deal.product_name = opportunity.product_name
    deal.merchant = opportunity.merchant or STORE_LABELS.get(deal.store)
    deal.category = infer_category(opportunity.product_name, opportunity.category)
    deal.image_url = opportunity.image_url
    deal.description = opportunity.description
    deal.coupon_code = opportunity.coupon_code
    hint = opportunity.payment_hint
    deal.payment_hint = None if hint and re.search(r"ganhos|comiss|commission|earning", hint, re.I) else hint
    deal.current_price = opportunity.current_price
    deal.list_price = list_price_of(opportunity)
    deal.announced_discount_pct = opportunity.announced_discount_pct
    deal.discount_pct, deal.discount_basis = discount_of(opportunity)
    deal.acceptance_score = opportunity.acceptance_score
    deal.currency = opportunity.currency
    deal.affiliate_network = opportunity.affiliate_network or deal.store
    deal.destination_url = destination_of(opportunity) or deal.destination_url
    deal.status = "active"
    observed = opportunity.fetched_at or opportunity.analyzed_at or opportunity.updated_at or now
    deal.updated_at = observed
    deal.last_seen_at = observed
    deal.expires_at = observed + ttl
    deal.expired_at = None


async def sync_catalog(session: AsyncSession, settings: Settings, *, now: datetime | None = None) -> dict[str, int]:
    moment = now or utcnow()
    ttl = timedelta(hours=max(1, settings.storefront_deal_ttl_hours))
    opportunities = (
        (
            await session.execute(
                select(Opportunity).where(
                    Opportunity.source.in_(tuple(PUBLIC_SOURCES)),
                    Opportunity.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    eligible = [item for item in opportunities if qualifies(item, settings)
                and (item.fetched_at or item.analyzed_at or item.updated_at or moment) + ttl > moment]
    eligible_ids = {item.id for item in eligible}
    existing = (
        (
            await session.execute(
                select(PublishedDeal).where(PublishedDeal.opportunity_id.in_(eligible_ids))
            )
        )
        .scalars()
        .all()
        if eligible_ids
        else []
    )
    by_opp = {deal.opportunity_id: deal for deal in existing}
    created = 0
    updated = 0
    for opportunity in eligible:
        deal = by_opp.get(opportunity.id)
        if deal is None:
            deal = PublishedDeal(
                opportunity_id=opportunity.id,
                slug=slugify(opportunity.product_name, opportunity.id),
                destination_url=destination_of(opportunity) or "",
                expires_at=moment + ttl,
                published_at=moment,
            )
            session.add(deal)
            created += 1
        else:
            updated += 1
        _apply_snapshot(deal, opportunity, now=moment, ttl=ttl)

    stale_stmt = select(PublishedDeal).where(PublishedDeal.status == "active")
    if eligible_ids:
        stale_stmt = stale_stmt.where(PublishedDeal.opportunity_id.notin_(eligible_ids))
    stale = (await session.execute(stale_stmt)).scalars().all()
    expired = 0
    for deal in stale:
        deal.status = "expired"
        deal.expired_at = moment
        deal.updated_at = moment
        expired += 1
    return {
        "seen": len(opportunities),
        "eligible": len(eligible),
        "created": created,
        "updated": updated,
        "expired": expired,
    }


async def publish_public_catalog(
    settings: Settings | None = None,
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> dict[str, int]:
    settings = settings or get_settings()
    if session is not None:
        stats = await sync_catalog(session, settings, now=now)
        log.info("catalog_publish_ok", **stats)
        return stats
    factory = get_session_factory()
    async with factory() as owned:
        stats = await sync_catalog(owned, settings, now=now)
        await owned.commit()
    log.info("catalog_publish_ok", **stats)
    return stats
