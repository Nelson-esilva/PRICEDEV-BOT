from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.core.db import get_session
from app.core.search import any_contains, category_match, reason_match, store_match
from app.models.entities import Opportunity
from app.schemas.api import OpportunityListOut, OpportunityOut

router = APIRouter()


@router.get("/opportunities", response_model=OpportunityListOut)
async def list_opportunities(
    session: AsyncSession = Depends(get_session),
    source: str | None = None,
    merchant: str | None = None,
    category: str | None = None,
    classification: str | None = None,
    price_verified: bool | None = None,
    min_score: int | None = Query(default=None),
    min_discount: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_price: float | None = Query(default=None),
    status: str = "active",
    since: datetime | None = None,
    q: str | None = None,
    store: str | None = None,
    reason: str | None = None,
    limit: int = Query(default=50, ge=1, le=400),
    offset: int = Query(default=0, ge=0),
) -> OpportunityListOut:
    stmt: Select = select(Opportunity)
    count_stmt = select(func.count()).select_from(Opportunity)
    if source:
        stmt = stmt.where(Opportunity.source == source)
        count_stmt = count_stmt.where(Opportunity.source == source)
    else:
        stmt = stmt.where(Opportunity.source != "mock", Opportunity.source != "mlhub")
        count_stmt = count_stmt.where(Opportunity.source != "mock", Opportunity.source != "mlhub")
    if merchant:
        stmt = stmt.where(Opportunity.merchant.ilike(f"%{merchant}%"))
        count_stmt = count_stmt.where(Opportunity.merchant.ilike(f"%{merchant}%"))
    searched = any_contains(
        [
            Opportunity.product_name,
            Opportunity.merchant,
            Opportunity.category,
            Opportunity.description,
            Opportunity.original_purchase_url,
        ],
        q,
    )
    if searched is not None:
        stmt = stmt.where(searched)
        count_stmt = count_stmt.where(searched)
    store_clause = store_match(
        store,
        merchant=Opportunity.merchant,
        source=Opportunity.source,
        urls=[Opportunity.original_purchase_url, Opportunity.final_purchase_url],
    )
    if store_clause is not None:
        stmt = stmt.where(store_clause)
        count_stmt = count_stmt.where(store_clause)
    cat_clause = category_match(
        Opportunity.product_name,
        category=category,
        category_col=Opportunity.category,
        reasons_col=Opportunity.reasons,
    )
    if cat_clause is not None:
        stmt = stmt.where(cat_clause)
        count_stmt = count_stmt.where(cat_clause)
    tagged = reason_match(Opportunity.reasons, reason)
    if tagged is not None:
        stmt = stmt.where(tagged)
        count_stmt = count_stmt.where(tagged)
    if classification:
        stmt = stmt.where(Opportunity.classification == classification)
        count_stmt = count_stmt.where(Opportunity.classification == classification)
    if price_verified is not None:
        stmt = stmt.where(Opportunity.price_verified.is_(price_verified))
        count_stmt = count_stmt.where(Opportunity.price_verified.is_(price_verified))
    if min_score is not None:
        stmt = stmt.where(Opportunity.acceptance_score >= min_score)
        count_stmt = count_stmt.where(Opportunity.acceptance_score >= min_score)
    if min_discount is not None:
        stmt = stmt.where(Opportunity.historical_discount_pct >= min_discount)
        count_stmt = count_stmt.where(Opportunity.historical_discount_pct >= min_discount)
    if max_price is not None:
        stmt = stmt.where(Opportunity.current_price <= max_price)
        count_stmt = count_stmt.where(Opportunity.current_price <= max_price)
    if min_price is not None:
        stmt = stmt.where(Opportunity.current_price >= min_price)
        count_stmt = count_stmt.where(Opportunity.current_price >= min_price)
    if status:
        stmt = stmt.where(Opportunity.status == status)
        count_stmt = count_stmt.where(Opportunity.status == status)
    if since:
        stmt = stmt.where(Opportunity.detected_at >= since)
        count_stmt = count_stmt.where(Opportunity.detected_at >= since)
    total = (await session.execute(count_stmt)).scalar_one()
    order = (
        Opportunity.detected_at.desc(),
        Opportunity.source_created_at.desc(),
    )
    rows = list(
        (await session.execute(stmt.order_by(*order).offset(offset).limit(limit))).scalars()
    )
    from app.core.config import get_settings

    settings = get_settings()
    return OpportunityListOut(items=[_to_out(row, settings) for row in rows], total=total)


@router.get("/opportunities/stream")
async def stream_opportunities():
    async def events():
        while True:
            yield "event: ping\ndata: {}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityOut)
async def get_opportunity(
    opportunity_id: str,
    session: AsyncSession = Depends(get_session),
) -> OpportunityOut:
    row = await session.get(Opportunity, opportunity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="opportunity_not_found")
    from app.core.config import get_settings

    return _to_out(row, get_settings())


def _to_out(row: Opportunity, settings) -> OpportunityOut:
    from app.affiliates.resolver import stamp_owned_link

    item = OpportunityOut.model_validate(row)
    stamped = None
    for candidate in (row.final_purchase_url, row.affiliate_url, row.validated_purchase_url, row.original_purchase_url):
        stamped = stamp_owned_link(candidate, settings)
        if stamped:
            break
    if not stamped:
        return item
    return item.model_copy(update={"purchase_url": stamped, "affiliate_url": stamped})
