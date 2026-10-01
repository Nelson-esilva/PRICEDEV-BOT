from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import Settings
from app.history.stats import HistoryStats
from app.pricing.engine import evaluate_offer
from app.schemas.normalized import Classification, IdentityConfidence
from tests.conftest import make_offer


def _settings(**kwargs) -> Settings:
    data = dict(
        min_historical_discount_pct=20,
        min_acceptance_score=75,
        min_history_observations=10,
        min_history_distinct_days=14,
        allow_provisional_opportunities=True,
        require_verified_price_for_historical_alert=True,
        anomaly_discount_pct=50,
    )
    data.update(kwargs)
    return Settings(**data)


def _stats(*, prices: list[Decimal], days: int | None = None) -> HistoryStats:
    days = days or len(prices)
    median = sorted(prices)[len(prices) // 2] if prices else None
    return HistoryStats(
        window_days=90,
        observations=len(prices),
        distinct_days=days,
        coverage_days=days,
        median=median,
        minimum=min(prices) if prices else None,
        mean=sum(prices) / len(prices) if prices else None,
        last_price=prices[-1] if prices else None,
        previous_price=prices[-2] if len(prices) >= 2 else None,
        last_observed_at=datetime(2026, 9, 30, tzinfo=UTC),
        currency="BRL",
        sample_prices=tuple(prices),
    )


def test_price_below_median_historically_validated():
    settings = _settings()
    stats = _stats(prices=[Decimal("699.00")] * 20)
    offer = make_offer(effective_price=Decimal("459.00"), listed_price=Decimal("459.00"), verified_price=Decimal("459.00"))
    result = evaluate_offer(offer, stats, settings, now=datetime(2026, 10, 1, tzinfo=UTC))
    assert result.classification is Classification.HISTORICALLY_VALIDATED
    assert result.historical_discount_pct == Decimal("34.33")
    assert result.acceptance_score >= 75
    assert "historical_discount" in result.score_breakdown


def test_price_above_median_rejected():
    stats = _stats(prices=[Decimal("459.00")] * 20)
    offer = make_offer(effective_price=Decimal("699.00"), listed_price=Decimal("699.00"), verified_price=Decimal("699.00"))
    result = evaluate_offer(offer, stats, _settings(), now=datetime(2026, 10, 1, tzinfo=UTC))
    assert result.classification is Classification.REJECTED
    assert result.historical_discount_pct is not None
    assert result.historical_discount_pct < 0


def test_price_equal_to_previous_minimum():
    stats = _stats(prices=[Decimal("459.00")] + [Decimal("699.00")] * 19)
    offer = make_offer(effective_price=Decimal("459.00"), listed_price=Decimal("459.00"), verified_price=Decimal("459.00"))
    result = evaluate_offer(offer, stats, _settings(), now=datetime(2026, 10, 1, tzinfo=UTC))
    assert result.discount_vs_minimum_pct == Decimal("0.00")


def test_price_below_previous_minimum_anomaly():
    stats = _stats(prices=[Decimal("1499.00")] * 20)
    offer = make_offer(
        native_product_id="monitor-27",
        product_name='Monitor 27"',
        effective_price=Decimal("499.00"),
        listed_price=Decimal("499.00"),
        verified_price=Decimal("499.00"),
    )
    result = evaluate_offer(offer, stats, _settings(), now=datetime(2026, 10, 1, tzinfo=UTC))
    assert result.classification is Classification.PRICE_ANOMALY_CANDIDATE
    assert result.historical_discount_pct == Decimal("66.71")


def test_empty_history_is_provisional():
    result = evaluate_offer(make_offer(), _stats(prices=[]), _settings())
    assert result.classification is Classification.PROVISIONAL
    assert "não classificar como mínimo histórico" in " ".join(result.reasons)


def test_insufficient_history():
    stats = _stats(prices=[Decimal("699.00")] * 3, days=3)
    result = evaluate_offer(make_offer(), stats, _settings())
    assert result.classification is Classification.PROVISIONAL
    assert result.history_confidence.value in {"LOW", "MEDIUM"}


def test_same_day_repeats_do_not_inflate_via_stats_distinct_days():
    stats = _stats(prices=[Decimal("699.00")] * 10, days=2)
    result = evaluate_offer(make_offer(), stats, _settings())
    assert result.classification is Classification.PROVISIONAL


def test_different_variants_are_not_the_engine_identity_problem():
    stats = _stats(prices=[Decimal("699.00")] * 20)
    offer = make_offer(condition="reembalado")
    result = evaluate_offer(offer, stats, _settings())
    assert any("condição" in r for r in result.risks)


def test_different_currency_skips_discount():
    stats = _stats(prices=[Decimal("699.00")] * 20)
    stats = HistoryStats(**{**stats.__dict__, "currency": "USD"})
    offer = make_offer()
    result = evaluate_offer(offer, stats, _settings())
    assert result.historical_discount_pct is None
    assert any("moeda" in r for r in result.risks)


def test_zero_price_non_gift_is_risk():
    stats = _stats(prices=[Decimal("10.00")] * 20)
    offer = make_offer(
        effective_price=Decimal("0.00"),
        listed_price=Decimal("0.00"),
        verified_price=Decimal("0.00"),
        category="informatica",
    )
    result = evaluate_offer(offer, stats, _settings())
    assert any("zero" in r for r in result.risks)


def test_announced_discount_mismatch_is_risk():
    stats = _stats(prices=[Decimal("100.00")] * 20)
    offer = make_offer(
        effective_price=Decimal("90.00"),
        listed_price=Decimal("90.00"),
        verified_price=Decimal("90.00"),
        announced_discount_pct=Decimal("80"),
    )
    result = evaluate_offer(offer, stats, _settings())
    assert any("diverge" in r for r in result.risks)


def test_unverified_price_cannot_be_historically_validated():
    stats = _stats(prices=[Decimal("699.00")] * 20)
    offer = make_offer(price_verified=False, verified_price=None)
    result = evaluate_offer(offer, stats, _settings())
    assert result.classification is Classification.PROVISIONAL
    assert any("PRICE_UNVERIFIED" in r for r in result.reasons)


def test_provisional_identity_never_historically_validated():
    stats = _stats(prices=[Decimal("699.00")] * 20)
    offer = make_offer(identity_confidence=IdentityConfidence.PROVISIONAL)
    result = evaluate_offer(offer, stats, _settings())
    assert result.classification is Classification.PROVISIONAL


def test_score_is_not_probability_and_uses_weights():
    stats = _stats(prices=[Decimal("699.00")] * 20)
    result = evaluate_offer(make_offer(), stats, _settings())
    total_weights = sum(v["weight"] for v in result.score_breakdown.values())
    assert total_weights == 100
    assert 0 <= result.acceptance_score <= 100
