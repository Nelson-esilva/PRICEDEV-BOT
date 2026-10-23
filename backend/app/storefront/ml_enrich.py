"""Completa as ofertas do Mercado Livre com o catálogo oficial.

Para cada oferta ML com produto de catálogo: fotos oficiais (galeria), frete grátis do anúncio,
categoria oficial (raiz do ML -> categoria pública) e posição no ranking de mais vendidos
("3º mais vendido em Monitores"). As chamadas à API acontecem fora de transação; a escrita é
uma sessão curta no fim, para não segurar o SQLite.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select

from app.core.config import Settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.models.entities import Opportunity, Product, PublishedDeal
from app.sources.mlapi import MlApi, ml_api_enabled
from app.sources.mlofficial import gallery_of, ranking_label, root_category
from app.storefront.taxonomy import ML_ROOT_KEYS

log = get_logger("ml_enrich")

ML_SOURCES = ("mlhub", "mlofficial")


async def _targets(settings: Settings, now: datetime) -> list[tuple[str, str, str, list[Decimal]]]:
    stale = now - timedelta(hours=max(1, settings.ml_enrich_refresh_hours))
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(Opportunity.id, Opportunity.catalog_product_id, Product.native_product_id,
                   Opportunity.current_price, Opportunity.regular_price)
            .join(Product, Product.id == Opportunity.product_id)
            .outerjoin(PublishedDeal, (PublishedDeal.opportunity_id == Opportunity.id) & (PublishedDeal.status == "active"))
            .where(
                Opportunity.source.in_(ML_SOURCES),
                Opportunity.status == "active",
                Opportunity.catalog_product_id.is_not(None),
                or_(Opportunity.enriched_at.is_(None), Opportunity.enriched_at < stale),
            )
            # Primeiro o que está no site, depois o que nunca foi completado.
            .order_by(PublishedDeal.id.is_(None), Opportunity.enriched_at.is_not(None), Opportunity.enriched_at)
            .limit(settings.ml_enrich_batch)
        )
        return [
            (opp_id, catalog_id, native, [p for p in (price, regular) if p is not None])
            for opp_id, catalog_id, native, price, regular in rows.all()
        ]


async def details(api: MlApi, catalog_id: str, native: str, prices: list[Decimal] | None = None) -> dict[str, Any]:
    """Campos oficiais de um produto de catálogo.

    O anúncio que decide o frete é o de id `native`; quando o hub aponta para a página do produto
    (id = catálogo), é o anúncio com o mesmo preço (normal ou "nos outros meios"). Sem nenhum dos dois,
    frete grátis só se todos os anúncios do produto têm.
    """
    out: dict[str, Any] = {}
    product = await api.get(f"/products/{catalog_id}") or {}
    gallery = gallery_of(product) if isinstance(product, dict) else []
    if gallery:
        out["gallery"] = gallery
    listings = await api.get(f"/products/{catalog_id}/items") or {}
    rows = [r for r in listings.get("results") or [] if isinstance(r, dict)] if isinstance(listings, dict) else []
    mine = next((r for r in rows if str(r.get("item_id") or "").upper() == native.upper()), None)
    if mine is None and prices:
        mine = next((r for r in rows if money(r.get("price")) in prices), None)
    free = [bool((r.get("shipping") or {}).get("free_shipping")) for r in ([mine] if mine else rows) if isinstance(r.get("shipping"), dict)]
    if free:
        out["free_shipping"] = all(free)
    reference = mine or (rows[0] if rows else None)
    if reference is not None:
        key = ML_ROOT_KEYS.get(await root_category(api, str(reference.get("category_id") or "")) or "")
        if key:
            out["official_category"] = key
    rank = await api.get(f"/highlights/MLB/product/{catalog_id}")
    # Só ranking por categoria: os por marca ("Perfumes Primacial") não fazem uma página útil.
    ranked = isinstance(rank, dict) and rank.get("dimension") == "category" and isinstance(rank.get("position"), int) and rank.get("id")
    label = await ranking_label(api, str(rank["id"])) if ranked else None
    if ranked and label:
        out.update(rank_position=rank["position"], rank_category=label[:120], rank_category_id=str(rank["id"])[:32])
    else:
        # Saiu do ranking: não deixa posição velha no site.
        out.update(rank_position=None, rank_category=None, rank_category_id=None)
    return out


async def enrich_batch(settings: Settings, *, api: MlApi | None = None, now: datetime | None = None) -> int:
    if not ml_api_enabled(settings):
        return 0
    moment = now or utcnow()
    targets = await _targets(settings, moment)
    if not targets:
        return 0
    owned = api is None
    api = api or MlApi(settings)
    updates: dict[str, dict[str, Any]] = {}
    try:
        for opp_id, catalog_id, native, prices in targets:
            try:
                updates[opp_id] = await details(api, catalog_id, native, prices)
            except Exception as exc:
                log.warning("ml_enrich_item", catalog_id=catalog_id, error=str(exc)[:160])
                if "401" in str(exc) or "OAuth" in str(exc):
                    break
    finally:
        if owned:
            await api.close()
    async with get_session_factory()() as session:
        rows = (await session.execute(select(Opportunity).where(Opportunity.id.in_(list(updates))))).scalars().all()
        for opportunity in rows:
            for key, value in updates[opportunity.id].items():
                setattr(opportunity, key, value)
            if updates[opportunity.id].get("rank_position"):
                opportunity.best_seller = True
            opportunity.enriched_at = moment
        await session.commit()
    log.info("ml_enrich_ok", items=len(updates), ranked=sum(1 for u in updates.values() if u.get("rank_position")))
    return len(updates)


async def run_ml_enrich(settings: Settings) -> None:
    while True:
        try:
            await enrich_batch(settings)
        except Exception as exc:
            log.warning("ml_enrich_failed", error=str(exc)[:200])
        await asyncio.sleep(max(120, settings.ml_enrich_poll_seconds))
