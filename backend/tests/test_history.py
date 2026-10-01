from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.history.stats import compute_history_stats
from app.ingestion.pipeline import ingest_offers
from tests.conftest import make_offer


async def test_history_excludes_current_and_collapses_same_day(db, test_settings):
    base = datetime(2026, 9, 1, tzinfo=UTC)
    prices = []
    for day in range(5):
        when = base + timedelta(days=day)
        price = Decimal("100.00")
        await ingest_offers(
            db,
            [
                make_offer(
                    now=when,
                    source_record_id=f"a-{day}-1",
                    effective_price=price,
                    listed_price=price,
                    verified_price=price,
                )
            ],
            test_settings,
            now=when,
        )
        await ingest_offers(
            db,
            [
                make_offer(
                    now=when.replace(hour=18),
                    source_record_id=f"a-{day}-2",
                    effective_price=Decimal("100.00"),
                    listed_price=Decimal("100.00"),
                    verified_price=Decimal("100.00"),
                )
            ],
            test_settings,
            now=when.replace(hour=18),
        )
        prices.append(price)

    current_when = base + timedelta(days=10)
    current = await ingest_offers(
        db,
        [
            make_offer(
                now=current_when,
                source_record_id="current",
                effective_price=Decimal("70.00"),
                listed_price=Decimal("70.00"),
                verified_price=Decimal("70.00"),
            )
        ],
        test_settings,
        now=current_when,
    )
    opp = current.opportunities[0]
    from sqlalchemy import select
    from app.models.entities import PriceObservation

    last = (
        await db.execute(select(PriceObservation).where(PriceObservation.id == opp.observation_id))
    ).scalar_one()
    stats = await compute_history_stats(
        db,
        product_id=opp.product_id,
        exclude_observation_id=last.id,
        window_days=90,
        now=current_when,
        currency="BRL",
        condition="new",
    )
    assert stats.distinct_days == 5
    assert stats.observations == 5
    assert stats.median == Decimal("100.00")
    assert Decimal("70.00") not in stats.sample_prices
