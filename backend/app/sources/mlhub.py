from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector, SourceError
from app.sources.mercadolivre import (
    MercadoLivreSource,
    parse_mais_vendidos_cards,
    parse_ofertas_cards,
)
from app.sources.rate import TokenBucket

log = get_logger("mlhub")

HUB_URL = "https://www.mercadolivre.com.br/afiliados/hub?is_affiliate=true"
SEARCH_URL = "https://www.mercadolivre.com.br/affiliate-program/api/hub/search"
SITE = "https://www.mercadolivre.com.br"
_GANHOS_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_CTX_R = "_n.ctx.r="
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_PRELOADED = re.compile(
    r'<script[^>]+id="__PRELOADED_STATE__"[^>]*>(.*?)</script>',
    re.S,
)
_JSON_SCRIPT = re.compile(
    r'<script[^>]+type="application/json"[^>]*>(.*?)</script>',
    re.S,
)
_API_HINT = re.compile(
    r"https://[a-zA-Z0-9._/-]*(?:afiliad|affiliat|creators-hub|affiliates-hub)[a-zA-Z0-9._/?=&%-]*",
    re.I,
)
_LOGIN_MARKERS = (
    "iniciar sess",
    "digite seu e-mail",
    "/jms/mlb/lgz",
    "login.mercadolivre",
)


def _cookie_header(raw: str) -> str:
    value = raw.strip()
    if value.lower().startswith("cookie:"):
        value = value.split(":", 1)[1].strip()
    return value


def _is_ml_api_host(host: str) -> bool:
    host = host.lower()
    return host.endswith("mercadolivre.com.br") or host.endswith("mercadolibre.com")


