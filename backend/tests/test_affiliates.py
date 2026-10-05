from app.affiliates.resolver import stamp_amazon, stamp_mercadolivre, stamp_owned_link
from app.core.config import Settings
from app.core.urls import is_ml_social_url
from app.inbox.extract import needs_resolve
from app.inbox.resolve import product_url_from_social_html


def test_replaces_foreign_mercadolivre_stamp():
    settings = Settings(ml_affiliate_matt_word="snmine", ml_affiliate_matt_tool="111")
    stamped = stamp_mercadolivre(
        "https://www.mercadolivre.com.br/whey/p/MLB12345678?matt_word=other&matt_tool=9",
        settings,
    )
    assert stamped
    assert "matt_word=snmine" in stamped
    assert "matt_tool=111" in stamped
    assert "matt_word=other" not in stamped


def test_stamps_amazon_tag():
    settings = Settings(amazon_affiliate_tag="pricedev-20")
    stamped = stamp_amazon("https://www.amazon.com.br/dp/B0ABCDEFGH?tag=other-20", settings)
    assert stamped
    assert stamped == "https://www.amazon.com.br/dp/B0ABCDEFGH?tag=pricedev-20"


def test_stamps_amazon_slug_url():
    settings = Settings(amazon_affiliate_tag="promodev00-20")
    stamped = stamp_amazon(
        "https://www.amazon.com.br/Air-Fryer-Mondial/dp/B0ABCDEFGH/ref=sr_1_1?tag=other-20",
        settings,
    )
    assert stamped == "https://www.amazon.com.br/dp/B0ABCDEFGH?tag=promodev00-20"


def test_owned_link_picks_store():
    settings = Settings(
        ml_affiliate_matt_word="snmine",
        ml_affiliate_matt_tool="111",
        amazon_affiliate_tag="pricedev-20",
    )
    ml = stamp_owned_link("https://produto.mercadolivre.com.br/MLB-12345678", settings)
    amazon = stamp_owned_link("https://www.amazon.com.br/gp/product/B0ABCDEFGH", settings)
    assert ml and "matt_word=snmine" in ml
    assert amazon and "tag=pricedev-20" in amazon


def test_stamps_social_profile_but_keeps_ref():
    settings = Settings(ml_affiliate_matt_word="snmine", ml_affiliate_matt_tool="111")
    stamped = stamp_mercadolivre(
        "https://www.mercadolivre.com.br/social/descontorapidoo?matt_word=other&matt_tool=9&forceInApp=true&ref=abc",
        settings,
    )
    assert stamped
    assert "matt_word=snmine" in stamped
    assert "matt_tool=111" in stamped
    assert "matt_word=other" not in stamped
    assert "ref=abc" in stamped
    assert "forceInApp" not in stamped and "forceinapp" not in stamped.lower()


def test_social_html_picks_featured_product():
    html = """
    <a href="https://www.mercadolivre.com.br/c/livros#c_category_id=MLB1196">cat</a>
    <a href="https://www.mercadolivre.com.br/kit-2-sutia/up/MLBU3804575881?pdp_filters=item_id%3AMLB4484779311">Ir para produto</a>
    <a href="https://produto.mercadolivre.com.br/MLB-4117193954-outro-_JM">outro</a>
    """
    assert product_url_from_social_html(html).startswith(
        "https://www.mercadolivre.com.br/kit-2-sutia/up/MLBU3804575881"
    )


def test_social_url_needs_resolve():
    url = "https://www.mercadolivre.com.br/social/descontorapidoo?matt_word=other"
    assert is_ml_social_url(url)
    assert needs_resolve(url)
