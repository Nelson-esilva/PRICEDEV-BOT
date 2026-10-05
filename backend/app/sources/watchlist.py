from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from urllib.parse import urlparse

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.ingestion.identity import infer_marketplace, parse_product_url
from app.ingestion.jsonld import parse_jsonld_product
from app.models.entities import WatchlistItem
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector
from app.sources.rate import TokenBucket

log = get_logger("watchlist")

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class WatchlistSource(SourceConnector):
    """Acompanha URLs coladas pelo usuário via JSON-LD da página."""

    name = "watchlist"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.watchlist_poll_seconds
        self.bucket = TokenBucket(0.4)
        self._client = client
        self._owns_client = client is None

    def is_enabled(self) -> bool:
        return self.settings.enable_watchlist

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": BROWSER_UA,
                    "Accept": "text/html,application/xhtml+xml,application/json",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                },
            )
        return self._client

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        factory = get_session_factory()
        async with factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(WatchlistItem)
                        .where(WatchlistItem.enabled.is_(True))
                        .order_by(WatchlistItem.last_checked_at.is_(None), WatchlistItem.updated_at.asc())
                        .limit(self.settings.watchlist_batch)
                    )
                ).scalars()
            )
        offers: list[NormalizedOffer] = []
        for item in rows:
            offer = await self._check(item, fetched_at)
            if offer:
                offers.append(offer)
        return offers

    async def _check(self, item: WatchlistItem, fetched_at: datetime) -> NormalizedOffer | None:
        await self.bucket.acquire()
        factory = get_session_factory()
        try:
            response = await self._http().get(item.url)
            if response.status_code in {403, 429, 401}:
                async with factory() as session:
                    fresh = await session.get(WatchlistItem, item.id)
                    if fresh is not None:
                        fresh.consecutive_errors += 1
                        fresh.last_error = f"loja bloqueou ({response.status_code})"
                        fresh.last_checked_at = fetched_at
                        await session.commit()
                return None
            if response.status_code in {404, 410}:
                async with factory() as session:
                    fresh = await session.get(WatchlistItem, item.id)
                    if fresh is not None:
                        fresh.consecutive_errors += 1
                        fresh.last_error = f"anúncio sumiu ({response.status_code})"
                        fresh.last_checked_at = fetched_at
                        if fresh.consecutive_errors >= 3:
                            fresh.enabled = False
                        await session.commit()
                return None
            parsed = parse_jsonld_product(response.text or "")
            if parsed is None or parsed.price is None:
                async with factory() as session:
                    fresh = await session.get(WatchlistItem, item.id)
                    if fresh is not None:
                        fresh.consecutive_errors += 1
                        fresh.last_error = "página sem JSON-LD de produto"
                        fresh.last_checked_at = fetched_at
                        await session.commit()
                return None
            offer = self._to_offer(item, parsed, fetched_at)
            async with factory() as session:
                fresh = await session.get(WatchlistItem, item.id)
                if fresh is None:
                    return offer
                fresh.last_price = parsed.price
                fresh.last_error = None
                fresh.consecutive_errors = 0
                fresh.last_checked_at = fetched_at
                fresh.product_name = parsed.name or fresh.product_name
                if parsed.name:
                    fresh.product_name = parsed.name
                await session.commit()
            return offer
        except Exception as exc:
            log.warning("watchlist_item_skip", url=item.url, error=str(exc))
            async with factory() as session:
                fresh = await session.get(WatchlistItem, item.id)
                if fresh is not None:
                    fresh.consecutive_errors += 1
                    fresh.last_error = str(exc)[:500]
                    fresh.last_checked_at = fetched_at
                    await session.commit()
            return None

    def _to_offer(self, item: WatchlistItem, parsed, fetched_at: datetime) -> NormalizedOffer:
        market, native = parse_product_url(item.url)
        marketplace = market or infer_marketplace(item.url, item.marketplace or "unknown")
        native = native or item.native_product_id or sha256(item.url.encode()).hexdigest()[:16]
        return NormalizedOffer(
            source=self.name,
            source_record_id=item.id,
            marketplace=marketplace,
            merchant_id="",
            merchant_name=urlparse(item.url).hostname,
            native_product_id=native,
            offer_id=item.id,
            product_name=parsed.name or item.product_name or "Produto acompanhado",
            listed_price=parsed.price,
            reported_price=parsed.price,
            verified_price=parsed.price,
            effective_price=parsed.price,
            currency=parsed.currency or "BRL",
            availability=parsed.availability,
            fetched_at=fetched_at,
            purchase_url=sanitize_purchase_url(item.url),
            image_url=sanitize_media_url(parsed.image),
            identity_confidence=IdentityConfidence.HIGH if market else IdentityConfidence.MEDIUM,
            price_verified=True,
            raw_payload={"watchlist_id": item.id, **parsed.raw},
        ).quantized()
