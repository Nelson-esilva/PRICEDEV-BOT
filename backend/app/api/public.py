from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session, utcnow
from app.core.search import any_contains, category_match
from app.models.entities import PublishedDeal
from app.schemas.public import PublicDealListOut, PublicDealOut
from app.storefront.catalog import STORE_LABELS

router = APIRouter()


def _is_live(deal: PublishedDeal, now: datetime) -> bool:
    return deal.status == "active" and deal.expires_at > now


def _to_out(deal: PublishedDeal) -> PublicDealOut:
    return PublicDealOut(
        id=deal.id,
        slug=deal.slug,
        store=deal.store,
        product=deal.product_name,
        merchant=deal.merchant,
        category=deal.category,
        image_url=deal.image_url,
        description=deal.description,
        coupon_code=deal.coupon_code,
        payment_hint=deal.payment_hint,
        current_price=deal.current_price,
        list_price=deal.list_price,
        announced_discount_pct=deal.announced_discount_pct,
        currency=deal.currency,
        go_path=f"/go/{deal.slug}",
        updated_at=deal.updated_at,
        expires_at=deal.expires_at,
    )


def _live_filters(stmt: Select, now: datetime) -> Select:
    return stmt.where(PublishedDeal.status == "active", PublishedDeal.expires_at > now)


@router.get("/deals", response_model=PublicDealListOut)
async def list_public_deals(
    session: AsyncSession = Depends(get_session),
    q: str | None = None,
    store: str | None = None,
    category: str | None = None,
    limit: int = Query(default=48, ge=1, le=120),
    offset: int = Query(default=0, ge=0),
) -> PublicDealListOut:
    now = utcnow()
    stmt: Select = _live_filters(select(PublishedDeal), now)
    count_stmt = _live_filters(select(func.count()).select_from(PublishedDeal), now)
    searched = any_contains(
        [PublishedDeal.product_name, PublishedDeal.merchant, PublishedDeal.description],
        q,
    )
    if searched is not None:
        stmt = stmt.where(searched)
        count_stmt = count_stmt.where(searched)
    if store:
        wanted = store.strip().lower()
        stmt = stmt.where(PublishedDeal.store == wanted)
        count_stmt = count_stmt.where(PublishedDeal.store == wanted)
    cat_clause = category_match(
        PublishedDeal.product_name,
        category=category,
        category_col=PublishedDeal.category,
    )
    if cat_clause is not None:
        stmt = stmt.where(cat_clause)
        count_stmt = count_stmt.where(cat_clause)
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = (
        (
            await session.execute(
                stmt.order_by(PublishedDeal.updated_at.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return PublicDealListOut(items=[_to_out(row) for row in rows], total=total)


@router.get("/deals/{slug}", response_model=PublicDealOut)
async def get_public_deal(slug: str, session: AsyncSession = Depends(get_session)) -> PublicDealOut:
    now = utcnow()
    deal = (
        await session.execute(
            select(PublishedDeal).where(
                or_(PublishedDeal.slug == slug, PublishedDeal.id == slug)
            )
        )
    ).scalar_one_or_none()
    if deal is None or not _is_live(deal, now):
        raise HTTPException(status_code=404, detail="oferta_encerrada")
    return _to_out(deal)


@router.get("/stores")
async def list_stores() -> dict:
    return {"items": [{"id": key, "label": label} for key, label in STORE_LABELS.items()]}
