"""Cliente da API oficial do Mercado Livre (OAuth do DevCenter), compartilhado por coletor e enriquecimento.

O refresh token é rotativo: cada renovação invalida o anterior. Por isso o token de acesso vive num
único lugar do processo, atrás de uma trava, e o refresh novo vai para um arquivo (não o banco, que
pode estar travado pela ingestão no exato momento em que o antigo já morreu).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.sources.base import SourceAuthError, SourceError
from app.sources.rate import TokenBucket

log = get_logger("mlapi")

API = "https://api.mercadolibre.com"
TOKEN_URL = f"{API}/oauth/token"
# data/ fica fora do git.
TOKEN_FILE = Path(__file__).resolve().parents[2] / "data" / "ml_oauth.json"

_lock = asyncio.Lock()
_access: dict[str, Any] = {"token": None, "expires_at": None}
# Compartilhado por coletor e enriquecimento: 4/s gerava 429 do ML com os dois rodando.
_bucket = TokenBucket(2.0)
RETRIES_429 = 3


class RateLimited(SourceError):
    """429 do ML que persistiu depois das novas tentativas."""

    def __init__(self) -> None:
        super().__init__("ML API 429", retryable=True)


def ml_api_enabled(settings: Settings) -> bool:
    return bool(settings.enable_ml_official and settings.ml_client_id and settings.ml_client_secret and settings.ml_refresh_token)


class MlApi:
    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0, headers={"Accept": "application/json"})
        return self._client

    async def get(self, path: str) -> Any:
        """JSON da rota, ou None quando a API nega/não encontra (403/404 são normais para terceiros)."""
        for attempt in range(RETRIES_429 + 1):
            token = await self.token()
            await _bucket.acquire()
            response = await self._http().get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 429:
                break
            if attempt == RETRIES_429:
                raise RateLimited()
            # Espera o que o ML pedir (Retry-After), senão 2, 4, 8 s.
            try:
                wait = float(response.headers.get("retry-after") or 0)
            except ValueError:
                wait = 0
            await asyncio.sleep(min(30.0, wait or 2.0 * 2**attempt))
        if response.status_code == 401:
            _access["token"] = None
            raise SourceError("ML API 401: token expirado", retryable=True)
        if response.status_code >= 500:
            raise SourceError(f"ML API {response.status_code}", retryable=True)
        if response.status_code != 200:
            log.debug("mlapi_skip", path=path.split("?")[0], status=response.status_code)
            return None
        return response.json()

    async def token(self) -> str:
        async with _lock:
            expires: datetime | None = _access["expires_at"]
            if _access["token"] and expires and utcnow() < expires:
                return _access["token"]
            # O do arquivo é o mais novo; o do .env vale na 1ª vez e depois de uma nova autorização.
            candidates = [t for t in dict.fromkeys([_stored_refresh(), self.settings.ml_refresh_token]) if t]
            last = ""
            for refresh in candidates:
                response = await self._http().post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.settings.ml_client_id,
                        "client_secret": self.settings.ml_client_secret,
                        "refresh_token": refresh,
                    },
                )
                data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                if response.status_code == 200 and data.get("access_token"):
                    if data.get("refresh_token"):
                        _store_refresh(data["refresh_token"])
                    _access["token"] = data["access_token"]
                    _access["expires_at"] = utcnow() + timedelta(seconds=int(data.get("expires_in") or 21600) - 300)
                    return _access["token"]
                if response.status_code >= 500:
                    raise SourceError(f"ML OAuth {response.status_code}", retryable=True)
                last = str(data.get("error") or response.status_code)
            raise SourceAuthError(f"ML OAuth recusou o refresh token ({last}); rode scripts/ml_oauth.py de novo")


def _stored_refresh() -> str | None:
    try:
        return json.loads(TOKEN_FILE.read_text()).get("refresh_token")
    except (OSError, ValueError):
        return None


def _store_refresh(token: str) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"refresh_token": token, "saved_at": utcnow().isoformat()}))
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_FILE)
