from datetime import UTC, datetime

from app.core.config import Settings
from app.sources.mercadolivre import MercadoLivreSource, parse_mais_vendidos_cards, parse_ofertas_cards


def test_normalize_official_item():
    source = MercadoLivreSource(Settings(enable_mercadolivre=True))
    now = datetime(2026, 10, 2, tzinfo=UTC)
    offers = source.normalize_search(
        {
            "results": [
                {
                    "id": "MLB1234567890",
                    "title": "SSD 1TB",
                    "price": 299.9,
                    "original_price": 399.9,
                    "currency_id": "BRL",
                    "permalink": "https://produto.mercadolivre.com.br/MLB-1234567890",
                    "thumbnail": "http://http2.mlstatic.com/ssd.jpg",
                    "available_quantity": 3,
                    "category_id": "MLB1051",
                    "seller": {"nickname": "LOJA OFICIAL"},
                    "shipping": {"free_shipping": True},
                }
            ]
        },
        fetched_at=now,
    )
    assert len(offers) == 1
    offer = offers[0]
    assert offer.source == "mercadolivre"
    assert offer.native_product_id == "MLB1234567890"
    assert offer.price_verified is True
    assert offer.merchant_id == ""
    assert float(offer.effective_price) == 299.9
    assert offer.announced_discount_pct is not None
    assert offer.purchase_url.startswith("https://")
    assert offer.image_url and offer.image_url.startswith("https://")


def test_normalize_ofertas_html():
    html = (
        '_n.ctx.r={"appProps":{"pageProps":{"data":{"items":[{"card":{'
        '"metadata":{"id":"MLB4081278987","url":"produto.mercadolivre.com.br/MLB-4081278987-tenis",'
        '"tracks":{"price":{"price":218.69}}},'
        '"components":[{"type":"title","title":{"text":"Tênis Reserva"}},'
        '{"type":"price","previous":true,"value":399.99}],'
        '"pictures":{"pictures":[{"id":"ABC123"}]}}}]}}}}'
    )
    assert len(parse_ofertas_cards(html)) == 1
    source = MercadoLivreSource(Settings(enable_mercadolivre=True))
    offers = source.normalize_ofertas_html(html, fetched_at=datetime(2026, 10, 2, tzinfo=UTC))
    assert len(offers) == 1
    offer = offers[0]
    assert offer.native_product_id == "MLB4081278987"
    assert float(offer.effective_price) == 218.69
    assert float(offer.listed_price) == 399.99
    assert offer.purchase_url.startswith("https://")
    assert "ABC123" in (offer.image_url or "")
    assert offer.category == "ofertas"
    assert offer.description == "Ofertas"


def test_disabled_without_flag():
    source = MercadoLivreSource(Settings(enable_mercadolivre=False))
    assert source.is_enabled() is False


def test_normalize_mais_vendidos_polycard():
    html = (
        '_n.ctx.r={"appProps":{"pageProps":{"floxPreloadedState":{"@meli/web/flox/FLOX_STATE":{"brickStack":{'
        '"products-carousel-1":{"data":{"items":{"result":{"polycards":[{'
        '"metadata":{"id":"MLB5314914634","url":"www.mercadolivre.com.br/ssd/up/MLBU1"},'
        '"components":[{"type":"title","title":{"text":"SSD NVMe 1TB"}},'
        '{"type":"price","price":{"current_price":{"value":299.9,"currency":"BRL"}}}],'
        '"pictures":{"pictures":[{"id":"XYZ"}]}]}}}}}}}'
    )
    assert len(parse_mais_vendidos_cards(html)) == 1
    source = MercadoLivreSource(Settings(enable_mercadolivre=True))
    offers = source.normalize_mais_vendidos_html(html, fetched_at=datetime(2026, 10, 2, tzinfo=UTC))
    assert len(offers) == 1
    assert offers[0].native_product_id == "MLB5314914634"
    assert float(offers[0].effective_price) == 299.9
    assert offers[0].raw_payload.get("via") == "mais-vendidos"
    assert offers[0].category == "mais-vendidos"
    assert offers[0].description == "Mais vendidos"
