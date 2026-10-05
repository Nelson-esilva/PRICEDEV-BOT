from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector, SourceError
from app.sources.rate import TokenBucket

log = get_logger("magalu")

SEARCH_URL = "https://www.magazineluiza.com.br/busca/{query}/"
SITE = "https://www.magazineluiza.com.br"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
CHALLENGE_MARKERS = ("just a moment", "sorry, you have been blocked", "cf-browser-verification")
PRODUCT_PATHS = (
    ("props", "pageProps", "data", "search", "products"),
    ("props", "pageProps", "search", "products"),
    ("props", "pageProps", "products"),
    ("props", "pageProps", "data", "products"),
    ("props", "pageProps", "initialState", "search", "products"),
)


def _nested(data: Any, path: tuple[str, ...]) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _price_of(raw: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    price_block = raw.get("price")
    if isinstance(price_block, dict):
        current = money(price_block.get("bestPrice") or price_block.get("price") or price_block.get("value"))
        listed = money(price_block.get("price") or price_block.get("fullPrice") or price_block.get("listPrice"))
        return current or listed, listed
    current = money(raw.get("bestPrice") or raw.get("price") or raw.get("value"))
    listed = money(raw.get("fullPrice") or raw.get("listPrice") or raw.get("priceFrom"))
    return current, listed


def _walk_products(node: Any, found: list[dict[str, Any]], *, depth: int = 0) -> None:
    if depth > 8 or len(found) > 80:
        return
    if isinstance(node, dict):
        title = node.get("title") or node.get("name")
        has_price = isinstance(node.get("price"), (dict, int, float, str)) or node.get("bestPrice") is not None
        ident = node.get("id") or node.get("sku") or node.get("variationId")
        if title and has_price and ident:
            found.append(node)
            return
        for value in node.values():
            _walk_products(value, found, depth=depth + 1)
    elif isinstance(node, list):
        for item in node[:60]:
            _walk_products(item, found, depth=depth + 1)


class MagaluSource(SourceConnector):
    """Vitrine Magalu via busca pública. Sem chave; pode levar 403."""

    name = "magalu"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.magalu_poll_seconds
        self.bucket = TokenBucket(0.4)
        self._client = client
        self._owns_client = client is None

    def is_enabled(self) -> bool:
        return self.settings.enable_magalu

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=25.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/json",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                },
            )
        return self._client

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        seen: set[str] = set()
        offers: list[NormalizedOffer] = []
        for keyword in self.settings.discovery_keyword_list[:3]:
            payload = await self.search(keyword)
            for offer in self.normalize_payload(payload, fetched_at=fetched_at, keyword=keyword):
                if offer.native_product_id in seen:
                    continue
                seen.add(offer.native_product_id)
                offers.append(offer)
        log.info("magalu_poll", received=len(offers))
        return offers

    async def search(self, keyword: str) -> dict[str, Any]:
        await self.bucket.acquire()
        url = SEARCH_URL.format(query=quote(keyword))
        response = await self._http().get(url)
        text = response.text or ""
        lowered = text.lower()
        if response.status_code in {403, 503} or any(marker in lowered for marker in CHALLENGE_MARKERS):
            raise SourceError("Magalu bloqueou a busca pública", retryable=True)
        if response.status_code >= 400:
            raise SourceError(f"Magalu search {response.status_code}", retryable=response.status_code >= 500)
        data = extract_next_data(text)
        if data is None:
            raise SourceError("Magalu: página sem dados de produto", retryable=True)
        return data

    def normalize_payload(
        self, payload: dict[str, Any], *, fetched_at: datetime, keyword: str
    ) -> list[NormalizedOffer]:
        products = collect_products(payload)
        offers: list[NormalizedOffer] = []
        for raw in products:
            try:
                offer = self.normalize_product(raw, fetched_at=fetched_at, keyword=keyword)
            except Exception as exc:
                log.warning("magalu_row_skipped", error=str(exc))
                continue
            if offer:
                offers.append(offer)
        return offers

    def normalize_product(
        self, raw: dict[str, Any], *, fetched_at: datetime, keyword: str
    ) -> NormalizedOffer | None:
        native = str(raw.get("id") or raw.get("sku") or raw.get("variationId") or "").strip()
        if not native:
            return None
        price, listed = _price_of(raw)
        if price is None:
            return None
        path = raw.get("path") or raw.get("url") or raw.get("shareUrl") or ""
        purchase = sanitize_purchase_url(str(path) if str(path).startswith("http") else urljoin(SITE, str(path)))
        image = raw.get("image") or raw.get("imageUrl") or raw.get("thumbnail")
        if isinstance(image, list) and image:
            image = image[0]
        if isinstance(image, dict):
            image = image.get("url") or image.get("src")
        seller = raw.get("seller") if isinstance(raw.get("seller"), dict) else {}
        announced = None
        if listed and listed > price:
            announced = money(((listed - price) / listed) * 100)
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace="magalu",
            merchant_id="",
            merchant_name=seller.get("name") or "Magazine Luiza",
            native_product_id=native,
            offer_id=native,
            product_name=str(raw.get("title") or raw.get("name") or "Produto Magalu"),
            category=keyword,
            listed_price=listed or price,
            reported_price=price,
            verified_price=price,
            effective_price=price,
            currency="BRL",
            availability="in_stock",
            fetched_at=fetched_at,
            purchase_url=purchase,
            image_url=sanitize_media_url(str(image) if image else None),
            announced_discount_pct=announced,
            identity_confidence=IdentityConfidence.HIGH,
            price_verified=True,
            raw_payload={"id": native, "keyword": keyword},
        ).quantized()


def extract_next_data(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def collect_products(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for path in PRODUCT_PATHS:
        rows = _nested(payload, path)
        if isinstance(rows, list) and rows:
            return [row for row in rows if isinstance(row, dict)]
    found: list[dict[str, Any]] = []
    _walk_products(payload, found)
    return found
