"""Leitura de Product/Offer em JSON-LD — recorte adaptado de bernalli (MIT)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.money import money

_LD = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_PRODUCT_TYPES = {"product", "productgroup"}
_FINANCE_HINTS = ("installment", "financing", "monthly", "subscription", "recurring")


@dataclass
class JsonLdProduct:
    name: str | None
    price: Decimal | None
    currency: str
    image: str | None
    availability: str
    raw: dict


def parse_jsonld_product(html: str) -> JsonLdProduct | None:
    for match in _LD.finditer(html or ""):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        product = _first_product(_flatten(payload))
        if product:
            return product
    return None


def _flatten(node: Any, found: list[dict] | None = None, *, depth: int = 0) -> list[dict]:
    found = found if found is not None else []
    if depth > 12 or len(found) > 80:
        return found
    if isinstance(node, list):
        for item in node:
            _flatten(item, found, depth=depth + 1)
        return found
    if not isinstance(node, dict):
        return found
    found.append(node)
    if "@graph" in node:
        _flatten(node.get("@graph"), found, depth=depth + 1)
    if str(node.get("@type") or "").endswith("Action"):
        _flatten(node.get("object"), found, depth=depth + 1)
    return found


def _types_of(node: dict) -> set[str]:
    raw = node.get("@type") or ""
    if isinstance(raw, list):
        return {str(item).split("/")[-1].lower() for item in raw}
    return {str(raw).split("/")[-1].lower()}


def _first_product(nodes: list[dict]) -> JsonLdProduct | None:
    for node in nodes:
        if not (_types_of(node) & _PRODUCT_TYPES):
            continue
        offers = node.get("offers")
        price, currency, availability = _offer_price(offers)
        if price is None:
            continue
        image = node.get("image")
        if isinstance(image, list) and image:
            image = image[0]
        if isinstance(image, dict):
            image = image.get("url") or image.get("contentUrl")
        return JsonLdProduct(
            name=str(node.get("name") or node.get("title") or "") or None,
            price=price,
            currency=currency,
            image=str(image) if image else None,
            availability=availability,
            raw={"name": node.get("name"), "sku": node.get("sku"), "gtin": node.get("gtin13") or node.get("gtin")},
        )
    return None


def _offer_price(offers: Any) -> tuple[Decimal | None, str, str]:
    rows: list[dict]
    if isinstance(offers, dict):
        rows = [offers]
    elif isinstance(offers, list):
        rows = [row for row in offers if isinstance(row, dict)]
    else:
        return None, "BRL", "unknown"
    best: Decimal | None = None
    currency = "BRL"
    availability = "unknown"
    in_stock = False
    out = False
    for row in rows:
        blob = " ".join(str(row.get(key) or "") for key in ("@type", "name", "priceType")).lower()
        if any(hint in blob for hint in _FINANCE_HINTS):
            continue
        parsed = money(row.get("price"))
        if parsed is None:
            continue
        if best is None or parsed > best:
            best = parsed
            currency = str(row.get("priceCurrency") or "BRL")
        avail = str(row.get("availability") or "").lower()
        if avail.endswith("instock"):
            in_stock = True
        if avail.endswith("outofstock") or avail.endswith("soldout"):
            out = True
    if in_stock:
        availability = "in_stock"
    elif out:
        availability = "unavailable"
    return best, currency, availability
