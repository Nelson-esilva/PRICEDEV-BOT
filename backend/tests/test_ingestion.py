from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import Settings
from app.ingestion.pipeline import ingest_offers
from tests.conftest import ingest_history, make_offer


async def test_new_offer_creates_observation(db, test_settings: Settings):
    now = datetime(2026, 10, 1, tzinfo=UTC)
    result = await ingest_offers(db, [make_offer(now=now)], test_settings, now=now)
    assert result.created == 1
    assert result.duplicates == 0


async def test_duplicate_same_price_is_ignored(db, test_settings: Settings):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    offer = make_offer(now=now, source_record_id="dup")
    first = await ingest_offers(db, [offer], test_settings, now=now)
    second = await ingest_offers(db, [offer], test_settings, now=now)
    assert first.created == 1
    assert second.duplicates == 1
    assert second.created == 0


async def test_price_update_appends_history(db, test_settings: Settings):
    t1 = datetime(2026, 9, 1, tzinfo=UTC)
    t2 = datetime(2026, 10, 1, tzinfo=UTC)
    await ingest_offers(
        db,
        [make_offer(now=t1, effective_price=Decimal("699.00"), listed_price=Decimal("699.00"), verified_price=Decimal("699.00"), source_record_id="a")],
        test_settings,
        now=t1,
    )
    result = await ingest_offers(
        db,
        [make_offer(now=t2, effective_price=Decimal("459.00"), listed_price=Decimal("459.00"), verified_price=Decimal("459.00"), source_record_id="b")],
        test_settings,
        now=t2,
    )
    assert result.created == 1
    from sqlalchemy import select
    from app.models.entities import PriceObservation

    rows = list((await db.execute(select(PriceObservation))).scalars())
    assert len(rows) == 2
    assert {r.effective_price for r in rows} == {Decimal("699.00"), Decimal("459.00")}


async def test_out_of_order_events_still_store(db, test_settings: Settings):
    later = datetime(2026, 10, 1, tzinfo=UTC)
    earlier = datetime(2026, 9, 1, tzinfo=UTC)
    await ingest_offers(db, [make_offer(now=later, source_record_id="new")], test_settings, now=later)
    result = await ingest_offers(
        db,
        [make_offer(now=earlier, source_record_id="old", effective_price=Decimal("800.00"), listed_price=Decimal("800.00"), verified_price=Decimal("800.00"))],
        test_settings,
        now=earlier,
    )
    assert result.created == 1


async def test_history_then_sale_is_historically_validated(db, test_settings: Settings):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    prices = [(Decimal("699.00"), now - timedelta(days=day)) for day in range(20, 0, -1)]
    await ingest_history(db, test_settings, prices=prices)
    result = await ingest_offers(
        db,
        [
            make_offer(
                now=now,
                source_record_id="sale",
                effective_price=Decimal("459.00"),
                listed_price=Decimal("459.00"),
                verified_price=Decimal("459.00"),
            )
        ],
        test_settings,
        now=now,
    )
    assert result.created == 1
    assert result.opportunities[0].classification in {"HISTORICALLY_VALIDATED", "PRICE_ANOMALY_CANDIDATE"}
    assert result.opportunities[0].final_purchase_url.startswith("https://www.kabum.com.br")


async def test_pelando_unverified_price_is_provisional(db, test_settings: Settings):
    now = datetime(2026, 10, 1, tzinfo=UTC)
    offer = make_offer(
        source="pelando",
        source_record_id="deal-1",
        marketplace="kabum",
        native_product_id="pelando-deal-1",
        price_verified=False,
        verified_price=None,
        identity_confidence=__import__("app.schemas.normalized", fromlist=["IdentityConfidence"]).IdentityConfidence.LOW,
        purchase_url="https://www.kabum.com.br/produto/1",
        now=now,
    )
    result = await ingest_offers(db, [offer], test_settings, now=now)
    assert result.opportunities[0].classification == "PROVISIONAL"
    assert result.opportunities[0].price_verified is False


async def test_duplicate_refreshes_display_fields(db, test_settings: Settings):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    first = make_offer(now=now, source_record_id="img-1")
    await ingest_offers(db, [first], test_settings, now=now)
    second = make_offer(
        now=now,
        source_record_id="img-1",
        image_url="https://media.pelando.com.br/s/ssd.png",
        coupon_code="SSD10",
        description="SSD em promoção",
        temperature=412,
        free_shipping=True,
        comment_count=12,
    )
    result = await ingest_offers(db, [second], test_settings, now=now)
    assert result.duplicates == 1
    from sqlalchemy import select
    from app.models.entities import Opportunity

    opp = (await db.execute(select(Opportunity))).scalar_one()
    assert opp.image_url == "https://media.pelando.com.br/s/ssd.png"
    assert opp.coupon_code == "SSD10"
    assert opp.description == "SSD em promoção"
    assert opp.temperature == 412
    assert opp.free_shipping is True
    assert opp.comment_count == 12
    assert opp.detected_at == now
