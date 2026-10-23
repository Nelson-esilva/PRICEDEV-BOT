from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlencode, urlparse, urlunparse

from app.affiliates.resolver import stamp_owned_link
from app.affiliates.awin import AWIN_HOSTS, awin_ready, ensure_owned_kabum, is_owned_kabum, kabum_destination
from app.core.config import Settings
from app.core.logging import get_logger
from sqlalchemy.exc import IntegrityError

from app.models.entities import InboxMessage, Opportunity, PublicationLog
from app.publishing.outbox import OutgoingDeal, enqueue
from app.schemas.normalized import Classification

log = get_logger("telegram")


def publish_chat(settings: Settings) -> str:
    return (settings.telegram_publish_chat or settings.telegram_chat_id or "").strip()


_PHOTO_HOSTS = (
    "mlstatic.com",
    "media-amazon.com",
    "images-amazon.com",
    "ssl-images-amazon.com",
    "images.kabum.com.br",
    "a-static.mlcdn.com.br",
    "cf.shopee.com.br",
    "susercontent.com",
    "media.pelando.com.br",
)
_PHOTO_EXT = re.compile(r"\.(?:jpe?g|png|webp)(?:\?|$)", re.I)


def compact_affiliate_url(url: str | None, settings: Settings) -> str | None:
    from app.core.urls import is_ml_social_url

    if is_owned_kabum(url, settings):
        return url
    if kabum_destination(url):
        return url if is_owned_kabum(url, settings) else None
    if (urlparse(url or "").hostname or "").lower() in AWIN_HOSTS:
        return None
    owned = owned_purchase_url(url, settings) or url
    if not owned or is_ml_social_url(owned):
        return None
    parsed = urlparse(owned)
    host = (parsed.hostname or "").lower()
    if "amazon." in host:
        stamped = stamp_owned_link(owned, settings)
        if stamped:
            return stamped
        tag = (settings.amazon_affiliate_tag or "").strip()
        if tag and f"tag={tag}" in owned:
            return owned
        return None
    if "mercadolivre." in host or "mercadolibre." in host:
        return _compact_ml_url(owned, settings)
    if "shopee." in host or host in {"s.shopee.com.br", "shope.ee", "shp.ee"}:
        from app.affiliates.resolver import is_owned_shopee

        # Shopee só passa se já tiver o an_<app_id> deste bot.
        return owned if is_owned_shopee(owned, settings) else None
    if "kabum." in host or "magazineluiza." in host or "magalu." in host:
        return _compact_store_url(owned, host)
    from app.inbox.extract import is_aggregator_url

    if is_aggregator_url(owned):
        return None
    return owned


async def ensure_publish_url(
    url: str | None,
    settings: Settings,
    *,
    existing: str | None = None,
    http=None,
) -> str | None:
    """Garante afiliado próprio. Shopee passa pela API; ML/Amazon carimbam local."""
    from app.affiliates.resolver import ensure_owned_shopee, is_shopee_url

    if kabum_destination(url) or kabum_destination(existing):
        return await ensure_owned_kabum(url, settings, existing=existing, http=http)
    sync = compact_affiliate_url(url, settings)
    if sync:
        return sync
    if existing:
        sync_existing = compact_affiliate_url(existing, settings)
        if sync_existing:
            return sync_existing
    if is_shopee_url(url) or is_shopee_url(existing):
        return await ensure_owned_shopee(url, settings, existing=existing, http=http)
    return None


