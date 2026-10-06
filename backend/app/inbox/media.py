from __future__ import annotations

import re
from pathlib import Path

import httpx

from app.core.urls import sanitize_media_url
from app.inbox.extract import extract_image_urls

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
_MLB = re.compile(r"^MLB\d{8,}$", re.I)
_ASIN = re.compile(r"^[A-Z0-9]{10}$")


def media_dir() -> Path:
    from app.core.config import runtime_data_dir

    root = runtime_data_dir() / "inbox_media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def media_path(name: str) -> Path | None:
    if not name or not _SAFE.fullmatch(name):
        return None
    path = (media_dir() / name).resolve()
    if not str(path).startswith(str(media_dir().resolve())):
        return None
    return path if path.is_file() else None


def public_media_url(filename: str) -> str:
    return f"/api/v1/inbox/media/{filename}"


def amazon_image(asin: str | None) -> str | None:
    token = (asin or "").strip().upper()
    if not _ASIN.fullmatch(token):
        return None
    return f"https://m.media-amazon.com/images/P/{token}.01.LZZZZZZZ.jpg"


def catalog_image(*, marketplace: str, native_id: str, text: str | None, urls: list[str] | None = None) -> str | None:
    pasted = extract_image_urls(text, urls)
    if pasted:
        return pasted[0]
    if marketplace == "amazon":
        return amazon_image(native_id)
    return None


async def ml_thumbnail(mlb: str, *, client: httpx.AsyncClient | None = None) -> str | None:
    token = (mlb or "").replace("-", "").upper()
    if not _MLB.fullmatch(token):
        return None
    close = client is None
    http = client or httpx.AsyncClient(timeout=8.0, follow_redirects=True)
    try:
        response = await http.get(f"https://api.mercadolivre.com/items/{token}")
        if response.status_code != 200:
            return None
        data = response.json()
        raw = data.get("secure_thumbnail") or data.get("thumbnail")
        pictures = data.get("pictures") or []
        if pictures and isinstance(pictures[0], dict):
            raw = pictures[0].get("secure_url") or pictures[0].get("url") or raw
        if isinstance(raw, str) and raw.startswith("http://"):
            raw = "https://" + raw[len("http://") :]
        return sanitize_media_url(raw)
    except Exception:
        return None
    finally:
        if close:
            await http.aclose()


async def resolve_catalog_image(
    *,
    marketplace: str,
    native_id: str,
    text: str | None,
    urls: list[str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    found = catalog_image(marketplace=marketplace, native_id=native_id, text=text, urls=urls)
    if found:
        return found
    if marketplace == "mercadolivre":
        return await ml_thumbnail(native_id, client=client)
    return None


def message_has_image(message) -> bool:
    if getattr(message, "photo", None):
        return True
    media = getattr(message, "media", None)
    webpage = getattr(media, "webpage", None)
    if webpage is not None and getattr(webpage, "photo", None):
        return True
    mime = getattr(getattr(message, "document", None), "mime_type", "") or ""
    return mime.startswith("image/")


async def download_telegram_image(client, message, *, chat_id: str, message_id: str) -> str | None:
    if client is None or not message_has_image(message):
        return None
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", f"{chat_id}_{message_id}")[:80]
    dest = media_dir() / stem
    try:
        path = await client.download_media(message, file=str(dest))
    except Exception:
        return None
    if not path:
        return None
    name = Path(path).name
    if not _SAFE.fullmatch(name):
        return None
    return public_media_url(name)
