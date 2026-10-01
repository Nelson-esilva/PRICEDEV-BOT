from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import Settings
from app.core.money import pct
from app.history.stats import HistoryStats
from app.schemas.normalized import (
    Classification,
    HistoryConfidence,
    IdentityConfidence,
    NormalizedOffer,
)


@dataclass
class ScoreFactor:
    name: str
    weight: int
    points: int
    reason: str


@dataclass
class EngineResult:
    classification: Classification
    acceptance_score: int
    score_breakdown: dict
    historical_discount_pct: Decimal | None
    discount_vs_minimum_pct: Decimal | None
    discount_vs_previous_pct: Decimal | None
    distance_to_min_pct: Decimal | None
    history_confidence: HistoryConfidence
    reasons: list[str]
    risks: list[str]
    confirmed: bool = False


def _age_hours(moment: datetime | None, now: datetime) -> float | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (now - moment).total_seconds() / 3600.0)


def _history_confidence(stats: HistoryStats, settings: Settings) -> HistoryConfidence:
    if stats.observations == 0:
        return HistoryConfidence.NONE
    if (
        stats.observations >= settings.min_history_observations
        and stats.distinct_days >= settings.min_history_distinct_days
    ):
        return HistoryConfidence.HIGH
    if stats.observations >= max(3, settings.min_history_observations // 2) and stats.distinct_days >= 3:
        return HistoryConfidence.MEDIUM
    return HistoryConfidence.LOW


def _discount_points(discount_pct: Decimal | None, settings: Settings) -> tuple[int, str]:
    weight = settings.score_weight_historical_discount
    if discount_pct is None:
        return 0, "sem desconto histórico calculável"
    if discount_pct <= 0:
        return 0, f"preço atual não está abaixo da mediana ({discount_pct}%)"
    ratio = float(discount_pct) / max(settings.min_historical_discount_pct, 1)
    points = int(round(min(1.0, ratio) * weight))
    return points, f"desconto vs mediana {discount_pct}%"


def _quality_points(stats: HistoryStats, settings: Settings) -> tuple[int, str]:
    weight = settings.score_weight_history_quality
    if stats.observations == 0:
        return 0, "histórico vazio"
    obs_ratio = min(1.0, stats.observations / max(settings.min_history_observations, 1))
    day_ratio = min(1.0, stats.distinct_days / max(settings.min_history_distinct_days, 1))
    points = int(round(((obs_ratio + day_ratio) / 2) * weight))
    return points, f"{stats.observations} obs. em {stats.distinct_days} dias distintos"


def _identity_points(confidence: IdentityConfidence, settings: Settings) -> tuple[int, str]:
    weight = settings.score_weight_identity
    mapping = {
        IdentityConfidence.HIGH: 1.0,
        IdentityConfidence.MEDIUM: 0.7,
        IdentityConfidence.LOW: 0.35,
        IdentityConfidence.PROVISIONAL: 0.15,
    }
    points = int(round(mapping[confidence] * weight))
    return points, f"confiança de identidade {confidence.value}"


def _verified_points(verified: bool, settings: Settings) -> tuple[int, str]:
    weight = settings.score_weight_price_verified
    if verified:
        return weight, "preço confirmado pela fonte autorizada"
    return 0, "PRICE_UNVERIFIED — preço não confirmado na loja"


def _freshness_points(offer: NormalizedOffer, now: datetime, settings: Settings) -> tuple[int, str]:
    weight = settings.score_weight_freshness
    age = _age_hours(offer.source_created_at or offer.fetched_at, now)
    if age is None:
        return weight // 2, "idade da fonte desconhecida"
    if age <= 1:
        return weight, f"oferta observada há {age:.1f}h"
    if age <= 24:
        return int(round(weight * 0.7)), f"oferta observada há {age:.1f}h"
    if age <= 72:
        return int(round(weight * 0.4)), f"oferta observada há {age:.1f}h"
    return 0, f"oferta antiga ({age:.1f}h)"


def _community_points(offer: NormalizedOffer, settings: Settings) -> tuple[int, str]:
    weight = settings.score_weight_community
    temp = offer.temperature
    if temp is None:
        return 0, "sem sinal de comunidade"
    if temp < 0:
        return 0, f"temperatura negativa ({temp}) — possível desconto questionado"
    if temp >= 300:
        return weight, f"temperatura alta ({temp})"
    if temp >= 50:
        return int(round(weight * 0.5)), f"temperatura moderada ({temp})"
    return int(round(weight * 0.2)), f"temperatura baixa ({temp})"


def evaluate_offer(
    offer: NormalizedOffer,
    stats: HistoryStats,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> EngineResult:
    now = now or datetime.now(UTC)
    reasons: list[str] = []
    risks: list[str] = []

    vs_median = pct(stats.median - offer.effective_price, stats.median) if stats.median else None
    vs_min = pct(stats.minimum - offer.effective_price, stats.minimum) if stats.minimum else None
    vs_prev = (
        pct(stats.previous_price - offer.effective_price, stats.previous_price)
        if stats.previous_price
        else None
    )
    distance_min = None
    if stats.minimum and stats.minimum > 0:
        distance_min = pct(offer.effective_price - stats.minimum, stats.minimum)

    if offer.effective_price <= 0 and offer.category not in {"games", "gratis", "free"}:
        risks.append("preço zero fora de categoria de brindes")
    if offer.currency != (stats.currency or offer.currency):
        risks.append("moeda incompatível com o histórico")
        vs_median = vs_min = vs_prev = None
    if offer.condition not in {"new", "unknown"} and offer.condition:
        risks.append(f"condição '{offer.condition}' — não comparar com unidade nova")
    if offer.announced_discount_pct is not None and vs_median is not None:
        gap = abs(offer.announced_discount_pct - vs_median)
        if gap > Decimal("15"):
            risks.append(
                f"desconto anunciado ({offer.announced_discount_pct}%) diverge do histórico ({vs_median}%)"
            )
    if offer.shipping_cost is None and offer.source == "pelando":
        risks.append("frete não informado pela fonte comunitária")
    if offer.availability not in {"in_stock", "unknown"}:
        risks.append(f"disponibilidade {offer.availability}")
    if offer.temperature is not None and offer.temperature < 0:
        risks.append("temperatura negativa da comunidade")

    factors = []
    for name, fn in (
        ("historical_discount", lambda: _discount_points(vs_median, settings)),
        ("history_quality", lambda: _quality_points(stats, settings)),
        ("identity", lambda: _identity_points(offer.identity_confidence, settings)),
        ("price_verified", lambda: _verified_points(offer.price_verified, settings)),
        ("freshness", lambda: _freshness_points(offer, now, settings)),
        ("community", lambda: _community_points(offer, settings)),
    ):
        points, reason = fn()
        weight = settings.score_weights[name]
        factors.append(ScoreFactor(name, weight, points, reason))

    score = max(0, min(100, sum(f.points for f in factors)))
    breakdown = {
        f.name: {"weight": f.weight, "points": f.points, "reason": f.reason} for f in factors
    }
    history_conf = _history_confidence(stats, settings)

    identity_ok = offer.identity_confidence in {IdentityConfidence.HIGH, IdentityConfidence.MEDIUM}
    history_ok = (
        stats.observations >= settings.min_history_observations
        and stats.distinct_days >= settings.min_history_distinct_days
        and history_conf is HistoryConfidence.HIGH
    )
    verified_ok = offer.price_verified or not settings.require_verified_price_for_historical_alert
    discount_ok = vs_median is not None and vs_median >= Decimal(str(settings.min_historical_discount_pct))
    available_ok = offer.availability in {"in_stock", "unknown"}
    score_ok = score >= settings.min_acceptance_score

    classification: Classification
    confirmed = False

    if offer.availability == "unavailable":
        classification = Classification.REJECTED
        reasons.append("produto indisponível")
    elif not identity_ok:
        classification = (
            Classification.PROVISIONAL
            if settings.allow_provisional_opportunities
            else Classification.INSUFFICIENT_HISTORY
        )
        reasons.append("identidade do produto insuficiente para validação histórica")
    elif not history_ok:
        if stats.observations > 0 and stats.median is not None:
            classification = Classification.INSUFFICIENT_HISTORY
            reasons.append(
                f"histórico insuficiente ({stats.observations} obs., {stats.distinct_days} dias)"
            )
            if settings.allow_provisional_opportunities:
                classification = Classification.PROVISIONAL
                reasons.append("oferta provisória — histórico ainda não confiável")
        else:
            classification = (
                Classification.PROVISIONAL
                if settings.allow_provisional_opportunities
                else Classification.INSUFFICIENT_HISTORY
            )
            reasons.append("sem histórico próprio anterior")
    elif not verified_ok:
        classification = Classification.PROVISIONAL
        reasons.append("PRICE_UNVERIFIED — alerta histórico exige preço confirmado")
    elif not discount_ok:
        classification = Classification.REJECTED
        reasons.append(
            f"desconto vs mediana {vs_median}% abaixo do mínimo {settings.min_historical_discount_pct}%"
        )
    elif not available_ok:
        classification = Classification.REJECTED
        reasons.append("disponibilidade incompatível")
    elif not score_ok:
        classification = Classification.REJECTED
        reasons.append(f"score {score} abaixo do mínimo {settings.min_acceptance_score}")
    else:
        classification = Classification.HISTORICALLY_VALIDATED
        confirmed = True
        reasons.append("desconto histórico e score atingiram os critérios configuráveis")
        if vs_median is not None and vs_median >= Decimal(str(settings.anomaly_discount_pct)):
            classification = Classification.PRICE_ANOMALY_CANDIDATE
            reasons.append(
                f"queda excepcional ({vs_median}%) — candidato a anomalia, não erro confirmado da loja"
            )

    if classification is Classification.PROVISIONAL:
        reasons.append("não classificar como mínimo histórico")

    return EngineResult(
        classification=classification,
        acceptance_score=score,
        score_breakdown=breakdown,
        historical_discount_pct=vs_median,
        discount_vs_minimum_pct=vs_min,
        discount_vs_previous_pct=vs_prev,
        distance_to_min_pct=distance_min,
        history_confidence=history_conf,
        reasons=reasons,
        risks=risks,
        confirmed=confirmed,
    )
