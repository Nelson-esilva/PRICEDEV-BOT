from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector, SourceError
from app.sources.rate import TokenBucket

log = get_logger("kabum")

SEARCH_URL = "https://www.kabum.com.br/busca/{query}"
SITE = "https://www.kabum.com.br"
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
DEFAULT_KEYWORDS = (
    "processador",
    "ryzen 5 5600",
    "ryzen 5 7600",
    "ryzen 7 5700x",
    "ryzen 7 7800x3d",
    "intel i5 12400",
    "intel i5 14400",
    "intel i7 14700",
    "placa de video",
    "rtx 4060",
    "rtx 4060 ti",
    "rtx 4070",
    "rtx 4070 super",
    "rtx 5060",
    "rx 7600",
    "rx 7700 xt",
    "arc b580",
    "placa mae",
    "placa mae b550",
    "placa mae b650",
    "placa mae h610",
    "memoria ram ddr4",
    "memoria ram ddr5",
    "kit ram 32gb",
    "ssd nvme",
    "ssd 500gb",
    "ssd 1tb",
    "ssd 2tb",
    "nvme gen4",
    "hd 1tb",
    "hd 2tb",
    "fonte 650w",
    "fonte 750w",
    "fonte 850w",
    "gabinete gamer",
    "gabinete mid tower",
    "water cooler 240",
    "water cooler 360",
    "air cooler",
    "cooler cpu",
    "pasta termica",
    "ventoinha 120mm",
    "kit fan argb",
    "monitor gamer",
    "monitor 24",
    "monitor 27",
    "monitor 144hz",
    "teclado mecanico",
    "mouse gamer",
    "mouse sem fio",
    "headset gamer",
    "webcam",
    "microfone condensador",
    "placa de captura",
    "wifi pci",
    "placa de som",
    "cabo displayport",
    "cabo hdmi 2.1",
    "hub usb",
    "dock station",
    "ssd externo",
    "no-break",
    "filtro de linha",
    "kit upgrade",
)
CATALOG_PATHS = (
    "hardware/processadores",
    "hardware/placa-de-video-vga",
    "hardware/memoria-ram",
    "hardware/ssd-2-5",
    "hardware/hard-disk",
    "hardware/placas-mae",
    "hardware/fontes",
    "hardware/gabinetes",
    "hardware/coolers",
    "perifericos/headset-gamer",
)


class KabumSource(SourceConnector):
    """Vitrine KaBuM via busca pública (__NEXT_DATA__)."""

    name = "kabum"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.kabum_poll_seconds
        self.bucket = TokenBucket(0.4)
        self._client = client
        self._owns_client = client is None
        self._keyword_offset = 0

    def is_enabled(self) -> bool:
        return self.settings.enable_kabum

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
                    "Accept": "text/html,application/xhtml+xml",
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
        keywords = self.settings.kabum_keyword_list
        batch = max(1, self.settings.kabum_keywords_per_poll)
        start = self._keyword_offset % max(len(keywords), 1)
        selected = [keywords[(start + index) % len(keywords)] for index in range(min(batch, len(keywords)))]
        self._keyword_offset = start + len(selected)
        for keyword in selected:
            await self._absorb(offers, seen, fetched_at, label=keyword, payload_factory=lambda q=keyword: self.search(q))
        path_start = (self._keyword_offset // max(batch, 1)) % max(len(CATALOG_PATHS), 1)
        for path in (CATALOG_PATHS[path_start], CATALOG_PATHS[(path_start + 1) % len(CATALOG_PATHS)]):
            await self._absorb(offers, seen, fetched_at, label=path, payload_factory=lambda p=path: self.fetch_catalog(p))
        log.info("kabum_poll", received=len(offers))
        return offers

    async def _absorb(
        self,
        offers: list[NormalizedOffer],
        seen: set[str],
        fetched_at: datetime,
        *,
        label: str,
        payload_factory,
    ) -> None:
        try:
            payload = await payload_factory()
        except SourceError as exc:
            log.warning("kabum_search_skip", keyword=label, error=str(exc))
            return
        for offer in self.normalize_payload(payload, fetched_at=fetched_at, keyword=label):
            if offer.native_product_id in seen:
                continue
            seen.add(offer.native_product_id)
            offers.append(offer)

    async def search(self, keyword: str) -> dict[str, Any]:
        await self.bucket.acquire()
        url = SEARCH_URL.format(query=quote(keyword))
        response = await self._http().get(url)
        if response.status_code >= 400:
            raise SourceError(f"KaBuM search {response.status_code}", retryable=response.status_code >= 500)
        data = extract_catalog(response.text or "")
        if data is None:
            raise SourceError("KaBuM: página sem catálogo", retryable=True)
        return data

    async def fetch_catalog(self, path: str) -> dict[str, Any]:
        await self.bucket.acquire()
        response = await self._http().get(f"{SITE}/{path.lstrip('/')}")
        if response.status_code >= 400:
            raise SourceError(f"KaBuM catalog {response.status_code}", retryable=response.status_code >= 500)
        data = extract_catalog(response.text or "")
        if data is None:
            raise SourceError("KaBuM: categoria sem catálogo", retryable=True)
        return data

    def normalize_payload(
        self, payload: dict[str, Any], *, fetched_at: datetime, keyword: str
    ) -> list[NormalizedOffer]:
        rows = ((payload.get("catalogServer") or {}).get("data")) or []
        offers: list[NormalizedOffer] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            try:
                offer = self.normalize_product(raw, fetched_at=fetched_at, keyword=keyword)
            except Exception as exc:
                log.warning("kabum_row_skipped", error=str(exc))
                continue
            if offer:
                offers.append(offer)
        return offers

    def normalize_product(
        self, raw: dict[str, Any], *, fetched_at: datetime, keyword: str
    ) -> NormalizedOffer | None:
        native = str(raw.get("code") or "").strip()
        if not native:
            return None
        price = money(raw.get("priceWithDiscount") or raw.get("price"))
        listed = money(raw.get("oldPrice") or raw.get("price"))
        if price is None:
            return None
        slug = raw.get("friendlyName") or native
        purchase = sanitize_purchase_url(f"{SITE}/produto/{native}/{slug}")
        announced = money(raw.get("discountPercentage")) if raw.get("discountPercentage") else None
        if announced is None and listed and listed > price:
            announced = money(((listed - price) / listed) * 100)
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace="kabum",
            merchant_id="",
            merchant_name=raw.get("sellerName") or "KaBuM!",
            native_product_id=native,
            offer_id=native,
            product_name=str(raw.get("name") or "Produto KaBuM!"),
            category=keyword,
            listed_price=listed or price,
            reported_price=price,
            verified_price=price,
            effective_price=price,
            currency="BRL",
            availability="in_stock" if raw.get("available") else "unknown",
            fetched_at=fetched_at,
            purchase_url=purchase,
            image_url=sanitize_media_url(raw.get("image") or (raw.get("images") or [None])[0]),
            announced_discount_pct=announced,
            identity_confidence=IdentityConfidence.HIGH,
            price_verified=True,
            raw_payload={"code": native, "keyword": keyword},
        ).quantized()


def extract_catalog(html: str) -> dict[str, Any] | None:
    match = NEXT_DATA.search(html)
    if not match:
        return None
    try:
        outer = json.loads(match.group(1))
        raw = ((outer.get("props") or {}).get("pageProps") or {}).get("data")
        if isinstance(raw, str):
            inner = json.loads(raw)
        elif isinstance(raw, dict):
            inner = raw
        else:
            return None
    except json.JSONDecodeError:
        return None
    return inner if isinstance(inner, dict) else None
