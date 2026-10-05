from app.inbox.extract import describe_link, extract_image_urls, extract_urls, needs_resolve, pick_product_url, title_from_text
from app.inbox.media import amazon_image, catalog_image


def test_picks_store_link_over_telegram():
    urls = extract_urls(
        "SSD em oferta https://t.me/grupo https://www.kabum.com.br/produto/123456/ssd-1tb"
    )
    assert pick_product_url(urls) == "https://www.kabum.com.br/produto/123456/ssd-1tb"


def test_title_ignores_bare_url_line():
    title = title_from_text("https://shopee.com.br/x\nSSD NVMe 1TB com cupom")
    assert title.startswith("SSD NVMe")


def test_ignores_message_without_store_link():
    urls = extract_urls("só conversa no grupo https://t.me/achadinhos")
    assert pick_product_url(urls) is None


def test_keeps_affiliate_short_links():
    urls = extract_urls("oferta https://amzn.to/abc123 https://bit.ly/xyz https://dpl.pelando.com.br/abc")
    assert any("amzn.to" in item for item in urls)
    assert any("bit.ly" in item for item in urls)
    assert any("dpl.pelando" in item for item in urls)
    assert pick_product_url(urls) is not None
    assert needs_resolve("https://amzn.to/abc123") is True


def test_extracts_store_image_from_text():
    urls = extract_image_urls("foto https://http2.mlstatic.com/D_NQ_NP_123-O.webp oferta")
    assert urls == ["https://http2.mlstatic.com/D_NQ_NP_123-O.webp"]


def test_amazon_cover_from_asin():
    assert amazon_image("B0ABCDEFGH") == "https://m.media-amazon.com/images/P/B0ABCDEFGH.01.LZZZZZZZ.jpg"
    assert catalog_image(marketplace="amazon", native_id="B0ABCDEFGH", text="")


def test_prefers_resolved_store_over_shortener():
    urls = [
        "https://bit.ly/xyz",
        "https://www.kabum.com.br/produto/123456/ssd",
    ]
    assert pick_product_url(urls) == "https://www.kabum.com.br/produto/123456/ssd"
    assert describe_link("https://bit.ly/xyz")[0] == "afiliado"
