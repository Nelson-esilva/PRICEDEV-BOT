from datetime import UTC, datetime

from app.core.config import Settings
from app.sources.lomadee import LomadeeSource


def test_normalize_lomadee_offer():
    source = LomadeeSource(Settings(enable_lomadee=True, lomadee_app_token="t", lomadee_source_id="1"))
    offers = source.normalize_offers(
        {
            "offers": [
                {
                    "id": "of-1",
                    "name": "Monitor 27",
                    "price": 899.0,
                    "priceFrom": 1299.0,
                    "link": "https://www.americanas.com.br/produto/123",
                    "thumbnail": "https://img.americanas.com/m.jpg",
                    "store": {"name": "Americanas"},
                }
            ]
        },
        fetched_at=datetime(2026, 10, 2, tzinfo=UTC),
        keyword="monitor",
    )
    assert len(offers) == 1
    assert offers[0].source == "lomadee"
    assert offers[0].merchant_name == "Americanas"
    assert float(offers[0].effective_price) == 899.0


def test_disabled_without_tokens():
    source = LomadeeSource(Settings(enable_lomadee=True, lomadee_app_token="", lomadee_source_id=""))
    assert source.is_enabled() is False
