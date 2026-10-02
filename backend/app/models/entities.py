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
