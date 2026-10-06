from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger
from app.inbox.extract import extract_urls
from app.inbox.media import download_telegram_image
from app.inbox.store import find_channel_post, save_channel_post, set_inbox_image

log = get_logger("inbox")


def _session_file(settings: Settings) -> str:
    raw = Path(settings.telegram_session_path)
    if raw.is_absolute():
        return str(raw)
    here = Path.cwd() / raw
    parent = Path.cwd().parent / raw
    if parent.exists() and not here.exists():
        return str(parent)
    return str(here)


def _normalize_chat_token(value: str) -> str:
    return value.strip().lstrip("@").lower()


def _chat_tokens(chat_id: int, username: str | None, title: str | None) -> set[str]:
    tokens = {str(chat_id), str(abs(chat_id))}
    if username:
        tokens.add(_normalize_chat_token(str(username)))
    if title:
        tokens.add(_normalize_chat_token(str(title)))
    return {item for item in tokens if item}


def _listed(wanted: list[str], chat_id: int, username: str | None, title: str | None) -> bool:
    needles = {_normalize_chat_token(item) for item in wanted}
    return bool(needles & _chat_tokens(chat_id, username, title))


def _allowed_chat(
    settings: Settings,
    chat_id: int,
    username: str | None,
    title: str | None = None,
) -> bool:
    if _listed(settings.telegram_inbox_block_chat_list, chat_id, username, title):
        return False
    wanted = settings.telegram_inbox_chat_list
    if not wanted:
        return True
    return _listed(wanted, chat_id, username, title)


def _entity_urls(message) -> list[str]:
    found: list[str] = []
    text = getattr(message, "raw_text", None) or getattr(message, "message", None) or ""
    for entity in getattr(message, "entities", None) or []:
        url = getattr(entity, "url", None)
        if url:
            found.append(str(url))
            continue
        offset = getattr(entity, "offset", None)
        length = getattr(entity, "length", None)
        if offset is None or length is None:
            continue
        slice_ = text[offset : offset + length]
        if slice_.startswith("http"):
            found.append(slice_)
    markup = getattr(message, "reply_markup", None)
    for row in getattr(markup, "rows", None) or []:
        for button in getattr(row, "buttons", None) or []:
            url = getattr(button, "url", None)
            if url:
                found.append(str(url))
    return found


async def _ingest(settings: Settings, message, chat, client=None, *, live: bool = False) -> bool:
    chat_id = getattr(chat, "id", None) or getattr(message, "chat_id", None)
    username = getattr(chat, "username", None)
    title = getattr(chat, "title", None) or username or (str(chat_id) if chat_id is not None else None)
    if chat_id is None or not _allowed_chat(settings, int(chat_id), username, title):
        return False
    text = getattr(message, "raw_text", None) or getattr(message, "message", None) or ""
    urls = extract_urls(text, _entity_urls(message))
    if not urls:
        return False
    existing = await find_channel_post(channel="telegram", chat_id=str(chat_id), message_id=str(message.id))
    picture = None
    if client is not None and (existing is None or not existing[1]):
        picture = await download_telegram_image(client, message, chat_id=str(chat_id), message_id=str(message.id))
    if existing:
        if picture:
            await set_inbox_image(existing[0], picture)
        return False
    row = await save_channel_post(
        channel="telegram",
        chat_id=str(chat_id),
        chat_title=str(title),
        message_id=str(message.id),
        text=text,
        urls=urls,
        posted_at=getattr(message, "date", None),
        extra={"username": username},
        image_url=picture,
    )
    if row:
        log.info("inbox_saved", chat=title, marketplace=row.marketplace)
        if live:
            await _publish_live(row, settings)
        return True
    return False


async def _publish_live(row, settings: Settings) -> None:
    if not settings.enable_telegram_publish:
        return
    try:
        from app.core.db import get_session_factory
        from app.publishing.telegram import publish_inbox

        factory = get_session_factory()
        async with factory() as session:
            status = await publish_inbox(session, row, settings)
            await session.commit()
        if status == "published":
            log.info("inbox_republished", product=row.product_name[:80], marketplace=row.marketplace)
    except Exception as exc:
        log.warning("inbox_publish_skip", error=str(exc)[:160])


async def _backfill(client, settings: Settings) -> None:
    limit = max(0, settings.telegram_inbox_backfill)
    if limit == 0:
        return
    scanned = 0
    saved = 0
    chats = 0
    async for dialog in client.iter_dialogs():
        if not (dialog.is_group or dialog.is_channel):
            continue
        entity = dialog.entity
        username = getattr(entity, "username", None)
        if not _allowed_chat(settings, int(dialog.id), username, dialog.name):
            continue
        if chats >= 60:
            break
        chats += 1
        try:
            async for message in client.iter_messages(entity, limit=limit):
                scanned += 1
                if await _ingest(settings, message, entity, client, live=False):
                    saved += 1
        except Exception as exc:
            log.warning("telegram_inbox_backfill_skip", chat=dialog.name, error=str(exc)[:160])
    log.info("telegram_inbox_backfill", chats=chats, scanned=scanned, saved=saved)


async def run_telegram_inbox(settings: Settings) -> None:
    if not settings.enable_channel_inbox:
        log.warning("telegram_inbox_desligada")
        return
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        log.warning("telegram_inbox_sem_credencial")
        return
    try:
        from telethon import TelegramClient, events
    except ImportError:
        log.warning("telegram_inbox_sem_telethon")
        return

    session = _session_file(settings)
    client = TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            log.warning("telegram_inbox_sem_sessao", hint="rode: python -m app.inbox.login")
            return

        @client.on(events.NewMessage)
        async def on_message(event) -> None:
            if not (event.is_group or event.is_channel):
                return
            chat = await event.get_chat()
            await _ingest(settings, event.message, chat, client, live=True)

        from app.publishing.outbox import pump

        asyncio.create_task(pump(client))
        extras = await _start_extra_clients(settings, events)
        log.info("telegram_inbox_start", session=session, extras=len(extras))
        await _backfill(client, settings)
        try:
            await client.run_until_disconnected()
        finally:
            for extra in extras:
                await extra.disconnect()
    finally:
        await client.disconnect()


async def _start_extra_clients(settings: Settings, events) -> list:
    from telethon import TelegramClient

    from app.inbox.login import list_extra_sessions

    started = []
    for session in list_extra_sessions():
        extra = TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash)
        try:
            await extra.connect()
            if not await extra.is_user_authorized():
                log.warning("telegram_inbox_extra_sem_sessao", session=session)
                await extra.disconnect()
                continue
        except Exception as exc:
            log.warning("telegram_inbox_extra_fail", session=session, error=str(exc)[:160])
            continue
        me = await extra.get_me()
        label = getattr(me, "username", None) or getattr(me, "first_name", None) or session

        @extra.on(events.NewMessage)
        async def on_extra(event, client=extra) -> None:
            if not (event.is_group or event.is_channel):
                return
            chat = await event.get_chat()
            await _ingest(settings, event.message, chat, client, live=True)

        asyncio.create_task(_backfill(extra, settings))
        started.append(extra)
        log.info("telegram_inbox_extra_start", session=session, user=str(label))
    return started
