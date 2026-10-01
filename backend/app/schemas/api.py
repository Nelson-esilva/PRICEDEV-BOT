from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    product_id: str
    product: str = Field(validation_alias="product_name")
    merchant: str | None
    source: str
    category: str | None = None
    current_price: Decimal
    currency: str
    historical_median: Decimal | None
    historical_minimum: Decimal | None
    historical_mean: Decimal | None = None
    historical_discount_pct: Decimal | None
    discount_vs_minimum_pct: Decimal | None = None
    discount_vs_previous_pct: Decimal | None = None
    distance_to_min_pct: Decimal | None = None
    acceptance_score: int
    classification: str
    status: str
    price_verified: bool
    history_confidence: str
    history_observations: int
    history_distinct_days: int
    purchase_url: str | None = Field(validation_alias="final_purchase_url")
    original_purchase_url: str | None = None
    validated_purchase_url: str | None = None
    affiliate_url: str | None
    image_url: str | None = None
    description: str | None = None
    coupon_code: str | None = None
    temperature: int | None = None
    free_shipping: bool | None = None
    comment_count: int | None = None
    announced_discount_pct: Decimal | None = None
    affiliate_network: str | None = None
    affiliate_status: str
    observed_at: datetime | None = Field(validation_alias="detected_at")
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    fetched_at: datetime | None = None
    ingested_at: datetime | None = None
    analyzed_at: datetime | None = None
    confirmed_at: datetime | None = None
    published_at: datetime | None = None
    score_breakdown: dict
    reasons: list = Field(default_factory=list)
    risks: list = Field(default_factory=list)

    @field_serializer(
        "current_price",
        "historical_median",
        "historical_minimum",
        "historical_mean",
        "historical_discount_pct",
        "discount_vs_minimum_pct",
        "discount_vs_previous_pct",
        "distance_to_min_pct",
        "announced_discount_pct",
    )
    def serialize_decimal(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class OpportunityListOut(BaseModel):
    items: list[OpportunityOut]
    total: int


class PricePointOut(BaseModel):
    observed_at: datetime
    effective_price: Decimal
    currency: str
    source: str
    price_verified: bool
    is_inferred: bool


class PriceStatisticsOut(BaseModel):
    window_days: int
    observations: int
    distinct_days: int
    coverage_days: int | None
    median: Decimal | None
    minimum: Decimal | None
    mean: Decimal | None
    last_price: Decimal | None
    previous_price: Decimal | None
    currency: str | None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    marketplace: str
    native_product_id: str
    variant_id: str
    merchant_id: str
    identity_confidence: str
    product_name: str
    merchant_name: str | None
    condition: str
    category: str | None


class SourceStatusOut(BaseModel):
    source: str
    enabled: bool
    configured: bool
    last_poll_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    circuit_open_until: datetime | None
    requests_total: int
    requests_failed: int
    rate_limit_events: int
    offers_received: int
    offers_new: int
    offers_duplicate: int
    offers_provisional: int
    offers_historically_validated: int
    offers_rejected: int
    poll_seconds: int
    metrics: dict = Field(default_factory=dict)


class HealthOut(BaseModel):
    status: str
    env: str
    database: str
