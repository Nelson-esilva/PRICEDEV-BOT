"""Promoções dos grupos de Telegram (inbox) para lojas sem API própria: Amazon e KaBuM.

Só entram mensagens cujo link já foi trocado pelo nosso afiliado. O grupo de origem nunca aparece:
no site a oferta é da loja. Não reposta no Telegram (o inbox já faz isso).

- KaBuM: a página do produto (JSON do Next.js) confirma preço, preço no Pix/à vista, preço "de",
  disponibilidade, frete grátis, Oferta Ninja e fotos. Esgotado não entra.
- Amazon: sem fonte oficial de preço; vale o da postagem, com validade curta. Foto oficial pelo ASIN
  quando existir, senão a do grupo.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.inbox.parse import parse_deal
from app.models.entities import InboxMessage
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector
from app.sources.mercadolivre import _discount
from app.sources.rate import TokenBucket

log = get_logger("community")

BROWSER = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_ASIN = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})")
# Foto do grupo vira URL pública (a do inbox fica atrás do token de operação).
_INBOX_MEDIA = "/api/v1/inbox/media/"
PUBLIC_MEDIA = "/api/public/v1/media/"
# A Amazon devolve um GIF de 43 bytes quando o ASIN não tem imagem nesse endpoint.
_MIN_IMAGE_BYTES = 1000


class CommunitySource(SourceConnector):
    name = "grupos"
    # O inbox já publica essas mensagens no Telegram; aqui é só para o site.
    telegram = False

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.community_poll_seconds
        self.bucket = TokenBucket(1.0)
        self._client = client
        self._owns_client = client is None
        self._kabum: dict[str, tuple[datetime, dict[str, Any] | None]] = {}
        self._amazon_images: dict[str, str | None] = {}

    def is_enabled(self) -> bool:
        return bool(self.settings.enable_community_deals and self.settings.community_store_list)

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=BROWSER)
        return self._client

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        since = fetched_at - timedelta(hours=self.settings.community_ttl_hours)
        async with get_session_factory()() as session:
            rows = (await session.execute(
                select(InboxMessage)
                .where(
                    InboxMessage.marketplace.in_(self.settings.community_store_list),
                    InboxMessage.affiliate_url.is_not(None),
                    InboxMessage.received_at >= since,
                )
                .order_by(InboxMessage.received_at.desc())
            )).scalars().all()
        offers: dict[tuple[str, str], NormalizedOffer] = {}
        for row in rows:
            key = (str(row.marketplace), str(row.native_product_id or ""))
            # Mais recente primeiro: a mesma oferta repostada por vários grupos entra uma vez.
            if not key[1] or key in offers:
                continue
            try:
                offer = await self._offer(row)
            except Exception as exc:
                log.warning("community_skip", store=row.marketplace, error=str(exc)[:160])
                continue
            if offer is not None:
                offers[key] = offer
        log.info("community_poll", messages=len(rows), offers=len(offers))
        return list(offers.values())

    async def _offer(self, row: InboxMessage) -> NormalizedOffer | None:
        parsed = parse_deal(row.body, fallback=row.product_name or "Oferta")
        if row.marketplace == "kabum":
            return await self._kabum_offer(row, parsed)
        if row.marketplace == "amazon":
            return await self._amazon_offer(row, parsed)
        return None

    async def _kabum_offer(self, row: InboxMessage, parsed) -> NormalizedOffer | None:
        native = str(row.native_product_id)
        product = await self._kabum_product(native)
        if product is None:
            return None
        facts = kabum_facts(product)
        if facts is None or not facts["sellable"]:
            return None
        return community_offer(
            row,
            parsed,
            marketplace="kabum",
            native=native,
            title=facts["title"] or parsed.title,
            purchase_url=f"https://www.kabum.com.br/produto/{native}",
            price=facts["price"],
            listed=facts["listed"],
            regular=facts["regular"],
            image=facts["gallery"][0] if facts["gallery"] else _public_media(row.image_url),
            gallery=facts["gallery"],
            free_shipping=facts["free_shipping"],
            verified=True,
            category=facts["category"],
        )

    async def _amazon_offer(self, row: InboxMessage, parsed) -> NormalizedOffer | None:
        asin = str(row.native_product_id or "")
        if not re.fullmatch(r"[A-Z0-9]{10}", asin) or parsed.price is None:
            return None
        image = await self._amazon_image(asin) or _public_media(row.image_url)
        return community_offer(
            row,
            parsed,
            marketplace="amazon",
            native=asin,
            title=parsed.title,
            purchase_url=f"https://www.amazon.com.br/dp/{asin}",
            price=parsed.price,
            listed=parsed.listed_price,
            regular=None,
            image=image,
            gallery=[image] if image else None,
            free_shipping=None,
            verified=False,
            category=None,
        )

    async def _kabum_product(self, native: str) -> dict[str, Any] | None:
        cached = self._kabum.get(native)
        # A página muda de preço ao longo do dia; 20 min de cache basta entre ciclos.
        if cached and utcnow() - cached[0] < timedelta(minutes=20):
            return cached[1]
        await self.bucket.acquire()
        response = await self._http().get(f"https://www.kabum.com.br/produto/{native}")
        product = kabum_product(response.text) if response.status_code == 200 else None
        self._kabum[native] = (utcnow(), product)
        return product

    async def _amazon_image(self, asin: str) -> str | None:
        if asin not in self._amazon_images:
            url = f"https://m.media-amazon.com/images/P/{asin}.01._SCLZZZZZZZ_.jpg"
            try:
                response = await self._http().get(url)
                ok = response.status_code == 200 and len(response.content) > _MIN_IMAGE_BYTES
            except httpx.HTTPError:
                ok = False
            self._amazon_images[asin] = url if ok else None
        return self._amazon_images[asin]


def kabum_product(html: str) -> dict[str, Any] | None:
    match = _NEXT_DATA.search(html or "")
    if not match:
        return None
    try:
        product = json.loads(match.group(1))["props"]["pageProps"]["product"]
    except (ValueError, KeyError, TypeError):
        return None
    return product if isinstance(product, dict) else None


def kabum_facts(product: dict[str, Any]) -> dict[str, Any] | None:
    prices = product.get("prices") if isinstance(product.get("prices"), dict) else {}
    regular = money(prices.get("price") or product.get("price"))
    cash = money(prices.get("priceWithDiscount")) or regular
    if cash is None:
        return None
    old = money(prices.get("oldPrice"))
    flags = product.get("flags") if isinstance(product.get("flags"), dict) else {}
    gallery: list[str] = []
    for media in product.get("medias") or []:
        images = media.get("images") if isinstance(media, dict) and isinstance(media.get("images"), dict) else {}
        url = images.get("gg") or images.get("g") or images.get("m")
        if url:
            gallery.append(str(url))
    top = max(x for x in (old, regular, cash) if x is not None)
    return {
        "title": str(product.get("title") or "").strip() or None,
        "price": cash,
        # Preço "de" só quando a loja informa um maior que o atual.
        "listed": top if top > cash else None,
        # À vista/Pix mais barato que o parcelado: mostra a condição como no ML.
        "regular": regular if regular and regular > cash else None,
        # Pré-venda também é compra possível.
        "sellable": bool(product.get("available") or product.get("preOrderDate")),
        "free_shipping": bool(flags.get("isFreeShipping")) or None,
        "flash": bool(flags.get("isFlash")),
        "gallery": gallery[:8],
        "category": str(product.get("category") or "").split("/")[0] or None,
    }


def community_offer(
    row: InboxMessage,
    parsed,
    *,
    marketplace: str,
    native: str,
    title: str,
    purchase_url: str,
    price: Decimal,
    listed: Decimal | None,
    regular: Decimal | None,
    image: str | None,
    gallery: list[str] | None,
    free_shipping: bool | None,
    verified: bool,
    category: str | None,
) -> NormalizedOffer:
    listed = listed if listed and listed > price else None
    # Preço conferido na loja vale de agora; o da postagem, de quando foi postado (a validade conta dali).
    observed = utcnow() if verified else (row.posted_at or row.received_at or utcnow())
    return NormalizedOffer(
        source="grupos",
        source_record_id=f"{marketplace}:{native}",
        marketplace=marketplace,
        merchant_id="",
        merchant_name={"amazon": "Amazon", "kabum": "KaBuM!"}.get(marketplace, marketplace),
        native_product_id=native,
        offer_id=native,
        product_name=title[:300],
        category=category or "grupos",
        listed_price=listed or price,
        reported_price=parsed.price or price,
        verified_price=price,
        effective_price=price,
        currency="BRL",
        availability="in_stock",
        fetched_at=observed,
        purchase_url=purchase_url,
        affiliate_url=row.affiliate_url,
        image_url=image,
        gallery=gallery or None,
        coupon_code=parsed.coupon,
        payment_hint=parsed.installment_hint,
        free_shipping=free_shipping,
        announced_discount_pct=_discount(price, listed),
        price_condition="pix" if regular else None,
        regular_price=regular,
        identity_confidence=IdentityConfidence.HIGH,
        price_verified=verified,
        raw_payload={"inbox_id": row.id, "via": "grupos"},
    ).quantized()


def _public_media(url: str | None) -> str | None:
    if url and url.startswith(_INBOX_MEDIA):
        return PUBLIC_MEDIA + url[len(_INBOX_MEDIA):]
    return url