def _compact_ml_url(url: str, settings: Settings) -> str:
    from app.ingestion.identity import parse_product_url

    parsed = urlparse(url)
    word = (settings.ml_affiliate_matt_word or "").strip()
    tool = (settings.ml_affiliate_matt_tool or "").strip()
    kept = [("matt_word", word), ("matt_tool", tool)] if word and tool else []
    query = urlencode(kept)
    _market, native = parse_product_url(url)
    if native:
        code = native.upper().replace("-", "")
        path = (parsed.path or "").lower()
        # MLBU é página /up/… — /p/MLBU… dá 404 no navegador desktop.
        if code.startswith("MLBU") or "/up/" in path:
            return urlunparse(("https", "www.mercadolivre.com.br", f"/up/{code}", "", query, ""))
        if "/p/" in path:
            return urlunparse(("https", "www.mercadolivre.com.br", f"/p/{code}", "", query, ""))
        dashed = f"MLB-{code[3:]}" if code.startswith("MLB") else code
        return urlunparse(("https", "produto.mercadolivre.com.br", f"/{dashed}", "", query, ""))
    return urlunparse(parsed._replace(query=query, fragment=""))


def _compact_store_url(url: str, host: str) -> str:
    from app.ingestion.identity import parse_product_url

    parsed = urlparse(url)
    clean = urlunparse(parsed._replace(query="", fragment=""))
    _market, native = parse_product_url(url)
    if not native:
        return clean
    if "kabum." in host:
        return f"https://www.kabum.com.br/produto/{native}"
    if "magazineluiza." in host or "magalu." in host:
        return f"https://www.magazineluiza.com.br/p/{native}/"
    return clean


def _catalog_cover(opp, url: str | None) -> str | None:
    from app.inbox.media import catalog_image
    from app.ingestion.identity import parse_product_url

    market = str(getattr(opp, "marketplace", "") or getattr(opp, "merchant", "") or "")
    native = str(getattr(opp, "native_product_id", "") or "")
    if not native and url:
        parsed_market, parsed_native = parse_product_url(url)
        native = parsed_native or ""
        market = parsed_market or market
    return catalog_image(
        marketplace=market.lower(),
        native_id=native,
        text=str(getattr(opp, "product_name", "") or ""),
        urls=[url] if url else None,
    )


async def _resolve_publish_photo(opp, link: str | None) -> str | None:
    """Só devolve URL/path se a imagem for JPEG/PNG utilizável."""
    from app.inbox.media import resolve_amazon_image, resolve_catalog_image
    from app.ingestion.identity import parse_product_url
    from app.publishing.outbox import _photo_jpeg

    candidates: list[str] = []
    primary = deal_photo(getattr(opp, "image_url", None))
    if primary:
        candidates.append(primary)
    cover = deal_photo(_catalog_cover(opp, link))
    if cover and cover not in candidates:
        candidates.append(cover)

    market = str(getattr(opp, "marketplace", "") or "").strip().lower()
    native = str(getattr(opp, "native_product_id", "") or "").strip()
    if not native and link:
        parsed_market, parsed_native = parse_product_url(link)
        native = parsed_native or ""
        market = (parsed_market or market).lower()
    if market == "amazon" and native:
        amazon = await resolve_amazon_image(native)
        if amazon:
            photo = deal_photo(amazon)
            if photo and photo not in candidates:
                candidates.append(photo)
    elif market == "mercadolivre" and native and not candidates:
        ml = await resolve_catalog_image(
            marketplace=market,
            native_id=native,
            text=str(getattr(opp, "product_name", "") or ""),
            urls=[link] if link else None,
        )
        photo = deal_photo(ml)
        if photo:
            candidates.append(photo)

    for candidate in candidates:
        if await _photo_jpeg(candidate) is not None:
            return candidate
    return None


def deal_photo(url: str | None) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    if raw.startswith("/api/v1/inbox/media/"):
        from app.inbox.media import media_path

        path = media_path(raw.rsplit("/", 1)[-1])
        return str(path) if path else None
    if not raw.startswith("http"):
        return None
    host = (urlparse(raw).hostname or "").lower()
    if any(token in host for token in _PHOTO_HOSTS) or _PHOTO_EXT.search(raw):
        return _as_jpeg_url(raw)
    return None


def _as_jpeg_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path.lower().endswith(".webp"):
        return urlunparse(parsed._replace(path=path[:-5] + ".jpg"))
    return url


