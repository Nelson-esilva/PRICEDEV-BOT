from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.urls import is_ml_social_url, sanitize_purchase_url

log = get_logger("affiliates")

SHOPEE_HOSTS = {"shopee.com.br", "shope.ee", "shp.ee"}
AMAZON_SHORT_HOSTS = {"amzn.to", "amzn.asia", "a.co"}
_ML_DROP = {"forceinapp", "ref", "matt_word", "matt_tool"}
_ML_SKIP_PREFIXES = ("/afiliados", "/gz/", "/ajuda")
_ML_SOCIAL_DROP = {"forceinapp", "matt_word", "matt_tool"}
_AMAZON_DROP = {"tag", "ascsubtag", "linkcode", "creative", "creativeasin", "adid", "camp"}
_AMAZON_PATH = ("/dp/", "/gp/product/", "/gp/aw/d/")
_AMAZON_ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.I)
_AMAZON_QUERY_ASIN = re.compile(r"(?:^|[?&])asin=([A-Z0-9]{10})", re.I)


class AffiliateResolution:
    def __init__(
        self,
        *,
        original: str | None,
        validated: str | None,
        affiliate: str | None,
        final: str | None,
        network: str | None,
        status: str,
    ) -> None:
        self.original = original
        self.validated = validated
        self.affiliate = affiliate
        self.final = final
        self.network = network
        self.status = status


def _host(url: str | None) -> str:
    if not url:
        return ""
    return (urlparse(url).hostname or "").lower()


def _is_mercadolivre_host(host: str) -> bool:
    return host.endswith("mercadolivre.com.br") or host.endswith("mercadolibre.com")


def _is_ml_product_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not _is_mercadolivre_host(host):
        return False
    path = (parsed.path or "/").lower()
    if is_ml_social_url(url):
        return True
    if any(path.startswith(prefix) for prefix in _ML_SKIP_PREFIXES):
        return False
    upper = (parsed.path or "").upper()
    return "MLB" in upper or host.startswith("produto.")


def stamp_mercadolivre(url: str | None, settings: Settings) -> str | None:
    word = (settings.ml_affiliate_matt_word or "").strip()
    tool = (settings.ml_affiliate_matt_tool or "").strip()
    if not url or not word or not tool or not _is_ml_product_url(url):
        return None
    drop = _ML_SOCIAL_DROP if is_ml_social_url(url) else _ML_DROP
    parsed = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in drop
    ]
    kept.append(("matt_word", word))
    kept.append(("matt_tool", tool))
    stamped = urlunparse(parsed._replace(query=urlencode(kept)))
    return sanitize_purchase_url(stamped)


def _amazon_asin(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    match = _AMAZON_ASIN.search(parsed.path or "") or _AMAZON_QUERY_ASIN.search(url)
    return match.group(1).upper() if match else None


def _is_amazon_product_url(url: str | None) -> bool:
    if not url:
        return False
    host = _host(url)
    if "amazon." not in host:
        return False
    path = (urlparse(url).path or "").lower()
    return bool(_amazon_asin(url)) or any(token in path for token in _AMAZON_PATH)


def stamp_amazon(url: str | None, settings: Settings) -> str | None:
    tag = (settings.amazon_affiliate_tag or "").strip()
    if not url or not tag or "amazon." not in _host(url):
        return None
    asin = _amazon_asin(url)
    if asin:
        host = urlparse(url).hostname or "www.amazon.com.br"
        return sanitize_purchase_url(f"https://{host}/dp/{asin}?tag={tag}")
    if not _is_amazon_product_url(url):
        return None
    parsed = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _AMAZON_DROP
    ]
    kept.append(("tag", tag))
    stamped = urlunparse(parsed._replace(query=urlencode(kept)))
    return sanitize_purchase_url(stamped)


def stamp_owned_link(url: str | None, settings: Settings) -> str | None:
    return stamp_mercadolivre(url, settings) or stamp_amazon(url, settings)


