from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session, utcnow
from app.core.search import any_contains
from app.inbox.media import media_path
from app.models.entities import PublishedDeal, PublicPromotion
from app.schemas.public import PublicDealListOut, PublicDealOut
from app.storefront.catalog import STORE_LABELS
from app.storefront.taxonomy import CATEGORIES

router = APIRouter()
MAX_SHOWCASE_DISCOUNT = Decimal('85')


def _to_out(deal: PublishedDeal) -> PublicDealOut:
    return PublicDealOut.model_validate(deal).model_copy(update={"go_path": f"/go/{deal.slug}"})


def _live_filters(stmt, now):
    return stmt.where(PublishedDeal.status == "active", PublishedDeal.expires_at > now)


@router.get('/deals', response_model=PublicDealListOut)
async def list_public_deals(
    session: AsyncSession = Depends(get_session), q: str | None = None,
    store: str | None = None, category: str | None = None,
    sort: Literal['featured', 'best_selling', 'recent', 'discount', 'price_asc', 'price_desc', 'rank'] = 'recent',
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    min_discount: Decimal | None = Query(default=None, ge=0, le=100),
    has_coupon: bool = False, ids: str | None = Query(default=None, max_length=4000),
    trending: bool = False, ranking: str | None = Query(default=None, max_length=32),
    pix: bool = False, free_shipping: bool = False, best_seller: bool = False, single_price: bool = False,
    min_rating: Decimal | None = Query(default=None, ge=0, le=5), min_sales: int | None = Query(default=None, ge=0),
    limit: int = Query(default=24, ge=1, le=120), offset: int = Query(default=0, ge=0),
) -> PublicDealListOut:
    now = utcnow()
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, 'invalid_price_range')
    filters = [PublishedDeal.status == 'active', PublishedDeal.expires_at > now]
    search = any_contains([PublishedDeal.product_name, PublishedDeal.merchant, PublishedDeal.description], q)
    if search is not None:
        filters.append(search)
    if store:
        filters.append(PublishedDeal.store == store.strip().lower())
    if category:
        # Só a categoria gravada: buscar palavras no título punha "controle compatível com celular" em Celulares.
        filters.append(PublishedDeal.category == category)
    if min_price is not None:
        filters.append(PublishedDeal.current_price >= min_price)
    if max_price is not None:
        filters.append(PublishedDeal.current_price <= max_price)
    discount = func.coalesce(PublishedDeal.discount_pct, PublishedDeal.announced_discount_pct)
    if min_discount is not None:
        filters.append(discount >= min_discount)
    if sort == 'discount':
        # Faixa de preço ("até −96%" numa variação de R$ 0,49) e desconto acima de 85% (preço "de"
        # quase sempre inflado) parecem isca: ficam fora da vitrine de maiores descontos.
        filters.extend([discount > 0, discount <= MAX_SHOWCASE_DISCOUNT, PublishedDeal.price_max.is_(None)])
    if has_coupon:
        filters.append(func.length(func.trim(func.coalesce(PublishedDeal.coupon_code, ''))) > 0)
    if trending:
        filters.append(PublishedDeal.trending.is_(True))
    if pix:
        filters.append(PublishedDeal.price_condition == 'pix')
    if single_price:
        # Vitrines da home: sem anúncio com faixa de preço ("a partir de R$ 0,49" de uma variação).
        filters.append(PublishedDeal.price_max.is_(None))
    if best_seller:
        filters.append(or_(PublishedDeal.best_seller.is_(True), PublishedDeal.rank_position.is_not(None)))
    if min_rating is not None:
        filters.append(PublishedDeal.rating >= min_rating)
    if min_sales is not None:
        filters.append(PublishedDeal.sales_count >= min_sales)
    if free_shipping:
        filters.append(PublishedDeal.free_shipping.is_(True))
    if ranking:
        filters.append(PublishedDeal.rank_category_id == ranking)
        filters.append(PublishedDeal.rank_position.is_not(None))
    if ids is not None:
        wanted = [value for value in ids.split(',') if value][:100]
        filters.append(PublishedDeal.id.in_(wanted))
    orders = {
        # Destaques = score de demanda (vendas, nota, desconto, comissão, cliques e pedidos reais).
        'featured': (PublishedDeal.demand_score.desc(), PublishedDeal.updated_at.desc()),
        'best_selling': (PublishedDeal.orders_30d.desc(), PublishedDeal.clicks_7d.desc(),
            func.coalesce(PublishedDeal.sales_count, 0).desc()),
        'recent': (PublishedDeal.updated_at.desc(),), 'discount': (discount.desc(),),
        'price_asc': (PublishedDeal.current_price.asc(),), 'price_desc': (PublishedDeal.current_price.desc(),),
        'rank': (PublishedDeal.rank_position.asc().nullslast(), PublishedDeal.demand_score.desc()),
    }
    total = (await session.execute(select(func.count()).select_from(PublishedDeal).where(*filters))).scalar_one()
    rows = (await session.execute(select(PublishedDeal).where(*filters)
        .order_by(*orders[sort], PublishedDeal.id.asc()).offset(offset).limit(limit))).scalars().all()
    return PublicDealListOut(items=[_to_out(row) for row in rows], total=total)


