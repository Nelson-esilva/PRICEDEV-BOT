from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.core.config import Settings
from app.schemas.normalized import NormalizedOffer


class SourceError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True, disable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.disable = disable


class SourceBlocked(SourceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False, disable=True)


class SourceAuthError(SourceError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False, disable=True)


class SourceConnector(ABC):
    name: str
    poll_seconds: int

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @abstractmethod
    def is_enabled(self) -> bool: ...

    @abstractmethod
    async def poll(self, *, now: datetime) -> list[NormalizedOffer]: ...

    async def close(self) -> None:
        return None
