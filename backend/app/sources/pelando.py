from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from decimal import Decimal
from html import unescape
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
from app.sources.rate import TokenBucket

log = get_logger("pelando")

CHALLENGE_MARKERS = ("just a moment", "sorry, you have been blocked", "cf-browser-verification")


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
        self._detailed_ids: set[str] = set()

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
        for slug in ("mercado-livre", "kabum", "amazon", "magazine-luiza", "shopee"):
            store_id = await self._store_id(slug)
            if store_id:
                payloads.extend(await self._paged("recents", pages=max(2, pages // 2), store_id=store_id))
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
        await self._enrich_details(offers)
        return offers

    async def fetch_deal(self, deal_id: str) -> dict[str, Any]:
        return await self._get(f"/deals/{deal_id}", {})

    async def fetch_recents(self) -> dict[str, Any]:
        return await self.fetch_feed("recents")

    async def _enrich_details(self, offers: list[NormalizedOffer]) -> None:
        budget = max(0, self.settings.pelando_deal_details_per_poll)
        if budget == 0:
            return
        for index, offer in enumerate(offers):
            if budget <= 0:
                break
            if not _needs_detail(offer) or offer.source_record_id in self._detailed_ids:
                continue
            try:
                payload = await self.fetch_deal(offer.source_record_id)
            except (SourceError, SourceBlocked) as exc:
                log.warning("pelando_deal_detail_skip", deal_id=offer.source_record_id, error=str(exc))
                self._detailed_ids.add(offer.source_record_id)
                continue
            raw = _deal_body(payload)
            offers[index] = _merge_deal_detail(offer, raw)
            self._detailed_ids.add(offer.source_record_id)
            budget -= 1

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
        coupon = _coupon_code(raw.get("couponCode") or raw.get("coupon_code"))
        desc = _plain_text(raw.get("shortDescription") or raw.get("short_description") or raw.get("description"))
        if not coupon:
            coupon = _coupon_from_text(desc)
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
            description=desc,
            coupon_code=coupon,
            payment_hint=_payment_hint(desc),
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
                "paymentHint": _payment_hint(desc),
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


_HTML_TAG = re.compile(r"<[^>]+>")
_COUPON_IN_TEXT = re.compile(r"(?:cupom|use o cupom)\s*[:\-]?\s*([A-Za-z0-9]{4,24})", re.I)
_COUPON_STOP = {
    "ABAIXO",
    "PRODUTO",
    "CODIGO",
    "AQUI",
    "DESCONTO",
    "CUPOM",
    "SELECIONE",
    "PIX",
    "BOLETO",
}


def _deal_body(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data", payload)
    if isinstance(data, dict) and isinstance(data.get("deal"), dict):
        return data["deal"]
    return data if isinstance(data, dict) else {}


def _plain_text(value) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = _HTML_TAG.sub(" ", text)
    text = unescape(text)
    text = " ".join(text.split())
    return text or None


def _coupon_code(value) -> str | None:
    if not isinstance(value, str):
        return None
    code = value.strip()
    if not code or " " in code or len(code) > 32:
        return None
    return code


def _coupon_from_text(value: str | None) -> str | None:
    if not value:
        return None
    match = _COUPON_IN_TEXT.search(value)
    if not match:
        return None
    code = match.group(1).strip()
    if code.upper() in _COUPON_STOP:
        return None
    return code


def _payment_hint(value: str | None) -> str | None:
    if not value:
        return None
    low = value.lower()
    if re.search(r"\bpix\b", low):
        return "Pix"
    if "boleto" in low:
        return "Boleto"
    return None


def _weak_purchase_url(url: str | None) -> bool:
    if not url:
        return True
    low = url.lower()
    return "/social/" in low or "forceinapp=" in low or "origin=copy_link" in low


def _needs_detail(offer: NormalizedOffer) -> bool:
    if not offer.coupon_code or not offer.payment_hint:
        return True
    return _weak_purchase_url(offer.purchase_url)


def _merge_deal_detail(offer: NormalizedOffer, raw: dict[str, Any]) -> NormalizedOffer:
    if not isinstance(raw, dict):
        return offer
    coupon = _coupon_code(raw.get("couponCode") or raw.get("coupon_code")) or offer.coupon_code
    desc = (
        _plain_text(raw.get("shortDescription") or raw.get("short_description") or raw.get("description"))
        or offer.description
    )
    if not coupon:
        coupon = _coupon_from_text(desc)
    hint = _payment_hint(" ".join(part for part in (desc, offer.description) if part)) or offer.payment_hint
    purchase = sanitize_purchase_url(raw.get("sourceUrl") or raw.get("source_url"))
    url = offer.purchase_url
    marketplace = offer.marketplace
    if purchase and _weak_purchase_url(url):
        url = purchase
        marketplace = infer_marketplace(url, marketplace)
    payload = dict(offer.raw_payload or {})
    payload["couponCode"] = coupon
    payload["paymentHint"] = hint
    return offer.model_copy(
        update={
            "coupon_code": coupon,
            "payment_hint": hint,
            "description": desc,
            "purchase_url": url,
            "marketplace": marketplace,
            "raw_payload": payload,
        }
    ).quantized()
