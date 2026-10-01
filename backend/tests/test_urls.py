from app.core.urls import sanitize_media_url, sanitize_purchase_url


def test_blocks_pelando_redirect():
    assert sanitize_purchase_url("https://dpl.pelando.com.br/jwt") is None
    assert sanitize_purchase_url("https://tracker.pelando.com.br/x") is None


def test_allows_merchant_https():
    assert sanitize_purchase_url("https://www.kabum.com.br/produto/1")
    assert sanitize_purchase_url("https://shopee.com.br/item")


def test_rejects_javascript_and_empty():
    assert sanitize_purchase_url("javascript:alert(1)") is None
    assert sanitize_purchase_url("") is None
    assert sanitize_purchase_url(None) is None


def test_allows_pelando_media_but_not_as_purchase():
    media = "https://media.pelando.com.br/hash=/0x100/filters:format(webp)/s/ssd.png"
    assert sanitize_media_url(media) == media
    assert sanitize_purchase_url(media) is None
    assert sanitize_media_url("https://dpl.pelando.com.br/jwt") is None
