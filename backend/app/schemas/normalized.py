from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import money


class Classification(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    HISTORICALLY_VALIDATED = "HISTORICALLY_VALIDATED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    PRICE_ANOMALY_CANDIDATE = "PRICE_ANOMALY_CANDIDATE"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class IdentityConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PROVISIONAL = "PROVISIONAL"


class HistoryConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


class NormalizedOffer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    source_record_id: str
    marketplace: str
    merchant_id: str = ""
    merchant_name: str | None = None
    native_product_id: str
    variant_id: str = ""
    offer_id: str | None = None
    product_name: str
    brand: str | None = None
    model: str | None = None
    variant: str | None = None
    condition: str = "unknown"
    category: str | None = None
    listed_price: Decimal | None = None
    reported_price: Decimal | None = None
    verified_price: Decimal | None = None
    coupon_value: Decimal | None = None
    shipping_cost: Decimal | None = None
    effective_price: Decimal
    currency: str = "BRL"
    availability: str = "unknown"
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    fetched_at: datetime
    purchase_url: str | None = None
    affiliate_url: str | None = None
    image_url: str | None = None
    description: str | None = None
    coupon_code: str | None = None
    payment_hint: str | None = None
    free_shipping: bool | None = None
    comment_count: int | None = None
    temperature: int | None = None
    announced_discount_pct: Decimal | None = None
    identity_confidence: IdentityConfidence = IdentityConfidence.LOW
    price_verified: bool = False
    is_inferred: bool = False
    community_signals: dict = Field(default_factory=dict)
    raw_payload: dict = Field(default_factory=dict)

    def quantized(self) -> NormalizedOffer:
        data = self.model_dump()
        for key in (
            "listed_price",
            "reported_price",
            "verified_price",
            "coupon_value",
            "shipping_cost",
            "effective_price",
            "announced_discount_pct",
        ):
            data[key] = money(data[key]) if data[key] is not None else None
        if data["effective_price"] is None:
            raise ValueError("effective_price is required")
        return NormalizedOffer.model_validate(data)
