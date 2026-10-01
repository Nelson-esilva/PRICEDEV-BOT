from __future__ import annotations

from app.core.config import Settings
from app.ingestion.pipeline import ingest_offers
from tests.conftest import make_offer


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "database" in body


async def test_opportunities_and_products_after_ingest(client, test_settings: Settings):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.core.db import get_session_factory

    factory = get_session_factory()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    async with factory() as session:
        await ingest_offers(
            session,
            [
                make_offer(
                    now=now - timedelta(days=20),
                    source_record_id="old",
                    effective_price=Decimal("699.00"),
                    listed_price=Decimal("699.00"),
                    verified_price=Decimal("699.00"),
                )
            ],
            test_settings,
            now=now - timedelta(days=20),
        )
        await ingest_offers(
            session,
            [
                make_offer(
                    now=now,
                    source_record_id="new",
                    effective_price=Decimal("459.00"),
                    listed_price=Decimal("459.00"),
                    verified_price=Decimal("459.00"),
                )
            ],
            test_settings,
            now=now,
        )

    listed = await client.get("/api/v1/opportunities")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] >= 1
    item = payload["items"][0]
    assert "score_breakdown" in item
    assert item["purchase_url"]

    detail = await client.get(f"/api/v1/opportunities/{item['id']}")
    assert detail.status_code == 200

    products = await client.get("/api/v1/products")
    assert products.status_code == 200
    product_id = products.json()[0]["id"]
    history = await client.get(f"/api/v1/products/{product_id}/price-history")
    assert history.status_code == 200
    assert len(history.json()) >= 2

    sources = await client.get("/api/v1/sources")
    assert sources.status_code == 200
    names = {row["source"] for row in sources.json()}
    assert names >= {"pelando", "shopee"}
    assert "mock" not in names


async def test_filters(client, test_settings: Settings):
    from datetime import UTC, datetime

    from app.core.db import get_session_factory
    from app.schemas.normalized import IdentityConfidence

    factory = get_session_factory()
    now = datetime(2026, 10, 1, tzinfo=UTC)
    async with factory() as session:
        await ingest_offers(
            session,
            [
                make_offer(
                    now=now,
                    source="pelando",
                    price_verified=False,
                    verified_price=None,
                    identity_confidence=IdentityConfidence.LOW,
                    purchase_url="https://www.kabum.com.br/produto/1",
                )
            ],
            test_settings,
            now=now,
        )
    resp = await client.get("/api/v1/opportunities", params={"classification": "PROVISIONAL"})
    assert resp.status_code == 200
    assert all(i["classification"] == "PROVISIONAL" for i in resp.json()["items"])
