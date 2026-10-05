from app.ingestion.identity import identity_from_offer, parse_product_url
from app.schemas.normalized import IdentityConfidence
from tests.conftest import make_offer


def test_mlb_from_url_replaces_pelando_id():
    offer = make_offer(
        native_product_id="pelando-2df0bc94-0024-4253-bc04-1bdc0154041d",
        marketplace="unknown",
        merchant_id="mercado-livre",
        identity_confidence=IdentityConfidence.LOW,
        purchase_url="https://produto.mercadolivre.com.br/MLB-5388126802",
        price_verified=False,
        verified_price=None,
    )
    marketplace, native, _variant, merchant, confidence = identity_from_offer(offer)
    assert marketplace == "mercadolivre"
    assert native == "MLB5388126802"
    assert merchant == ""
    assert confidence is IdentityConfidence.HIGH


def test_asin_and_shopee_and_kabum():
    assert parse_product_url("https://www.amazon.com.br/dp/B0ABCD1234") == ("amazon", "B0ABCD1234")
    assert parse_product_url("https://shopee.com.br/product/123/456") == ("shopee", "456")
    assert parse_product_url("https://www.kabum.com.br/produto/123456") == ("kabum", "123456")
    assert parse_product_url("https://www.magazineluiza.com.br/fone/p/ab12cd34ef/") == ("magalu", "ab12cd34ef")


def test_pelando_page_does_not_become_marketplace():
    offer = make_offer(
        marketplace="unknown",
        merchant_id="loja-x",
        native_product_id="pelando-abc",
        identity_confidence=IdentityConfidence.LOW,
        purchase_url="https://www.pelando.com.br/d/abc",
        price_verified=False,
        verified_price=None,
    )
    marketplace, native, _variant, merchant, confidence = identity_from_offer(offer)
    assert marketplace == "unknown"
    assert native == "pelando-abc"
    assert merchant == "loja-x"
    assert confidence is IdentityConfidence.PROVISIONAL


def test_keeps_strong_identity_without_url_id():
    offer = make_offer(purchase_url="https://www.kabum.com.br/produto/ssd-nvme-2tb")
    marketplace, native, _variant, merchant, confidence = identity_from_offer(offer)
    assert marketplace == "kabum"
    assert native == "ssd-nvme-2tb"
    assert merchant == "kabum"
    assert confidence is IdentityConfidence.HIGH
