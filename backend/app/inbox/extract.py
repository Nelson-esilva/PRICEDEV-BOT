from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

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
    "a.aliexpress.com",
    "s.shopee.com.br",
    "shope.ee",
    "heylink.me",
    "www.heylink.me",
    "aoferta.net",
    "www.aoferta.net",
    "amzlinks.in",
    "link.amazon",
    "shorturl.at",
    "t.co",
    "tinyurl.com",
    "meli.la",
    "www.meli.la",
}
_ALI_PC_LINK = re.compile(
    r"link\s*pc\b[^\n\r]{0,80}?(https?://[^\s<>\"']+)",
    re.I,
)
_ALI_COINS_LINK = re.compile(
    r"(?:moedas|vai\s+abrir|pelo\s+app|no\s+app|primeiro\s+produto|p[aá]gina\s+de\s+moedas)"
    r"[^\n\r]{0,160}?(https?://[^\s<>\"']+)",
    re.I,
)


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


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip(").,]}>")


def _urls_labeled(pattern: re.Pattern[str], text: str | None) -> set[str]:
    found: set[str] = set()
    for match in pattern.finditer(text or ""):
        raw = _norm_url(match.group(1))
        if raw:
            found.add(raw)
    return found


def pick_product_url(urls: list[str], text: str | None = None) -> str | None:
    """Escolhe o link do produto. No AliExpress, prefere 'Link PC' e evita moedas/app/heylink."""
    pc_links = _urls_labeled(_ALI_PC_LINK, text)
    coins_links = _urls_labeled(_ALI_COINS_LINK, text)
    ranked: list[tuple[int, str]] = []
    for url in urls:
        candidate = _norm_url(url)
        market, native = parse_product_url(candidate)
        host = (host_of(candidate) or "").lower()
        if any(token == host or host.endswith("." + token) for token in _SKIP_HOSTS):
            score = 0
        elif is_aggregator_url(candidate):
            score = 0
        elif native and (market or infer_marketplace(candidate, "")) in _CANONICAL:
            score = 3
        elif (market or infer_marketplace(candidate, "")) in _CANONICAL:
            score = 2
        elif "aliexpress." in host or host in {"a.aliexpress.com", "s.click.aliexpress.com", "ali.pub"}:
            score = 2
        elif needs_resolve(candidate) or sanitize_purchase_url(candidate):
            score = 1
        else:
            score = 0
        if candidate in pc_links or any(
            candidate.rstrip("/") == item.rstrip("/") for item in pc_links
        ):
            score += 10
        if candidate in coins_links or any(
            candidate.rstrip("/") == item.rstrip("/") for item in coins_links
        ):
            score -= 8
        # Empate: AliExpress costuma pôr moedas/app antes e o Link PC depois.
        position = (text or "").rfind(candidate)
        ranked.append((score, position, candidate))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2] if ranked and ranked[0][0] > 0 else None


# Só bloco explícito de links de cupom — "aplique o cupom de R$300 OFF" não conta.
_COUPON_HINT = re.compile(
    r"resgate\s+(?:todos\s+os\s+)?cupons|cupons\s*:|links?\s+(?:dos?\s+)?cupons?",
    re.I,
)


def extract_coupon_links(
    text: str | None,
    urls: list[str],
    product_url: str | None = None,
    *,
    limit: int = 5,
) -> list[str]:
    """Links extras de cupom (ex.: 'Resgate todos os cupons' + s.shopee.com.br/…)."""
    raw_text = text or ""
    hint = _COUPON_HINT.search(raw_text)
    if not hint:
        return []
    # Preferência: URLs que aparecem depois do bloco de cupom no texto.
    section = extract_urls(raw_text[hint.start() :])
    pool = section or list(urls)
    product_canon = canonical_product_url(product_url)
    _market, product_native = parse_product_url(product_url)
    found: list[str] = []
    seen: set[str] = set()
    for url in pool:
        raw = (url or "").strip()
        if not raw or raw in seen:
            continue
        host = (host_of(raw) or "").lower()
        if any(token == host or host.endswith("." + token) for token in _SKIP_HOSTS):
            continue
        if any(token in host for token in _IMAGE_HOSTS) or _IMAGE_EXT.search(raw):
            continue
        canon = canonical_product_url(raw)
        if product_canon and canon == product_canon:
            continue
        if product_url and raw.rstrip("/") == product_url.rstrip("/"):
            continue
        _m, native = parse_product_url(raw)
        if product_native and native and native.lower() == product_native.lower():
            continue
        seen.add(raw)
        found.append(raw)
        if len(found) >= limit:
            break
    return found


