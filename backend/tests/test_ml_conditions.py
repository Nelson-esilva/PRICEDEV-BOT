from __future__ import annotations

from decimal import Decimal

from app.publishing.telegram import format_deal
from app.sources.mercadolivre import card_price_condition
from app.sources.mlofficial import best_listing, offer_from_catalog
from app.core.db import utcnow


def _card(label: str, total: float | None) -> dict:
    values = [{"key": "price_total", "type": "price", "price": {"value": total, "currency": "BRL"}}] if total else []
    return {"components": [{"type": "price", "price": {
        "previous_price": {"value": 699}, "current_price": {"value": 275.08},
        "discount_label": {"text": label},
        "installments": {"text": "ou {price_total} em outros meios", "values": values},
    }}]}


def test_hub_card_price_condition():
    assert card_price_condition(_card("60% OFF no Pix ou Saldo no Mercado Pago", 299)) == ("pix", Decimal("299.00"))
    assert card_price_condition(_card("62% OFF com Cupom", 27.25)) == ("coupon", Decimal("27.25"))
    assert card_price_condition(_card("57% OFF", None)) == (None, None)


def test_telegram_shows_condition_and_regular_price():
    pix = format_deal(title="Panelas", price=Decimal("275.08"), url="https://x", price_condition="pix", regular_price=Decimal("299"))
    assert "POR R$ 275,08</u></b> no Pix" in pix and "ou R$ 299,00 nos outros meios" in pix
    coupon = format_deal(title="Tapioqueira", price=Decimal("26.25"), url="https://x", price_condition="coupon", regular_price=Decimal("27.25"))
    assert "com cupom" in coupon and "sem o cupom" in coupon and "Ative o cupom" in coupon


def test_official_catalog_offer():
    item = best_listing([
        {"item_id": "MLB2", "price": 310, "original_price": 699, "shipping": {"free_shipping": True}},
        {"item_id": "MLB1", "price": 299, "original_price": 699, "shipping": {"free_shipping": True}},
        {"item_id": None, "price": 1},
    ])
    assert item["item_id"] == "MLB1"
    product = {"id": "MLB67003545", "name": "Jogo De Panelas", "pictures": [{"url": "https://http2.mlstatic.com/D_1-F.jpg"}, {"url": "https://http2.mlstatic.com/D_2-F.jpg"}]}
    offer = offer_from_catalog(product, item, rank=(3, "MLB99245", "Monitores"), official_category="casa", fetched_at=utcnow())
    assert offer.native_product_id == "MLB1" and offer.effective_price == Decimal("299.00")
    assert offer.listed_price == Decimal("699.00") and offer.best_seller and offer.free_shipping
    assert offer.description == "3º mais vendido em Monitores"
    assert (offer.rank_position, offer.rank_category, offer.rank_category_id) == (3, "Monitores", "MLB99245")
    assert offer.gallery == ["https://http2.mlstatic.com/D_1-F.jpg", "https://http2.mlstatic.com/D_2-F.jpg"]
    assert offer.catalog_product_id == "MLB67003545" and offer.official_category == "casa"
    assert offer.purchase_url.endswith("/p/MLB67003545")
    unranked = offer_from_catalog(product, item, fetched_at=utcnow())
    assert unranked.rank_position is None and unranked.best_seller is None and unranked.description is None
    gift = offer_from_catalog({"name": "Xbox Cartão Presente R$ 100"}, item, fetched_at=utcnow())
    assert gift is None
