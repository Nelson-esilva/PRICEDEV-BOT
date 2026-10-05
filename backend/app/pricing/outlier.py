"""Outlier de leitura — adaptado de bernalli/price-tracker-bot (MIT).

Uma leitura só não entra no histórico: ACCEPT grava, CONFIRM espera
leituras concordantes, REJECT (lixo de parse / escala) nunca grava.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from statistics import median


class ReadVerdict(StrEnum):
    ACCEPT = "accept"
    CONFIRM = "confirm"
    REJECT = "reject"


MIN_HISTORY = 5
DEFAULT_MAX_RATIO = Decimal("2.5")
LOW_OUTLIER_RATIO = Decimal("50")
ABSURD_HIGH_RATIO = Decimal("20")
SUSPICIOUS_DROP_RATIO = Decimal("0.6")
REQUIRED_CONFIRMATIONS = 3
CONFIRMATION_TOLERANCE = Decimal("0.02")
MAX_HELD_READS = 8


@dataclass(frozen=True)
class OutlierDecision:
    verdict: ReadVerdict
    reason: str


def classify_read(
    price: Decimal,
    history: list[Decimal],
    *,
    allow_zero: bool = False,
) -> OutlierDecision:
    if price <= 0:
        if allow_zero:
            return OutlierDecision(ReadVerdict.ACCEPT, "preço zero permitido (cupom/brinde)")
        return OutlierDecision(ReadVerdict.REJECT, "preço não positivo")
    if len(history) < MIN_HISTORY:
        return OutlierDecision(ReadVerdict.ACCEPT, "histórico curto — baseline")

    med = Decimal(str(median(history)))
    if med == 0:
        return OutlierDecision(ReadVerdict.ACCEPT, "mediana zero")

    if price > med * ABSURD_HIGH_RATIO or med / price > LOW_OUTLIER_RATIO:
        return OutlierDecision(ReadVerdict.REJECT, "leitura absurda vs mediana (provável erro de parse)")
    if price > med * DEFAULT_MAX_RATIO or price < med * SUSPICIOUS_DROP_RATIO:
        return OutlierDecision(ReadVerdict.CONFIRM, "queda ou alta forte — espera 2ª leitura")
    return OutlierDecision(ReadVerdict.ACCEPT, "leitura compatível com o histórico")


def reads_agree(first: Decimal, second: Decimal, *, tolerance: Decimal = CONFIRMATION_TOLERANCE) -> bool:
    if first <= 0 or second <= 0:
        return False
    return abs(first - second) / max(first, second) <= tolerance
