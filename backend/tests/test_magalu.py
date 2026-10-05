from datetime import UTC, datetime

from app.core.config import Settings
from app.sources.magalu import MagaluSource, collect_products, extract_next_data


def test_extracts_products_from_next_data():
    html = """<html><script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"data":{"search":{"products":[{"id":"abc12345","title":"Air Fryer","price":{"bestPrice":199.9,"price":259.9},"path":"/air-fryer/p/abc12345/","image":"https://a-static.mlcdn.com.br/fry.jpg"}]}}}}}</script></html>"""
    payload = extract_next_data(html)
    assert payload is not None
    products = collect_products(payload)
    assert products[0]["id"] == "abc12345"

    source = MagaluSource(Settings(enable_magalu=True))
    offers = source.normalize_payload(payload, fetched_at=datetime(2026, 10, 2, tzinfo=UTC), keyword="air fryer")
    assert len(offers) == 1
    assert offers[0].source == "magalu"
    assert offers[0].native_product_id == "abc12345"
    assert offers[0].price_verified is True
    assert float(offers[0].effective_price) == 199.9
