from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlencode, urlparse, urlunparse

from app.affiliates.resolver import stamp_owned_link
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.entities import Opportunity, PublicationLog
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

    owned = owned_purchase_url(url, settings) or url
    if not owned or is_ml_social_url(owned):
        return None
    parsed = urlparse(owned)
    host = (parsed.hostname or "").lower()
    if "amazon." in host:
        return stamp_owned_link(owned, settings) or owned
    if "mercadolivre." in host or "mercadolibre." in host:
        word = (settings.ml_affiliate_matt_word or "").strip()
        tool = (settings.ml_affiliate_matt_tool or "").strip()
        kept = [("matt_word", word), ("matt_tool", tool)] if word and tool else []
        return urlunparse(parsed._replace(query=urlencode(kept), fragment=""))
    if any(token in host for token in ("kabum.", "magazineluiza.", "magalu.", "shopee.")):
        return urlunparse(parsed._replace(query="", fragment=""))
    return owned


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
    "amazon": "Amazon",
    "shopee": "Shopee",
    "magalu": "Magazine Luiza",
    "magazine luiza": "Magazine Luiza",
    "kabum": "KaBuM!",
    "kabum!": "KaBuM!",
    "aliexpress": "AliExpress",
    "netshoes": "Netshoes",
    "pelando": "Pelando",
}


def format_message(opp: Opportunity, settings: Settings | None = None) -> str:
    from app.core.config import get_settings

    settings = settings or get_settings()
    raw = opp.final_purchase_url or getattr(opp, "purchase_url", None)
    url = compact_affiliate_url(raw, settings) or ""
    return format_deal(
        title=opp.product_name,
        price=_positive(opp.current_price),
        listed=_listed_price(opp),
        url=url,
        coupon=getattr(opp, "coupon_code", None),
        store=store_label(getattr(opp, "merchant", None), url),
        installment=_installment_of(getattr(opp, "payment_hint", None)),
    )


def format_deal(
    *,
    title: str,
    price: Decimal | None,
    url: str,
    listed: Decimal | None = None,
    coupon: str | None = None,
    store: str | None = None,
    installment: str | None = None,
    **_unused,
) -> str:
    blocks = ["🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥", "", _html(_clean_title(title))]
    listed = _positive(listed)
    price = _positive(price)
    prices: list[str] = []
    if listed and price and listed > price:
        prices.append(f"💰 <b>Preço normal:</b> {_brl(listed)}")
    if price:
        prices.append(f"💚 <b>PREÇO PROMOCIONAL:</b> {_brl(price)}")
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
    if shop:
        extras.append(f"🛒 <b>Loja:</b> {_html(shop)}")
    if extras:
        blocks.extend(["", "\n".join(extras)])
    if url:
        blocks.extend(["", f"🔗 <b>LINK DA PROMOÇÃO:</b>\n👉 {_html(url)}"])
    blocks.extend(
        [
            "",
            "⚡ <b>APROVEITE ANTES QUE ACABE!</b>",
            "",
            "⚠️ <i>Preço sujeito a alterações. Confira o valor final antes de comprar.</i>",
        ]
    )
    return "\n".join(blocks)


def store_label(store: str | None, url: str = "") -> str | None:
    raw = (store or "").strip()
    if raw:
        return _STORE.get(raw.lower(), raw)
    host = (urlparse(url).hostname or "").lower()
    if "amazon." in host:
        return "Amazon"
    if "mercadolivre." in host or "mercadolibre." in host:
        return "Mercado Livre"
    if "kabum." in host:
        return "KaBuM!"
    if "magazineluiza." in host or "magalu." in host:
        return "Magazine Luiza"
    if "shopee." in host:
        return "Shopee"
    if "aliexpress." in host:
        return "AliExpress"
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
    if compact_affiliate_url(raw, settings) is None:
        return False, "not_affiliate"
    return True, None


def dedup_key(opp: Opportunity) -> str:
    price = str(getattr(opp, "current_price", "") or "")
    return f"{opp.product_id}:{price}"


async def publish_opportunity(session, opp: Opportunity, settings: Settings, *, http=None) -> str:
    allowed, reason = should_publish(opp, settings)
    if not allowed:
        return reason or "skipped"
    key = dedup_key(opp)
    from sqlalchemy import select

    existing = (
        await session.execute(
            select(PublicationLog).where(
                PublicationLog.channel == "telegram",
                PublicationLog.dedup_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return "duplicate"
    body = format_message(opp, settings)
    photo = deal_photo(getattr(opp, "image_url", None))
    sent = await _deliver(settings, body, photo, http=http)
    if not sent:
        return "deliver_failed"
    session.add(
        PublicationLog(
            opportunity_id=opp.id,
            channel="telegram",
            dedup_key=key,
            body=body,
        )
    )
    from app.core.db import utcnow

    if hasattr(opp, "published_at"):
        opp.published_at = utcnow()
    return "published"


async def publish_inbox(session, row, settings: Settings) -> str:
    from types import SimpleNamespace

    from app.core.urls import is_ml_social_url
    from app.inbox.parse import parse_deal
    from app.inbox.resolve import resolve_social_product

    raw = row.affiliate_url or row.purchase_url
    if is_ml_social_url(raw):
        raw = await resolve_social_product(raw) or raw
    stamped = compact_affiliate_url(raw, settings)
    if not stamped:
        return "not_affiliate"
    parsed = parse_deal(row.body or row.product_name, fallback=row.product_name)
    fake = SimpleNamespace(
        id=row.id,
        product_id=f"inbox:{row.id}",
        product_name=parsed.title or row.product_name,
        merchant=row.marketplace,
        current_price=parsed.price,
        listed_price=parsed.listed_price,
        coupon_code=parsed.coupon,
        payment_hint=parsed.installment_hint or parsed.payment_hint,
        status="active",
        classification="",
        final_purchase_url=stamped,
        purchase_url=stamped,
        image_url=row.image_url,
    )
    return await publish_opportunity(session, fake, settings)


async def _deliver(settings: Settings, body: str, photo: str | None, *, http=None) -> bool:
    chat = publish_chat(settings)
    if settings.telegram_bot_token:
        return await _send_bot(settings, chat, body, photo, http=http)
    await enqueue(
        OutgoingDeal(
            chat=chat,
            text=body,
            photo_url=photo,
            dedup_key="live",
            opportunity_id="",
        )
    )
    return True


async def _send_bot(settings: Settings, chat: str, body: str, photo: str | None, *, http=None) -> bool:
    import httpx

    client = http or httpx.AsyncClient(timeout=15.0)
    close = http is None
    try:
        if photo:
            photo_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"
            payload = {"chat_id": chat, "caption": body, "parse_mode": "HTML"}
            if photo.startswith("http"):
                resp = await client.post(photo_url, json={**payload, "photo": photo})
            else:
                with open(photo, "rb") as handle:
                    resp = await client.post(
                        photo_url,
                        data=payload,
                        files={"photo": handle},
                    )
            if resp.status_code < 400:
                return True
            log.warning("telegram_bot_photo_skip", status=resp.status_code, body=resp.text[:160])
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        resp = await client.post(
            url,
            json={"chat_id": chat, "text": body, "disable_web_page_preview": True, "parse_mode": "HTML"},
        )
        if resp.status_code >= 400:
            log.warning("telegram_bot_http", status=resp.status_code, body=resp.text[:160])
            return False
        return True
    except Exception as exc:
        log.warning("telegram_bot_fail", error=str(exc)[:200])
        return False
    finally:
        if close:
            await client.aclose()
