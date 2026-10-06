from app.core.config import Settings
from app.inbox.telegram import _allowed_chat


def test_block_one_group_by_title_or_id():
    settings = Settings(telegram_inbox_block_chats="Promo Ruim, -10042")
    assert _allowed_chat(settings, -10042, "promoruim", "Promo Ruim") is False
    assert _allowed_chat(settings, 42, None, "Promo Ruim") is False
    assert _allowed_chat(settings, -10099, "ofertasboas", "Ofertas Boas") is True


def test_allowlist_still_works_with_block():
    settings = Settings(
        telegram_inbox_chats="@ofertasboas",
        telegram_inbox_block_chats="Promo Ruim",
    )
    assert _allowed_chat(settings, 1, "ofertasboas", "Ofertas Boas") is True
    assert _allowed_chat(settings, 2, None, "Promo Ruim") is False
    assert _allowed_chat(settings, 3, "outro", "Outro Grupo") is False
