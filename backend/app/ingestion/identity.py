from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from app.schemas.normalized import IdentityConfidence, NormalizedOffer

_SHOPEE_ITEM = re.compile(r"(?:i\.|/product/)(\d+)\.(\d+)", re.I)
_AMAZON_ASIN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})", re.I)
_MLB = re.compile(r"(MLB-?\d{8,})", re.I)


def extract_native_id(url: str | None, marketplace: str) -> str | None:
    if not url:
        return None
    path = urlparse(url).path or url
    if marketplace in {"shopee", "shopee.com.br"}:
        match = _SHOPEE_ITEM.search(url)
        if match:
            return match.group(2)
    if "amazon" in marketplace or "amazon." in (urlparse(url).hostname or ""):
        match = _AMAZON_ASIN.search(path)
        if match:
            return match.group(1).upper()
    if marketplace in {"mercadolivre", "mercadolivre.com.br", "mlb"}:
        match = _MLB.search(url)
        if match:
            return match.group(1).replace("-", "").upper()
    return None


def infer_marketplace(url: str | None, fallback: str) -> str:
    if not url:
        return fallback
    host = (urlparse(url).hostname or "").lower()
    if "shopee.com" in host:
        return "shopee"
    if "amazon." in host:
        return "amazon"
    if "mercadolivre.com" in host or "mercadolivre.com.br" in host:
        return "mercadolivre"
    if "kabum.com" in host:
        return "kabum"
    if "magazineluiza.com" in host or "magalu.com" in host:
        return "magalu"
    if "netshoes.com" in host:
        return "netshoes"
    return fallback or host


def identity_from_offer(offer: NormalizedOffer) -> tuple[str, str, str, str, IdentityConfidence]:
    marketplace = offer.marketplace
    native = offer.native_product_id
    variant = offer.variant_id or ""
    merchant = offer.merchant_id or ""
    confidence = offer.identity_confidence

    extracted = extract_native_id(offer.purchase_url, marketplace)
    if extracted and (not native or native.startswith("tmp-") or confidence is IdentityConfidence.PROVISIONAL):
        native = extracted
        confidence = IdentityConfidence.MEDIUM

    if not native:
        basis = f"{marketplace}|{merchant}|{offer.product_name.strip().lower()}"
        digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
        native = f"tmp-{digest}"
        confidence = IdentityConfidence.PROVISIONAL

    return marketplace, native, variant, merchant, confidence
