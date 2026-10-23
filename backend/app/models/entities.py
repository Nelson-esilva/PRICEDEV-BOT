from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime, utcnow

Money = Numeric(14, 2)


def _uuid() -> str:
    return str(uuid.uuid4())


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "marketplace",
            "native_product_id",
            "variant_id",
            "merchant_id",
            name="uq_product_identity",
        ),
        Index("ix_products_marketplace_native", "marketplace", "native_product_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    native_product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    identity_confidence: Mapped[str] = mapped_column(String(32), default="LOW", nullable=False)
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    variant: Mapped[str | None] = mapped_column(String(128))
    condition: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    category: Mapped[str | None] = mapped_column(String(128))
    merchant_name: Mapped[str | None] = mapped_column(String(256))
    held_price: Mapped[Decimal | None] = mapped_column(Money)
    held_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    observations: Mapped[list[PriceObservation]] = relationship(back_populates="product")
    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="product")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        Index("ix_obs_product_observed", "product_id", "observed_at"),
        Index("ix_obs_source_record", "source", "source_record_id"),
        UniqueConstraint(
            "source",
            "source_record_id",
            "effective_price",
            "observed_bucket",
            name="uq_obs_idempotent",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(256), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    native_product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    variant_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    offer_id: Mapped[str | None] = mapped_column(String(128))
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(128))
    variant: Mapped[str | None] = mapped_column(String(128))
    condition: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    price_type: Mapped[str] = mapped_column(String(32), default="listed", nullable=False)
    listed_price: Mapped[Decimal | None] = mapped_column(Money)
    reported_price: Mapped[Decimal | None] = mapped_column(Money)
    verified_price: Mapped[Decimal | None] = mapped_column(Money)
    coupon_value: Mapped[Decimal | None] = mapped_column(Money)
    shipping_cost: Mapped[Decimal | None] = mapped_column(Money)
    effective_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="BRL", nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(UTCDateTime)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    observed_bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    purchase_url: Mapped[str | None] = mapped_column(Text)
    affiliate_url: Mapped[str | None] = mapped_column(Text)
    temperature: Mapped[int | None] = mapped_column(Integer)
    announced_discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    is_inferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)

    product: Mapped[Product] = relationship(back_populates="observations")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opp_detected", "detected_at"),
        Index("ix_opp_class_status", "classification", "status"),
        UniqueConstraint("product_id", name="uq_opp_product_latest"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    observation_id: Mapped[str] = mapped_column(ForeignKey("price_observations.id"), nullable=False)
    classification: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="BRL", nullable=False)
    historical_median: Mapped[Decimal | None] = mapped_column(Money)
    historical_minimum: Mapped[Decimal | None] = mapped_column(Money)
    historical_mean: Mapped[Decimal | None] = mapped_column(Money)
    historical_discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    discount_vs_minimum_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    discount_vs_previous_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    distance_to_min_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    acceptance_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    history_confidence: Mapped[str] = mapped_column(String(32), default="NONE", nullable=False)
    price_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    history_observations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    history_distinct_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(256))
    category: Mapped[str | None] = mapped_column(String(128))
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    coupon_code: Mapped[str | None] = mapped_column(String(128))
    payment_hint: Mapped[str | None] = mapped_column(String(64))
    temperature: Mapped[int | None] = mapped_column(Integer)
    free_shipping: Mapped[bool | None] = mapped_column(Boolean)
    comment_count: Mapped[int | None] = mapped_column(Integer)
    announced_discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    listed_price: Mapped[Decimal | None] = mapped_column(Money)
    price_max: Mapped[Decimal | None] = mapped_column(Money)
    sales_count: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    commission_value: Mapped[Decimal | None] = mapped_column(Money)
    best_seller: Mapped[bool | None] = mapped_column(Boolean)
    price_condition: Mapped[str | None] = mapped_column(String(16))
    regular_price: Mapped[Decimal | None] = mapped_column(Money)
    catalog_product_id: Mapped[str | None] = mapped_column(String(32))
    gallery: Mapped[list | None] = mapped_column(JSON)
    rank_position: Mapped[int | None] = mapped_column(Integer)
    rank_category: Mapped[str | None] = mapped_column(String(120))
    rank_category_id: Mapped[str | None] = mapped_column(String(32))
    official_category: Mapped[str | None] = mapped_column(String(32))
    enriched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    original_purchase_url: Mapped[str | None] = mapped_column(Text)
    validated_purchase_url: Mapped[str | None] = mapped_column(Text)
    affiliate_url: Mapped[str | None] = mapped_column(Text)
    final_purchase_url: Mapped[str | None] = mapped_column(Text)
    affiliate_network: Mapped[str | None] = mapped_column(String(64))
    affiliate_status: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    source_created_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ingested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    analyzed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    product: Mapped[Product] = relationship(back_populates="opportunities")


