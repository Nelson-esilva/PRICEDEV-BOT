from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models.entities import InboxMessage, Opportunity, PriceObservation, Product
from app.monitoring.retention import purge_stale_promos
from tests.conftest import ingest_history


async def test_purge_drops_promos_older_than_five_days(db, test_settings):
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    old = now - timedelta(days=8)
    recent = now - timedelta(days=1)
    await ingest_history(
        db,
        test_settings,
        prices=[(Decimal("100.00"), old)],
        native_id="old-ssd",
    )
    await ingest_history(
        db,
        test_settings,
        prices=[(Decimal("200.00"), recent)],
        native_id="new-ssd",
    )
    db.add(
        InboxMessage(
            channel="telegram",
            chat_id="1",
            chat_title="grupo",
            message_id="old",
            product_name="oferta velha",
            posted_at=old,
            received_at=old,
        )
    )
    db.add(
        InboxMessage(
            channel="telegram",
            chat_id="1",
            chat_title="grupo",
            message_id="new",
            product_name="oferta nova",
            posted_at=recent,
            received_at=recent,
        )
    )
    await db.commit()

    stats = await purge_stale_promos(db, days=5, now=now)
    await db.commit()
    db.expire_all()

    names = set((await db.execute(select(Product.native_product_id))).scalars().all())
    inbox = set((await db.execute(select(InboxMessage.message_id))).scalars().all())
    opp_count = len((await db.execute(select(Opportunity.id))).scalars().all())
    obs_count = len((await db.execute(select(PriceObservation.id))).scalars().all())

    assert "old-ssd" not in names
    assert "new-ssd" in names
    assert inbox == {"new"}
    assert opp_count == 1
    assert obs_count == 1
    assert stats["inbox"] == 1
    assert stats["opportunities"] >= 1
    assert stats["products"] >= 1
