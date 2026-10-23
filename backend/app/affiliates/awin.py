"""Conversão KaBuM! pelo Link Builder oficial da Awin."""

from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("awin")
AWIN_HOSTS = {"awin1.com", "www.awin1.com"}


def kabum_destination(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.hostname in AWIN_HOSTS:
        query = parse_qs(parsed.query)
        url = (query.get("ued") or [""])[0]
        parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "kabum.com.br" or host.endswith(".kabum.com.br")):
        return None
    # Só produtos; remove tracking de terceiros antes de gerar o nosso link.
    import re

    match = re.match(r"^/produto/(\d+)(?:/|$)", parsed.path)
    if not match:
        return None
    return f"https://www.kabum.com.br/produto/{match.group(1)}"


def awin_ready(settings: Settings) -> bool:
    return bool(
        settings.enable_awin
        and settings.awin_publisher_id.isdigit()
        and settings.awin_kabum_advertiser_id.isdigit()
        and settings.awin_api_token.strip()
    )


def is_owned_kabum(url: str | None, settings: Settings) -> bool:
    if not url or not settings.enable_awin:
        return False
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.scheme != "https" or parsed.hostname not in AWIN_HOSTS:
        return False
    if parsed.path == "/pclick.php":
        return bool(
            settings.awin_publisher_id and settings.awin_kabum_advertiser_id
            and query.get("a") == [settings.awin_publisher_id]
            and query.get("m") == [settings.awin_kabum_advertiser_id]
            and len(query.get("p", [])) == 1 and query["p"][0].isdigit()
        )
    return bool(
        kabum_destination(url)
        and
        settings.awin_publisher_id
        and settings.awin_kabum_advertiser_id
        and parsed.hostname in AWIN_HOSTS
        and parsed.path == "/cread.php"
        and query.get("awinaffid") == [settings.awin_publisher_id]
        and query.get("awinmid") == [settings.awin_kabum_advertiser_id]
    )


async def ensure_owned_kabum(
    url: str | None, settings: Settings, *, existing: str | None = None,
    http: httpx.AsyncClient | None = None,
) -> str | None:
    for candidate in (existing, url):
        if is_owned_kabum(candidate, settings):
            return candidate
    destination = kabum_destination(url) or kabum_destination(existing)
    if not destination or not awin_ready(settings):
        return None
    client = http or httpx.AsyncClient(timeout=15.0)
    try:
        response = await client.post(
            f"https://api.awin.com/publishers/{settings.awin_publisher_id}/linkbuilder/generate",
            headers={"Authorization": f"Bearer {settings.awin_api_token}"},
            json={"advertiserId": int(settings.awin_kabum_advertiser_id),
                  "destinationUrl": destination, "shorten": False},
        )
        if response.status_code != 200:
            log.warning("link_failed", status=response.status_code)
            return None
        payload = response.json()
        link = payload.get("url") if isinstance(payload, dict) else None
        if isinstance(link, str) and is_owned_kabum(link, settings) and kabum_destination(link) == destination:
            return link
        log.warning("invalid_tracking_link")
        return None
    except (httpx.HTTPError, ValueError):
        # Não registrar exceções/respostas que possam conter credenciais.
        log.warning("link_request_failed")
        return None
    finally:
        if http is None:
            await client.aclose()