def owned_purchase_url(url: str | None, settings: Settings) -> str | None:
    if not url:
        return None
    stamped = stamp_owned_link(url, settings)
    if stamped:
        return stamped
    word = (settings.ml_affiliate_matt_word or "").strip()
    tag = (settings.amazon_affiliate_tag or "").strip()
    if word and f"matt_word={word}" in url:
        return url
    if tag and f"tag={tag}" in url:
        return url
    return None


_STORE = {
    "mercadolivre": "Mercado Livre",
    "mercado livre": "Mercado Livre",
    "amazon": "Amazon",
    "shopee": "Shopee",
    "magalu": "Magazine Luiza",
    "magazine luiza": "Magazine Luiza",
    "kabum": "KaBuM!",
    "kabum!": "KaBuM!",
    "aliexpress": "AliExpress",
    "netshoes": "Netshoes",
    "americanas": "Americanas",
    "submarino": "Submarino",
    "casasbahia": "Casas Bahia",
    "casas bahia": "Casas Bahia",
    "ponto": "Ponto",
    "extra": "Extra",
    "terabyte": "Terabyte",
    "pichau": "Pichau",
}
_BAD_STORE = {"", "afiliado", "unknown", "pelando", "none", "null"}

_SLUG_STORE = {
    "mercadolivre": "mercadolivre",
    "amazon": "amazon",
    "shopee": "shopee",
    "magalu": "magalu",
    "kabum": "kabum",
    "aliexpress": "aliexpress",
    "terabyte": "terabyte",
    "netshoes": "netshoes",
    "pichau": "pichau",
}


def _store_key_from_host(url: str | None) -> str | None:
    url = kabum_destination(url) or url
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return None
    if "amazon." in host or host in {"amzn.to", "amzn.asia", "a.co", "amzlinks.in", "link.amazon"}:
        return "amazon"
    if "mercadolivre." in host or "mercadolibre." in host or host in {"meli.la", "www.meli.la"}:
        return "mercadolivre"
    if "shopee." in host or host in {"s.shopee.com.br", "shope.ee", "shp.ee"}:
        return "shopee"
    if "kabum." in host:
        return "kabum"
    if "magazineluiza." in host or "magalu." in host or host in {"magalu.app"}:
        return "magalu"
    if "aliexpress." in host:
        return "aliexpress"
    if "terabyte" in host or host.endswith("aoferta.net"):
        return "terabyte"
    if "netshoes." in host:
        return "netshoes"
    if "pichau." in host:
        return "pichau"
    return None


def _path_code(url: str | None) -> str | None:
    path = (urlparse(url or "").path or "").strip("/")
    if not path:
        return None
    parts = [part for part in path.split("/") if part and part.lower() not in {"product", "produto", "p", "item"}]
    if not parts:
        return None
    token = parts[-1]
    token = re.sub(r"[^A-Za-z0-9_-]+", "", token)
    if len(token) < 3:
        return None
    return token[:40]


def short_store_slug(url: str | None) -> str | None:
    from app.ingestion.identity import parse_product_url

    if not url:
        return None
    market, native = parse_product_url(url)
    store = _SLUG_STORE.get((market or "").lower()) or _store_key_from_host(url)
    code = (native or "").strip() or (_path_code(url) or "")
    if store and code:
        if store == "amazon":
            code = code.upper()
        elif store == "mercadolivre":
            code = code.upper().replace("-", "")
        return f"{store}/{code}"
    if store:
        return store
    return None


def _link_label(url: str, store: str | None = None, link_label: str | None = None) -> str:
    slug = (link_label or short_store_slug(url) or "").strip()
    if slug:
        return slug
    shop = store_label(store, url)
    if shop:
        return re.sub(r"\s+", "", shop.lower())
    return "abrir oferta"