class SourceCheckpoint(Base):
    __tablename__ = "source_checkpoints"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_poll_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    circuit_open_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    requests_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rate_limit_events: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_provisional: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_historically_validated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    offers_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SourceMetricSample(Base):
    __tablename__ = "source_metric_samples"
    __table_args__ = (Index("ix_metrics_source_at", "source", "recorded_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    source_latency_seconds: Mapped[float | None] = mapped_column()
    processing_latency_seconds: Mapped[float | None] = mapped_column()
    total_observable_latency_seconds: Mapped[float | None] = mapped_column()
    within_slo: Mapped[bool | None] = mapped_column(Boolean)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("url", name="uq_watchlist_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    native_product_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(512))
    target_price: Mapped[Decimal | None] = mapped_column(Money)
    last_price: Mapped[Decimal | None] = mapped_column(Money)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class InboxMessage(Base):
    """Post de grupo Telegram/WhatsApp. Não entra na vitrine de ofertas."""

    __tablename__ = "inbox_messages"
    __table_args__ = (
        UniqueConstraint("channel", "chat_id", "message_id", name="uq_inbox_message"),
        Index("ix_inbox_posted", "posted_at"),
        Index("ix_inbox_identity", "marketplace", "native_product_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chat_title: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    purchase_url: Mapped[str | None] = mapped_column(Text)
    marketplace: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    native_product_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    affiliate_url: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)


class PublicationLog(Base):
    __tablename__ = "publication_logs"
    __table_args__ = (
        UniqueConstraint("channel", "dedup_key", name="uq_pub_dedup"),
        Index("ix_pub_opportunity", "opportunity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    opportunity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    skipped_reason: Mapped[str | None] = mapped_column(String(128))
    body: Mapped[str | None] = mapped_column(Text)


class PublishedDeal(Base):
    """Snapshot aprovado para a vitrine pública. Sem FK para overviver à retenção do ops."""

    __tablename__ = "published_deals"
    __table_args__ = (
        UniqueConstraint("opportunity_id", name="uq_published_opportunity"),
        UniqueConstraint("slug", name="uq_published_slug"),
        Index("ix_published_status_updated", "status", "updated_at"),
        Index("ix_published_store", "store", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    opportunity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    store: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(256))
    category: Mapped[str | None] = mapped_column(String(128))
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    coupon_code: Mapped[str | None] = mapped_column(String(128))
    payment_hint: Mapped[str | None] = mapped_column(String(64))
    current_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    list_price: Mapped[Decimal | None] = mapped_column(Money)
    announced_discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    discount_basis: Mapped[str | None] = mapped_column(String(32))
    acceptance_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    price_max: Mapped[Decimal | None] = mapped_column(Money)
    sales_count: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    best_seller: Mapped[bool | None] = mapped_column(Boolean)
    free_shipping: Mapped[bool | None] = mapped_column(Boolean)
    price_condition: Mapped[str | None] = mapped_column(String(16))
    regular_price: Mapped[Decimal | None] = mapped_column(Money)
    gallery: Mapped[list | None] = mapped_column(JSON)
    rank_position: Mapped[int | None] = mapped_column(Integer)
    rank_category: Mapped[str | None] = mapped_column(String(120))
    rank_category_id: Mapped[str | None] = mapped_column(String(32))
    trending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    orders_30d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks_7d: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    demand_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="BRL", nullable=False)
    affiliate_network: Mapped[str | None] = mapped_column(String(64))
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    expired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class DealClick(Base):
    __tablename__ = "deal_clicks"
    __table_args__ = (Index("ix_clicks_deal_at", "deal_id", "clicked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    deal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    store: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(256))
    referer: Mapped[str | None] = mapped_column(String(512))
    channel: Mapped[str] = mapped_column(String(16), default="site", nullable=False)
    clicked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class TrackedLink(Base):
    """Link curto /go/t/<id> dos posts do Telegram. Fora da retenção: posts antigos continuam funcionando."""

    __tablename__ = "tracked_links"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    opportunity_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    store: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="telegram", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AffiliateConversion(Base):
    """Item de pedido atribuído ao afiliado (relatório de conversões da loja)."""

    __tablename__ = "affiliate_conversions"
    __table_args__ = (
        UniqueConstraint("store", "order_id", "item_id", name="uq_conversion_order_item"),
        Index("ix_conversion_item_time", "store", "item_id", "purchased_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    store: Mapped[str] = mapped_column(String(32), nullable=False)
    conversion_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    item_name: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Money)
    commission: Mapped[Decimal | None] = mapped_column(Money)
    sub_ids: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class PublicPromotion(Base):
    """Campanha/cupom independente do histórico de preços e da retenção do ops."""

    __tablename__ = "public_promotions"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_public_promotion_external"),
        Index("ix_promotion_store_kind", "store", "kind", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    store: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(String(128))
    image_url: Mapped[str | None] = mapped_column(Text)
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
