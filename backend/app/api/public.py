from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session, utcnow
from app.core.search import any_contains
from app.models.entities import PublishedDeal, PublicPromotion
from app.schemas.public import PublicDealListOut, PublicDealOut
from app.storefront.catalog import STORE_LABELS
from app.storefront.taxonomy import CATEGORIES

router = APIRouter()


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
        # Exact persisted category, with legacy fallback for snapshots not yet refreshed.
        words = CATEGORIES.get(category, ('', ()))[1]
        filters.append(or_(PublishedDeal.category == category,
            *[PublishedDeal.product_name.ilike(f'%{word}%') for word in words]))
    if min_price is not None:
        filters.append(PublishedDeal.current_price >= min_price)
    if max_price is not None:
        filters.append(PublishedDeal.current_price <= max_price)
    discount = func.coalesce(PublishedDeal.discount_pct, PublishedDeal.announced_discount_pct)
    if min_discount is not None:
        filters.append(discount >= min_discount)
    if sort == 'discount':
        filters.append(discount > 0)
    if has_coupon:
        filters.append(func.length(func.trim(func.coalesce(PublishedDeal.coupon_code, ''))) > 0)
    if trending:
        filters.append(PublishedDeal.trending.is_(True))
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


@router.get('/categories')
async def list_categories(session: AsyncSession = Depends(get_session)):
    counts = dict((await session.execute(select(PublishedDeal.category, func.count()).where(
        PublishedDeal.status == 'active', PublishedDeal.expires_at > utcnow()).group_by(PublishedDeal.category))).all())
    return {'items': [{'id': key, 'label': value[0], 'count': counts.get(key, 0)} for key, value in CATEGORIES.items()]}


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


@router.get('/home')
async def home(session: AsyncSession = Depends(get_session)):
    deals = await list_public_deals(session=session, q=None, store=None, category=None, sort='featured',
        min_price=None, max_price=None, min_discount=None, has_coupon=False, ids=None, limit=8, offset=0,
        trending=False, ranking=None)
    trending = await list_public_deals(session=session, q=None, store=None, category=None, sort='featured',
        min_price=None, max_price=None, min_discount=None, has_coupon=False, ids=None, limit=8, offset=0,
        trending=True, ranking=None)
    discounts = await list_public_deals(session=session, q=None, store=None, category=None, sort='discount',
        min_price=None, max_price=None, min_discount=None, has_coupon=False, ids=None, limit=8, offset=0,
        trending=False, ranking=None)
    bestsellers = await list_public_deals(session=session, q=None, store=None, category=None, sort='best_selling',
        min_price=None, max_price=None, min_discount=None, has_coupon=False, ids=None, limit=8, offset=0,
        trending=False, ranking=None)
    campaigns = await list_promotions(session=session, store=None, kind='campaign', q=None, limit=6, offset=0)
    coupons = await list_promotions(session=session, store=None, kind='coupon', q=None, limit=6, offset=0)
    return {'featured': deals, 'trending': trending, 'bestsellers': bestsellers, 'discounts': discounts, 'campaigns': campaigns, 'coupons': coupons}
