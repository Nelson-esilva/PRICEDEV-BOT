from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector, SourceError
from app.sources.rate import TokenBucket

log = get_logger("mercadolivre")

API_BASE = "https://api.mercadolibre.com"
OFERTAS_URL = "https://www.mercadolivre.com.br/ofertas"
MAIS_VENDIDOS_URL = "https://www.mercadolivre.com.br/mais-vendidos"
DEFAULT_CATEGORIES = ("MLB1051", "MLB1648", "MLB1002", "MLB1144")
OFERTAS_PAGES = 8
_CTX_R = "_n.ctx.r="
_FLOX_KEY = "@meli/web/flox/FLOX_STATE"
VIA_LABELS = {
    "ofertas": "Ofertas",
    "relampago": "Oferta relâmpago",
    "mais-vendidos": "Mais vendidos",
}


def _https(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http://"):
        return f"https://{url[7:]}"
    return url


def _discount(price: Decimal | None, original: Decimal | None) -> Decimal | None:
    if price is None or original is None or original <= 0 or price >= original:
        return None
    return money(((original - price) / original) * 100)


class MercadoLivreSource(SourceConnector):
    """Busca pública oficial do Mercado Livre (sites/MLB). Sem chave."""

    name = "mercadolivre"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.mercadolivre_poll_seconds
        self.bucket = TokenBucket(1.0)
        self._client = client
        self._owns_client = client is None
        self._api_blocked = False

    def is_enabled(self) -> bool:
        return self.settings.enable_mercadolivre

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                },
            )
        return self._client

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        if not self._api_blocked:
            offers = await self._poll_api(fetched_at)
            if offers:
                log.info("ml_poll", received=len(offers), via="api")
                return offers
            self._api_blocked = True
        offers = await self._poll_ofertas(fetched_at)
        log.info("ml_poll", received=len(offers), via="ofertas")
        return offers

    async def _poll_api(self, fetched_at: datetime) -> list[NormalizedOffer]:
        seen: set[str] = set()
        offers: list[NormalizedOffer] = []
        queries: list[dict[str, str]] = [{"category": category} for category in DEFAULT_CATEGORIES]
        for keyword in self.settings.discovery_keyword_list[:4]:
            queries.append({"q": keyword, "sort": "relevance"})
        for params in queries:
            payload = await self.search(params)
            if payload.get("_blocked"):
                return []
            for offer in self.normalize_search(payload, fetched_at=fetched_at):
                if offer.native_product_id in seen:
                    continue
                seen.add(offer.native_product_id)
                offers.append(offer)
        return offers

    async def search(self, params: dict[str, str]) -> dict[str, Any]:
        await self.bucket.acquire()
        query = {"limit": "20", **params}
        response = await self._http().get(f"{API_BASE}/sites/MLB/search", params=query)
        if response.status_code == 429:
            raise SourceError("Mercado Livre rate limit 429", retryable=True)
        if response.status_code in {401, 403}:
            log.warning("ml_search_blocked", status=response.status_code, params=params)
            return {"results": [], "_blocked": True}
        if response.status_code >= 400:
            raise SourceError(f"Mercado Livre search {response.status_code}", retryable=response.status_code >= 500)
        data = response.json()
        if not isinstance(data, dict):
            raise SourceError("Mercado Livre search: JSON inesperado", retryable=False)
        return data

    async def fetch_item(self, item_id: str) -> dict[str, Any] | None:
        await self.bucket.acquire()
        response = await self._http().get(f"{API_BASE}/items/{item_id}")
        if response.status_code in {401, 403, 404}:
            return None
        if response.status_code == 429:
            raise SourceError("Mercado Livre rate limit 429", retryable=True)
        if response.status_code >= 400:
            log.warning("ml_item_blocked", status=response.status_code, item=item_id)
            return None
        data = response.json()
        return data if isinstance(data, dict) else None

    def normalize_search(self, payload: dict[str, Any], *, fetched_at: datetime) -> list[NormalizedOffer]:
        rows = payload.get("results") or []
        offers: list[NormalizedOffer] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            try:
                offer = self.normalize_item(raw, fetched_at=fetched_at)
            except Exception as exc:
                log.warning("ml_row_skipped", error=str(exc), item=raw.get("id"))
                continue
            if offer:
                offers.append(offer)
        return offers

    def normalize_item(self, raw: dict[str, Any], *, fetched_at: datetime) -> NormalizedOffer | None:
        native = str(raw.get("id") or "").replace("-", "").upper()
        if not native.startswith("MLB"):
            return None
        price = money(raw.get("price"))
        if price is None:
            return None
        original = money(raw.get("original_price"))
        permalink = sanitize_purchase_url(raw.get("permalink") or raw.get("secure_thumbnail"))
        image = sanitize_media_url(_https(raw.get("thumbnail") or raw.get("secure_thumbnail")))
        seller = raw.get("seller") if isinstance(raw.get("seller"), dict) else {}
        shipping = raw.get("shipping") if isinstance(raw.get("shipping"), dict) else {}
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace="mercadolivre",
            merchant_id="",
            merchant_name=seller.get("nickname") or "Mercado Livre",
            native_product_id=native,
            offer_id=native,
            product_name=str(raw.get("title") or "Produto Mercado Livre"),
            category=str(raw.get("category_id") or "") or None,
            listed_price=original or price,
            reported_price=price,
            verified_price=price,
            effective_price=price,
            currency=str(raw.get("currency_id") or "BRL"),
            availability="in_stock" if raw.get("available_quantity") else "unknown",
            fetched_at=fetched_at,
            purchase_url=permalink,
            image_url=image,
            free_shipping=shipping.get("free_shipping") if isinstance(shipping.get("free_shipping"), bool) else None,
            announced_discount_pct=_discount(price, original),
            identity_confidence=IdentityConfidence.HIGH,
            price_verified=True,
            raw_payload={"id": native, "category_id": raw.get("category_id")},
        ).quantized()

    async def _poll_ofertas(self, fetched_at: datetime) -> list[NormalizedOffer]:
        seen: set[str] = set()
        offers: list[NormalizedOffer] = []

        async def absorb(batch: list[NormalizedOffer]) -> None:
            for offer in batch:
                if offer.native_product_id in seen:
                    continue
                seen.add(offer.native_product_id)
                offers.append(offer)

        for page in range(1, OFERTAS_PAGES + 1):
            try:
                html = await self.fetch_html(OFERTAS_URL, params={"page": str(page)} if page > 1 else None)
                batch = self.normalize_ofertas_html(html, fetched_at=fetched_at)
            except SourceError as exc:
                log.warning("ml_ofertas_page_skip", page=page, error=str(exc))
                if page > 1:
                    break
                continue
            if not batch and page > 1:
                break
            await absorb(batch)
        try:
            html = await self.fetch_html(OFERTAS_URL, params={"promotion_type": "lightning"})
            await absorb(self._normalize_cards(parse_ofertas_cards(html), fetched_at=fetched_at, via="relampago"))
        except SourceError as exc:
            log.warning("ml_lightning_skip", error=str(exc))
        for category in DEFAULT_CATEGORIES:
            try:
                html = await self.fetch_html(OFERTAS_URL, params={"category": category})
                await absorb(self.normalize_ofertas_html(html, fetched_at=fetched_at))
            except SourceError as exc:
                log.warning("ml_filter_skip", category=category, error=str(exc))
        try:
            html = await self.fetch_html(MAIS_VENDIDOS_URL)
            await absorb(self.normalize_mais_vendidos_html(html, fetched_at=fetched_at))
        except SourceError as exc:
            log.warning("ml_mais_vendidos_skip", error=str(exc))
        for category in DEFAULT_CATEGORIES:
            try:
                html = await self.fetch_html(f"{MAIS_VENDIDOS_URL}/{category}")
                await absorb(self.normalize_mais_vendidos_html(html, fetched_at=fetched_at))
            except SourceError as exc:
                log.warning("ml_mais_vendidos_cat_skip", category=category, error=str(exc))
        return offers

    async def fetch_html(self, url: str, params: dict[str, str] | None = None) -> str:
        await self.bucket.acquire()
        response = await self._http().get(
            url,
            params=params,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "pt-BR,pt;q=0.9",
            },
        )
        if response.status_code >= 400:
            raise SourceError(f"Mercado Livre {url} {response.status_code}", retryable=response.status_code >= 500)
        return response.text or ""

    async def fetch_ofertas(self, *, page: int = 1) -> str:
        return await self.fetch_html(OFERTAS_URL, params={"page": str(page)} if page > 1 else None)

    def normalize_ofertas_html(self, html: str, *, fetched_at: datetime) -> list[NormalizedOffer]:
        return self._normalize_cards(parse_ofertas_cards(html), fetched_at=fetched_at, via="ofertas")

    def normalize_mais_vendidos_html(self, html: str, *, fetched_at: datetime) -> list[NormalizedOffer]:
        return self._normalize_cards(parse_mais_vendidos_cards(html), fetched_at=fetched_at, via="mais-vendidos")

    def _normalize_cards(
        self, cards: list[dict[str, Any]], *, fetched_at: datetime, via: str
    ) -> list[NormalizedOffer]:
        offers: list[NormalizedOffer] = []
        seen: set[str] = set()
        for card in cards:
            try:
                offer = self._card_to_offer(card, fetched_at=fetched_at, via=via)
            except Exception as exc:
                log.warning("ml_card_skip", via=via, error=str(exc))
                continue
            if not offer or offer.native_product_id in seen:
                continue
            seen.add(offer.native_product_id)
            offers.append(offer)
        return offers

    def _card_to_offer(self, card: dict[str, Any], *, fetched_at: datetime, via: str = "ofertas") -> NormalizedOffer | None:
        meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        native = str(meta.get("id") or "").replace("-", "").upper()
        if not native.startswith("MLB"):
            return None
        price = _card_price(card)
        previous = _previous_price(card)
        if price is None:
            price = previous
        if price is None:
            return None
        title = _card_title(card) or "Oferta Mercado Livre"
        path = str(meta.get("url") or "").lstrip("/")
        if path.startswith("http"):
            purchase = sanitize_purchase_url(path)
        elif path:
            purchase = sanitize_purchase_url(f"https://{path}")
        else:
            purchase = sanitize_purchase_url(f"https://produto.mercadolivre.com.br/{native[:3]}-{native[3:]}")
        pic_id = None
        pictures = card.get("pictures") if isinstance(card.get("pictures"), dict) else {}
        pics = pictures.get("pictures") if isinstance(pictures, dict) else None
        if isinstance(pics, list) and pics and isinstance(pics[0], dict):
            pic_id = pics[0].get("id")
        image = sanitize_media_url(f"https://http2.mlstatic.com/D_NQ_NP_{pic_id}-O.webp") if pic_id else None
        pix = "pix" in json.dumps(meta.get("tracks") or {}, ensure_ascii=False).lower()
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace="mercadolivre",
            merchant_id="",
            merchant_name=_card_seller(card) or "Mercado Livre",
            native_product_id=native,
            offer_id=native,
            product_name=title,
            category=via,
            description=VIA_LABELS.get(via, via),
            listed_price=previous or price,
            reported_price=price,
            verified_price=price,
            effective_price=price,
            currency="BRL",
            availability="in_stock",
            fetched_at=fetched_at,
            purchase_url=purchase,
            image_url=image,
            payment_hint="Pix" if pix else None,
            announced_discount_pct=_discount(price, previous),
            identity_confidence=IdentityConfidence.HIGH,
            price_verified=True,
            raw_payload={"id": native, "via": via},
        ).quantized()


