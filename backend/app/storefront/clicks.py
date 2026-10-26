"""Fila de cliques do /go: o redirecionamento nunca espera o banco.

O SQLite tem um escritor só. Gravar o clique dentro da requisição fazia o visitante esperar
qualquer escrita em andamento (até o busy_timeout de 30 s). Agora o clique entra numa fila em
memória e um laço grava em lote; se o banco estiver ocupado, tenta de novo no próximo ciclo.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.models.entities import DealClick

log = get_logger("clicks")

FLUSH_SECONDS = 5
# Teto da fila se o banco ficar indisponível por muito tempo (descarta os mais antigos).
MAX_PENDING = 20_000
_pending: deque[dict[str, Any]] = deque(maxlen=MAX_PENDING)


def record_click(**fields: Any) -> None:
    fields.setdefault("clicked_at", utcnow())
    _pending.append(fields)


async def flush_clicks() -> int:
    if not _pending:
        return 0
    batch = list(_pending)
    try:
        async with get_session_factory()() as session:
            session.add_all(DealClick(**row) for row in batch)
            await session.commit()
    except Exception as exc:
        log.warning("click_flush_failed", pending=len(batch), error=str(exc)[:160])
        return 0
    for _ in batch:
        _pending.popleft()
    return len(batch)


async def run_click_flusher() -> None:
    try:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            await flush_clicks()
    finally:
        # Desligando: última tentativa para não perder os cliques da fila.
        await flush_clicks()
