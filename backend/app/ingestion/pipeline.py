from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.affiliates.resolver import resolve_links
from app.history.stats import compute_history_stats
from app.ingestion.identity import identity_from_offer
from app.models.entities import Opportunity, PriceObservation, Product, SourceMetricSample
from app.pricing.crowd import crowd_signals
from app.pricing.engine import evaluate_offer
from app.pricing.outlier import (
    MAX_HELD_READS,
    REQUIRED_CONFIRMATIONS,
    ReadVerdict,
    classify_read,
    reads_agree,
)
from app.schemas.normalized import Classification, NormalizedOffer

log = get_logger("ingestion")


class OutlierRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class IngestionResult:
    def __init__(self) -> None:
        self.received = 0
        self.created = 0
        self.duplicates = 0
        self.rejected = 0
        self.provisional = 0
        self.historically_validated = 0
        self.opportunities: list[Opportunity] = []


def _bucket(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def _hub_reason_tags(offer: NormalizedOffer) -> list[str]:
    if offer.source != "mlhub":
        return []
    signals = offer.community_signals or {}
    tags: list[str] = []
    if signals.get("hub_extra"):
        tags.append("hub_extra")
    if signals.get("hub_best"):
        tags.append("hub_best")
    for name in signals.get("hub_categories") or []:
        label = str(name).strip()
        if label:
            tags.append(f"hub_cat:{label}")
    return tags


def _display_fields(offer: NormalizedOffer) -> dict:
    return {
        "image_url": sanitize_media_url(offer.image_url),
        "description": offer.description,
        "coupon_code": offer.coupon_code,
        "payment_hint": offer.payment_hint,
        "temperature": offer.temperature,
        "free_shipping": offer.free_shipping,
        "comment_count": offer.comment_count,
        "announced_discount_pct": offer.announced_discount_pct,
    }


async def _refresh_display(
    session: AsyncSession,
    offer: NormalizedOffer,
    settings: Settings,
    *,
    marketplace: str,
    native_id: str,
    variant_id: str,
    merchant_id: str,
    at: datetime,
) -> None:
    product = (
        await session.execute(
            select(Product).where(
                Product.marketplace == marketplace,
                Product.native_product_id == native_id,
                Product.variant_id == variant_id,
                Product.merchant_id == merchant_id,
            )
        )
    ).scalar_one_or_none()
    opportunity = None
    if product is not None:
        opportunity = (
            await session.execute(select(Opportunity).where(Opportunity.product_id == product.id))
        ).scalar_one_or_none()
    if opportunity is None:
        observation = (
            await session.execute(
                select(PriceObservation)
                .where(
                    PriceObservation.source == offer.source,
                    PriceObservation.source_record_id == offer.source_record_id,
                )
                .order_by(PriceObservation.observed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if observation is None:
            return
        opportunity = (
            await session.execute(select(Opportunity).where(Opportunity.product_id == observation.product_id))
        ).scalar_one_or_none()
        if opportunity is None:
            return
    for key, value in _display_fields(offer).items():
        if value is not None:
            setattr(opportunity, key, value)
    if offer.product_name:
        opportunity.product_name = offer.product_name
    opportunity.current_price = offer.effective_price
    opportunity.fetched_at = offer.fetched_at or at
    opportunity.ingested_at = at
    if offer.purchase_url:
        links = await resolve_links(
            original_url=offer.purchase_url,
            existing_affiliate=offer.affiliate_url,
            settings=settings,
        )
        opportunity.original_purchase_url = links.original
        opportunity.validated_purchase_url = links.validated
        opportunity.affiliate_url = links.affiliate
        opportunity.final_purchase_url = links.final
        opportunity.affiliate_network = links.network
        opportunity.affiliate_status = links.status
    if offer.merchant_name:
        opportunity.merchant = offer.merchant_name
    if offer.source == "mlhub":
        if offer.category:
            opportunity.category = offer.category
        tags = _hub_reason_tags(offer)
        if tags:
            reasons = list(opportunity.reasons or [])
            for tag in tags:
                if tag not in reasons:
                    reasons.append(tag)
            opportunity.reasons = reasons


def _effective(offer: NormalizedOffer) -> Decimal:
    value = offer.effective_price
    if offer.coupon_value:
        value = value - offer.coupon_value
    if offer.shipping_cost:
        value = value + offer.shipping_cost
    quantized = money(value)
    if quantized is None:
        raise ValueError("invalid effective price")
    return quantized


async def ingest_offers(
    session: AsyncSession,
    offers: list[NormalizedOffer],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> IngestionResult:
    moment = now or utcnow()
    result = IngestionResult()
    total = len(offers)
    for index, offer in enumerate(offers):
        stamp = moment + timedelta(microseconds=total - index)
        result.received += 1
        try:
            opportunity = await _ingest_one(session, offer, settings, stamp)
        except OutlierRejected:
            result.rejected += 1
            continue
        except Exception:
            log.exception("ingest_failed", source=offer.source, record=offer.source_record_id)
            result.rejected += 1
            continue
        if opportunity is None:
            result.duplicates += 1
            continue
        result.created += 1
        result.opportunities.append(opportunity)
        if opportunity.classification == Classification.PROVISIONAL:
            result.provisional += 1
        elif opportunity.classification in {
            Classification.HISTORICALLY_VALIDATED,
            Classification.PRICE_ANOMALY_CANDIDATE,
        }:
            result.historically_validated += 1
        elif opportunity.classification == Classification.REJECTED:
            result.rejected += 1
    await session.commit()
    return result


async def _ingest_one(
    session: AsyncSession,
    offer: NormalizedOffer,
    settings: Settings,
    now: datetime,
) -> Opportunity | None:
    offer = offer.quantized()
    offer.purchase_url = sanitize_purchase_url(offer.purchase_url)
    offer.affiliate_url = sanitize_purchase_url(offer.affiliate_url)
    offer.image_url = sanitize_media_url(offer.image_url)
    marketplace, native_id, variant_id, merchant_id, confidence = identity_from_offer(offer)
    offer.identity_confidence = confidence
    offer.marketplace = marketplace
    offer.native_product_id = native_id
    offer.variant_id = variant_id
    offer.merchant_id = merchant_id
    effective = _effective(offer)
    observed_at = offer.fetched_at or now
    bucket = _bucket(observed_at)

    existing = await session.execute(
        select(PriceObservation).where(
            PriceObservation.source == offer.source,
            PriceObservation.source_record_id == offer.source_record_id,
            PriceObservation.effective_price == effective,
            PriceObservation.observed_bucket == bucket,
        )
    )
    if existing.scalar_one_or_none():
        await _refresh_display(
            session,
            offer,
            settings,
            marketplace=marketplace,
            native_id=native_id,
            variant_id=variant_id,
            merchant_id=merchant_id,
            at=now,
        )
        return None

    latest = (
        await session.execute(
            select(PriceObservation)
            .where(
                PriceObservation.source == offer.source,
                PriceObservation.native_product_id == native_id,
                PriceObservation.marketplace == marketplace,
                PriceObservation.variant_id == variant_id,
                PriceObservation.merchant_id == merchant_id,
            )
            .order_by(PriceObservation.observed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest and latest.effective_price == effective:
        if latest.observed_at.date() == observed_at.date():
            await _refresh_display(
                session,
                offer,
                settings,
                marketplace=marketplace,
                native_id=native_id,
                variant_id=variant_id,
                merchant_id=merchant_id,
                at=now,
            )
            return None

    product = (
        await session.execute(
            select(Product).where(
                Product.marketplace == marketplace,
                Product.native_product_id == native_id,
                Product.variant_id == variant_id,
                Product.merchant_id == merchant_id,
            )
        )
    ).scalar_one_or_none()
    if product is None:
        product = Product(
            marketplace=marketplace,
            native_product_id=native_id,
            variant_id=variant_id,
            merchant_id=merchant_id,
            identity_confidence=confidence.value,
            product_name=offer.product_name,
            brand=offer.brand,
            model=offer.model,
            variant=offer.variant,
            condition=offer.condition,
            category=offer.category,
            merchant_name=offer.merchant_name,
        )
        session.add(product)
        await session.flush()
    else:
        product.product_name = offer.product_name
        product.identity_confidence = confidence.value
        product.merchant_name = offer.merchant_name or product.merchant_name
        product.category = offer.category or product.category
        product.condition = offer.condition or product.condition

    stats_before = await compute_history_stats(
        session,
        product_id=product.id,
        exclude_observation_id=None,
        window_days=settings.history_window_days,
        now=now,
        currency=offer.currency,
        condition=offer.condition,
    )
    allow_zero = bool(offer.coupon_code) or (offer.category or "") in {"games", "gratis", "free"}
    decision = classify_read(effective, list(stats_before.sample_prices), allow_zero=allow_zero)
    if decision.verdict is ReadVerdict.REJECT:
        log.warning(
            "outlier_reject",
            source=offer.source,
            native=native_id,
            price=str(effective),
            reason=decision.reason,
        )
        await _touch_opportunity_risk(session, product, offer, decision.reason)
        raise OutlierRejected(decision.reason)
    if decision.verdict is ReadVerdict.CONFIRM:
        held = product.held_price
        if held is not None and reads_agree(held, effective):
            product.held_count = (product.held_count or 0) + 1
        else:
            product.held_price = effective
            product.held_count = (product.held_count or 0) + 1
        if product.held_count < REQUIRED_CONFIRMATIONS and product.held_count < MAX_HELD_READS:
            log.info(
                "outlier_hold",
                source=offer.source,
                native=native_id,
                price=str(effective),
                held=product.held_count,
            )
            await _touch_opportunity_risk(
                session,
                product,
                offer,
                f"{decision.reason} ({product.held_count}/{REQUIRED_CONFIRMATIONS})",
            )
            return None
        product.held_price = None
        product.held_count = 0
    else:
        product.held_price = None
        product.held_count = 0

    observation = PriceObservation(
        product_id=product.id,
        source=offer.source,
        source_record_id=offer.source_record_id,
        marketplace=marketplace,
        merchant_id=merchant_id,
        native_product_id=native_id,
        variant_id=variant_id,
        offer_id=offer.offer_id,
        product_name=offer.product_name,
        brand=offer.brand,
        model=offer.model,
        variant=offer.variant,
        condition=offer.condition,
        price_type="verified" if offer.price_verified else "reported",
        listed_price=offer.listed_price,
        reported_price=offer.reported_price,
        verified_price=offer.verified_price,
        coupon_value=offer.coupon_value,
        shipping_cost=offer.shipping_cost,
        effective_price=effective,
        currency=offer.currency,
        availability=offer.availability,
        source_timestamp=offer.source_created_at,
        observed_at=observed_at,
        observed_bucket=bucket,
        fetched_at=offer.fetched_at,
        ingested_at=now,
        purchase_url=offer.purchase_url,
        affiliate_url=offer.affiliate_url,
        temperature=offer.temperature,
        announced_discount_pct=offer.announced_discount_pct,
        is_inferred=offer.is_inferred,
        price_verified=offer.price_verified,
        raw_payload=offer.raw_payload,
    )
    session.add(observation)
    await session.flush()

    stats = await compute_history_stats(
        session,
        product_id=product.id,
        exclude_observation_id=observation.id,
        window_days=settings.history_window_days,
        now=now,
        currency=offer.currency,
        condition=offer.condition,
    )
    engine = evaluate_offer(offer, stats, settings, now=now)
    extra_reasons, extra_risks = crowd_signals(offer, now=now)
    extra_reasons.extend(_hub_reason_tags(offer))
    engine.reasons.extend(extra_reasons)
    engine.risks.extend(extra_risks)
    links = await resolve_links(
        original_url=offer.purchase_url,
        existing_affiliate=offer.affiliate_url,
        settings=settings,
    )
    analyzed_at = utcnow()
    confirmed_at = analyzed_at if engine.confirmed else None

    opportunity = (
        await session.execute(select(Opportunity).where(Opportunity.product_id == product.id))
    ).scalar_one_or_none()
    payload = dict(
        observation_id=observation.id,
        classification=engine.classification.value,
        status="expired" if engine.classification is Classification.EXPIRED else "active",
        current_price=effective,
        currency=offer.currency,
        historical_median=stats.median,
        historical_minimum=stats.minimum,
        historical_mean=stats.mean,
        historical_discount_pct=engine.historical_discount_pct,
        discount_vs_minimum_pct=engine.discount_vs_minimum_pct,
        discount_vs_previous_pct=engine.discount_vs_previous_pct,
        distance_to_min_pct=engine.distance_to_min_pct,
        acceptance_score=engine.acceptance_score,
        score_breakdown=engine.score_breakdown,
        history_confidence=engine.history_confidence.value,
        price_verified=offer.price_verified,
        history_observations=stats.observations,
        history_distinct_days=stats.distinct_days,
        reasons=engine.reasons,
        risks=engine.risks,
        source=offer.source,
        merchant=offer.merchant_name,
        category=offer.category,
        product_name=offer.product_name,
        **_display_fields(offer),
        original_purchase_url=links.original,
        validated_purchase_url=links.validated,
        affiliate_url=links.affiliate,
        final_purchase_url=links.final,
        affiliate_network=links.network,
        affiliate_status=links.status,
        source_created_at=offer.source_created_at,
        source_updated_at=offer.source_updated_at,
        fetched_at=offer.fetched_at,
        ingested_at=observation.ingested_at,
        analyzed_at=analyzed_at,
        confirmed_at=confirmed_at,
    )
    if opportunity is None:
        opportunity = Opportunity(
            product_id=product.id,
            detected_at=now,
            updated_at=now,
            **payload,
        )
        session.add(opportunity)
    else:
        keep_hub = opportunity.source == "mlhub" and offer.source != "mlhub"
        for key, value in payload.items():
            if keep_hub and key in {"source", "category"}:
                continue
            setattr(opportunity, key, value)
    await session.flush()

    source_latency = None
    if offer.source_created_at:
        source_latency = (observation.ingested_at - offer.source_created_at).total_seconds()
    processing = (analyzed_at - observation.ingested_at).total_seconds()
    total = None
    if offer.source_created_at:
        total = (analyzed_at - offer.source_created_at).total_seconds()
    session.add(
        SourceMetricSample(
            source=offer.source,
            source_latency_seconds=source_latency,
            processing_latency_seconds=processing,
            total_observable_latency_seconds=total,
            within_slo=total is not None and total <= settings.slo_seconds,
        )
    )
    return opportunity


async def _touch_opportunity_risk(
    session: AsyncSession,
    product: Product,
    offer: NormalizedOffer,
    reason: str,
) -> None:
    opportunity = (
        await session.execute(select(Opportunity).where(Opportunity.product_id == product.id))
    ).scalar_one_or_none()
    if opportunity is None:
        return
    risks = list(opportunity.risks or [])
    if reason not in risks:
        risks.append(reason)
        opportunity.risks = risks
    if offer.product_name:
        opportunity.product_name = offer.product_name
    for key, value in _display_fields(offer).items():
        if value is not None:
            setattr(opportunity, key, value)