def title_from_text(text: str | None, fallback: str = "Promoção do grupo") -> str:
    return parse_deal(text, fallback=fallback).title


def describe_link(url: str | None) -> tuple[str, str]:
    market, native = parse_product_url(url)
    marketplace = market or infer_marketplace(url, "unknown")
    if marketplace not in _CANONICAL:
        marketplace = "afiliado" if url else "unknown"
    return marketplace, native or ""


def canonical_product_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = (parsed.path or "").rstrip("/")
    return urlunparse((parsed.scheme.lower() or "https", host, path, "", "", ""))


_GENERIC_CODES = {"AMAZON", "SHOPEE", "MERCADO", "MAGALU", "KABUM", "PRIME"}
_TRAIL_CODE = re.compile(r":\s*([A-Z0-9]{5,24})\s*$")
_STORE_HOME = re.compile(
    r"^https://(?:www\.)?(?:amazon\.com\.br|mercadolivre\.com\.br|shopee\.com\.br)/?$",
    re.I,
)
# Só páginas de bio/lista — aoferta.net é short de loja (Terabyte etc.), não mechan.
_AGGREGATOR_HOSTS = {
    "heylink.me",
    "www.heylink.me",
    "linktr.ee",
    "www.linktr.ee",
    "bio.site",
    "beacons.ai",
    "lit.link",
}
_COUPON_MECHAN = re.compile(
    r"\d+\s*%\s*off|"
    r"a\s+partir\s+de\s+r\$|"
    r"limite\s+de\s+r\$|"
    r"cupom\s+(?:mercado|amazon|shopee|magalu|kabum)\b|"
    r"resgatar\s+agora|"
    r"resgate\s+(?:todos\s+os\s+)?cupons",
    re.I,
)


def is_aggregator_url(url: str | None) -> bool:
    host = (host_of(url) or "").lower()
    if not host:
        return False
    if host in _AGGREGATOR_HOSTS:
        return True
    return any(host.endswith("." + token) for token in _AGGREGATOR_HOSTS if not token.startswith("www."))


def is_coupon_mechan(
    *,
    text: str | None,
    title: str | None = None,
    url: str | None = None,
    native_id: str | None = None,
) -> bool:
    """Banner/campanha de cupom sem produto real (mechan de outro grupo)."""
    if (native_id or "").strip():
        return False
    blob = f"{title or ''}\n{text or ''}"
    campaign = bool(_COUPON_MECHAN.search(blob))
    aggregator = is_aggregator_url(url)
    return aggregator or campaign


def inbox_fingerprint(title: str | None, marketplace: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", (title or "").lower())[:48]
    if len(slug) < 20:
        return ""
    return f"fp:{(marketplace or 'x').strip().lower()}:{slug}"


def inbox_campaign_key(
    *,
    marketplace: str | None,
    title: str | None,
    coupon: str | None = None,
    price=None,
    listed=None,
) -> str:
    market = (marketplace or "x").strip().lower()
    codes: list[str] = []
    trail = _TRAIL_CODE.search((title or "").strip())
    if trail:
        codes.append(trail.group(1).upper())
    if coupon:
        codes.append(str(coupon).strip().upper())
    code = next((item.lower() for item in codes if item and item not in _GENERIC_CODES), "")
    if not code:
        return ""
    amounts: list[int] = []
    for value in (price, listed):
        if value is None:
            continue
        try:
            reais = int(value)
        except (TypeError, ValueError):
            continue
        if reais > 0:
            amounts.append(reais)
    if amounts:
        return f"campaign:{market}:{code}:{max(amounts)}"
    return f"campaign:{market}:{code}"


def inbox_identity_key(
    marketplace: str | None,
    native_id: str | None,
    url: str | None = None,
) -> str:
    """Mesmo MLB/ASIN/item em grupos diferentes vira a mesma chave."""
    native = (native_id or "").strip()
    market = (marketplace or "unknown").strip().lower()
    if not native and url:
        parsed_market, parsed_native = parse_product_url(url)
        if parsed_native:
            native = parsed_native
            market = (parsed_market or market).lower()
    if native:
        return f"{market}:{native.lower()}"
    if needs_resolve(url) or is_ml_social_url(url):
        return ""
    canon = canonical_product_url(url)
    if not canon or _STORE_HOME.match(canon):
        return ""
    return f"url:{canon}"
