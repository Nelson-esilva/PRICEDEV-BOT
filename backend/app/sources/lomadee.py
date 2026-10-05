from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.ingestion.identity import infer_marketplace, parse_product_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector, SourceError
from app.sources.rate import TokenBucket

log = get_logger("lomadee")

API_BASE = "https://api.lomadee.com/v3"


class LomadeeSource(SourceConnector):
    """Rede Lomadee (Americanas, Submarino e lojas parceiras) quando há token."""

    name = "lomadee"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.lomadee_poll_seconds
        self.bucket = TokenBucket(0.5)
        self._client = client
        self._owns_client = client is None

    def is_enabled(self) -> bool:
        return bool(
            self.settings.enable_lomadee
            and self.settings.lomadee_app_token
            and self.settings.lomadee_source_id
        )

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        seen: set[str] = set()
        offers: list[NormalizedOffer] = []
        for keyword in self.settings.discovery_keyword_list[:4]:
            payload = await self.search(keyword)
            for offer in self.normalize_offers(payload, fetched_at=fetched_at, keyword=keyword):
                key = offer.native_product_id
                if key in seen:
                    continue
                seen.add(key)
                offers.append(offer)
        log.info("lomadee_poll", received=len(offers))
        return offers

    async def search(self, keyword: str) -> dict[str, Any]:
        await self.bucket.acquire()
        token = self.settings.lomadee_app_token
        url = f"{API_BASE}/{token}/offer/_search"
        response = await self._http().get(
            url,
            params={"sourceId": self.settings.lomadee_source_id, "keyword": keyword, "size": 20},
        )
        if response.status_code == 429:
            raise SourceError("Lomadee rate limit 429", retryable=True)
        if response.status_code >= 400:
            raise SourceError(f"Lomadee search {response.status_code}", retryable=response.status_code >= 500)
        data = response.json()
        if not isinstance(data, dict):
            raise SourceError("Lomadee: JSON inesperado", retryable=False)
        return data

    def normalize_offers(
        self, payload: dict[str, Any], *, fetched_at: datetime, keyword: str
    ) -> list[NormalizedOffer]:
        rows = payload.get("offers") or []
        if isinstance(rows, dict):
            rows = rows.get("offer") or []
        offers: list[NormalizedOffer] = []
        for raw in rows or []:
            if not isinstance(raw, dict):
                continue
            try:
                offer = self.normalize_offer(raw, fetched_at=fetched_at, keyword=keyword)
            except Exception as exc:
                log.warning("lomadee_row_skipped", error=str(exc))
                continue
            if offer:
                offers.append(offer)
        return offers

    def normalize_offer(self, raw: dict[str, Any], *, fetched_at: datetime, keyword: str) -> NormalizedOffer | None:
        link = sanitize_purchase_url(raw.get("link") or raw.get("url") or raw.get("offerLink"))
        price = money(raw.get("price") or raw.get("priceMin"))
        if price is None or not link:
            return None
        listed = money(raw.get("priceFrom") or raw.get("priceMax"))
        store = raw.get("store") if isinstance(raw.get("store"), dict) else {}
        market, native = parse_product_url(link)
        marketplace = market or infer_marketplace(link, "lomadee")
        native = native or str(raw.get("id") or raw.get("sku") or "")
        if not native:
            return None
        announced = None
        if listed and listed > price:
            announced = money(((listed - price) / listed) * 100)
        return NormalizedOffer(
            source=self.name,
            source_record_id=str(raw.get("id") or native),
            marketplace=marketplace,
            merchant_id="",
            merchant_name=store.get("name") or raw.get("storeName") or "Lomadee",
            native_product_id=native,
            offer_id=str(raw.get("id") or native),
            product_name=str(raw.get("name") or raw.get("productName") or "Oferta Lomadee"),
            category=keyword,
            listed_price=listed or price,
            reported_price=price,
            verified_price=price,
            effective_price=price,
            currency="BRL",
            availability="in_stock",
            fetched_at=fetched_at,
            purchase_url=link,
            affiliate_url=link,
            image_url=sanitize_media_url(raw.get("thumbnail") or raw.get("image")),
            announced_discount_pct=announced,
            identity_confidence=IdentityConfidence.MEDIUM if market else IdentityConfidence.LOW,
            price_verified=True,
            raw_payload={"id": raw.get("id"), "keyword": keyword, "store": store.get("name")},
        ).quantized()
