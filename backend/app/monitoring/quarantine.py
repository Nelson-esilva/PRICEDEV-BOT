"""Quarentena por fonte — backoff curto para 403/429.

Não deixa a fonte horas fora: 2 min → 10 min → 15 min.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.db import utcnow
from app.models.entities import SourceCheckpoint

_BACKOFF_SECONDS = (2 * 60, 10 * 60, 15 * 60, 15 * 60)


def trip(checkpoint: SourceCheckpoint, *, reason: str, blocked: bool = False) -> None:
    now = utcnow()
    state = dict(checkpoint.state or {})
    current = dict(state.get("quarantine") or {})
    tier = min(int(current.get("tier") or 0) + 1, len(_BACKOFF_SECONDS))
    delay = _BACKOFF_SECONDS[tier - 1]
    until = now + timedelta(seconds=delay)
    state["quarantine"] = {
        "tier": tier,
        "reason": reason[:500],
        "until": until.isoformat(),
        "blocked": blocked,
    }
    checkpoint.state = state
    checkpoint.circuit_open_until = until
    checkpoint.last_error = reason[:2000]
    if blocked and tier >= len(_BACKOFF_SECONDS):
        checkpoint.enabled = False


def clear(checkpoint: SourceCheckpoint) -> None:
    state = dict(checkpoint.state or {})
    if "quarantine" in state:
        state.pop("quarantine", None)
        checkpoint.state = state
    checkpoint.circuit_open_until = None