class MlHubSource(SourceConnector):
    """Destaques do hub de afiliados. Usa a sessão que o dono colou no .env."""

    name = "mlhub"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.ml_hub_poll_seconds
        self.bucket = TokenBucket(0.6)
        self._client = client
        self._owns_client = client is None

    def is_enabled(self) -> bool:
        return bool(self.settings.enable_ml_hub and self.settings.ml_affiliate_cookie.strip())

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

    def _headers(self) -> dict[str, str]:
        return {
            "Cookie": _cookie_header(self.settings.ml_affiliate_cookie),
            "Referer": HUB_URL,
        }

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        cap = max(50, self.settings.ml_hub_max_items)
        pages = max(1, self.settings.ml_hub_pages_per_query)
        tagged: dict[str, dict[str, Any]] = {}
        first = await self._search(filters=[])
        if first is None:
            html, final_url, status = await self._get(HUB_URL)
            if _looks_like_login(html, final_url, status):
                log.warning("mlhub_login", status=status, url=urlparse(final_url).path)
                return []
            offers = self.offers_from_html(html, fetched_at=fetched_at)
            log.info("mlhub_poll", received=len(offers), via="html")
            return offers
        names = _category_names(first)
        await self._fill(tagged, filters=[], cap=cap, pages=pages, start=first)
        await self._fill(
            tagged,
            filters=[{"id": "extra_commission", "value": True}],
            cap=cap,
            pages=pages,
            extra=True,
        )
        await self._fill(
            tagged,
            filters=[{"id": "best_seller", "value": True}],
            cap=cap,
            pages=pages,
            best=True,
        )
        for category in names:
            if len(tagged) >= cap:
                break
            await self._fill(
                tagged,
                filters=[{"id": "category", "value": category}],
                cap=cap,
                pages=1,
                category=names[category],
            )
        offers = self.offers_from_cards(
            [row["card"] for row in tagged.values()],
            fetched_at=fetched_at,
            tags=tagged,
        )[:cap]
        log.info("mlhub_poll", received=len(offers), via="search", cards=len(tagged), cap=cap)
        return offers

    async def _fill(
        self,
        tagged: dict[str, dict[str, Any]],
        *,
        filters: list[dict[str, Any]],
        cap: int,
        pages: int,
        start: dict[str, Any] | None = None,
        category: str | None = None,
        extra: bool = False,
        best: bool = False,
    ) -> None:
        offset = 0
        used = 0
        seed = start
        while used < pages and len(tagged) < cap:
            payload = seed if seed is not None else await self._search(filters=filters, offset=offset)
            seed = None
            if payload is None:
                break
            cards = _polycards(payload)
            if not cards:
                break
            before = len(tagged)
            _absorb_cards(tagged, cards, category=category, extra=extra, best=best)
            used += 1
            nxt = _next_offset(payload, offset)
            if nxt is None or nxt <= offset:
                break
            if len(tagged) == before and used > 1:
                break
            offset = nxt

    def offers_from_html(self, html: str, *, fetched_at: datetime) -> list[NormalizedOffer]:
        cards = parse_mais_vendidos_cards(html) or parse_ofertas_cards(html)
        offers = self.offers_from_cards(cards, fetched_at=fetched_at)
        seen = {offer.native_product_id for offer in offers}
        for extra in self.normalize_items(extract_hub_items(html), fetched_at=fetched_at):
            if extra.native_product_id in seen:
                continue
            seen.add(extra.native_product_id)
            offers.append(extra)
        return offers

    def offers_from_cards(
        self,
        cards: list[dict[str, Any]],
        *,
        fetched_at: datetime,
        tags: dict[str, dict[str, Any]] | None = None,
    ) -> list[NormalizedOffer]:
        fallback = MercadoLivreSource(self.settings, client=self._http())
        offers = fallback._normalize_cards(cards, fetched_at=fetched_at, via="hub")
        commissions = _commissions_from_cards(cards)
        for offer in offers:
            rec = (tags or {}).get(offer.native_product_id) or {}
            names = [str(name) for name in rec.get("categories") or [] if name]
            extra = bool(rec.get("extra"))
            best = bool(rec.get("best"))
            offer.source = self.name
            offer.category = names[0] if names else "hub"
            offer.community_signals = {
                **(offer.community_signals or {}),
                "hub_categories": names,
                "hub_extra": extra,
                "hub_best": best,
            }
            pct = commissions.get(offer.native_product_id)
            if pct is not None:
                pretty = str(int(pct)) if pct == pct.to_integral() else str(pct)
                label = f"Ganhos extras {pretty}%" if extra else f"Ganhos {pretty}%"
                offer.description = label
                offer.payment_hint = label[:64]
                payload = dict(offer.raw_payload or {})
                payload["via"] = "hub"
                payload["commission_pct"] = str(pct)
                offer.raw_payload = payload
            elif not offer.description:
                offer.description = "Destaque do hub"
        return offers

    async def _search(self, *, filters: list[dict[str, Any]], offset: int = 0) -> dict[str, Any] | None:
        await self.bucket.acquire()
        response = await self._http().post(
            SEARCH_URL,
            params={"is_affiliate": "true", "device": "desktop"},
            headers={
                **self._headers(),
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": SITE,
            },
            json={"search": "", "filters": filters, "offset": offset},
        )
        if response.status_code in {401, 403}:
            log.warning("mlhub_login", status=response.status_code)
            return None
        if response.status_code >= 500:
            raise SourceError(f"Hub search {response.status_code}", retryable=True)
        if response.status_code != 200:
            log.warning("mlhub_search_skip", status=response.status_code)
            return None
        data = response.json()
        return data if isinstance(data, dict) else None

    async def _get(self, url: str) -> tuple[str, str, int]:
        await self.bucket.acquire()
        response = await self._http().get(url, headers=self._headers())
        if response.status_code >= 500:
            raise SourceError(f"Hub afiliados {response.status_code}", retryable=True)
        return response.text or "", str(response.url), response.status_code

    def normalize_items(self, items: list[dict[str, Any]], *, fetched_at: datetime) -> list[NormalizedOffer]:
        offers: list[NormalizedOffer] = []
        seen: set[str] = set()
        for raw in items:
            offer = self._to_offer(raw, fetched_at=fetched_at)
            if not offer or offer.native_product_id in seen:
                continue
            seen.add(offer.native_product_id)
            offers.append(offer)
        return offers

    def _to_offer(self, raw: dict[str, Any], *, fetched_at: datetime) -> NormalizedOffer | None:
        native = str(raw.get("id") or "").replace("-", "").upper()
        if not native.startswith("MLB"):
            return None
        price = money(raw.get("price"))
        if price is None:
            return None
        listed = money(raw.get("listed_price")) or price
        path = raw.get("url")
        if isinstance(path, str) and path.startswith("http"):
            purchase = sanitize_purchase_url(path)
        elif isinstance(path, str) and path:
            purchase = sanitize_purchase_url(f"https://{path.lstrip('/')}")
        else:
            purchase = sanitize_purchase_url(f"https://produto.mercadolivre.com.br/{native[:3]}-{native[3:]}")
        commission = money(raw.get("commission_pct"))
        hint = f"Ganhos {commission}%" if commission else None
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace="mercadolivre",
            merchant_id="",
            merchant_name="Mercado Livre",
            native_product_id=native,
            offer_id=native,
            product_name=str(raw.get("title") or "Destaque do hub"),
            category="hub",
            description=hint or "Destaque do hub",
            listed_price=listed,
            reported_price=price,
            verified_price=price,
            effective_price=price,
            currency="BRL",
            availability="in_stock",
            fetched_at=fetched_at,
            purchase_url=purchase,
            image_url=sanitize_media_url(raw.get("image")),
            payment_hint=hint,
            announced_discount_pct=_discount(price, listed),
            identity_confidence=IdentityConfidence.HIGH,
            price_verified=True,
            raw_payload={"id": native, "via": "hub", "commission_pct": str(commission) if commission else None},
        ).quantized()


