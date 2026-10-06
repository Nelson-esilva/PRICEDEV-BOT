from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import as_utc, get_session
from app.core.search import any_contains, category_match, contains
from app.inbox.media import catalog_image, media_path, ml_thumbnail
from app.inbox.parse import parse_deal
from app.models.entities import InboxMessage

router = APIRouter()


class InboxItemOut(BaseModel):
    id: str
    channel: str
    chat_title: str
    product: str
    body: str | None
    purchase_url: str | None
    marketplace: str
    image_url: str | None = None
    stamped: bool = False
    price: float | None = None
    listed_price: float | None = None
    coupon_code: str | None = None
    payment_hint: str | None = None
    posted_at: str
    received_at: str


class InboxListOut(BaseModel):
    items: list[InboxItemOut]
    total: int
    listening: bool


def _iso(value) -> str:
    aware = as_utc(value)
    if aware is None:
        return ""
    return aware.isoformat().replace("+00:00", "Z")


def _out(row: InboxMessage, settings) -> InboxItemOut:
    from app.affiliates.resolver import stamp_owned_link

    parsed = parse_deal(row.body or row.product_name, fallback=row.product_name)
    stamped = stamp_owned_link(row.purchase_url, settings) or row.affiliate_url
    return InboxItemOut(
        id=row.id,
        channel=row.channel,
        chat_title=row.chat_title,
        product=parsed.title,
        body=row.body,
        purchase_url=stamped or row.purchase_url,
        marketplace=row.marketplace,
        image_url=row.image_url,
        stamped=bool(stamped),
        price=float(parsed.price) if parsed.price is not None else None,
        listed_price=float(parsed.listed_price) if parsed.listed_price is not None else None,
        coupon_code=parsed.coupon,
        payment_hint=parsed.payment_hint,
        posted_at=_iso(row.posted_at),
        received_at=_iso(row.received_at),
    )


def _blocked_inbox(settings):
    tokens = settings.telegram_inbox_block_chat_list
    if not tokens:
        return None
    parts = []
    for raw in tokens:
        token = raw.strip().lstrip("@")
        if not token:
            continue
        digits = token.lstrip("-")
        parts.append(InboxMessage.chat_id == token)
        parts.append(InboxMessage.chat_id == digits)
        if digits.isdigit():
            parts.append(InboxMessage.chat_id == f"-{digits}")
            parts.append(InboxMessage.chat_id == f"-100{digits}")
        parts.append(func.lower(InboxMessage.chat_title) == token.lower())
    return or_(*parts) if parts else None


@router.get("/inbox", response_model=InboxListOut)
async def list_inbox(
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=48, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = None,
    marketplace: str | None = None,
    chat: str | None = None,
    category: str | None = None,
) -> InboxListOut:
    from app.core.config import get_settings

    settings = get_settings()
    stmt = select(InboxMessage)
    count_stmt = select(func.count()).select_from(InboxMessage)
    blocked = _blocked_inbox(settings)
    if blocked is not None:
        stmt = stmt.where(not_(blocked))
        count_stmt = count_stmt.where(not_(blocked))
    searched = any_contains(
        [
            InboxMessage.product_name,
            InboxMessage.body,
            InboxMessage.chat_title,
            InboxMessage.marketplace,
            InboxMessage.purchase_url,
        ],
        q,
    )
    if searched is not None:
        stmt = stmt.where(searched)
        count_stmt = count_stmt.where(searched)
    if marketplace:
        stmt = stmt.where(InboxMessage.marketplace == marketplace)
        count_stmt = count_stmt.where(InboxMessage.marketplace == marketplace)
    chat_clause = contains(InboxMessage.chat_title, chat)
    if chat_clause is not None:
        stmt = stmt.where(chat_clause)
        count_stmt = count_stmt.where(chat_clause)
    cat_clause = category_match(InboxMessage.product_name, category=category)
    if cat_clause is not None:
        stmt = stmt.where(cat_clause)
        count_stmt = count_stmt.where(cat_clause)
    total = (await session.execute(count_stmt)).scalar_one()
    rows = list(
        (
            await session.execute(
                stmt.order_by(InboxMessage.posted_at.desc(), InboxMessage.received_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
    )
    await _hydrate_social(session, rows, settings)
    await _hydrate_images(session, rows)
    await _hydrate_affiliates(session, rows, settings)
    return InboxListOut(
        items=[_out(row, settings) for row in rows],
        total=total,
        listening=bool(
            settings.enable_channel_inbox and settings.telegram_api_id and settings.telegram_api_hash
        ),
    )


async def _hydrate_social(session: AsyncSession, rows: list[InboxMessage], settings) -> None:
    from app.affiliates.resolver import stamp_owned_link
    from app.core.urls import is_ml_social_url
    from app.inbox.extract import describe_link
    from app.inbox.resolve import resolve_social_product

    pending = 0
    dirty = False
    for row in rows:
        if not is_ml_social_url(row.purchase_url):
            continue
        if pending >= 3:
            break
        product = await resolve_social_product(row.purchase_url)
        pending += 1
        if not product:
            continue
        row.purchase_url = product
        marketplace, native = describe_link(product)
        row.marketplace = marketplace
        if native:
            row.native_product_id = native
        stamped = stamp_owned_link(product, settings)
        if stamped:
            row.affiliate_url = stamped
        dirty = True
    if dirty:
        await session.commit()


async def _hydrate_images(session: AsyncSession, rows: list[InboxMessage]) -> None:
    pending = 0
    dirty = False
    for row in rows:
        if row.image_url:
            continue
        payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        urls = [*(payload.get("urls") or []), *(payload.get("resolved") or [])]
        picture = catalog_image(
            marketplace=row.marketplace,
            native_id=row.native_product_id,
            text=row.body,
            urls=urls,
        )
        if picture is None and pending < 5 and row.marketplace == "mercadolivre" and row.native_product_id:
            picture = await ml_thumbnail(row.native_product_id)
            pending += 1
        if picture:
            row.image_url = picture
            dirty = True
    if dirty:
        await session.commit()


async def _hydrate_affiliates(session: AsyncSession, rows: list[InboxMessage], settings) -> None:
    from app.affiliates.resolver import resolve_links, stamp_owned_link

    pending = 0
    dirty = False
    for row in rows:
        if row.affiliate_url:
            continue
        stamped = stamp_owned_link(row.purchase_url, settings)
        if stamped:
            row.affiliate_url = stamped
            dirty = True
            continue
        if pending >= 3:
            continue
        if row.marketplace not in {"shopee", "magalu", "kabum", "afiliado"}:
            continue
        links = await resolve_links(original_url=row.purchase_url, existing_affiliate=None, settings=settings)
        if links.affiliate:
            row.affiliate_url = links.affiliate
            dirty = True
            pending += 1
    if dirty:
        await session.commit()


@router.get("/inbox/media/{name}")
async def inbox_media(name: str):
    path = media_path(name)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path)
