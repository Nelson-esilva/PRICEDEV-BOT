from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.core.config import Settings
from app.publishing.telegram import (
    compact_affiliate_url,
    deal_photo,
    format_deal,
    format_message,
    owned_purchase_url,
    short_store_slug,
    should_publish,
    store_label,
)
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
    assert "💚 <b><u>POR R$ 459,00</u></b>" in text
    assert "💰 De:" not in text
    assert "🎟️" not in text
    assert "🛒 <b>Loja:</b> Amazon" in text
    assert "🔗 <b>Link p/ Compra:</b>" in text
    assert ">amazon/B0ABCDEFGH</a>" in text
    assert "tag=promodev00-20" in text
    assert "parafusadeira" not in text
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
    assert "💰 De: <s>R$ 120,00</s>" in full
    assert "💚 <b><u>POR R$ 80,00</u></b>" in full
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


def test_coupon_links_listed_when_present():
    text = format_deal(
        title="Cooktop",
        price=Decimal("234"),
        url="https://shopee.com.br/product/1/2",
        coupon_links=[
            "https://s.shopee.com.br/8AWstpqRdH",
            "https://s.shopee.com.br/905ztMrfjp",
        ],
        store="Shopee",
        link_label="shopee/2",
    )
    assert "🎟️ <b>Resgate os cupons:</b>" in text
    assert "1. <a href=\"https://s.shopee.com.br/8AWstpqRdH\">" in text
    assert "2. <a href=\"https://s.shopee.com.br/905ztMrfjp\">" in text
    assert "shopee/2" in text


def test_store_label_never_shows_afiliado():
    assert store_label("afiliado", "https://s.shopee.com.br/abc") == "Shopee"
    assert store_label("afiliado", "https://amzn.to/xyz") == "Amazon"
    assert store_label("afiliado", "https://meli.la/abc") == "Mercado Livre"
    assert store_label("unknown", "https://www.kabum.com.br/produto/1") == "KaBuM!"
    text = format_deal(
        title="Item",
        price=Decimal("10"),
        url="https://s.shopee.com.br/abc",
        store=store_label("afiliado", "https://s.shopee.com.br/abc"),
    )
    assert "Loja: Afiliado" not in text
    assert "Loja: Shopee" in text


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
    assert compact == (
        "https://www.mercadolivre.com.br/p/MLB63904966?matt_word=snmine&matt_tool=111"
    )
    long_slug = (
        "https://www.mercadolivre.com.br/parafusadeira-de-impacto-20v-dcd7781d2-brindes"
        "-original-amarelo-e-preto-20/p/MLBU29712786897?matt_word=other&matt_tool=9"
    )
    short = compact_affiliate_url(long_slug, settings)
    assert short == (
        "https://www.mercadolivre.com.br/up/MLBU29712786897?matt_word=snmine&matt_tool=111"
    )
    assert "parafusadeira" not in (short or "")


def test_skips_amazon_homepage_without_asin():
    assert compact_affiliate_url("https://www.amazon.com.br/?tag=santanatech-20", _settings()) is None


def test_compacts_kabum_tracking():
    raw = "https://www.kabum.com.br/produto/531155/teclado?gclid=abc&utm_source=x"
    assert compact_affiliate_url(raw, _settings()) == "https://www.kabum.com.br/produto/531155"


def test_rejects_foreign_or_raw_shopee():
    settings = _settings(enable_shopee=True, shopee_app_id="18390061275", shopee_app_secret="sec")
    foreign = (
        "https://shopee.com.br/product/1/2"
        "?mmp_pid=an_18378730520&utm_source=an_18378730520"
    )
    assert compact_affiliate_url(foreign, settings) is None
    assert compact_affiliate_url(
        "https://shopee.com.br/YESOP-x-i.464586953.28076889498", settings
    ) is None
    owned = "https://shopee.com.br/product/1/2?mmp_pid=an_18390061275&utm_source=an_18390061275"
    assert compact_affiliate_url(owned, settings) == owned


def test_short_store_slug_matches_item_code():
    assert short_store_slug("https://www.amazon.com.br/dp/B0HB6MPF6C?tag=promodev00-20") == (
        "amazon/B0HB6MPF6C"
    )
    assert short_store_slug("https://www.mercadolivre.com.br/p/MLB286415217?matt_word=x") == (
        "mercadolivre/MLB286415217"
    )
    assert short_store_slug("https://www.kabum.com.br/produto/1053828/fonte-gigante") == "kabum/1053828"


def test_terabyte_and_aliexpress_keep_purchase_link():
    tb = format_deal(
        title="Mouse Gamer Scyrox V6",
        price=Decimal("374.99"),
        url="https://www.terabyteshop.com.br/produto/12345/mouse-scyrox",
        store="Terabyte",
    )
    assert "🔗 <b>Link p/ Compra:</b>" in tb
    assert "terabyte" in tb
    assert "terabyteshop.com.br" in tb
    ali = format_deal(
        title="Mouse K-Snake X11",
        price=Decimal("164"),
        url="https://pt.aliexpress.com/item/100500123.html",
        store="AliExpress",
        coupon="IFPKPEBS",
    )
    assert "🔗 <b>Link p/ Compra:</b>" in ali
    assert "aliexpress" in ali
    assert "aliexpress.com" in ali


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