def _decode_ctx(html: str) -> dict[str, Any] | None:
    idx = (html or "").find(_CTX_R)
    if idx < 0:
        return None
    try:
        data, _end = json.JSONDecoder().raw_decode(html[idx + len(_CTX_R) :])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_ofertas_cards(html: str) -> list[dict[str, Any]]:
    data = _decode_ctx(html)
    if data is None:
        return []
    items = (
        ((data.get("appProps") or {}).get("pageProps") or {}).get("data") or {}
    ).get("items") or []
    cards: list[dict[str, Any]] = []
    for row in items:
        if isinstance(row, dict) and isinstance(row.get("card"), dict):
            cards.append(row["card"])
    return cards


def parse_mais_vendidos_cards(html: str) -> list[dict[str, Any]]:
    data = _decode_ctx(html)
    if data is None:
        return []
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()

    def take(card: dict[str, Any]) -> None:
        meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        native = str(meta.get("id") or "")
        if not native or native in seen:
            return
        if not native.replace("-", "").upper().startswith("MLB"):
            return
        seen.add(native)
        cards.append(card)

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 14 or len(cards) > 400:
            return
        if isinstance(node, dict):
            polycards = node.get("polycards")
            if isinstance(polycards, list):
                for card in polycards:
                    if isinstance(card, dict):
                        take(card)
            if node.get("components") and isinstance(node.get("metadata"), dict):
                take(node)
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node[:120]:
                walk(item, depth + 1)

    flox = ((data.get("appProps") or {}).get("pageProps") or {}).get("floxPreloadedState") or {}
    state = flox.get(_FLOX_KEY) if isinstance(flox, dict) else {}
    walk(state or flox or data)
    if not cards:
        walk(data)
    return cards


