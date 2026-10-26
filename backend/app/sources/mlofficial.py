from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.models.entities import Opportunity, Product
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector
from app.sources.mercadolivre import _discount
from app.sources.mlapi import MlApi, RateLimited, ml_api_enabled
from app.storefront.taxonomy import ML_ROOT_KEYS
from app.storefront.trends import save_trends

log = get_logger("mlofficial")

# Itens que o hub viu há pouco ficam com ele: o card do hub traz o preço no Pix / com cupom,
# a API só o preço normal — alternar entre os dois bagunçaria preço e histórico.
HUB_FRESH = timedelta(hours=6)
# Cartão-presente / crédito digital lidera vários rankings, mas não é oferta.
_NOT_A_DEAL = re.compile(
    r"gift ?card|cart[aã]o[- ]presente|vale[- ]presente|recarga|cr[eé]dito digital|\(digital\)|razer gold|"
    r"google play|playstation store|steam wallet|nintendo eshop",
    re.I,
)
GALLERY_MAX = 8
CATEGORY_LABELS = {
    "MLB1051": "Celulares e Telefones",
    "MLB1648": "Informática",
    "MLB1000": "Eletrônicos, Áudio e Vídeo",
    "MLB1574": "Casa, Móveis e Decoração",
    "MLB5726": "Eletrodomésticos",
    "MLB1276": "Esportes e Fitness",
    "MLB1246": "Beleza e Cuidado Pessoal",
    "MLB1144": "Games",
    "MLB1132": "Brinquedos e Hobbies",
    "MLB263532": "Ferramentas",
    "MLB1384": "Bebês",
    "MLB1071": "Animais",
    "MLB1430": "Calçados, Roupas e Bolsas",
}
# Categoria do ML -> caminho desde a raiz ([{id, name}, ...]); muda raramente, vale o processo inteiro.
_PATHS: dict[str, list[dict[str, Any]]] = {}
_LOOSE_LABEL = re.compile(r"^(de|da|do|para|com|sem|em)\b", re.I)


