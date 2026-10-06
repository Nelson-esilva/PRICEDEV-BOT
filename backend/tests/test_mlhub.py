from datetime import UTC, datetime

from app.core.config import Settings
from app.sources.mlhub import MlHubSource, _next_offset, extract_hub_items


def test_disabled_without_cookie():
    source = MlHubSource(Settings(enable_ml_hub=True, ml_affiliate_cookie=""))
    assert source.is_enabled() is False


def test_extracts_hub_json():
    payload = {
        "results": [
            {
                "id": "MLB18995411",
                "title": "Whey Black Skull",
                "price": 101.61,
                "original_price": 112.9,
                "permalink": "https://www.mercadolivre.com.br/whey/p/MLB18995411",
                "thumbnail": "https://http2.mlstatic.com/whey.jpg",
                "commission": {"rate": 12},
            }
        ]
    }
    items = extract_hub_items(payload)
    assert len(items) == 1
    assert items[0]["id"] == "MLB18995411"
    assert float(items[0]["commission_pct"]) == 12
    source = MlHubSource(Settings(enable_ml_hub=True, ml_affiliate_cookie="ssid=test"))
    offers = source.normalize_items(items, fetched_at=datetime(2026, 10, 4, tzinfo=UTC))
    assert len(offers) == 1
    assert offers[0].source == "mlhub"
    assert offers[0].category == "hub"
    assert "12" in (offers[0].description or "")
    assert "matt_word" not in (offers[0].purchase_url or "")


def test_offers_from_hub_polycard():
    html = (
        '_n.ctx.r={"appProps":{"pageProps":{"floxPreloadedState":{"@meli/web/flox/FLOX_STATE":{"brickStack":{'
        '"products-carousel-1":{"data":{"items":{"result":{"polycards":[{'
        '"metadata":{"id":"MLB4067001915","url":"www.mercadolivre.com.br/alcool/p/MLB39324972"},'
        '"components":[{"type":"title","title":{"text":"Álcool Isopropílico"}},'
        '{"type":"price","price":{"current_price":{"value":78.66,"currency":"BRL"}}},'
        '{"type":"chip","id":"affiliates_commission_chip","chip":{"pill":{"text":"GANHOS 5%"}}}],'
        '"pictures":{"pictures":[{"id":"ABC"}]}}]}}}}}}}'
    )
    source = MlHubSource(Settings(enable_ml_hub=True, ml_affiliate_cookie="ssid=test"))
    offers = source.offers_from_html(html, fetched_at=datetime(2026, 10, 4, tzinfo=UTC))
    assert len(offers) == 1
    assert offers[0].source == "mlhub"
    assert offers[0].native_product_id == "MLB4067001915"
    assert float(offers[0].effective_price) == 78.66
    assert offers[0].description == "Ganhos 5%"


def test_offers_from_search_polycards():
    cards = [
        {
            "metadata": {"id": "MLB4067001915", "url": "www.mercadolivre.com.br/alcool/p/MLB39324972"},
            "components": [
                {"type": "title", "title": {"text": "Álcool Isopropílico"}},
                {"type": "price", "price": {"current_price": {"value": 78.66, "currency": "BRL"}}},
                {"type": "chip", "id": "affiliates_commission_chip", "chip": {"pill": {"text": "GANHOS 5%"}}},
            ],
            "pictures": {"pictures": [{"id": "ABC"}]},
        }
    ]
    source = MlHubSource(Settings(enable_ml_hub=True, ml_affiliate_cookie="ssid=test"))
    offers = source.offers_from_cards(cards, fetched_at=datetime(2026, 10, 4, tzinfo=UTC))
    assert len(offers) == 1
    assert offers[0].native_product_id == "MLB4067001915"


def test_next_offset_pages_until_total():
    full = {
        "paging": {"total": 200, "offset": 0, "limit": 48},
        "polycard_client_model": {"polycards": [{}] * 48},
    }
    last = {
        "paging": {"total": 200, "offset": 192, "limit": 48},
        "polycard_client_model": {"polycards": [{}] * 8},
    }
    assert _next_offset(full, 0) == 48
    assert _next_offset(last, 192) is None
    assert _next_offset({"polycard_client_model": {"polycards": [{}] * 48}}, 0) == 48
    assert _next_offset({"polycard_client_model": {"polycards": []}}, 0) is None
