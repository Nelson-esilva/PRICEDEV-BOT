from __future__ import annotations

import asyncio
import time
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.ingestion.identity import infer_marketplace
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceBlocked, SourceConnector, SourceError

log = get_logger("pelando")

CHALLENGE_MARKERS = ("just a moment", "sorry, you have been blocked", "cf-browser-verification")


class TokenBucket:
    def __init__(self, rps: float = 1.0) -> None:
        self.rate = max(0.1, rps)
        self.tokens = 1.0
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(1.0, self.tokens + (now - self.updated_at) * self.rate)
                self.updated_at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


class PelandoSource(SourceConnector):
    """Adaptador isolado. Não chama a API a menos que ENABLE_PELANDO=true.

    A API JSON interna não é contrato público. Sem ToS/autorização, permanece desligado.
    Não há cache de 15 min no feed de recents. Preço comunitário nunca vira verified_price.
    redirectUrl JWT é ignorado.
    """

    name = "pelando"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.pelando_poll_seconds
        self.bucket = TokenBucket(1.0)
        self._client = client
        self._owns_client = client is None
        self._robots_ok_until = 0.0
        self._store_ids: dict[str, str] = {}

    def is_enabled(self) -> bool:
        return self.settings.enable_pelando

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": self.settings.pelando_user_agent,
                    "Accept": "application/json",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                },
            )
        return self._client

    async def poll(self, *, now=None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        pages = self.settings.pelando_feed_pages
        payloads: list[dict[str, Any]] = []
        payloads.extend(await self._paged("recents", pages=pages))
        ml_id = await self._store_id("mercado-livre")
        if ml_id:
            payloads.extend(await self._paged("recents", pages=pages, store_id=ml_id))
        for feed in ("hottest", "last-commented"):
            payloads.extend(await self._paged(feed, pages=max(2, pages // 2)))
        seen: set[str] = set()
        offers: list[NormalizedOffer] = []
        for payload in payloads:
            for offer in self.normalize_payload(payload, fetched_at=fetched_at):
                if offer.source_record_id in seen:
                    continue
                seen.add(offer.source_record_id)
                offers.append(offer)
        offers.sort(key=lambda row: row.source_created_at or row.fetched_at, reverse=True)
        return offers

    async def fetch_recents(self) -> dict[str, Any]:
        return await self.fetch_feed("recents")

    async def fetch_search(
        self,
        *,
        term: str,
        page: int = 1,
        sort: str = "createdAt",
    ) -> dict[str, Any]:
        return await self._get(
            "/feed/search",
            {
                "term": term,
                "size": 50,
                "page": page,
                "hideExpired": "true",
                "sortOption": sort,
            },
        )

    async def fetch_feed(
        self,
        feed: str,
        *,
        after: str | None = None,
        store_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": 50, "hideExpired": "true"}
        if after:
            params["after"] = after
        if store_id:
            params["storeId"] = store_id
        return await self._get(f"/feed/v2/{feed}", params)

    async def _paged(
        self,
        feed: str,
        *,
        pages: int,
        store_id: str | None = None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        after: str | None = None
        for index in range(max(1, pages)):
            try:
                payload = await self.fetch_feed(feed, after=after, store_id=store_id)
            except SourceError as exc:
                log.warning(
                    "pelando_page_skip" if out else "pelando_feed_skip",
                    feed=feed,
                    page=index + 1,
                    store_id=store_id,
                    error=str(exc),
                )
                break
            out.append(payload)
            info = _page_info(payload)
            cursor = info.get("endCursor")
            if not info.get("hasNextPage") or not cursor:
                break
            after = str(cursor)
        return out

    async def _store_id(self, slug: str) -> str | None:
        if slug in self._store_ids:
            return self._store_ids[slug]
        try:
            payload = await self._get("/stores/search", {"term": slug.replace("-", " ")})
        except SourceError as exc:
            log.warning("pelando_store_skip", slug=slug, error=str(exc))
            return "921" if slug == "mercado-livre" else None
        stores = (payload.get("data") or payload).get("stores") or []
        for row in stores:
            if isinstance(row, dict) and row.get("slug") == slug and row.get("id") is not None:
                self._store_ids[slug] = str(row["id"])
                return self._store_ids[slug]
        if slug == "mercado-livre":
            return "921"
        return None

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = urljoin(self.settings.pelando_base_url.rstrip("/") + "/", path.lstrip("/"))
        query = urlencode({k: v for k, v in params.items() if v is not None})
        if query:
            url = f"{url}?{query}"
        await self._assert_robots(url)
        await self.bucket.acquire()
        resp = await self._http().get(url)
        body = resp.text
        if _is_challenge(body) or resp.status_code == 403:
            raise SourceBlocked(f"Pelando bloqueou ou desafiou a coleta (HTTP {resp.status_code})")
        if resp.status_code == 429:
            raise SourceError("Pelando HTTP 429", retryable=True)
        if resp.status_code >= 400:
            raise SourceError(f"Pelando HTTP {resp.status_code}", retryable=resp.status_code >= 500)
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(f"JSON inválido do Pelando: {exc}") from exc

    def normalize_payload(self, payload: dict[str, Any], *, fetched_at) -> list[NormalizedOffer]:
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        deals = data.get("deals") or []
        offers: list[NormalizedOffer] = []
        for raw in deals:
            try:
                offer = self._normalize_deal(raw, fetched_at)
            except Exception as exc:
                log.warning("pelando_row_skipped", error=str(exc), deal_id=(raw or {}).get("id"))
                continue
            if offer:
                offers.append(offer)
        return offers

    def _normalize_deal(self, raw: dict[str, Any], fetched_at) -> NormalizedOffer | None:
        if not isinstance(raw, dict):
            return None
        kind = (raw.get("kind") or "promotion").lower()
        if kind == "discussion":
            return None
        listed = money(raw.get("price"))
        if listed is None:
            if raw.get("discountPercentage") is not None or raw.get("couponCode") or kind == "coupon":
                listed = Decimal("0.00")
            else:
                return None
        availability = "unavailable" if (raw.get("status") or "").lower() == "expired" else "unknown"
        store = raw.get("store") if isinstance(raw.get("store"), dict) else {}
        merchant_name = store.get("name")
        merchant_id = str(store.get("slug") or store.get("id") or "")
        purchase = sanitize_purchase_url(raw.get("sourceUrl") or raw.get("source_url"))
        marketplace = infer_marketplace(purchase, merchant_id or "unknown")
        native = str(raw.get("id") or "")
        if not native:
            return None
        created = _parse_dt(raw.get("createdAt") or raw.get("created_at"))
        approved = _parse_dt(raw.get("firstApprovedAt") or raw.get("first_approved_at"))
        temp = raw.get("temperature")
        temperature = None
        try:
            if temp is not None and not isinstance(temp, bool):
                temperature = int(temp)
        except (TypeError, ValueError):
            temperature = None
        coupon = raw.get("couponCode") or raw.get("coupon_code")
        if isinstance(coupon, str) and not coupon.strip():
            coupon = None
        desc = raw.get("shortDescription") or raw.get("short_description")
        comments = raw.get("commentCount") or raw.get("comment_count")
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace=marketplace,
            merchant_id=merchant_id,
            merchant_name=merchant_name,
            native_product_id=f"pelando-{native}",
            offer_id=native,
            product_name=str(raw.get("title") or "Oferta Pelando"),
            listed_price=listed,
            reported_price=listed,
            verified_price=None,
            effective_price=listed,
            currency="BRL",
            availability=availability,
            source_created_at=approved or created,
            source_updated_at=created,
            fetched_at=fetched_at,
            purchase_url=purchase,
            image_url=_best_image(raw),
            description=str(desc).strip() if isinstance(desc, str) and desc.strip() else None,
            coupon_code=str(coupon).strip() if isinstance(coupon, str) else None,
            free_shipping=raw.get("freeShipping") if isinstance(raw.get("freeShipping"), bool) else None,
            comment_count=int(comments) if isinstance(comments, int) else None,
            temperature=temperature,
            announced_discount_pct=money(raw.get("discountPercentage")),
            identity_confidence=IdentityConfidence.LOW,
            price_verified=False,
            community_signals={"temperature": temperature, "status": raw.get("status")},
            raw_payload={
                "id": native,
                "store": merchant_name,
                "imageUrl": raw.get("imageUrl"),
                "couponCode": coupon,
            },
        ).quantized()

    async def _assert_robots(self, url: str) -> None:
        if time.monotonic() < self._robots_ok_until:
            return
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        try:
            resp = await self._http().get(f"{origin}/robots.txt")
        except httpx.HTTPError:
            self._robots_ok_until = time.monotonic() + 1800
            return
        if resp.status_code != 200:
            self._robots_ok_until = time.monotonic() + 1800
            return
        parser = RobotFileParser()
        parser.parse(resp.text.splitlines())
        if not parser.can_fetch(self.settings.pelando_user_agent, url):
            raise SourceBlocked(f"robots.txt impede {url}")
        self._robots_ok_until = time.monotonic() + 1800


def _page_info(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or payload if isinstance(payload, dict) else {}
    info = data.get("pageInfo") if isinstance(data, dict) else None
    return info if isinstance(info, dict) else {}


def _best_image(raw: dict[str, Any]) -> str | None:
    best_url = None
    best_width = -1
    srcset = raw.get("imageSrcset") or raw.get("image_srcset") or []
    if isinstance(srcset, list):
        for item in srcset:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            try:
                width = int(item.get("width") or 0)
            except (TypeError, ValueError):
                width = 0
            if url and width >= best_width:
                best_url = url
                best_width = width
    return sanitize_media_url(best_url or raw.get("imageUrl") or raw.get("image_url"))


def _is_challenge(body: str) -> bool:
    head = body[:4096].lower()
    return any(marker in head for marker in CHALLENGE_MARKERS)


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
