from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.core.config import Settings
from app.publishing.telegram import compact_affiliate_url, deal_photo, format_deal, format_message, owned_purchase_url, should_publish
from app.schemas.normalized import Classification


def _opp(**kwargs):
    data = dict(
        id="opp-1",
        product_id="p1",
        product_name="SSD NVMe 2TB",
        merchant="Amazon",
        current_price=Decimal("459.00"),
        historical_median=Decimal("699.00"),
        historical_discount_pct=Decimal("34.33"),
        acceptance_score=91,
        classification=Classification.HISTORICALLY_VALIDATED.value,
        status="active",
        price_verified=True,
        final_purchase_url="https://www.amazon.com.br/dp/B0ABCDEFGH",
        affiliate_status="converted",
        coupon_code=None,
        payment_hint=None,
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def _settings(**kwargs) -> Settings:
    data = dict(
        enable_telegram_publish=True,
        telegram_publish_chat="@ofertas",
        telegram_api_id=1,
        telegram_api_hash="x",
        amazon_affiliate_tag="promodev00-20",
        ml_affiliate_matt_word="snmine",
        ml_affiliate_matt_tool="111",
    )
    data.update(kwargs)
    return Settings(**data)


def test_message_is_name_price_link():
    text = format_message(_opp(), _settings())
    assert "🔥 <b>OFERTA IMPERDÍVEL!</b> 🔥" in text
    assert "SSD NVMe 2TB" in text
    assert "💚 <b>PREÇO PROMOCIONAL:</b> R$ 459,00" in text
    assert "💰 <b>Preço normal:</b>" not in text
    assert "🎟️" not in text
    assert "🛒 <b>Loja:</b> Amazon" in text
    assert "👉 https://www.amazon.com.br/dp/B0ABCDEFGH?tag=promodev00-20" in text
    assert "APROVEITE ANTES QUE ACABE" in text


def test_skips_store_and_other_group_copy():
    text = format_deal(title="Sapato Loafer", price=Decimal("97"), url="https://x")
    assert "Sapato Loafer" in text
    assert "Cupom" not in text
    assert "CONFORTO" not in text


def test_coupon_and_listed_only_when_present():
    bare = format_deal(title="Mouse", price=Decimal("80"), url="https://x")
    assert "Cupom" not in bare
    assert "Preço normal" not in bare
    full = format_deal(
        title="Mouse",
        price=Decimal("80"),
        listed=Decimal("120"),
        url="https://x",
        coupon="PROMO100",
        store="AliExpress",
    )
    assert "💰 <b>Preço normal:</b> R$ 120,00" in full
    assert "🎟️ <b>Cupom:</b> PROMO100" in full
    assert "🛒 <b>Loja:</b> AliExpress" in full
    with_parcel = format_deal(
        title="Poco",
        price=Decimal("2799"),
        url="https://x",
        installment="12x de R$ 233,25 sem juros",
    )
    assert "💳 12x de R$ 233,25 sem juros" in with_parcel
    assert "Pix" not in with_parcel


def test_deal_photo_keeps_catalog_hosts():
    assert deal_photo("https://http2.mlstatic.com/D_NQ_NP_123-O.webp") == (
        "https://http2.mlstatic.com/D_NQ_NP_123-O.jpg"
    )
    assert deal_photo("https://m.media-amazon.com/images/I/abc.jpg")
    assert deal_photo("https://evil.example/photo.jpg") is None


def test_compacts_long_mercadolivre_url():
    settings = _settings()
    raw = (
        "https://www.mercadolivre.com.br/camiseta/p/MLB63904966"
        "?pdp_filters=item_id%3AMLB1&matt_event_ts=1&matt_d2id=abc"
        "&matt_word=other&matt_tool=9"
    )
    compact = compact_affiliate_url(raw, settings)
    assert compact
    assert "matt_word=snmine" in compact
    assert "pdp_filters" not in compact
    assert "matt_event_ts" not in compact


def test_compacts_kabum_tracking():
    raw = "https://www.kabum.com.br/produto/531155/teclado?gclid=abc&utm_source=x"
    assert compact_affiliate_url(raw, _settings()) == "https://www.kabum.com.br/produto/531155/teclado"


def test_requires_owned_affiliate_link():
    settings = _settings()
    allowed, reason = should_publish(_opp(), settings)
    assert allowed is True
    allowed, reason = should_publish(
        _opp(final_purchase_url="https://www.mercadolivre.com.br/social/descontorapidoo"),
        settings,
    )
    assert allowed is False
    assert reason == "not_affiliate"


def test_expired_and_invalid_url_blocked():
    settings = _settings()
    allowed, reason = should_publish(_opp(status="expired"), settings)
    assert allowed is False
    allowed, reason = should_publish(_opp(final_purchase_url=None), settings)
    assert reason == "invalid_url"


def test_disabled_telegram():
    settings = _settings(enable_telegram_publish=False)
    allowed, reason = should_publish(_opp(), settings)
    assert allowed is False
    assert reason == "telegram_disabled"


def test_owned_url_keeps_existing_stamp():
    settings = _settings()
    url = "https://www.amazon.com.br/dp/B0ABCDEFGH?tag=promodev00-20"
    assert owned_purchase_url(url, settings) == url
