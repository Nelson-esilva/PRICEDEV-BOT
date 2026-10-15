from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger
from app.inbox.extract import extract_urls
from app.inbox.media import download_telegram_image
from app.inbox.store import find_channel_post, save_channel_post

log = get_logger("inbox")
_uv = logging.getLogger("uvicorn.error")

_connected = False
_status = "off"


def is_connected() -> bool:
    return _connected


def connection_status() -> str:
    if _connected:
        return "live"
    return _status


def _note(msg: str, **kwargs) -> None:
    global _status
    _status = msg
    extra = " ".join(f"{key}={value}" for key, value in kwargs.items())
    line = f"telegram_inbox {msg} {extra}".strip()
    print(line, flush=True)
    _uv.info(line)
    log.info(msg, **kwargs)


def _session_file(settings: Settings) -> str:
    raw = Path(settings.telegram_session_path)
    if raw.is_absolute():
        return str(raw)
    here = (Path.cwd() / raw).resolve()
    parent = (Path.cwd().parent / raw).resolve()
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
    if existing:
        return False
    picture = None
    if client is not None:
        picture = await download_telegram_image(client, message, chat_id=str(chat_id), message_id=str(message.id))
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
        _note("saved", chat=str(title)[:48], marketplace=row.marketplace)
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
        _note("desligada")
        return
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        _note("sem_credencial")
        return
    while True:
        try:
            from telethon import TelegramClient, events
        except ImportError:
            _note("sem_telethon")
            await asyncio.sleep(10)
            continue
        try:
            _note("loop")
            await _listen(settings, TelegramClient, events)
            _note("disconnected")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _note("drop", error=str(exc)[:200])
            log.exception("telegram_inbox_drop", error=str(exc)[:200])
        await asyncio.sleep(5)


async def _poll_heads(
    client,
    settings: Settings,
    *,
    per_chat: int = 8,
    max_chats: int = 40,
    live: bool = False,
) -> int:
    saved = 0
    chats = 0
    try:
        async for dialog in client.iter_dialogs():
            if not (dialog.is_group or dialog.is_channel):
                continue
            entity = dialog.entity
            username = getattr(entity, "username", None)
            if not _allowed_chat(settings, int(dialog.id), username, dialog.name):
                continue
            chats += 1
            if chats > max_chats:
                break
            try:
                async for message in client.iter_messages(entity, limit=per_chat):
                    if await _ingest(settings, message, entity, client, live=live):
                        saved += 1
            except Exception as exc:
                log.warning("telegram_inbox_poll_skip", chat=dialog.name, error=str(exc)[:160])
    except Exception as exc:
        log.warning("telegram_inbox_poll_fail", error=str(exc)[:160])
        raise
    if saved:
        _note("poll", chats=chats, saved=saved)
    return saved


async def _watchdog(client, settings: Settings) -> None:
    fails = 0
    while True:
        await asyncio.sleep(25)
        if not client.is_connected():
            return
        try:
            await _poll_heads(client, settings)
            fails = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            fails += 1
            if fails >= 3:
                log.warning("telegram_inbox_stale_reconnect")
                await client.disconnect()
                return


async def _listen(settings: Settings, TelegramClient, events) -> None:
    global _connected
    session = _session_file(settings)
    _note("connecting", session=session)
    client = TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash)
    _connected = False
    extras: list = []
    try:
        await asyncio.wait_for(client.connect(), 20)
        if not await client.is_user_authorized():
            _note("sem_sessao")
            await asyncio.sleep(30)
            return
        _connected = True
        _note("authorized")

        @client.on(events.NewMessage)
        async def on_message(event) -> None:
            try:
                if not (event.is_group or event.is_channel):
                    return
                chat = await event.get_chat()
                await _ingest(settings, event.message, chat, client, live=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("inbox_event_skip", error=str(exc)[:160])

        from app.publishing.outbox import pump

        asyncio.create_task(pump(client))
        asyncio.create_task(_boot_extras(settings, events, extras))
        tasks = [
            asyncio.create_task(_backfill(client, settings)),
            asyncio.create_task(_watchdog(client, settings)),
        ]
        try:
            saved = await asyncio.wait_for(_poll_heads(client, settings, live=False), 90)
            _note("catchup", saved=saved)
        except Exception as exc:
            _note("catchup_fail", error=str(exc)[:160])
        _note("live")
        try:
            while client.is_connected():
                await asyncio.sleep(2)
        finally:
            _connected = False
            for task in tasks:
                task.cancel()
            for extra in extras:
                await extra.disconnect()
    finally:
        _connected = False
        await client.disconnect()


async def _boot_extras(settings: Settings, events, extras: list) -> None:
    try:
        extras.extend(await _start_extra_clients(settings, events))
    except Exception as exc:
        _note("extras_skip", error=str(exc)[:160])


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
            try:
                if not (event.is_group or event.is_channel):
                    return
                chat = await event.get_chat()
                await _ingest(settings, event.message, chat, client, live=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("inbox_extra_skip", error=str(exc)[:160])

        asyncio.create_task(_backfill(extra, settings))
        asyncio.create_task(_watchdog(extra, settings))
        started.append(extra)
        log.info("telegram_inbox_extra_start", session=session, user=str(label))
    return started
