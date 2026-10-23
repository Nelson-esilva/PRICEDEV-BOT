"""Troca o code do OAuth do Mercado Livre por tokens e grava ML_REFRESH_TOKEN no .env.

Uso (a partir de backend/):  python scripts/ml_oauth.py TG-xxxxxxxx
Lê ML_CLIENT_ID, ML_CLIENT_SECRET e ML_REDIRECT_URI do ../.env. Nunca imprime segredos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

ENV = Path(__file__).resolve().parents[2] / ".env"


def read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV.read_text().splitlines():
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if match:
            values[match.group(1)] = match.group(2).strip().strip('"').strip("'")
    return values


def write_env(key: str, value: str) -> None:
    text = ENV.read_text()
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, re.M):
        text = re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV.write_text(text)


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("TG-"):
        print("Uso: python scripts/ml_oauth.py TG-xxxxxxxx")
        return 2
    env = read_env()
    missing = [k for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET") if not env.get(k)]
    if missing:
        print(f"Faltam no .env: {', '.join(missing)}")
        return 2
    response = httpx.post(
        "https://api.mercadolibre.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": env["ML_CLIENT_ID"],
            "client_secret": env["ML_CLIENT_SECRET"],
            "code": sys.argv[1],
            "redirect_uri": env.get("ML_REDIRECT_URI") or "https://www.google.com",
        },
        headers={"Accept": "application/json"},
        timeout=20,
    )
    data = response.json()
    if response.status_code != 200 or "refresh_token" not in data:
        print(f"Falhou (HTTP {response.status_code}): {data.get('error')} - {data.get('message')}")
        return 1
    write_env("ML_REFRESH_TOKEN", data["refresh_token"])
    print(f"OK: ML_REFRESH_TOKEN gravado no .env (user_id {data.get('user_id')}, escopos: {data.get('scope')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
