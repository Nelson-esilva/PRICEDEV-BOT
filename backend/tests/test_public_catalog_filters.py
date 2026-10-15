from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.db import get_session_factory, utcnow
from app.models.entities import PublishedDeal


async def seed_catalog():
    now = utcnow()
    rows = [
        ("a", "Fone básico", "shopee", "50.00", None, "active", 1),
        ("b", "Fone premium", "shopee", "110.00", "AUDIO10", "active", 1),
        ("c", "Fone compacto", "mercadolivre", "90.00", "SOM10", "active", 1),
        ("d", "Fone inativo", "shopee", "10.00", "OFF", "expired", 1),
        ("e", "Fone vencido", "shopee", "5.00", "OFF", "active", -1),
        ("f", "Fone sem cupom", "shopee", "70.00", "   ", "active", 1),
    ]
    async with get_session_factory()() as session:
        for token, name, store, price, coupon, status, days in rows:
            session.add(
                PublishedDeal(
                    id=token,
                    opportunity_id=token,
                    slug=token,
                    product_name=name,
                    source="shopee" if store == "shopee" else "mlhub",
                    store=store,
                    category="eletronicos",
                    current_price=Decimal(price),
                    coupon_code=coupon,
                    status=status,
                    updated_at=now,
                    expires_at=now + timedelta(days=days),
                    destination_url="https://example.com/product",
                )
            )
        await session.commit()


async def test_sort_applies_before_pagination_and_preserves_live_filter(client):
    await seed_catalog()
    first = (await client.get("/api/public/v1/deals?sort=price_asc&limit=2")).json()
    second = (await client.get("/api/public/v1/deals?sort=price_asc&limit=2&offset=2")).json()
    assert first["total"] == second["total"] == 4
    assert [row["current_price"] for row in first["items"]] == [50, 70]
    assert [row["current_price"] for row in second["items"]] == [90, 110]
    descending = (await client.get("/api/public/v1/deals?sort=price_desc")).json()
    assert [row["current_price"] for row in descending["items"]] == [110, 90, 70, 50]


async def test_filters_combine_and_count_matches(client):
    await seed_catalog()
    response = await client.get(
        "/api/public/v1/deals",
        params={
            "q": "fone",
            "category": "eletronicos",
            "store": "mercadolivre",
            "max_price": 100,
            "has_coupon": "true",
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == "c"
    empty = (await client.get("/api/public/v1/deals?max_price=49")).json()
    assert empty == {"items": [], "total": 0}


async def test_coupon_filter_excludes_null_and_whitespace(client):
    await seed_catalog()
    payload = (await client.get("/api/public/v1/deals?has_coupon=true")).json()
    assert payload["total"] == 2
    assert {row["id"] for row in payload["items"]} == {"b", "c"}


async def test_recent_pagination_has_stable_tie_breaker(client):
    await seed_catalog()
    first = (await client.get("/api/public/v1/deals?limit=2")).json()
    second = (await client.get("/api/public/v1/deals?limit=2&offset=2")).json()
    assert {row["id"] for row in first["items"]}.isdisjoint(row["id"] for row in second["items"])


@pytest.mark.parametrize("query", ["sort=invalid", "max_price=-1", "max_price=abc"])
async def test_invalid_filters_are_rejected(client, query):
    assert (await client.get(f"/api/public/v1/deals?{query}")).status_code == 422
