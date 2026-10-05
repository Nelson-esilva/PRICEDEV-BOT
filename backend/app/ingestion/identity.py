from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlparse

from app.schemas.normalized import IdentityConfidence, NormalizedOffer

_SHOPEE_ITEM = re.compile(r"(?:i\.|/product/)(\d+)[./](\d+)", re.I)
_AMAZON_ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.I)
_AMAZON_QUERY = re.compile(r"(?:^|[?&])asin=([A-Z0-9]{10})", re.I)
_MLB = re.compile(r"(MLB-?\d{8,})", re.I)
_KABUM = re.compile(r"/produto/(\d{3,})", re.I)
_MAGALU = re.compile(r"/p/([a-z0-9]{8,})/?", re.I)
_WEAK_PREFIXES = ("tmp-", "pelando-", "campaign-")
_CANONICAL = {"mercadolivre", "amazon", "shopee", "magalu", "kabum"}


def known_marketplace(url: str | None) -> str | None:
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if "shopee.com" in host:
        return "shopee"
    if "amazon." in host:
        return "amazon"
    if "mercadolivre.com" in host or "mercadolivre.com.br" in host:
        return "mercadolivre"
    if "kabum.com" in host:
        return "kabum"
    if "magazineluiza.com" in host or "magalu.com" in host or "magazinevoce.com" in host:
        return "magalu"
    if "netshoes.com" in host:
        return "netshoes"
    return None


def infer_marketplace(url: str | None, fallback: str) -> str:
    return known_marketplace(url) or fallback or (urlparse(url).hostname if url else "") or "unknown"


def parse_product_url(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return None, None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query)
    haystack = f"{path}?{parsed.query}"

    mlb = _MLB.search(haystack) or _MLB.search(url)
    if mlb or "mercadolivre.com" in host:
        item = query.get("item_id") or query.get("itemId")
        raw = (mlb.group(1) if mlb else None) or (item[0] if item else None)
        if raw:
            return "mercadolivre", raw.replace("-", "").upper()

    if "amazon." in host or _AMAZON_ASIN.search(path):
        match = _AMAZON_ASIN.search(path) or _AMAZON_QUERY.search(url)
        if match:
            return "amazon", match.group(1).upper()

    if "shopee.com" in host or _SHOPEE_ITEM.search(url):
        match = _SHOPEE_ITEM.search(url)
        if match:
            return "shopee", match.group(2)

    if "kabum.com" in host:
        match = _KABUM.search(path)
        if match:
            return "kabum", match.group(1)

    if any(token in host for token in ("magazineluiza.com", "magalu.com", "magazinevoce.com")):
        match = _MAGALU.search(path)
        if match:
            return "magalu", match.group(1).lower()
        sku = query.get("productId") or query.get("sku")
        if sku:
            return "magalu", sku[0]

    market = known_marketplace(url)
    return market, None


def extract_native_id(url: str | None, marketplace: str) -> str | None:
    parsed_market, native = parse_product_url(url)
    if native and (not marketplace or parsed_market == marketplace or parsed_market):
        return native
    if not url:
        return None
    path = urlparse(url).path or url
    if marketplace in {"shopee", "shopee.com.br"}:
        match = _SHOPEE_ITEM.search(url)
        if match:
            return match.group(2)
    if "amazon" in marketplace:
        match = _AMAZON_ASIN.search(path) or _AMAZON_QUERY.search(url)
        if match:
            return match.group(1).upper()
    if marketplace in {"mercadolivre", "mercadolivre.com.br", "mlb"}:
        match = _MLB.search(url)
        if match:
            return match.group(1).replace("-", "").upper()
    if marketplace == "kabum":
        match = _KABUM.search(path)
        if match:
            return match.group(1)
    if marketplace == "magalu":
        match = _MAGALU.search(path)
        if match:
            return match.group(1).lower()
    return None


def _is_weak_native(native: str, confidence: IdentityConfidence) -> bool:
    if not native:
        return True
    if native.startswith(_WEAK_PREFIXES):
        return True
    return confidence in {IdentityConfidence.LOW, IdentityConfidence.PROVISIONAL}


def identity_from_offer(offer: NormalizedOffer) -> tuple[str, str, str, str, IdentityConfidence]:
    marketplace = infer_marketplace(offer.purchase_url, offer.marketplace)
    native = offer.native_product_id
    variant = offer.variant_id or ""
    merchant = offer.merchant_id or ""
    confidence = offer.identity_confidence

    parsed_market, parsed_native = parse_product_url(offer.purchase_url)
    extracted = parsed_native or extract_native_id(offer.purchase_url, marketplace)
    if parsed_market:
        marketplace = parsed_market

    if extracted:
        native = extracted
        confidence = IdentityConfidence.HIGH
        if marketplace in _CANONICAL:
            merchant = ""
    elif _is_weak_native(native, confidence):
        if not native:
            basis = f"{marketplace}|{merchant}|{offer.product_name.strip().lower()}"
            digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
            native = f"tmp-{digest}"
        confidence = IdentityConfidence.PROVISIONAL

    return marketplace, native, variant, merchant, confidence
