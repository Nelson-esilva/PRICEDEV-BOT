from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.core.db import get_session_factory, utcnow
from app.ingestion.pipeline import ingest_offers
from app.models.entities import AffiliateConversion, DealClick, PublishedDeal, TrackedLink
from app.sources.mercadolivre import card_best_seller, card_reviews, _previous_price
from app.storefront.catalog import demand_score_of, publish_public_catalog
from app.storefront.conversions import rows_from_report
from tests.conftest import make_offer

HUB_CARD = {
    "metadata": {"id": "MLB5298166742", "url": "www.mercadolivre.com.br/bike/p/MLB42978348"},
    "components": [
        {"type": "highlight", "highlight": {"text": "MAIS VENDIDO"}},
        {"type": "title", "title": {"text": "Bicicleta Ergométrica"}},
        {"type": "review_compacted", "review_compacted": {
            "alt_text": "Classificação 4.7 de 5 estrelas. Mais de 50mil produtos vendidos.",
            "values": [{"key": "label", "label": {"text": "4.7"}}, {"key": "label2", "label": {"text": "| +50mil vendidos"}}]}},
        {"type": "price", "price": {"previous_price": {"value": 1094}, "current_price": {"value": 468}}},
    ],
}


def test_hub_card_previous_price_reviews_and_best_seller():
    assert _previous_price(HUB_CARD) == Decimal("1094.00")
    assert card_reviews(HUB_CARD) == (Decimal("4.70"), 50000)
    assert card_best_seller(HUB_CARD) is True


def test_demand_score_rewards_real_orders_and_sales():
    base = dict(rating=Decimal("4.8"), discount=Decimal("30"), commission=Decimal("5"), best_seller=False, clicks_7d=0)
    quiet = demand_score_of(sales=10, orders_30d=0, **base)
    popular = demand_score_of(sales=50000, orders_30d=0, **base)
    proven = demand_score_of(sales=50000, orders_30d=9, **base)
    assert quiet < popular < proven <= 100
    assert demand_score_of(sales=None, rating=None, discount=None, commission=None,
                           best_seller=None, clicks_7d=0, orders_30d=0) == 0


def test_conversion_report_rows():
    payload = {"data": {"conversionReport": {"nodes": [{
        "purchaseTime": 1792439084, "conversionId": 246138284184482, "utmContent": "pricedev----",
        "orders": [{"orderId": "26102040S62GQ0", "orderStatus": "CANCELLED", "items": [
            {"itemId": 20298033438, "itemName": "Barraca", "actualAmount": "49.64", "qty": 1, "itemTotalCommission": "0"}]}],
    }], "pageInfo": {"hasNextPage": False}}}}
    [row] = rows_from_report(payload)
    assert row["item_id"] == "20298033438" and row["order_id"] == "26102040S62GQ0"
    assert row["sub_ids"] == "pricedev" and row["amount"] == Decimal("49.64")


async def _publish_two(settings: Settings, now):
    factory = get_session_factory()
    settings.shopee_app_id = "123"
    offers = [
        make_offer(now=now, source="shopee", marketplace="shopee", merchant_name="Shopee",
                   source_record_id=f"d{n}", native_product_id=f"9{n}", product_name=f"Produto {n}",
                   announced_discount_pct=Decimal("20"), sales_count=sales, rating=Decimal("4.8"),
                   purchase_url=f"https://shopee.com.br/product/{n}",
                   affiliate_url=f"https://shopee.com.br/product/{n}?mmp_pid=an_123")
        for n, sales in ((1, 100), (2, 20000))
    ]
    async with factory() as session:
        await ingest_offers(session, offers, settings, now=now)
        await session.commit()
    return factory


async def test_orders_drive_best_selling_and_featured(client, test_settings: Settings):
    now = utcnow()
    factory = await _publish_two(test_settings, now)
    async with factory() as session:
        session.add(AffiliateConversion(store="shopee", order_id="o1", item_id="91", purchased_at=now - timedelta(days=1)))
        session.add(AffiliateConversion(store="shopee", order_id="o2", item_id="91", purchased_at=now - timedelta(days=2)))
        await session.commit()
        await publish_public_catalog(test_settings, now=now, session=session)
        await session.commit()
        deals = {d.product_name: d for d in (await session.execute(select(PublishedDeal))).scalars()}
    assert deals["Produto 1"].orders_30d == 2 and deals["Produto 2"].orders_30d == 0
    assert deals["Produto 2"].sales_count == 20000

    best = (await client.get("/api/public/v1/deals?sort=best_selling")).json()["items"]
    assert best[0]["product"] == "Produto 1"
    assert best[1]["sales_count"] == 20000 and best[1]["rating"] == 4.8
    home = (await client.get("/api/public/v1/home")).json()
    assert home["bestsellers"]["items"][0]["product"] == "Produto 1"


async def test_tracked_link_redirects_and_logs_telegram_click(client, test_settings: Settings):
    factory = get_session_factory()
    async with factory() as session:
        session.add(TrackedLink(id="abc123", destination="https://s.shopee.com.br/x", opportunity_id="opp1", store="shopee"))
        await session.commit()
    hit = await client.get("/go/t/abc123", follow_redirects=False)
    assert hit.status_code == 302 and hit.headers["location"] == "https://s.shopee.com.br/x"
    assert (await client.get("/go/t/nope", follow_redirects=False)).status_code == 410
    async with factory() as session:
        click = (await session.execute(select(DealClick))).scalars().one()
    assert click.channel == "telegram" and click.deal_id == "opp1"


async def test_telegram_message_uses_tracked_link_only_with_public_url(db, test_settings: Settings):
    from types import SimpleNamespace

    from app.publishing.telegram import create_tracked_link

    opp = SimpleNamespace(id="opp9", source="shopee")
    assert await create_tracked_link(db, "https://s.shopee.com.br/y", opp, test_settings) is None
    test_settings.public_site_url = "https://promodev.example/"
    link = await create_tracked_link(db, "https://s.shopee.com.br/y", opp, test_settings)
    assert link and link.startswith("https://promodev.example/go/t/")
    token = link.rsplit("/", 1)[1]
    assert (await db.get(TrackedLink, token)).destination == "https://s.shopee.com.br/y"
