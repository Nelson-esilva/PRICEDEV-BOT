from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

_ASYNCPG_DROP = {"channel_binding"}


class UTCDateTime(TypeDecorator):
    """SQLite devolve datetime naive; normaliza para UTC aware na leitura."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return as_utc(value)

    def process_result_value(self, value, dialect):
        return as_utc(value)

class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_database_url(url: str) -> str:
    """Neon/psql colam parâmetros que o asyncpg não aceita (ex.: channel_binding)."""
    raw = (url or "").strip()
    if not raw or raw.startswith("sqlite"):
        return raw
    parts = urlsplit(raw)
    scheme = parts.scheme
    if scheme in {"postgres", "postgresql"}:
        scheme = "postgresql+asyncpg"
    query: list[tuple[str, str]] = []
    seen_ssl = False
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        low = key.lower()
        if low in _ASYNCPG_DROP:
            continue
        if low == "ssl":
            seen_ssl = True
            query.append((key, value))
            continue
        if low == "sslmode":
            if not seen_ssl:
                query.append(("ssl", value))
                seen_ssl = True
            continue
        query.append((key, value))
    return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        database_url = normalize_database_url(settings.database_url)
        kwargs: dict = {"echo": False}
        if database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_async_engine(database_url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    from app import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(connection) -> None:
    inspector = inspect(connection)
    if "opportunities" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("opportunities")}
    extras = {
        "image_url": "TEXT",
        "description": "TEXT",
        "coupon_code": "VARCHAR(128)",
        "payment_hint": "VARCHAR(64)",
        "temperature": "INTEGER",
        "free_shipping": "BOOLEAN",
        "comment_count": "INTEGER",
        "announced_discount_pct": "NUMERIC(8,2)",
    }
    for name, ddl in extras.items():
        if name not in existing:
            connection.execute(text(f"ALTER TABLE opportunities ADD COLUMN {name} {ddl}"))
    if "products" in inspector.get_table_names():
        product_cols = {col["name"] for col in inspector.get_columns("products")}
        product_extras = {
            "held_price": "NUMERIC(14,2)",
            "held_count": "INTEGER DEFAULT 0",
        }
        for name, ddl in product_extras.items():
            if name not in product_cols:
                connection.execute(text(f"ALTER TABLE products ADD COLUMN {name} {ddl}"))
    if "inbox_messages" in inspector.get_table_names():
        inbox_cols = {col["name"] for col in inspector.get_columns("inbox_messages")}
        if "image_url" not in inbox_cols:
            connection.execute(text("ALTER TABLE inbox_messages ADD COLUMN image_url TEXT"))
        if "affiliate_url" not in inbox_cols:
            connection.execute(text("ALTER TABLE inbox_messages ADD COLUMN affiliate_url TEXT"))


def reset_engine() -> None:
    global _engine, _session_factory
    _engine = None
    _session_factory = None

