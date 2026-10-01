from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def money(value) -> Decimal | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite():
        return None
    return d.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return ((numerator / denominator) * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def median_money(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return money((ordered[mid - 1] + ordered[mid]) / Decimal("2"))