def _card_price(card: dict[str, Any]) -> Decimal | None:
    meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    tracks = meta.get("tracks") if isinstance(meta.get("tracks"), dict) else {}
    parsed = money((tracks.get("price") or {}).get("price")) if isinstance(tracks.get("price"), dict) else None
    if parsed:
        return parsed
    for component in card.get("components") or []:
        if not isinstance(component, dict):
            continue
        block = component.get("price") if isinstance(component.get("price"), dict) else component
        current = block.get("current_price") if isinstance(block.get("current_price"), dict) else {}
        parsed = money(
            current.get("value")
            or current.get("amount")
            or block.get("value")
            or block.get("amount")
            or (block.get("fraction") if block.get("cent") is not None else None)
        )
        if parsed:
            return parsed
    return None


def _card_title(card: dict[str, Any]) -> str | None:
    for component in card.get("components") or []:
        if not isinstance(component, dict) or component.get("type") != "title":
            continue
        title = component.get("title") if isinstance(component.get("title"), dict) else {}
        text = title.get("text")
        if text:
            return str(text)
    return None


def _card_seller(card: dict[str, Any]) -> str | None:
    for component in card.get("components") or []:
        if not isinstance(component, dict) or component.get("type") != "seller":
            continue
        seller = component.get("seller") if isinstance(component.get("seller"), dict) else {}
        for value in seller.get("values") or []:
            if isinstance(value, dict) and value.get("key") == "label":
                label = value.get("label") if isinstance(value.get("label"), dict) else {}
                text = label.get("text")
                if text:
                    return str(text)
    return None


def _previous_price(card: dict[str, Any]) -> Decimal | None:
    for component in card.get("components") or []:
        found = _find_previous(component)
        if found is not None:
            return found
    return None


def _find_previous(node: Any) -> Decimal | None:
    if isinstance(node, dict):
        if node.get("previous") and node.get("value") is not None:
            parsed = money(node.get("value"))
            if parsed:
                return parsed
        for value in node.values():
            found = _find_previous(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_previous(item)
            if found is not None:
                return found
    return None
