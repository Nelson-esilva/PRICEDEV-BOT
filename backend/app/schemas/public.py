from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class PublicDealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    slug: str
    store: str
    product: str = Field(validation_alias="product_name")
    merchant: str | None
    category: str | None
    image_url: str | None
    description: str | None
    coupon_code: str | None
    payment_hint: str | None
    current_price: Decimal
    list_price: Decimal | None
    announced_discount_pct: Decimal | None
    discount_pct: Decimal | None = None
    discount_basis: str | None = None
    price_max: Decimal | None = None
    sales_count: int | None = None
    rating: Decimal | None = None
    best_seller: bool | None = None
    free_shipping: bool | None = None
    price_condition: str | None = None
    regular_price: Decimal | None = None
    gallery: list[str] | None = None
    rank_position: int | None = None
    rank_category: str | None = None
    rank_category_id: str | None = None
    trending: bool = False
    currency: str
    go_path: str = ""
    updated_at: datetime
    expires_at: datetime

    @field_serializer("current_price", "list_price", "announced_discount_pct", "discount_pct", "price_max", "rating", "regular_price")
    def serialize_decimal(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class PublicDealListOut(BaseModel):
    items: list[PublicDealOut]
    total: int
