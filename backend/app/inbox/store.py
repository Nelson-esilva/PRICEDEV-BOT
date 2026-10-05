from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.core.db import as_utc, get_session_factory, utcnow
from app.affiliates.resolver import resolve_links, stamp_owned_link
from app.core.config import get_settings
from app.inbox.extract import describe_link, pick_product_url
from app.inbox.media import resolve_catalog_image
from app.inbox.parse import parse_deal
from app.inbox.resolve import unveil_urls
from app.models.entities import InboxMessage


async def find_channel_post(*, channel: str, chat_id: str, message_id: str) -> tuple[str, str | None] | None:
    factory = get_session_factory()
    async with factory() as session:
        row = (
            await session.execute(
                select(InboxMessage).where(
                    InboxMessage.channel == channel,
                    InboxMessage.chat_id == str(chat_id),
                    InboxMessage.message_id == str(message_id),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return row.id, row.image_url


async def set_inbox_image(row_id: str, image_url: str) -> None:
    factory = get_session_factory()
    async with factory() as session:
        row = await session.get(InboxMessage, row_id)
        if row is None or row.image_url:
            return
        row.image_url = image_url
        await session.commit()


async def save_channel_post(
    *,
    channel: str,
    chat_id: str,
    chat_title: str,
    message_id: str,
    text: str,
    urls: list[str],
    posted_at: datetime | None = None,
    extra: dict | None = None,
    image_url: str | None = None,
) -> InboxMessage | None:
    unveiled = await unveil_urls(urls)
    purchase = pick_product_url(unveiled) or pick_product_url(urls)
    if purchase is None:
        return None
    marketplace, native = describe_link(purchase)
    parsed = parse_deal(text, fallback=chat_title or "Promoção do grupo")
    picture = image_url or await resolve_catalog_image(
        marketplace=marketplace,
        native_id=native,
        text=text,
        urls=urls + unveiled,
    )
    settings = get_settings()
    affiliate = stamp_owned_link(purchase, settings)
    if affiliate is None:
        links = await resolve_links(original_url=purchase, existing_affiliate=None, settings=settings)
        affiliate = links.affiliate
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(
                select(InboxMessage).where(
                    InboxMessage.channel == channel,
                    InboxMessage.chat_id == str(chat_id),
                    InboxMessage.message_id == str(message_id),
                )
            )
        ).scalar_one_or_none()
        if existing:
            dirty = False
            if picture and not existing.image_url:
                existing.image_url = picture
                dirty = True
            if affiliate and not existing.affiliate_url:
                existing.affiliate_url = affiliate
                dirty = True
            if dirty:
                await session.commit()
            return None
        row = InboxMessage(
            channel=channel,
            chat_id=str(chat_id),
            chat_title=(chat_title or "")[:256],
            message_id=str(message_id),
            product_name=parsed.title,
            body=(text or "")[:4000] or None,
            purchase_url=purchase,
            marketplace=marketplace,
            native_product_id=native,
            image_url=picture,
            affiliate_url=affiliate,
            posted_at=as_utc(posted_at) or utcnow(),
            received_at=utcnow(),
            raw_payload={"urls": urls, "resolved": unveiled, **(extra or {})},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row
