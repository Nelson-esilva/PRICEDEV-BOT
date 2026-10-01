from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.core.db import get_session
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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OpportunityListOut:
    stmt: Select = select(Opportunity)
    count_stmt = select(func.count()).select_from(Opportunity)
    if source:
        stmt = stmt.where(Opportunity.source == source)
        count_stmt = count_stmt.where(Opportunity.source == source)
    else:
        stmt = stmt.where(Opportunity.source != "mock")
        count_stmt = count_stmt.where(Opportunity.source != "mock")
    if merchant:
        stmt = stmt.where(Opportunity.merchant.ilike(f"%{merchant}%"))
        count_stmt = count_stmt.where(Opportunity.merchant.ilike(f"%{merchant}%"))
    if category:
        stmt = stmt.where(Opportunity.category == category)
        count_stmt = count_stmt.where(Opportunity.category == category)
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
    rows = list(
        (
            await session.execute(
                stmt.order_by(
                    Opportunity.source_created_at.is_(None),
                    Opportunity.source_created_at.desc(),
                    Opportunity.detected_at.desc(),
                ).offset(offset).limit(limit)
            )
        ).scalars()
    )
    return OpportunityListOut(items=[OpportunityOut.model_validate(r) for r in rows], total=total)


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
    return OpportunityOut.model_validate(row)
