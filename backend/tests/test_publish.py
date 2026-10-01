from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.config import Settings
from app.publishing.telegram import format_message, should_publish
from app.schemas.normalized import Classification


def _opp(**kwargs):
    data = dict(
        id="opp-1",
        product_id="p1",
        product_name="SSD NVMe 2TB",
        merchant="Loja Exemplo",
        current_price=Decimal("459.00"),
        historical_median=Decimal("699.00"),
        historical_discount_pct=Decimal("34.33"),
        acceptance_score=91,
        classification=Classification.HISTORICALLY_VALIDATED.value,
        status="active",
        price_verified=True,
        final_purchase_url="https://example.com/item",
        affiliate_status="direct",
    )
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_message_validated():
    text = format_message(_opp())
    assert "OFERTA DETECTADA" in text
    assert "Histórico validado" in text
    assert "R$ 459,00" in text
    assert "https://example.com/item" in text


def test_message_provisional_disclaimer():
    text = format_message(_opp(classification=Classification.PROVISIONAL.value, price_verified=False))
    assert "Oferta reportada — preço ou histórico não confirmado." in text


def test_provisional_auto_publish_blocked():
    settings = Settings(enable_telegram_publish=True, telegram_bot_token="x", telegram_chat_id="1")
    allowed, reason = should_publish(_opp(classification=Classification.PROVISIONAL.value), settings)
    assert allowed is False
    assert reason == "provisional_blocked"


def test_expired_and_invalid_url_blocked():
    settings = Settings(enable_telegram_publish=True, telegram_bot_token="x", telegram_chat_id="1")
    allowed, reason = should_publish(_opp(status="expired"), settings)
    assert allowed is False
    allowed, reason = should_publish(_opp(final_purchase_url=None), settings)
    assert reason == "invalid_url"


def test_unverified_still_can_publish_if_validated_config():
    settings = Settings(enable_telegram_publish=True, telegram_bot_token="x", telegram_chat_id="1")
    allowed, reason = should_publish(_opp(), settings)
    assert allowed is True


def test_disabled_telegram():
    settings = Settings(enable_telegram_publish=False, telegram_bot_token="x", telegram_chat_id="1")
    allowed, reason = should_publish(_opp(), settings)
    assert allowed is False
    assert reason == "telegram_disabled"