class MlOfficialSource(SourceConnector):
    """Catálogo oficial do ML (OAuth do DevCenter).

    - /highlights: mais vendidos das categorias raiz e de categorias específicas ("monitor" -> Monitores),
      que alimentam as páginas de ranking.
    - /trends: termos mais buscados; ficam salvos para priorizar ofertas e buscar esses termos nas lojas.
    - /products/search: ofertas de catálogo dos termos em alta.
    /items, /sale_price e a busca geral respondem 403 para apps comuns.
    """

    name = "mlofficial"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.ml_official_poll_seconds
        self.api = MlApi(settings, client=client)
        # Nome/fotos/link do produto quase não mudam: evita 1 chamada por produto a cada ciclo.
        self._products: dict[str, dict[str, Any]] = {}
        self._leaves: dict[str, tuple[str, str] | None] = {}

    def is_enabled(self) -> bool:
        return ml_api_enabled(self.settings)

    async def close(self) -> None:
        await self.api.close()

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        skip = await _hub_covered(fetched_at - HUB_FRESH)
        offers: dict[str, NormalizedOffer] = {}

        def keep(offer: NormalizedOffer | None) -> None:
            if offer is None or offer.native_product_id in skip:
                return
            current = offers.get(offer.native_product_id)
            # Mesmo produto em dois rankings: fica a posição da categoria mais específica.
            replace = current is None or (
                offer.rank_position is not None
                and (current.rank_position is None or current.rank_category_id in CATEGORY_LABELS)
            )
            if replace:
                offers[offer.native_product_id] = offer

        # Termos em alta primeiro: poucas chamadas, e o site depende deles mesmo se o resto falhar.
        terms = await self._trends()
        try:
            for term in terms[: self.settings.ml_trend_search_terms]:
                found = await self.api.get(f"/products/search?status=active&site_id=MLB&q={quote(term)}&limit=5") or {}
                for product in found.get("results") or []:
                    if isinstance(product, dict) and product.get("id"):
                        self._products.setdefault(str(product["id"]), product)
                        keep(await self._product_offer(str(product["id"]), fetched_at))
            for category_id, label in await self._ranking_categories():
                ranking = await self.api.get(f"/highlights/MLB/category/{category_id}") or {}
                entries = [e for e in ranking.get("content") or [] if isinstance(e, dict) and e.get("type") == "PRODUCT"]
                for entry in entries[: self.settings.ml_official_per_category]:
                    keep(await self._product_offer(
                        str(entry.get("id") or ""), fetched_at,
                        rank=(entry.get("position"), category_id, label),
                    ))
        except RateLimited:
            # Limite do ML mesmo após as novas tentativas: fica o que já veio; o resto no próximo ciclo.
            log.warning("mlofficial_partial", received=len(offers), reason="429")
        log.info("mlofficial_poll", received=len(offers), skipped_hub=len(skip), trends=len(terms))
        return list(offers.values())

    async def _ranking_categories(self) -> list[tuple[str, str]]:
        """Raízes configuradas + categorias específicas descobertas pelos termos de ranking."""
        pairs = [(c, CATEGORY_LABELS.get(c, c)) for c in self.settings.ml_official_category_list]
        for term in self.settings.ml_ranking_term_list:
            if term not in self._leaves:
                found = await self.api.get(f"/sites/MLB/domain_discovery/search?limit=1&q={quote(term)}") or []
                first = found[0] if isinstance(found, list) and found and isinstance(found[0], dict) else {}
                category_id = str(first.get("category_id") or "")
                label = await ranking_label(self.api, category_id) if category_id else None
                self._leaves[term] = (category_id, label or str(first.get("domain_name") or term.title())) if category_id else None
            if self._leaves[term]:
                pairs.append(self._leaves[term])
        return list(dict.fromkeys(pairs))

    async def _trends(self) -> list[str]:
        terms: list[str] = []
        for path in ["/trends/MLB"] + [f"/trends/MLB/{c}" for c in self.settings.ml_official_category_list]:
            rows = await self.api.get(path) or []
            # Por categoria só os primeiros: o fim da lista é cauda longa.
            limit = None if path == "/trends/MLB" else 5
            terms += [str(r.get("keyword")) for r in rows[:limit] if isinstance(r, dict) and r.get("keyword")]
        return save_trends(terms) if terms else []

    async def _product_offer(
        self, product_id: str, fetched_at: datetime, *, rank: tuple[Any, str, str] | None = None
    ) -> NormalizedOffer | None:
        if not product_id.startswith("MLB"):
            return None
        listings = await self.api.get(f"/products/{product_id}/items") or {}
        item = best_listing(listings.get("results") or [])
        if item is None:
            return None
        product = self._products.get(product_id)
        if product is None or "permalink" not in product:
            product = await self.api.get(f"/products/{product_id}") or product or {}
            if product:
                self._products[product_id] = product
        root = await root_category(self.api, str(item.get("category_id") or ""))
        return offer_from_catalog(product, item, rank=rank, official_category=ML_ROOT_KEYS.get(root or ""), fetched_at=fetched_at)


async def category_path(api: MlApi, category_id: str) -> list[dict[str, Any]]:
    if not category_id:
        return []
    if category_id not in _PATHS:
        data = await api.get(f"/categories/{category_id}") or {}
        _PATHS[category_id] = [p for p in data.get("path_from_root") or [] if isinstance(p, dict) and p.get("id")]
    return _PATHS[category_id]


async def root_category(api: MlApi, category_id: str) -> str | None:
    path = await category_path(api, category_id)
    return str(path[0]["id"]) if path else None


