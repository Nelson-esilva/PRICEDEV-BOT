from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings


def require_ops(request: Request, settings: Settings = Depends(get_settings)) -> None:
    token = (settings.ops_api_token or "").strip()
    if not token:
        return
    header = request.headers.get("authorization") or ""
    raw = request.headers.get("x-ops-token") or ""
    bearer = header.removeprefix("Bearer ").strip() if header.lower().startswith("bearer ") else ""
    if token in {bearer, raw, header.strip()}:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ops_auth_required")
