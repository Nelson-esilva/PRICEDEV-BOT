from __future__ import annotations

from urllib.parse import urlparse

BLOCKED_HOSTS = {"dpl.pelando.com.br"}
ALLOWED_SCHEMES = {"https", "http"}


def sanitize_purchase_url(url: str | None) -> str | None:
    return _sanitize(url, allow_pelando_media=False)


def sanitize_media_url(url: str | None) -> str | None:
    return _sanitize(url, allow_pelando_media=True)


def _sanitize(url: str | None, *, allow_pelando_media: bool) -> str | None:
    if not url or not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return None
    host = (parsed.hostname or "").lower()
    if not host or host in BLOCKED_HOSTS:
        return None
    if host.endswith(".pelando.com.br") and host != "www.pelando.com.br":
        if not (allow_pelando_media and host.startswith("media.")):
            return None
    return raw


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    return (urlparse(url).hostname or "").lower() or None


def is_ml_social_url(url: str | None) -> bool:
    host = host_of(url)
    if not host:
        return False
    if host in {"meli.la", "www.meli.la"}:
        return True
    if not (
        host.endswith("mercadolivre.com.br")
        or host.endswith("mercadolivre.com")
        or host.endswith("mercadolibre.com")
    ):
        return False
    path = (urlparse(url).path or "").lower()
    return path.startswith(("/social/", "/l/", "/sec/"))