@router.get('/deals/{slug}', response_model=PublicDealOut)
async def get_public_deal(slug: str, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(_live_filters(select(PublishedDeal), utcnow()).where(
        or_(PublishedDeal.slug == slug, PublishedDeal.id == slug)))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, 'oferta_encerrada')
    return _to_out(row)


def live_promotions(now):
    return [PublicPromotion.status == 'active',
        or_(PublicPromotion.starts_at.is_(None), PublicPromotion.starts_at <= now),
        or_(PublicPromotion.expires_at.is_(None), PublicPromotion.expires_at > now),
        PublicPromotion.updated_at > now - timedelta(hours=24)]


def promotion_out(row):
    return dict(id=row.id, slug=row.slug, store=row.store, kind=row.kind, title=row.title,
        description=row.description, terms=row.terms, code=row.code, image_url=row.image_url,
        starts_at=row.starts_at, expires_at=row.expires_at, updated_at=row.updated_at,
        go_path=f'/go/promotions/{row.slug}')


@router.get('/promotions')
async def list_promotions(session: AsyncSession = Depends(get_session), store: str | None = None,
    kind: Literal['campaign', 'coupon'] | None = None, q: str | None = None,
    limit: int = Query(default=24, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    filters = live_promotions(utcnow())
    if store:
        filters.append(PublicPromotion.store == store)
    if kind:
        filters.append(PublicPromotion.kind == kind)
    search = any_contains([PublicPromotion.title, PublicPromotion.description], q)
    if search is not None:
        filters.append(search)
    total = (await session.execute(select(func.count()).select_from(PublicPromotion).where(*filters))).scalar_one()
    rows = (await session.execute(select(PublicPromotion).where(*filters).order_by(
        PublicPromotion.expires_at.asc().nullslast(), PublicPromotion.id).offset(offset).limit(limit))).scalars().all()
    return {'items': [promotion_out(row) for row in rows], 'total': total}


@router.get('/promotions/{slug}')
async def get_promotion(slug: str, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(select(PublicPromotion).where(
        *live_promotions(utcnow()), PublicPromotion.slug == slug))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, 'campanha_encerrada')
    return promotion_out(row)


@router.get('/stores')
async def list_stores(session: AsyncSession = Depends(get_session)):
    now = utcnow()
    counts = dict((await session.execute(select(PublishedDeal.store, func.count()).where(
        PublishedDeal.status == 'active', PublishedDeal.expires_at > now).group_by(PublishedDeal.store))).all())
    return {'items': [{'id': key, 'label': label, 'count': counts.get(key, 0)} for key, label in STORE_LABELS.items()]}


@router.get('/site')
async def site_info(session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    """Dados do cabeçalho, menu lateral e rodapé: link do grupo e ofertas ativas por loja."""
    stores = await list_stores(session=session)
    return {'telegram_url': settings.public_telegram_url.strip() or None, 'stores': stores['items']}


@router.get('/categories')
async def list_categories(session: AsyncSession = Depends(get_session)):
    counts = dict((await session.execute(select(PublishedDeal.category, func.count()).where(
        PublishedDeal.status == 'active', PublishedDeal.expires_at > utcnow()).group_by(PublishedDeal.category))).all())
    return {'items': [{'id': key, 'label': value[0], 'count': counts.get(key, 0)} for key, value in CATEGORIES.items()]}


@router.get('/media/{name}')
async def public_media(name: str):
    """Fotos de ofertas vindas dos grupos (a rota do inbox exige o token de operação)."""
    path = media_path(name)
    if path is None:
        raise HTTPException(404)
    return FileResponse(path, headers={'Cache-Control': 'public, max-age=86400'})


@router.get('/rankings')
async def list_rankings(session: AsyncSession = Depends(get_session), min_items: int = Query(default=3, ge=1, le=20)):
    """Rankings oficiais de mais vendidos com ofertas no site, com a capa do 1º colocado."""
    now = utcnow()
    live = (PublishedDeal.status == 'active', PublishedDeal.expires_at > now, PublishedDeal.rank_position.is_not(None),
        PublishedDeal.rank_category_id.is_not(None))
    groups = (await session.execute(select(PublishedDeal.rank_category_id, func.max(PublishedDeal.rank_category), func.count())
        .where(*live).group_by(PublishedDeal.rank_category_id).having(func.count() >= min_items)
        .order_by(func.count().desc()))).all()
    items = []
    for ranking_id, label, count in groups:
        top = (await session.execute(select(PublishedDeal).where(*live, PublishedDeal.rank_category_id == ranking_id)
            .order_by(PublishedDeal.rank_position.asc()).limit(1))).scalar_one()
        items.append({'id': ranking_id, 'label': label, 'count': count, 'image_url': top.image_url, 'top': top.product_name})
    return {'items': items, 'total': len(items)}


def _deals(session, **overrides):
    """Atalho da home para list_public_deals com os mesmos padrões da rota."""
    args = dict(q=None, store=None, category=None, sort='featured', min_price=None, max_price=None,
        min_discount=None, has_coupon=False, ids=None, limit=8, offset=0, trending=False, ranking=None,
        pix=False, free_shipping=False, best_seller=False, min_rating=None, min_sales=None, single_price=False)
    args.update(overrides)
    return list_public_deals(session=session, **args)


@router.get('/home')
async def home(session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    """Tudo o que o mosaico da home mostra, numa chamada só."""
    rankings = (await list_rankings(session=session, min_items=3))['items']
    top = rankings[0] if rankings else None
    return {
        'featured': await _deals(session),
        'trending': await _deals(session, trending=True),
        # Fileiras com 24 para sobrar depois de tirar o que já apareceu nas de cima.
        'bestsellers': await _deals(session, sort='best_selling', limit=24, single_price=True),
        'loved': await _deals(session, min_rating=Decimal('4.7'), min_sales=1000, limit=24, single_price=True),
        'under100': await _deals(session, max_price=Decimal('100'), limit=24, single_price=True),
        'premium': await _deals(session, min_price=Decimal('1000'), sort='discount', limit=24, single_price=True),
        'discounts': await _deals(session, sort='discount', limit=12),
        'pix': await _deals(session, pix=True, limit=4),
        'cheap': await _deals(session, max_price=Decimal('50'), limit=4),
        'free_shipping': await _deals(session, free_shipping=True, limit=4),
        'recent': await _deals(session, sort='recent', limit=24),
        'ranking': top and {**top, 'items': (await _deals(session, ranking=top['id'], sort='rank', limit=3)).items},
        'campaigns': await list_promotions(session=session, store=None, kind='campaign', q=None, limit=6, offset=0),
        'coupons': await list_promotions(session=session, store=None, kind='coupon', q=None, limit=6, offset=0),
        'telegram_url': settings.public_telegram_url.strip() or None,
    }
