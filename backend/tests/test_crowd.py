from datetime import UTC, datetime, timedelta

from app.pricing.crowd import crowd_signals
from tests.conftest import make_offer


def test_negative_temperature_is_risk():
    offer = make_offer(source="pelando", temperature=-12)
    reasons, risks = crowd_signals(offer, now=datetime(2026, 10, 2, tzinfo=UTC))
    assert reasons == []
    assert any("negativa" in risk for risk in risks)


def test_stale_pelando_is_risk():
    now = datetime(2026, 10, 2, tzinfo=UTC)
    offer = make_offer(source="pelando", temperature=10, comment_count=0, source_created_at=now - timedelta(days=10))
    _reasons, risks = crowd_signals(offer, now=now)
    assert any("dias" in risk for risk in risks)
