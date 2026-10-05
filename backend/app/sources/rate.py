from __future__ import annotations

import asyncio
import time


class TokenBucket:
    def __init__(self, rps: float = 1.0) -> None:
        self.rate = max(0.1, rps)
        self.tokens = 1.0
        self.updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(1.0, self.tokens + (now - self.updated_at) * self.rate)
                self.updated_at = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)