def format_message(opp: Opportunity, settings: Settings | None = None) -> str:
    from app.affiliates.resolver import is_owned_shopee, is_shopee_url
    from app.core.config import get_settings

    settings = settings or get_settings()
    raw = opp.final_purchase_url or getattr(opp, "purchase_url", None)
    url = compact_affiliate_url(raw, settings) or ""
    # Short Shopee gerado pela API não traz an_<id> na URL; se não for de terceiro, mantém.
    if not url and raw and is_shopee_url(raw) and (
        is_owned_shopee(raw, settings) or "an_" not in raw.lower()
    ):
        url = raw
    # Lojas sem afiliado próprio (Terabyte, AliExpress, aoferta…): mantém o link cru.
    if not url and raw and _store_key_from_host(raw):
        from app.inbox.extract import is_aggregator_url

        if not is_aggregator_url(raw):
            url = raw
    store = store_label(getattr(opp, "merchant", None), url or raw or "")
    return format_deal(
        title=opp.product_name,
        price=_positive(opp.current_price),
        listed=_listed_price(opp),
        url=url,
        coupon=getattr(opp, "coupon_code", None),
        coupon_links=list(getattr(opp, "coupon_links", None) or []),
        store=store,
        installment=_installment_of(getattr(opp, "payment_hint", None)),
        link_label=short_store_slug(url),
    )


def format_deal(
    *,
    title: str,
    price: Decimal | None,
    url: str,
    listed: Decimal | None = None,
    coupon: str | None = None,
    coupon_links: list[str] | None = None,
    store: str | None = None,
    installment: str | None = None,
    link_label: str | None = None,
    **_unused,
) -> str:
    blocks = ["🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥", "", _html(_clean_title(title))]
    listed = _positive(listed)
    price = _positive(price)
    prices: list[str] = []
    if listed and price and listed > price:
        prices.append(f"💰 De: <s>{_brl(listed)}</s>")
    if price:
        prices.append(f"💚 <b><u>POR {_brl(price)}</u></b>")
    parcel = _installment_of(installment)
    if parcel:
        prices.append(f"💳 {_html(parcel)}")
    if prices:
        blocks.extend(["", "\n".join(prices)])
    extras: list[str] = []
    code = (coupon or "").strip()
    if code:
        extras.append(f"🎟️ <b>Cupom:</b> {_html(code)}")
    shop = (store or "").strip()
    if shop and shop.lower() not in _BAD_STORE:
        extras.append(f"🛒 <b>Loja:</b> {_html(shop)}")
    if extras:
        blocks.extend(["", "\n".join(extras)])
    claim = [item.strip() for item in (coupon_links or []) if (item or "").strip()]
    if claim:
        lines = ["🎟️ <b>Resgate os cupons:</b>"]
        for index, link in enumerate(claim[:5], start=1):
            href = _html(link).replace('"', "%22")
            lines.append(f'{index}. <a href="{href}">{_html(link)}</a>')
        blocks.extend(["", "\n".join(lines)])
    if url:
        label = _link_label(url, store, link_label)
        href = _html(url).replace('"', "%22")
        blocks.extend(["", "🔗 <b>Link p/ Compra:</b>", f'<a href="{href}">{_html(label)}</a>'])
    blocks.extend(
        [
            "",
            "⚡ <b>APROVEITE ANTES QUE ACABE!</b>",
            "",
            "⚠️ <i>Preço sujeito a alterações. Confira o valor final antes de comprar.</i>",
        ]
    )
    return "\n".join(blocks)


def button_label(store: str | None, url: str = "") -> str:
    shop = store_label(store, url)
    return f"Abrir no {shop}" if shop else "Abrir oferta"


