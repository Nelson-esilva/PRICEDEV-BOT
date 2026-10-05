from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

import httpx

from app.core.logging import get_logger
from app.core.urls import is_ml_social_url, sanitize_purchase_url
from app.inbox.extract import needs_resolve
from app.ingestion.identity import parse_product_url

log = get_logger("inbox")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


_PRODUCT_HREF = re.compile(
    r'href="(https://(?:www|produto)\.mercadolivre\.com\.br/[^"]+)"',
    re.I,
)
_SKIP_PATH = ("/social/", "/c/", "/gz/", "/login", "/afiliados", "/ajuda")


def product_url_from_social_html(html: str) -> str | None:
    for raw in _PRODUCT_HREF.findall(html or ""):
        candidate = unescape(raw).split("#")[0]
        if not re.search(r"MLB", candidate, re.I):
            continue
        path = (urlparse(candidate).path or "").lower()
        if any(token in path for token in _SKIP_PATH):
            continue
        cleaned = sanitize_purchase_url(candidate)
        if cleaned:
            return cleaned
    return None


async def fetch_page(url: str, *, client: httpx.AsyncClient | None = None) -> tuple[str | None, str]:
    owns = client is None
    http = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_HEADERS, max_redirects=8)
    try:
        response = await http.get(url)
        final = str(response.url) if response.url else None
        return sanitize_purchase_url(final) or final, response.text or ""
    except Exception as exc:
        log.warning("inbox_redirect_skip", url=url[:160], error=str(exc)[:160])
        return None, ""
    finally:
        if owns:
            await http.aclose()


async def follow_redirect(url: str, *, client: httpx.AsyncClient | None = None) -> str | None:
    final, _html = await fetch_page(url, client=client)
    return final


async def resolve_social_product(url: str, *, client: httpx.AsyncClient | None = None) -> str | None:
    final, html = await fetch_page(url, client=client)
    found = product_url_from_social_html(html) if html else None
    if found:
        return found
    if final and not is_ml_social_url(final):
        _market, native = parse_product_url(final)
        if native:
            return final
    return None


async def unveil_urls(urls: list[str]) -> list[str]:
    if not urls:
        return []
    seen: set[str] = set()
    resolved: list[str] = []

    def take(item: str | None) -> None:
        if not item or item in seen:
            return
        seen.add(item)
        resolved.append(item)

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=_HEADERS, max_redirects=8) as client:
        for url in urls:
            take(url)
            market, native = parse_product_url(url)
            landing = is_ml_social_url(url)
            if native and not landing:
                continue
            if not landing and not needs_resolve(url):
                continue
            final, html = await fetch_page(url, client=client)
            take(final)
            if html and (landing or is_ml_social_url(final)):
                take(product_url_from_social_html(html))
    return resolved
