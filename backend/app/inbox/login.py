"""Login Telegram para a conta dona ou para outra pessoa escutar grupos.

Uso (na pasta backend, venv ativo):
    python -m app.inbox.login
    python -m app.inbox.login --extra maria
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.core.config import get_settings


def extra_session_dir() -> Path:
    root = Path.cwd() / "data" / "sessions"
    parent = Path.cwd().parent / "data" / "sessions"
    if parent.exists() and not root.exists():
        return parent
    root.mkdir(parents=True, exist_ok=True)
    return root


def extra_session_path(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")[:40]
    if not slug:
        raise SystemExit("Use um nome simples, tipo: python -m app.inbox.login --extra maria")
    return str(extra_session_dir() / slug)


def list_extra_sessions() -> list[str]:
    root = extra_session_dir()
    found: list[str] = []
    for path in sorted(root.glob("*.session")):
        if path.name.endswith("-journal"):
            continue
        found.append(str(path.with_suffix("")))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Login Telegram da escuta de grupos")
    parser.add_argument(
        "--extra",
        metavar="NOME",
        help="Login de outra pessoa. Cria sessão extra só para escutar, sem publicar.",
    )
    args = parser.parse_args()
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit(
            "Falta TELEGRAM_API_ID e TELEGRAM_API_HASH. Crie em https://my.telegram.org/apps"
        )
    from telethon.sync import TelegramClient

    session = extra_session_path(args.extra) if args.extra else settings.telegram_session_path
    with TelegramClient(session, settings.telegram_api_id, settings.telegram_api_hash) as client:
        me = client.get_me()
        who = f"{me.first_name} (@{me.username or 'sem-username'})"
        if args.extra:
            print(f"Sessão extra ok ({args.extra}): {who}")
            print("Essa conta só escuta grupos. Reinicie a API para começar.")
        else:
            print(f"Sessão ok: {who}")
            print("Ligue ENABLE_CHANNEL_INBOX=true e reinicie a API.")


if __name__ == "__main__":
    main()
