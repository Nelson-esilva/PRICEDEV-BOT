from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.history.stats import compute_history_stats
from app.models.entities import PriceObservation, Product
from app.schemas.api import PricePointOut, PriceStatisticsOut, ProductOut

router = APIRouter()


@router.get("/products", response_model=list[ProductOut])
async def list_products(session: AsyncSession = Depends(get_session)) -> list[ProductOut]:
    rows = list((await session.execute(select(Product).order_by(Product.updated_at.desc()).limit(200))).scalars())
    return [ProductOut.model_validate(r) for r in rows]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, session: AsyncSession = Depends(get_session)) -> ProductOut:
    row = await session.get(Product, product_id)
    if row is None:
        raise HTTPException(status_code=404, detail="product_not_found")
    return ProductOut.model_validate(row)


@router.get("/products/{product_id}/price-history", response_model=list[PricePointOut])
async def price_history(product_id: str, session: AsyncSession = Depends(get_session)) -> list[PricePointOut]:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product_not_found")
    rows = list(
        (
            await session.execute(
                select(PriceObservation)
                .where(PriceObservation.product_id == product_id)
                .order_by(PriceObservation.observed_at.asc())
            )
        ).scalars()
    )
    return [
        PricePointOut(
            observed_at=r.observed_at,
            effective_price=r.effective_price,
            currency=r.currency,
            source=r.source,
            price_verified=r.price_verified,
            is_inferred=r.is_inferred,
        )
        for r in rows
    ]


@router.get("/products/{product_id}/price-statistics", response_model=PriceStatisticsOut)
async def price_statistics(
    product_id: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> PriceStatisticsOut:
    from app.core.db import utcnow

    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product_not_found")
    stats = await compute_history_stats(
        session,
        product_id=product_id,
        exclude_observation_id=None,
        window_days=settings.history_window_days,
        now=utcnow(),
        currency="BRL",
        condition=product.condition,
    )
    return PriceStatisticsOut(
        window_days=stats.window_days,
        observations=stats.observations,
        distinct_days=stats.distinct_days,
        coverage_days=stats.coverage_days,
        median=stats.median,
        minimum=stats.minimum,
        mean=stats.mean,
        last_price=stats.last_price,
        previous_price=stats.previous_price,
        currency=stats.currency,
    )