def store_label(store: str | None, url: str = "") -> str | None:
    url = kabum_destination(url) or url
    from app.ingestion.identity import known_marketplace, parse_product_url

    raw = (store or "").strip()
    if raw and raw.lower() not in _BAD_STORE:
        mapped = _STORE.get(raw.lower())
        if mapped:
            return mapped
        # Nome de loja legível (não slug genérico) — mantém.
        if " " in raw or raw[:1].isupper():
            return raw
    market, _native = parse_product_url(url)
    known = market or known_marketplace(url)
    if known:
        return _STORE.get(known.lower()) or known
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    if "amazon." in host or host in {"amzn.to", "amzn.asia", "a.co", "amzlinks.in", "link.amazon"}:
        return "Amazon"
    if (
        "mercadolivre." in host
        or "mercadolibre." in host
        or host in {"meli.la", "www.meli.la"}
    ):
        return "Mercado Livre"
    if "kabum." in host:
        return "KaBuM!"
    if "magazineluiza." in host or "magalu." in host or host in {"magalu.app"}:
        return "Magazine Luiza"
    if "shopee." in host or host in {"s.shopee.com.br", "shope.ee", "shp.ee"}:
        return "Shopee"
    if "aliexpress." in host or host.endswith("aliexpress.com"):
        return "AliExpress"
    if "netshoes." in host:
        return "Netshoes"
    if "americanas." in host:
        return "Americanas"
    if "casasbahia." in host:
        return "Casas Bahia"
    if "terabyte" in host or host.endswith("aoferta.net"):
        return "Terabyte"
    if "pichau." in host:
        return "Pichau"
    return None


def _listed_price(opp) -> Decimal | None:
    listed = _positive(getattr(opp, "listed_price", None))
    current = _positive(getattr(opp, "current_price", None))
    if listed and current and listed > current:
        return listed
    pct = _positive(getattr(opp, "announced_discount_pct", None))
    if pct and current and 0 < pct < 90:
        reconstructed = (current / (Decimal("1") - pct / Decimal("100"))).quantize(Decimal("0.01"))
        if reconstructed > current:
            return reconstructed
    return None


