from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.urls import sanitize_purchase_url

log = get_logger("affiliates")

SHOPEE_HOSTS = {"shopee.com.br", "shope.ee", "shp.ee"}


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


async def resolve_links(
    *,
    original_url: str | None,
    existing_affiliate: str | None,
    settings: Settings,
    http: httpx.AsyncClient | None = None,
) -> AffiliateResolution:
    original = sanitize_purchase_url(original_url)
    affiliate = sanitize_purchase_url(existing_affiliate)
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
