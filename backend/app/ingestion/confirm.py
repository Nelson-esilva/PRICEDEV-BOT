from __future__ import annotations

from decimal import Decimal

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_purchase_url
from app.ingestion.identity import identity_from_offer
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.mercadolivre import MercadoLivreSource, _discount

log = get_logger("confirm")


async def confirm_marketplace_prices(
    offers: list[NormalizedOffer],
    settings: Settings,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[NormalizedOffer]:
    if not settings.enable_price_confirm:
        return offers
    ml = MercadoLivreSource(settings, client=client)
    confirmed = 0
    attempts = 0
    blocked = 0
    try:
        for offer in offers:
            if confirmed >= settings.price_confirm_per_poll or attempts >= settings.price_confirm_per_poll:
                break
            if blocked >= 2:
                log.warning("confirm_ml_aborted", reason="api_bloqueada")
                break
            if offer.price_verified:
                continue
            marketplace, native, _, _, _ = identity_from_offer(offer)
            if marketplace != "mercadolivre" or not native.startswith("MLB"):
                continue
            attempts += 1
            try:
                item = await ml.fetch_item(native)
            except Exception as exc:
                log.warning("confirm_ml_skip", native=native, error=str(exc))
                blocked += 1
                continue
            if not item:
                blocked += 1
                continue
            blocked = 0
            official = money(item.get("price"))
            if official is None:
                continue
            original = money(item.get("original_price"))
            if offer.effective_price is None or offer.effective_price <= 0:
                offer.effective_price = official
                offer.reported_price = official
            offer.verified_price = official
            offer.listed_price = original or offer.listed_price or official
            offer.price_verified = True
            offer.identity_confidence = IdentityConfidence.HIGH
            offer.native_product_id = native
            offer.marketplace = "mercadolivre"
            permalink = sanitize_purchase_url(item.get("permalink"))
            if permalink and not offer.purchase_url:
                offer.purchase_url = permalink
            if offer.announced_discount_pct is None:
                offer.announced_discount_pct = _discount(official, original)
            confirmed += 1
    finally:
        if client is None:
            await ml.close()
    if confirmed:
        log.info("confirm_ml_ok", confirmed=confirmed)
    return offers


def prices_close(left: Decimal | None, right: Decimal | None, *, pct: float = 5) -> bool:
    if left is None or right is None or right == 0:
        return False
    return abs(left - right) / right * 100 <= pct