def _html(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _installment_of(hint: str | None) -> str | None:
    raw = (hint or "").strip()
    if raw and re.search(r"\d+\s*x|parcela", raw, re.I):
        return raw
    return None


def _clean_title(title: str | None) -> str:
    text = re.sub(r"https?://\S+", "", title or "")
    text = re.sub(r"\s+", " ", text).strip(" -–|•*:")
    if len(text) > 120:
        cut = text[:117].rsplit(" ", 1)[0]
        text = f"{cut}…"
    return text or "Oferta"


def _positive(value) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if number <= 0:
        return None
    return number


def _brl(value: Decimal | None) -> str:
    if value is None:
        return "n/d"
    quantized = value.quantize(Decimal("0.01"))
    return f"R$ {quantized:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def should_publish(opp: Opportunity, settings: Settings) -> tuple[bool, str | None]:
    from app.affiliates.resolver import is_shopee_url

    if not settings.enable_telegram_publish:
        return False, "telegram_disabled"
    if not publish_chat(settings):
        return False, "missing_credentials"
    has_bot = bool(settings.telegram_bot_token)
    has_user = bool(settings.telegram_api_id and settings.telegram_api_hash)
    if not has_bot and not has_user:
        return False, "missing_credentials"
    if getattr(opp, "status", "active") != "active":
        return False, "inactive"
    raw = opp.final_purchase_url or getattr(opp, "purchase_url", None)
    if not raw:
        return False, "invalid_url"
    if getattr(opp, "classification", "") == Classification.EXPIRED.value:
        return False, "expired"
    if getattr(opp, "classification", "") == Classification.REJECTED.value:
        return False, "rejected"
    if compact_affiliate_url(raw, settings) is not None:
        return True, None
    if kabum_destination(raw) and awin_ready(settings):
        return True, None
    # Shopee cru / de terceiro: ainda pode virar nosso link na hora do publish.
    if is_shopee_url(raw) and settings.enable_shopee and settings.shopee_app_id:
        return True, None
    return False, "not_affiliate"


def dedup_key(opp: Opportunity) -> str:
    product_id = str(getattr(opp, "product_id", "") or "")
    if product_id.startswith("inbox:"):
        return product_id
    price = str(getattr(opp, "current_price", "") or "")
    return f"{product_id}:{price}"


def inbox_publish_key(row) -> str:
    keys = inbox_publish_keys(row)
    return keys[0] if keys else ""


def inbox_publish_keys(row) -> list[str]:
    from app.inbox.extract import inbox_campaign_key, inbox_fingerprint, inbox_identity_key
    from app.inbox.parse import parse_deal

    keys: list[str] = []
    identity = inbox_identity_key(row.marketplace, row.native_product_id, row.purchase_url)
    if identity:
        keys.append(f"inbox:{identity}")
    parsed = parse_deal(row.body or row.product_name, fallback=row.product_name)
    campaign = inbox_campaign_key(
        marketplace=row.marketplace,
        title=parsed.title or row.product_name,
        coupon=parsed.coupon,
        price=parsed.price,
        listed=parsed.listed_price,
    )
    if campaign:
        keys.append(f"inbox:{campaign}")
    if not keys:
        fingerprint = inbox_fingerprint(parsed.title or row.product_name, row.marketplace)
        if fingerprint:
            keys.append(f"inbox:{fingerprint}")
    seen: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.append(key)
    return seen


def _telegram_dedup_since(settings: Settings):
    from datetime import timedelta

    from app.core.db import utcnow

    hours = max(0.0, float(settings.telegram_dedup_hours or 0))
    return utcnow() - timedelta(hours=hours)


async def _already_published(session, keys: list[str], opp, *, since) -> bool:
    from sqlalchemy import func, select

    wanted = [item for item in keys if item]
    if wanted:
        found = (
            await session.execute(
                select(PublicationLog.id).where(
                    PublicationLog.channel == "telegram",
                    PublicationLog.dedup_key.in_(wanted),
                    PublicationLog.published_at >= since,
                )
            )
        ).scalar_one_or_none()
        if found:
            return True
    native = str(getattr(opp, "native_product_id", "") or "").strip()
    market = str(getattr(opp, "marketplace", "") or "").strip()
    if not native or not market:
        return False
    inbox_ids = select(InboxMessage.id).where(
        func.lower(InboxMessage.marketplace) == market.lower(),
        func.lower(InboxMessage.native_product_id) == native.lower(),
    )
    sibling = (
        await session.execute(
            select(PublicationLog.id)
            .where(
                PublicationLog.channel == "telegram",
                PublicationLog.opportunity_id.in_(inbox_ids),
                PublicationLog.published_at >= since,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return sibling is not None


async def _claim_publication(
    keys: list[str],
    opportunity_id: str,
    body: str,
    *,
    since,
) -> bool:
    from sqlalchemy import select

    from app.core.db import get_session_factory, utcnow

    wanted = [item for item in keys if item]
    if not wanted:
        return False
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(
                select(PublicationLog).where(
                    PublicationLog.channel == "telegram",
                    PublicationLog.dedup_key.in_(wanted),
                )
            )
        ).scalars().all()
        if any(row.published_at and row.published_at >= since for row in existing):
            return False
        now = utcnow()
        by_key = {row.dedup_key: row for row in existing}
        for key in wanted:
            row = by_key.get(key)
            if row is not None:
                row.opportunity_id = opportunity_id
                row.body = body
                row.published_at = now
                row.skipped_reason = None
            else:
                session.add(
                    PublicationLog(
                        opportunity_id=opportunity_id,
                        channel="telegram",
                        dedup_key=key,
                        body=body,
                        published_at=now,
                    )
                )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return False
        return True


async def publish_opportunity(session, opp: Opportunity, settings: Settings, *, http=None) -> str:
    allowed, reason = should_publish(opp, settings)
    if not allowed:
        return reason or "skipped"
    raw = opp.final_purchase_url or getattr(opp, "purchase_url", None)
    link = await ensure_publish_url(
        raw,
        settings,
        existing=getattr(opp, "affiliate_url", None),
        http=http,
    )
    if not link:
        return "not_affiliate"
    if hasattr(opp, "final_purchase_url"):
        opp.final_purchase_url = link
    key = dedup_key(opp)
    extra = [str(item) for item in getattr(opp, "extra_dedup_keys", []) or [] if item]
    keys = [item for item in [key, *extra] if item and item != "inbox:"]
    if not keys:
        return "no_identity"
    since = _telegram_dedup_since(settings)
    if await _already_published(session, keys, opp, since=since):
        return "duplicate"
    photo = await _resolve_publish_photo(opp, link)
    if not photo:
        return "no_image"
    body = format_message(opp, settings)
    if not await _claim_publication(keys, str(opp.id), body, since=since):
        return "duplicate"
    sent = await _deliver(
        settings,
        body,
        photo,
        http=http,
        key=keys[0],
        button_url=link,
        button_label=button_label(getattr(opp, "merchant", None), link or ""),
    )
    if not sent:
        return "deliver_failed"
    from app.core.db import utcnow

    if hasattr(opp, "published_at"):
        opp.published_at = utcnow()
    return "published"


async def publish_inbox(session, row, settings: Settings) -> str:
    from types import SimpleNamespace

    from app.core.urls import is_ml_social_url
    from app.inbox.extract import describe_link
    from app.inbox.parse import parse_deal
    from app.inbox.resolve import resolve_social_product, unveil_urls

    raw = row.affiliate_url or row.purchase_url
    if is_ml_social_url(raw):
        raw = await resolve_social_product(raw) or raw
    marketplace, native = describe_link(raw)
    if raw and not native:
        for candidate in await unveil_urls([raw]):
            marketplace, native = describe_link(candidate)
            if native:
                raw = candidate
                break
    if raw:
        row.purchase_url = raw
        if marketplace:
            row.marketplace = marketplace
        if native:
            row.native_product_id = native
    parsed = parse_deal(row.body or row.product_name, fallback=row.product_name)
    from app.inbox.extract import is_coupon_mechan

    if is_coupon_mechan(
        text=row.body,
        title=parsed.title or row.product_name,
        url=raw,
        native_id=native or row.native_product_id,
    ):
        return "coupon_mechan"
    from app.affiliates.resolver import is_shopee_url

    stamped = compact_affiliate_url(raw, settings)
    if stamped is None and not (
        is_shopee_url(raw) or is_shopee_url(row.affiliate_url)
        or (kabum_destination(raw) and awin_ready(settings))
    ):
        return "not_affiliate"
    from app.inbox.media import resolve_catalog_image

    if not row.image_url and row.chat_id and row.message_id:
        from app.inbox.media import media_path, public_media_url

        stem = re.sub(r"[^A-Za-z0-9_-]", "_", f"{row.chat_id}_{row.message_id}")[:80]
        for name in (f"{stem}.jpg", f"{stem}.jpeg", f"{stem}.png", f"{stem}.webp"):
            if media_path(name):
                row.image_url = public_media_url(name)
                break
    catalog = await resolve_catalog_image(
        marketplace=row.marketplace,
        native_id=row.native_product_id,
        text=row.body,
        urls=[raw] if raw else None,
    )
    local = bool(row.image_url and str(row.image_url).startswith("/api/v1/inbox/media/"))
    market = (row.marketplace or "").strip().lower()
    # Amazon P/…LZZZZZZZ.jpg costuma ser GIF vazio — não sobrescrever foto do Telegram.
    if catalog and (not row.image_url or (local and market == "mercadolivre")):
        row.image_url = catalog
    publish_keys = inbox_publish_keys(row)
    if not publish_keys:
        return "no_identity"
    coupon_links = await _owned_coupon_links(row, stamped or raw, settings)
    store_name = store_label(row.marketplace, stamped or raw or "") or store_label(
        None, stamped or raw or ""
    )
    fake = SimpleNamespace(
        id=row.id,
        product_id=publish_keys[0],
        extra_dedup_keys=publish_keys[1:],
        native_product_id=row.native_product_id,
        marketplace=row.marketplace,
        product_name=parsed.title or row.product_name,
        merchant=store_name,
        current_price=parsed.price,
        listed_price=parsed.listed_price,
        coupon_code=parsed.coupon,
        coupon_links=coupon_links,
        payment_hint=parsed.installment_hint or parsed.payment_hint,
        status="active",
        classification="",
        final_purchase_url=stamped or raw,
        purchase_url=stamped or raw,
        affiliate_url=row.affiliate_url,
        image_url=row.image_url,
    )
    return await publish_opportunity(session, fake, settings)


async def _owned_coupon_links(row, product_url: str | None, settings: Settings) -> list[str]:
    from app.affiliates.resolver import ensure_owned_shopee, is_shopee_url, stamp_owned_link
    from app.inbox.extract import extract_coupon_links

    payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    stored = [str(item) for item in (payload.get("coupon_links") or []) if item]
    pool = list(payload.get("urls") or []) + list(payload.get("resolved") or [])
    found = stored or extract_coupon_links(row.body, pool, product_url or row.purchase_url)
    owned: list[str] = []
    seen: set[str] = set()

    for link in found:
        raw = (link or "").strip()
        if not raw or raw in seen:
            continue
        stamped = stamp_owned_link(raw, settings)
        if stamped:
            final = stamped
        elif is_shopee_url(raw):
            final = await ensure_owned_shopee(raw, settings)
            if not final:
                continue
        else:
            final = raw
        if final in seen:
            continue
        seen.add(raw)
        seen.add(final)
        owned.append(final)
        if len(owned) >= 5:
            break
    return owned


def _inline_keyboard(button_url: str | None, button_label: str) -> dict | None:
    url = (button_url or "").strip()
    if not url:
        return None
    return {"inline_keyboard": [[{"text": (button_label or "Abrir oferta")[:64], "url": url}]]}


async def _deliver(
    settings: Settings,
    body: str,
    photo: str | None,
    *,
    http=None,
    key: str = "live",
    button_url: str | None = None,
    button_label: str = "Abrir oferta",
) -> bool:
    chat = publish_chat(settings)
    if settings.telegram_bot_token:
        return await _send_bot(
            settings, chat, body, photo, http=http, button_url=button_url, button_label=button_label
        )
    await enqueue(
        OutgoingDeal(
            chat=chat,
            text=body,
            photo_url=photo,
            dedup_key=key,
            opportunity_id="",
            button_url=button_url,
            button_label=button_label,
        )
    )
    return True


async def _send_bot(
    settings: Settings,
    chat: str,
    body: str,
    photo: str | None,
    *,
    http=None,
    button_url: str | None = None,
    button_label: str = "Abrir oferta",
) -> bool:
    import httpx

    client = http or httpx.AsyncClient(timeout=15.0)
    close = http is None
    markup = _inline_keyboard(button_url, button_label)
    try:
        if not photo:
            log.warning("telegram_bot_skip_no_photo", chat=chat)
            return False
        photo_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"
        payload = {"chat_id": chat, "caption": body, "parse_mode": "HTML"}
        if markup:
            payload["reply_markup"] = markup
        if photo.startswith("http"):
            resp = await client.post(photo_url, json={**payload, "photo": photo})
        else:
            with open(photo, "rb") as handle:
                data = {k: v for k, v in payload.items() if k != "reply_markup"}
                if markup:
                    import json

                    data["reply_markup"] = json.dumps(markup)
                resp = await client.post(
                    photo_url,
                    data=data,
                    files={"photo": handle},
                )
        if resp.status_code < 400:
            return True
        log.warning("telegram_bot_photo_skip", status=resp.status_code, body=resp.text[:160])
        return False
    except Exception as exc:
        log.warning("telegram_bot_fail", error=str(exc)[:200])
        return False
    finally:
        if close:
            await client.aclose()
