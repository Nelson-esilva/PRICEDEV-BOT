import json
from datetime import UTC, datetime

from app.core.config import Settings
from app.sources.kabum import KabumSource, extract_catalog


def test_extracts_catalog_from_next_data():
    inner = {
        "catalogServer": {
            "data": [
                {
                    "code": "123456",
                    "name": "SSD 1TB",
                    "priceWithDiscount": 299.9,
                    "oldPrice": 399.9,
                    "friendlyName": "ssd-1tb",
                    "image": "https://images.kabum.com.br/ssd.jpg",
                    "available": True,
                    "sellerName": "KaBuM!",
                    "discountPercentage": 25,
                }
            ]
        }
    }
    html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"pageProps": {"data": json.dumps(inner)}}})
        + "</script></html>"
    )
    payload = extract_catalog(html)
    assert payload is not None
    source = KabumSource(Settings(enable_kabum=True))
    offers = source.normalize_payload(
        payload, fetched_at=datetime(2026, 10, 2, tzinfo=UTC), keyword="ssd"
    )
    assert len(offers) == 1
    offer = offers[0]
    assert offer.source == "kabum"
    assert offer.native_product_id == "123456"
    assert offer.price_verified is True
    assert float(offer.effective_price) == 299.9
    assert "/produto/123456/" in (offer.purchase_url or "")


def test_default_pc_keyword_list():
    source = KabumSource(Settings(enable_kabum=True))
    words = source.settings.kabum_keyword_list
    assert len(words) >= 50
    assert "placa de video" in words
    assert "ryzen 5 5600" in words
    assert "ssd nvme" in words


def test_disabled_without_flag():
    source = KabumSource(Settings(enable_kabum=False))
    assert source.is_enabled() is False
