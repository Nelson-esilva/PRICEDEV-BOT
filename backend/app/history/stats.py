from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import median_money, money
from app.models.entities import PriceObservation


@dataclass(frozen=True)
class HistoryStats:
    window_days: int
    observations: int
    distinct_days: int
    coverage_days: int | None
    median: Decimal | None
    minimum: Decimal | None
    mean: Decimal | None
    last_price: Decimal | None
    previous_price: Decimal | None
    last_observed_at: datetime | None
    currency: str | None
    sample_prices: tuple[Decimal, ...]


def _day_key(moment: datetime) -> str:
    return moment.date().isoformat()


async def compute_history_stats(
    session: AsyncSession,
    *,
    product_id: str,
    exclude_observation_id: str | None,
    window_days: int,
    now: datetime,
    currency: str,
    condition: str,
) -> HistoryStats:
    cutoff = now - timedelta(days=window_days)
    stmt: Select[tuple[PriceObservation]] = (
        select(PriceObservation)
        .where(PriceObservation.product_id == product_id)
        .where(PriceObservation.observed_at >= cutoff)
        .where(PriceObservation.observed_at <= now)
        .where(PriceObservation.currency == currency)
        .where(PriceObservation.condition == condition)
        .where(PriceObservation.is_inferred.is_(False))
        .order_by(PriceObservation.observed_at.asc())
    )
    if exclude_observation_id:
        stmt = stmt.where(PriceObservation.id != exclude_observation_id)
    rows = list((await session.execute(stmt)).scalars().all())

    # Uma observação por dia (a última) evita inflar a série com polling repetido.
    by_day: dict[str, PriceObservation] = {}
    for row in rows:
        by_day[_day_key(row.observed_at)] = row
    daily = sorted(by_day.values(), key=lambda r: r.observed_at)
    prices = [r.effective_price for r in daily]
    median = median_money(prices)
    minimum = min(prices) if prices else None
    mean = money(sum(prices) / len(prices)) if prices else None
    last = daily[-1] if daily else None
    previous = daily[-2] if len(daily) >= 2 else None
    coverage = None
    if daily:
        coverage = (daily[-1].observed_at.date() - daily[0].observed_at.date()).days + 1
    return HistoryStats(
        window_days=window_days,
        observations=len(daily),
        distinct_days=len(by_day),
        coverage_days=coverage,
        median=median,
        minimum=minimum,
        mean=mean,
        last_price=last.effective_price if last else None,
        previous_price=previous.effective_price if previous else None,
        last_observed_at=last.observed_at if last else None,
        currency=currency if daily else None,
        sample_prices=tuple(prices),
    )
