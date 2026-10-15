from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import Settings
from app.models.entities import InboxMessage, PublicationLog
from app.publishing.telegram import inbox_publish_key, inbox_publish_keys, publish_inbox


def _row(**kwargs) -> InboxMessage:
    data = dict(
        channel="telegram",
        chat_id="1",
        chat_title="Grupo A",
        message_id="10",
        product_name="Fone Bluetooth",
        body="Fone em oferta por R$ 99",
        purchase_url="https://www.mercadolivre.com.br/fone/p/MLB12345678",
        marketplace="mercadolivre",
        native_product_id="MLB12345678",
        posted_at=datetime(2026, 10, 8, 12, tzinfo=UTC),
        received_at=datetime(2026, 10, 8, 12, tzinfo=UTC),
    )
    data.update(kwargs)
    return InboxMessage(**data)


def _publish_settings() -> Settings:
    return Settings(
        enable_telegram_publish=True,
        telegram_api_id=1,
        telegram_api_hash="x",
        telegram_publish_chat="@ofertas",
        ml_affiliate_matt_word="word",
        ml_affiliate_matt_tool="tool",
        amazon_affiliate_tag="tag-20",
    )


def test_inbox_publish_key_ignores_group_and_caption():
    a = _row()
    b = _row(
        chat_id="2",
        chat_title="Grupo B",
        message_id="99",
        product_name="FONE BT PROMO",
        body="outro texto",
        purchase_url="https://www.mercadolivre.com.br/outro-titulo/p/MLB12345678?hidab_from=share",
    )
    assert inbox_publish_key(a) == inbox_publish_key(b)
    assert inbox_publish_key(a) == "inbox:mercadolivre:mlb12345678"
    short = _row(
        marketplace="shopee",
        native_product_id="",
        purchase_url="https://s.shopee.com.br/7faRKeFnHI",
        product_name="Nova Profissional Placa De Carbono Tênis De Corrida",
    )
    long = _row(
        marketplace="shopee",
        native_product_id="46054420959",
        purchase_url="https://shopee.com.br/opaanlp/662418492/46054420959",
        product_name="Nova Profissional Placa De Carbono Tênis De Corrida",
    )
    assert inbox_publish_key(long) == "inbox:shopee:46054420959"
    assert inbox_publish_key(short).startswith("inbox:fp:shopee:")
    assert inbox_publish_key(short) == inbox_publish_key(
        _row(
            chat_id="9",
            message_id="88",
            marketplace="shopee",
            native_product_id="",
            purchase_url="https://s.shopee.com.br/outro",
            product_name="Nova Profissional Placa De Carbono Tênis De Corrida",
        )
    )
    asin = _row(
        marketplace="amazon",
        native_product_id="B0CNKVYLF5",
        purchase_url="https://www.amazon.com.br/dp/B0CNKVYLF5",
        product_name="10% OFF em R$ 400, máx de R$ 100 OFF: PRIMEHOJE",
        body="10% OFF em R$ 400, máx de R$ 100 OFF: PRIMEHOJE",
    )
    home = _row(
        chat_id="9",
        message_id="2",
        marketplace="amazon",
        native_product_id="",
        purchase_url="https://www.amazon.com.br/?tag=santanatech-20",
        product_name="10% OFF a partir de R$ 400, Limite de R$ 100 OFF: PRIMEHOJE",
        body="10% OFF a partir de R$ 400, Limite de R$ 100 OFF: PRIMEHOJE",
    )
    assert "inbox:campaign:amazon:primehoje:400" in inbox_publish_keys(asin)
    assert "inbox:campaign:amazon:primehoje:400" in inbox_publish_keys(home)


async def test_second_group_does_not_republish(db, monkeypatch):
    monkeypatch.setattr("app.publishing.telegram._deliver", AsyncMock(return_value=True))
    settings = _publish_settings()
    first = _row()
    second = _row(chat_id="2", chat_title="Grupo B", message_id="11", product_name="Mesmo fone")
    db.add(first)
    db.add(second)
    await db.commit()
    await db.refresh(first)
    await db.refresh(second)
    assert await publish_inbox(db, first, settings) == "published"
    await db.commit()
    assert await publish_inbox(db, second, settings) == "duplicate"


async def test_republish_allowed_after_dedup_window(db, monkeypatch):
    monkeypatch.setattr("app.publishing.telegram._deliver", AsyncMock(return_value=True))
    settings = _publish_settings()
    settings.telegram_dedup_hours = 3
    first = _row()
    later = _row(chat_id="2", chat_title="Grupo B", message_id="12", product_name="Mesmo fone de novo")
    db.add(first)
    db.add(later)
    await db.commit()
    await db.refresh(first)
    await db.refresh(later)
    assert await publish_inbox(db, first, settings) == "published"
    await db.commit()
    logs = (
        await db.execute(select(PublicationLog).where(PublicationLog.channel == "telegram"))
    ).scalars().all()
    assert logs
    stale = datetime.now(UTC) - timedelta(hours=4)
    for row in logs:
        row.published_at = stale
    await db.commit()
    assert await publish_inbox(db, later, settings) == "published"


async def test_skips_coupon_mechan_without_product(db, monkeypatch):
    monkeypatch.setattr("app.publishing.telegram._deliver", AsyncMock(return_value=True))
    settings = _publish_settings()
    row = _row(
        product_name="10% OFF a partir de R$ 89, Limite de R$ 20: FULL1510",
        body="10% OFF a partir de R$ 89, Limite de R$ 20: FULL1510\nhttps://heylink.me/customer9725",
        purchase_url="https://heylink.me/customer9725",
        marketplace="afiliado",
        native_product_id="",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    assert await publish_inbox(db, row, settings) == "coupon_mechan"


async def test_inbox_api_collapses_same_product(client, db):
    db.add(_row())
    db.add(_row(chat_id="2", chat_title="Grupo B", message_id="11", product_name="Mesmo fone"))
    db.add(
        _row(
            chat_id="3",
            chat_title="Grupo C",
            message_id="12",
            product_name="SSD",
            body="SSD NVMe 2TB",
            purchase_url="https://www.amazon.com.br/dp/B0ABCDEFGH",
            marketplace="amazon",
            native_product_id="B0ABCDEFGH",
        )
    )
    await db.commit()
    listed = await client.get("/api/v1/inbox")
    assert listed.status_code == 200
    assert listed.json()["total"] == 3
    collapsed = await client.get("/api/v1/inbox?unique=true")
    payload = collapsed.json()
    assert payload["total"] == 2
    names = {item["product"] for item in payload["items"]}
    markets = {item["marketplace"] for item in payload["items"]}
    assert "SSD NVMe 2TB" in names
    assert markets == {"mercadolivre", "amazon"}