async def resolve_links(
    *,
    original_url: str | None,
    existing_affiliate: str | None,
    settings: Settings,
    http: httpx.AsyncClient | None = None,
) -> AffiliateResolution:
    original = sanitize_purchase_url(original_url)
    affiliate = sanitize_purchase_url(existing_affiliate)
    if original and _host(original) in AMAZON_SHORT_HOSTS:
        followed = await _follow(original, http)
        if followed:
            original = followed
    for candidate in (original, affiliate):
        stamped = stamp_owned_link(candidate, settings)
        if stamped:
            host = _host(stamped)
            network = "amazon" if "amazon." in host else "mercadolivre"
            return AffiliateResolution(
                original=original_url,
                validated=original,
                affiliate=stamped,
                final=stamped,
                network=network,
                status="converted",
            )
    if affiliate:
        return AffiliateResolution(
            original=original_url,
            validated=original,
            affiliate=affiliate,
            final=affiliate,
            network="shopee" if _host(affiliate) in SHOPEE_HOSTS or "shopee" in _host(affiliate) else "unknown",
            status="official",
        )
    if original and _host(original) in SHOPEE_HOSTS and settings.enable_shopee and settings.shopee_app_id:
        short = await _shopee_shortlink(original, settings, http)
        if short:
            return AffiliateResolution(
                original=original_url,
                validated=original,
                affiliate=short,
                final=short,
                network="shopee",
                status="converted",
            )
    if original and settings.enable_lomadee and settings.lomadee_app_token:
        converted = await _lomadee_create_link(original, settings, http)
        if converted:
            return AffiliateResolution(
                original=original_url,
                validated=original,
                affiliate=converted,
                final=converted,
                network="lomadee",
                status="converted",
            )
    if original:
        return AffiliateResolution(
            original=original_url,
            validated=original,
            affiliate=None,
            final=original,
            network=None,
            status="direct",
        )
    return AffiliateResolution(
        original=original_url,
        validated=None,
        affiliate=None,
        final=None,
        network=None,
        status="unpublishable",
    )


async def _follow(url: str, http: httpx.AsyncClient | None) -> str | None:
    client = http or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    close = http is None
    try:
        response = await client.get(url)
        final = str(response.url) if response.url else None
        return sanitize_purchase_url(final) or final
    except Exception as exc:
        log.warning("amazon_short_follow_failed", error=str(exc)[:160])
        return None
    finally:
        if close:
            await client.aclose()


async def _shopee_shortlink(
    url: str, settings: Settings, http: httpx.AsyncClient | None
) -> str | None:
    from app.sources.shopee import ShopeeSource

    client = http or httpx.AsyncClient(timeout=20.0)
    close = http is None
    try:
        source = ShopeeSource(settings, client=client)
        return await source.generate_short_link(url)
    except Exception as exc:
        log.warning("shopee_shortlink_failed", error=str(exc))
        return None
    finally:
        if close:
            await client.aclose()


async def _lomadee_create_link(
    url: str, settings: Settings, http: httpx.AsyncClient | None
) -> str | None:
    """Adaptador opcional. Contrato histórico; falha devolve None e o pipeline segue com link direto."""
    token = settings.lomadee_app_token
    source_id = settings.lomadee_source_id
    if not token or not source_id:
        return None
    endpoint = (
        f"https://api.lomadee.com/v3/{token}/createLinks"
        f"?sourceId={source_id}&url={url}"
    )
    client = http or httpx.AsyncClient(timeout=15.0)
    close = http is None
    try:
        resp = await client.get(endpoint)
        if resp.status_code != 200:
            log.warning("lomadee_http", status=resp.status_code)
            return None
        payload = resp.json()
        link = None
        if isinstance(payload, dict):
            link = (
                payload.get("shortUrl")
                or payload.get("redirectLink")
                or (payload.get("lomadees") or [{}])[0].get("redirectLink")
            )
        return sanitize_purchase_url(link) if isinstance(link, str) else None
    except Exception as exc:
        log.warning("lomadee_failed", error=str(exc))
        return None
    finally:
        if close:
            await client.aclose()
