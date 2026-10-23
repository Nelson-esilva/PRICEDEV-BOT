"""Termos mais buscados no Mercado Livre, usados só nos bastidores.

Não aparecem no site: servem para (1) buscar ofertas desses termos em todas as lojas e
(2) marcar como "Em alta" e priorizar as ofertas que batem com eles.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from app.core.db import utcnow

TRENDS_FILE = Path(__file__).resolve().parents[2] / "data" / "ml_trends.json"
MAX_AGE = timedelta(hours=12)
_cache: dict = {"mtime": None, "terms": []}


def fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


def _useful(term: str) -> bool:
    # "h t v", "x" e afins casariam com qualquer título.
    words = fold(term).split()
    return bool(words) and max(len(w) for w in words) >= 3


def save_trends(terms: list[str]) -> list[str]:
    clean = list(dict.fromkeys(t.strip().lower() for t in terms if t and _useful(t)))
    TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TRENDS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"terms": clean, "saved_at": utcnow().isoformat()}, ensure_ascii=False))
    os.replace(tmp, TRENDS_FILE)
    return clean


def load_trends() -> list[str]:
    try:
        mtime = TRENDS_FILE.stat().st_mtime
    except OSError:
        return []
    if _cache["mtime"] != mtime:
        try:
            data = json.loads(TRENDS_FILE.read_text())
        except (OSError, ValueError):
            return []
        try:
            fresh = utcnow() - datetime.fromisoformat(data.get("saved_at") or "") < MAX_AGE
        except ValueError:
            fresh = False
        # Termos velhos param de valer sozinhos se a coleta parar.
        _cache.update(mtime=mtime, terms=list(data.get("terms") or []) if fresh else [])
    return _cache["terms"]


def trend_of(name: str, terms: list[str]) -> str | None:
    """Primeiro termo em alta cujas palavras estão todas no título (ordem livre, sem acento)."""
    words = set(fold(name).split())
    for term in terms:
        needed = fold(term).split()
        if needed and all(word in words for word in needed):
            return term
    return None
