from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from app.core.logging import get_logger

log = get_logger("telegram")


@dataclass
class OutgoingDeal:
    chat: str
    text: str
    photo_url: str | None
    dedup_key: str
    opportunity_id: str


_queue: asyncio.Queue[OutgoingDeal] | None = None
_CAPTION_MAX = 1024


def get_queue() -> asyncio.Queue[OutgoingDeal]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def enqueue(deal: OutgoingDeal) -> None:
    await get_queue().put(deal)


def _as_jpeg_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path.lower().endswith(".webp"):
        return urlunparse(parsed._replace(path=path[:-5] + ".jpg"))
    return url


def _image_kind(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def _photo_jpeg(photo: str) -> BytesIO | None:
    raw: bytes | None = None
    if photo.startswith("http"):
        url = _as_jpeg_url(photo)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    return None
                raw = resp.content
        except Exception:
            return None
    else:
        path = Path(photo)
        if not path.is_file():
            return None
        raw = path.read_bytes()
    kind = _image_kind(raw or b"")
    if kind not in {"jpg", "png"}:
        return None
    buf = BytesIO(raw)
    buf.name = "oferta.jpg"
    return buf


def _posted_items(posted) -> list:
    if posted is None:
        return []
    if isinstance(posted, (list, tuple)):
        return [item for item in posted if item is not None]
    return [posted]


def _caption_of(posted) -> str:
    for item in _posted_items(posted):
        text = getattr(item, "message", None) or getattr(item, "raw_text", None) or ""
        if str(text).strip():
            return str(text).strip()
    return ""


def _is_sticker(posted) -> bool:
    for item in _posted_items(posted):
        if getattr(item, "sticker", None):
            return True
        media = getattr(item, "media", None)
        document = getattr(media, "document", None)
        for attr in getattr(document, "attributes", None) or []:
            if type(attr).__name__ == "DocumentAttributeSticker":
                return True
    return False


def _caption_stuck(posted, text: str) -> bool:
    if _is_sticker(posted):
        return False
    caption = _caption_of(posted)
    if not caption:
        return False
    return any(marker in caption for marker in ("OFERTA IMPERDÍVEL", "PREÇO PROMOCIONAL", "LINK DA PROMOÇÃO"))


async def _delete_posted(client, chat: str, posted) -> None:
    ids = [item.id for item in _posted_items(posted) if getattr(item, "id", None)]
    if not ids:
        return
    try:
        await client.delete_messages(chat, ids)
    except Exception as exc:
        log.warning("telegram_photo_delete_fail", error=str(exc)[:160])


async def send_via_telethon(client, deal: OutgoingDeal) -> None:
    text = (deal.text or "").strip()[:_CAPTION_MAX]
    if not text:
        return
    if deal.photo_url:
        try:
            photo = await _photo_jpeg(deal.photo_url)
            if photo is not None:
                posted = await client.send_file(
                    deal.chat,
                    photo,
                    caption=text,
                    parse_mode="html",
                    force_document=False,
                )
                if _caption_stuck(posted, text):
                    return
                await _delete_posted(client, deal.chat, posted)
                log.warning("telegram_photo_without_caption")
        except Exception as exc:
            log.warning("telegram_photo_skip", error=str(exc)[:160])
    await client.send_message(deal.chat, text, link_preview=False, parse_mode="html")


async def pump(client) -> None:
    queue = get_queue()
    while True:
        deal = await queue.get()
        try:
            await send_via_telethon(client, deal)
            log.info("telegram_published", key=deal.dedup_key, via="telethon")
        except Exception as exc:
            log.warning("telegram_publish_fail", error=str(exc)[:200], key=deal.dedup_key)
        await asyncio.sleep(1.5)
