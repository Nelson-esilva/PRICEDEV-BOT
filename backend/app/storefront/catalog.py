from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.search import CATEGORY_KEYS
from app.models.entities import AffiliateConversion, DealClick, Opportunity, Product, PublishedDeal
from app.storefront.taxonomy import category_of
from app.storefront.trends import load_trends, trend_of

log = get_logger("storefront")

PUBLIC_SOURCES = frozenset({"shopee", "mlhub", "mlofficial", "grupos"})
AFFILIATE_OK = frozenset({"converted", "official"})
STORE_BY_SOURCE = {
    "shopee": "shopee",
    "mlhub": "mercadolivre",
    "mlofficial": "mercadolivre",
}
STORE_LABELS = {
    "shopee": "Shopee",
    "mercadolivre": "Mercado Livre",
    "kabum": "KaBuM!",
    "amazon": "Amazon",
}
# Promoções dos grupos: a loja sai do link de compra.
_STORE_HOSTS = (("amazon.", "amazon"), ("kabum.com.br", "kabum"), ("awin1.com", "kabum"))


def slugify(name: str, short_id: str) -> str:
    folded = unicodedata.normalize("NFKD", name or "")
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()[:72]
    token = (short_id or "deal").replace("-", "")[:8]
    return f"{cleaned}-{token}" if cleaned else token


def store_of(opportunity: Opportunity) -> str:
    if opportunity.source == "grupos":
        url = (opportunity.original_purchase_url or opportunity.affiliate_url or "").lower()
        return next((store for needle, store in _STORE_HOSTS if needle in url), "grupos")
    return STORE_BY_SOURCE.get(opportunity.source, opportunity.source)


def infer_category(product_name: str, declared: str | None, official: str | None = None) -> str | None:
    return category_of(product_name, declared, official)


def discount_of(opportunity: Opportunity) -> tuple[Decimal | None, str | None]:
    if opportunity.classification in {"HISTORICALLY_VALIDATED", "PRICE_ANOMALY_CANDIDATE"}:
        if opportunity.historical_discount_pct and opportunity.historical_discount_pct > 0:
            return opportunity.historical_discount_pct, "historical"
    if opportunity.announced_discount_pct and 5 <= opportunity.announced_discount_pct < 100:
        return opportunity.announced_discount_pct, "store"
    return None, None


def list_price_of(opportunity: Opportunity) -> Decimal | None:
    listed = opportunity.listed_price
    if listed is not None and listed > opportunity.current_price:
        return listed
    pct, basis = discount_of(opportunity)
    if basis == "store" and opportunity.price_max and opportunity.price_max > opportunity.current_price:
        # Anúncio com variações: o percentual da loja é o "até X%" da opção mais descontada,
        # não do menor preço. Reconstruir o "De" daria um preço riscado inventado.
        return None
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


def demand_score_of(
    *,
    sales: int | None,
    rating: Decimal | None,
    discount: Decimal | None,
    commission: Decimal | None,
    best_seller: bool | None,
    clicks_7d: int,
    orders_30d: int,
    trending: bool = False,
    rank_position: int | None = None,
) -> int:
    """0–100. Pedidos reais pesam mais; vendas e nota da loja dão o sinal inicial."""
    def log_points(value: float, per_decade: float, cap: float) -> float:
        return min(cap, per_decade * math.log10(1 + max(0.0, value)))

    points = log_points(sales or 0, 7, 35)
    points += min(15.0, max(0.0, (float(rating) - 4.0) * 15)) if rating else 0
    points += min(15.0, float(discount or 0) * 0.3)
    points += log_points(float(commission or 0), 5, 10)
    points += 5 if best_seller else 0
    points += log_points(clicks_7d, 5, 10)
    points += log_points(orders_30d, 10, 20)
    # O que as pessoas estão buscando agora sobe na vitrine; top 10 do ranking oficial também.
    points += 12 if trending else 0
    points += 6 if rank_position and rank_position <= 10 else 0
    return max(0, min(100, round(points)))


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
    # Grupos já selecionam promoções; sem preço "de" a oferta entra sem selo de desconto.
    if opportunity.source != "grupos" and discount_of(opportunity)[0] is None and not (opportunity.coupon_code or "").strip():
        return False
    if opportunity.affiliate_status not in AFFILIATE_OK:
        return False
    if opportunity.acceptance_score < settings.storefront_min_score:
        return False
    return destination_of(opportunity) is not None


