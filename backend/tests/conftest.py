from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory, init_db, reset_engine
from app.ingestion.pipeline import ingest_offers
from app.schemas.normalized import IdentityConfidence, NormalizedOffer


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("ENABLE_PELANDO", "false")
    monkeypatch.setenv("ENABLE_SHOPEE", "false")
    monkeypatch.setenv("ENABLE_MERCADOLIVRE", "false")
    monkeypatch.setenv("ENABLE_MAGALU", "false")
    monkeypatch.setenv("ENABLE_LOMADEE", "false")
    monkeypatch.setenv("ENABLE_PRICE_CONFIRM", "false")
    monkeypatch.setenv("ENABLE_WATCHLIST", "false")
    monkeypatch.setenv("ENABLE_TELEGRAM_PUBLISH", "false")
    monkeypatch.setenv("ALLOW_PROVISIONAL_AUTO_PUBLISH", "false")
    get_settings.cache_clear()
    reset_engine()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture
async def db(test_settings: Settings) -> AsyncSession:
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
async def client(test_settings: Settings):
    await init_db()
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def make_offer(**kwargs) -> NormalizedOffer:
    now = kwargs.pop("now", datetime(2026, 10, 1, 12, 0, tzinfo=UTC))
    defaults = dict(
        source="pelando",
        source_record_id="item-1",
        marketplace="kabum",
        merchant_id="kabum",
        merchant_name="KaBuM!",
        native_product_id="ssd-nvme-2tb",
        product_name="SSD NVMe 2TB",
        condition="new",
        listed_price=Decimal("459.00"),
        verified_price=Decimal("459.00"),
        effective_price=Decimal("459.00"),
        currency="BRL",
        availability="in_stock",
        fetched_at=now,
        purchase_url="https://www.kabum.com.br/produto/ssd-nvme-2tb",
        identity_confidence=IdentityConfidence.HIGH,
        price_verified=True,
    )
    defaults.update(kwargs)
    return NormalizedOffer(**defaults)


async def ingest_history(
    session: AsyncSession,
    settings: Settings,
    *,
    prices: list[tuple[Decimal, datetime]],
    native_id: str = "ssd-nvme-2tb",
    condition: str = "new",
    currency: str = "BRL",
    verified: bool = True,
) -> None:
    for idx, (price, when) in enumerate(prices):
        offer = make_offer(
            source_record_id=f"{native_id}-{idx}",
            native_product_id=native_id,
            listed_price=price,
            verified_price=price if verified else None,
            effective_price=price,
            fetched_at=when,
            now=when,
            condition=condition,
            currency=currency,
            price_verified=verified,
        )
        await ingest_offers(session, [offer], settings, now=when)