def extract_hub_items(payload: str | dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    blobs: list[Any] = []
    if isinstance(payload, (dict, list)):
        blobs.append(payload)
    else:
        blobs.extend(_json_blobs(payload or ""))
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blob in blobs:
        _walk(blob, found, seen)
    return found


def _json_blobs(html: str) -> list[Any]:
    blobs: list[Any] = []
    idx = html.find(_CTX_R)
    if idx >= 0:
        try:
            data, _end = json.JSONDecoder().raw_decode(html[idx + len(_CTX_R) :])
            blobs.append(data)
        except json.JSONDecodeError:
            pass
    for pattern in (_NEXT_DATA, _PRELOADED, _JSON_SCRIPT):
        for match in pattern.finditer(html):
            try:
                blobs.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue
    stripped = html.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            blobs.append(json.loads(stripped))
        except json.JSONDecodeError:
            pass
    return blobs


def _walk(node: Any, found: list[dict[str, Any]], seen: set[str], depth: int = 0) -> None:
    if depth > 16 or len(found) > 400:
        return
    if isinstance(node, dict):
        item = _item_from(node)
        if item and item["id"] not in seen:
            seen.add(item["id"])
            found.append(item)
        for value in node.values():
            _walk(value, found, seen, depth + 1)
    elif isinstance(node, list):
        for child in node[:200]:
            _walk(child, found, seen, depth + 1)


def _item_from(node: dict[str, Any]) -> dict[str, Any] | None:
    native = _native_id(node)
    if not native:
        return None
    price = _price_of(node)
    if price is None:
        return None
    title = _title_of(node)
    return {
        "id": native,
        "title": title or "Destaque do hub",
        "price": price,
        "listed_price": _listed_of(node) or price,
        "url": _url_of(node),
        "image": _image_of(node),
        "commission_pct": _commission_of(node),
    }


def _native_id(node: dict[str, Any]) -> str | None:
    for key in ("id", "item_id", "itemId", "catalog_product_id", "product_id"):
        raw = str(node.get(key) or "").replace("-", "").upper()
        if raw.startswith("MLB") and raw[3:].isdigit():
            return raw
    meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    raw = str(meta.get("id") or "").replace("-", "").upper()
    if raw.startswith("MLB") and raw[3:].isdigit():
        return raw
    return None


def _price_of(node: dict[str, Any]) -> Decimal | None:
    for key in ("price", "amount", "value", "current_price"):
        parsed = money(node.get(key) if not isinstance(node.get(key), dict) else None)
        if parsed:
            return parsed
        block = node.get(key)
        if isinstance(block, dict):
            parsed = money(block.get("price") or block.get("value") or block.get("amount") or block.get("fraction"))
            if parsed:
                return parsed
    tracks = node.get("tracks") if isinstance(node.get("tracks"), dict) else {}
    price = tracks.get("price") if isinstance(tracks.get("price"), dict) else {}
    return money(price.get("price"))


def _listed_of(node: dict[str, Any]) -> Decimal | None:
    for key in ("original_price", "listed_price", "regular_price", "previous_price"):
        parsed = money(node.get(key) if not isinstance(node.get(key), dict) else node.get(key, {}).get("value"))
        if parsed:
            return parsed
    return None


def _title_of(node: dict[str, Any]) -> str | None:
    for key in ("title", "name", "product_name"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict) and value.get("text"):
            return str(value["text"]).strip()
    return None


def _url_of(node: dict[str, Any]) -> str | None:
    for key in ("permalink", "url", "link", "product_url"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    value = meta.get("url")
    return str(value) if value else None


def _image_of(node: dict[str, Any]) -> str | None:
    for key in ("thumbnail", "image", "picture", "secure_thumbnail"):
        value = node.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value if value.startswith("https") else f"https://{value[7:]}"
    pictures = node.get("pictures")
    if isinstance(pictures, dict):
        rows = pictures.get("pictures")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and rows[0].get("id"):
            return f"https://http2.mlstatic.com/D_NQ_NP_{rows[0]['id']}-O.webp"
    return None


def _commission_of(node: dict[str, Any]) -> Decimal | None:
    for key in ("commission", "commission_pct", "earning", "earnings", "rate", "ganhos"):
        value = node.get(key)
        if isinstance(value, dict):
            parsed = money(value.get("rate") or value.get("percentage") or value.get("value") or value.get("pct"))
            if parsed:
                return parsed
        parsed = money(value)
        if parsed:
            return parsed
    return None


def _polycards(payload: dict[str, Any]) -> list[dict[str, Any]]:
    model = payload.get("polycard_client_model") if isinstance(payload, dict) else {}
    rows = (model or {}).get("polycards") or []
    return [row for row in rows if isinstance(row, dict)]


def _next_offset(payload: dict[str, Any], offset: int) -> int | None:
    cards = _polycards(payload)
    if not cards:
        return None
    paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
    limit = paging.get("limit") or paging.get("page_size")
    total = paging.get("total")
    current = paging.get("offset")
    step = limit if isinstance(limit, int) and limit > 0 else len(cards)
    base = current if isinstance(current, int) else offset
    nxt = base + step
    if isinstance(total, int) and nxt >= total:
        return None
    if isinstance(limit, int) and limit > 0 and len(cards) < limit:
        return None
    if nxt <= offset:
        return None
    return nxt


def _card_id(card: dict[str, Any]) -> str:
    meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    return str(meta.get("id") or "").replace("-", "").upper()


def _category_names(payload: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for block in payload.get("filters") or []:
        if not isinstance(block, dict) or block.get("id") != "category":
            continue
        for value in block.get("values") or []:
            if not isinstance(value, dict):
                continue
            ident = str(value.get("id") or "")
            name = str(value.get("name") or "").strip()
            if ident.startswith("MLB") and name:
                found[ident] = name
    return found


def _absorb_cards(
    store: dict[str, dict[str, Any]],
    cards: list[dict[str, Any]],
    *,
    category: str | None = None,
    extra: bool = False,
    best: bool = False,
) -> None:
    for card in cards:
        native = _card_id(card)
        if not native:
            continue
        rec = store.get(native)
        if rec is None:
            rec = {"card": card, "categories": [], "extra": False, "best": False}
            store[native] = rec
        else:
            rec["card"] = card
        if category and category not in rec["categories"]:
            rec["categories"].append(category)
        rec["extra"] = rec["extra"] or extra or _card_flag_extra(card)
        rec["best"] = rec["best"] or best or _card_flag_best(card)


def _card_flag_extra(card: dict[str, Any]) -> bool:
    return "extras" in json.dumps(card, ensure_ascii=False).lower()


def _card_flag_best(card: dict[str, Any]) -> bool:
    return "mais vendido" in json.dumps(card, ensure_ascii=False).lower()


def _commissions_from_cards(cards: list[dict[str, Any]]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for card in cards:
        meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        native = str(meta.get("id") or "").replace("-", "").upper()
        pct = _commission_from_card(card)
        if native.startswith("MLB") and pct is not None:
            out[native] = pct
    return out


def _commission_from_card(card: dict[str, Any]) -> Decimal | None:
    for component in card.get("components") or []:
        if not isinstance(component, dict):
            continue
        ident = str(component.get("id") or "")
        if ident != "affiliates_commission_chip" and component.get("type") != "chip":
            continue
        match = _GANHOS_PCT.search(json.dumps(component, ensure_ascii=False))
        if match:
            return money(match.group(1).replace(",", "."))
    return None


def _discount(price: Decimal | None, original: Decimal | None) -> Decimal | None:
    if price is None or original is None or original <= 0 or price >= original:
        return None
    return money(((original - price) / original) * 100)


def _looks_like_login(html: str, final_url: str, status: int) -> bool:
    if status in {401, 403}:
        return True
    host = (urlparse(final_url).hostname or "").lower()
    path = (urlparse(final_url).path or "").lower()
    if "login" in host or "/jms/" in path or "/lgz" in path:
        return True
    low = (html or "").lower()
    return any(marker in low for marker in _LOGIN_MARKERS) and "afiliados/hub" not in path


def _api_paths_from(html: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in _API_HINT.findall(html or ""):
        url = raw.rstrip(").,]}>'\"")
        host = (urlparse(url).hostname or "").lower()
        if not _is_ml_api_host(host) or url in seen:
            continue
        seen.add(url)
        found.append(url)
        if len(found) >= 6:
            break
    return found