def _apply_snapshot(
    deal: PublishedDeal,
    opportunity: Opportunity,
    *,
    now: datetime,
    ttl: timedelta,
    clicks_7d: int = 0,
    orders_30d: int = 0,
    trends: list[str] | None = None,
) -> None:
    deal.product_id = opportunity.product_id
    deal.source = opportunity.source
    deal.store = store_of(opportunity)
    deal.product_name = opportunity.product_name
    deal.merchant = opportunity.merchant or STORE_LABELS.get(deal.store)
    # O nome do produto no título decide; a categoria oficial do ML entra quando o título não diz.
    deal.category = infer_category(opportunity.product_name, opportunity.category, opportunity.official_category)
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
    deal.price_max = opportunity.price_max if opportunity.price_max and opportunity.price_max > deal.current_price else None
    deal.sales_count = opportunity.sales_count
    deal.rating = opportunity.rating
    deal.best_seller = opportunity.best_seller
    deal.free_shipping = opportunity.free_shipping
    deal.price_condition = opportunity.price_condition
    deal.regular_price = (
        opportunity.regular_price
        if opportunity.price_condition and opportunity.regular_price and opportunity.regular_price > deal.current_price
        else None
    )
    deal.gallery = opportunity.gallery or None
    deal.rank_position = opportunity.rank_position
    deal.rank_category = opportunity.rank_category if opportunity.rank_position else None
    deal.rank_category_id = opportunity.rank_category_id if opportunity.rank_position else None
    deal.trending = trend_of(opportunity.product_name, trends or []) is not None
    deal.clicks_7d = clicks_7d
    deal.orders_30d = orders_30d
    deal.demand_score = demand_score_of(
        sales=opportunity.sales_count,
        rating=opportunity.rating,
        discount=deal.discount_pct,
        commission=opportunity.commission_value,
        best_seller=opportunity.best_seller,
        clicks_7d=clicks_7d,
        orders_30d=orders_30d,
        trending=deal.trending,
        rank_position=deal.rank_position,
    )
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
    community_ttl = timedelta(hours=max(1, settings.community_ttl_hours))
    eligible = [item for item in opportunities if qualifies(item, settings)
                and (item.fetched_at or item.analyzed_at or item.updated_at or moment)
                + (community_ttl if item.source == "grupos" else ttl) > moment]
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
    clicks = await _recent_clicks(session, since=moment - timedelta(days=7))
    orders = await _recent_orders(session, eligible, since=moment - timedelta(days=30))
    trends = load_trends()
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
        _apply_snapshot(
            deal,
            opportunity,
            now=moment,
            ttl=community_ttl if opportunity.source == "grupos" else ttl,
            # Cliques do site usam o id do deal; os do Telegram, o id da oportunidade.
            clicks_7d=clicks.get(deal.id or "", 0) + clicks.get(opportunity.id, 0),
            orders_30d=orders.get(opportunity.id, 0),
            trends=trends,
        )

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


async def _recent_clicks(session: AsyncSession, *, since: datetime) -> dict[str, int]:
    rows = await session.execute(
        select(DealClick.deal_id, func.count()).where(DealClick.clicked_at >= since).group_by(DealClick.deal_id)
    )
    return {deal_id: count for deal_id, count in rows.all()}


async def _recent_orders(session: AsyncSession, eligible: list[Opportunity], *, since: datetime) -> dict[str, int]:
    """Pedidos atribuídos (qualquer status) por oportunidade, casando loja + id nativo do produto."""
    if not eligible:
        return {}
    natives = dict(
        (await session.execute(
            select(Product.id, Product.native_product_id).where(Product.id.in_({o.product_id for o in eligible}))
        )).all()
    )
    rows = await session.execute(
        select(AffiliateConversion.store, AffiliateConversion.item_id, func.count(func.distinct(AffiliateConversion.order_id)))
        .where(AffiliateConversion.purchased_at >= since)
        .group_by(AffiliateConversion.store, AffiliateConversion.item_id)
    )
    counts = {(store, item): count for store, item, count in rows.all()}
    return {
        o.id: counts.get((store_of(o), natives.get(o.product_id, "")), 0)
        for o in eligible
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
