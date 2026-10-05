from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.urls import host_of, is_ml_social_url, sanitize_media_url, sanitize_purchase_url
from app.inbox.parse import parse_deal
from app.ingestion.identity import infer_marketplace, parse_product_url

_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_SKIP_HOSTS = ("t.me", "telegram.me", "whatsapp.com", "wa.me")
_CANONICAL = {"mercadolivre", "amazon", "shopee", "magalu", "kabum", "netshoes"}
_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", re.I)
_IMAGE_HOSTS = (
    "mlstatic.com",
    "m.media-amazon.com",
    "images-na.ssl-images-amazon.com",
    "images-amazon.com",
    "images.kabum.com.br",
    "a-static.mlcdn.com.br",
    "cf.shopee.com.br",
    "down-br.img.susercontent.com",
    "media.pelando.com.br",
)
RESOLVE_HOSTS = {
    "amzn.to",
    "amzn.asia",
    "awin1.com",
    "www.awin1.com",
    "bit.ly",
    "bitly.com",
    "click.lomadee.com",
    "cutt.ly",
    "dpl.pelando.com.br",
    "is.gd",
    "ali.pub",
    "magalu.app",
    "rb.gy",
    "redir.lomadee.com",
    "s.click.aliexpress.com",
    "s.shopee.com.br",
    "shope.ee",
    "shorturl.at",
    "t.co",
    "tinyurl.com",
    "meli.la",
    "www.meli.la",
}


def needs_resolve(url: str | None) -> bool:
    host = host_of(url)
    if not host:
        return False
    if any(token == host or host.endswith("." + token) for token in _SKIP_HOSTS):
        return False
    if is_ml_social_url(url):
        return True
    market, native = parse_product_url(url)
    if native and market in _CANONICAL:
        return False
    if host in RESOLVE_HOSTS or host.endswith(".lomadee.com"):
        return True
    if host.endswith(".pelando.com.br") and host != "www.pelando.com.br":
        return True
    return market not in _CANONICAL


def extract_urls(text: str | None, extra: list[str] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in [*(extra or []), *(_URL.findall(text or ""))]:
        candidate = raw.rstrip(").,]}>")
        cleaned = sanitize_purchase_url(candidate) or _keep_opaque(candidate)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        found.append(cleaned)
    return found


def _keep_opaque(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if any(token == host or host.endswith("." + token) for token in _SKIP_HOSTS):
        return None
    if needs_resolve(url):
        return url.strip()
    return None


def extract_image_urls(text: str | None, extra: list[str] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in [*(extra or []), *(_URL.findall(text or ""))]:
        cleaned = sanitize_media_url(raw.rstrip(").,]}>"))
        if not cleaned or cleaned in seen:
            continue
        host = host_of(cleaned) or ""
        if _IMAGE_EXT.search(cleaned) or any(token in host for token in _IMAGE_HOSTS):
            seen.add(cleaned)
            found.append(cleaned)
    return found


def pick_product_url(urls: list[str]) -> str | None:
    ranked: list[tuple[int, str]] = []
    for url in urls:
        market, native = parse_product_url(url)
        host = (host_of(url) or "").lower()
        if any(token == host or host.endswith("." + token) for token in _SKIP_HOSTS):
            score = 0
        elif native and (market or infer_marketplace(url, "")) in _CANONICAL:
            score = 3
        elif (market or infer_marketplace(url, "")) in _CANONICAL:
            score = 2
        elif needs_resolve(url) or sanitize_purchase_url(url):
            score = 1
        else:
            score = 0
        ranked.append((score, url))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else None


def title_from_text(text: str | None, fallback: str = "Promoção do grupo") -> str:
    return parse_deal(text, fallback=fallback).title


def describe_link(url: str | None) -> tuple[str, str]:
    market, native = parse_product_url(url)
    marketplace = market or infer_marketplace(url, "unknown")
    if marketplace not in _CANONICAL:
        marketplace = "afiliado" if url else "unknown"
    return marketplace, native or ""
