from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session, utcnow
from app.core.urls import sanitize_purchase_url
from app.ingestion.identity import infer_marketplace, parse_product_url
from app.models.entities import WatchlistItem

router = APIRouter()


class WatchlistIn(BaseModel):
    url: str
    target_price: float | None = None


class WatchlistOut(BaseModel):
    id: str
    url: str
    marketplace: str
    native_product_id: str
    product_name: str | None
    target_price: float | None
    last_price: float | None
    enabled: bool
    last_error: str | None
    last_checked_at: str | None


def _out(row: WatchlistItem) -> WatchlistOut:
    return WatchlistOut(
        id=row.id,
        url=row.url,
        marketplace=row.marketplace,
        native_product_id=row.native_product_id,
        product_name=row.product_name,
        target_price=float(row.target_price) if row.target_price is not None else None,
        last_price=float(row.last_price) if row.last_price is not None else None,
        enabled=row.enabled,
        last_error=row.last_error,
        last_checked_at=row.last_checked_at.isoformat() if row.last_checked_at else None,
    )


@router.get("/watchlist", response_model=list[WatchlistOut])
async def list_watchlist(session: AsyncSession = Depends(get_session)) -> list[WatchlistOut]:
    rows = list((await session.execute(select(WatchlistItem).order_by(WatchlistItem.created_at.desc()))).scalars())
    return [_out(row) for row in rows]


@router.post("/watchlist", response_model=WatchlistOut)
async def add_watchlist(body: WatchlistIn, session: AsyncSession = Depends(get_session)) -> WatchlistOut:
    url = sanitize_purchase_url(body.url)
    if not url:
        raise HTTPException(status_code=400, detail="url_invalida")
    existing = (
        await session.execute(select(WatchlistItem).where(WatchlistItem.url == url))
    ).scalar_one_or_none()
    market, native = parse_product_url(url)
    marketplace = market or infer_marketplace(url, "unknown")
    native = native or ""
    if existing:
        existing.enabled = True
        existing.marketplace = marketplace
        existing.native_product_id = native or existing.native_product_id
        if body.target_price is not None:
            existing.target_price = body.target_price
        existing.updated_at = utcnow()
        await session.commit()
        return _out(existing)
    row = WatchlistItem(
        url=url,
        marketplace=marketplace,
        native_product_id=native,
        target_price=body.target_price,
        enabled=True,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _out(row)


@router.delete("/watchlist/{item_id}")
async def remove_watchlist(item_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    row = await session.get(WatchlistItem, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="watchlist_not_found")
    await session.delete(row)
    await session.commit()
    return {"ok": True}
