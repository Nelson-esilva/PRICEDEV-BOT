"""Veredito da comunidade Pelando — adaptado de gabrielbelli/pelando-mcp (BSD-2)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.schemas.normalized import NormalizedOffer

HOT_TEMPERATURE = 300
QUIET_TEMPERATURE = 50
STALE_DAYS = 7.0


def crowd_signals(offer: NormalizedOffer, *, now: datetime) -> tuple[list[str], list[str]]:
    if offer.source != "pelando":
        return [], []
    reasons: list[str] = []
    risks: list[str] = []
    temp = offer.temperature
    if temp is not None and temp < 0:
        risks.append(
            f"temperatura negativa ({temp}) — a comunidade costuma marcar desconto inflado ou anúncio enganoso"
        )
    elif temp is not None and temp >= HOT_TEMPERATURE:
        reasons.append(f"comunidade endossou (temperatura {temp})")
    comments = offer.comment_count or 0
    if (temp is None or temp < QUIET_TEMPERATURE) and comments == 0:
        risks.append("pouco sinal da comunidade (fria e sem comentários)")
    created = offer.source_created_at or offer.fetched_at
    if created is not None:
        age = now - created
        if age > timedelta(days=STALE_DAYS):
            risks.append(f"oferta comunitária com mais de {int(STALE_DAYS)} dias")
    return reasons, risks
