from __future__ import annotations

__all__ = ["run_telegram_inbox"]


def __getattr__(name: str):
    if name == "run_telegram_inbox":
        from app.inbox.telegram import run_telegram_inbox

        return run_telegram_inbox
    raise AttributeError(name)