async def ranking_label(api: MlApi, category_id: str) -> str | None:
    """Nome legível do ranking pela árvore oficial: "De Ar" sozinho vira "Fritadeiras de ar"."""
    path = await category_path(api, category_id)
    if not path:
        return None
    name = str(path[-1].get("name") or "").strip()
    if len(path) > 1 and (_LOOSE_LABEL.match(name) or len(name.split()) == 1 and name.endswith(("os", "as")) and name[0].isupper() and name.lower() in _ADJECTIVES):
        return f"{path[-2]['name']} {name[0].lower()}{name[1:]}"
    return name or None


# Nomes de subcategoria que são só adjetivo ("Elétricos") e precisam do pai ("Fogões elétricos").
_ADJECTIVES = {"elétricos", "elétricas", "manuais", "automáticos", "automáticas", "portáteis", "digitais", "infantis", "profissionais"}


def best_listing(results: list[Any]) -> dict[str, Any] | None:
    """Anúncio mais barato do produto de catálogo (o que costuma ganhar a vitrine)."""
    rows = [r for r in results if isinstance(r, dict) and money(r.get("price")) and r.get("item_id")]
    return min(rows, key=lambda r: money(r.get("price"))) if rows else None


def gallery_of(product: dict[str, Any]) -> list[str]:
    pictures = product.get("pictures") if isinstance(product.get("pictures"), list) else []
    urls = [sanitize_media_url(p.get("url")) for p in pictures if isinstance(p, dict) and p.get("url")]
    return [u for u in dict.fromkeys(urls) if u][:GALLERY_MAX]


def offer_from_catalog(
    product: dict[str, Any],
    item: dict[str, Any],
    *,
    fetched_at: datetime,
    rank: tuple[Any, str, str] | None = None,
    official_category: str | None = None,
) -> NormalizedOffer | None:
    native = str(item.get("item_id") or "").replace("-", "").upper()
    price = money(item.get("price"))
    if not native.startswith("MLB") or price is None or _NOT_A_DEAL.search(str(product.get("name") or "")):
        return None
    original = money(item.get("original_price"))
    gallery = gallery_of(product)
    product_id = str(product.get("id") or item.get("catalog_product_id") or "")
    permalink = product.get("permalink") or (f"https://www.mercadolivre.com.br/p/{product_id}" if product_id else None)
    shipping = item.get("shipping") if isinstance(item.get("shipping"), dict) else {}
    position, rank_id, rank_label = rank if rank and isinstance(rank[0], int) else (None, None, None)
    return NormalizedOffer(
        source="mlofficial",
        source_record_id=native,
        marketplace="mercadolivre",
        merchant_id="",
        merchant_name="Mercado Livre",
        native_product_id=native,
        offer_id=native,
        product_name=str(product.get("name") or "Produto Mercado Livre"),
        category=official_category or rank_label or "catalogo",
        description=f"{position}º mais vendido em {rank_label}" if position else None,
        listed_price=original if original and original > price else price,
        reported_price=price,
        verified_price=price,
        effective_price=price,
        currency=str(item.get("currency_id") or "BRL"),
        availability="in_stock",
        fetched_at=fetched_at,
        purchase_url=sanitize_purchase_url(permalink) if permalink else None,
        image_url=gallery[0] if gallery else None,
        free_shipping=bool(shipping.get("free_shipping")) if shipping else None,
        announced_discount_pct=_discount(price, original),
        best_seller=True if position else None,
        catalog_product_id=product_id or None,
        gallery=gallery or None,
        rank_position=position,
        rank_category=rank_label,
        rank_category_id=rank_id,
        official_category=official_category,
        identity_confidence=IdentityConfidence.HIGH,
        price_verified=True,
        raw_payload={"id": native, "product_id": product_id, "via": "highlights" if position else "catalogo"},
    ).quantized()


async def _hub_covered(since: datetime) -> set[str]:
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(Product.native_product_id)
            .join(Opportunity, Opportunity.product_id == Product.id)
            .where(Opportunity.source == "mlhub", Opportunity.fetched_at >= since)
        )
        return {str(native) for native in rows.scalars()}
