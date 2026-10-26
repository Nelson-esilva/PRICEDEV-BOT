from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.db import get_session_factory, init_db, reset_engine
from app.ingestion.pipeline import ingest_offers
from app.models.entities import PublishedDeal
from app.storefront.catalog import publish_public_catalog
from tests.conftest import make_offer


async def test_catalog_publishes_official_sources_only(client, test_settings: Settings):
    factory = get_session_factory()
    from app.core.db import utcnow
    now = utcnow()
    test_settings.shopee_app_id = "123"
    async with factory() as session:
        await ingest_offers(
            session,
            [
                make_offer(
                    now=now,
                    source="shopee",
                    marketplace="shopee",
                    merchant_name="Shopee",
                    source_record_id="s1",
                    native_product_id="sp-fone",
                    product_name="Fone bluetooth Shopee",
                    announced_discount_pct=Decimal("20"),
                    purchase_url="https://shopee.com.br/product/111",
                    affiliate_url="https://shopee.com.br/product/111?mmp_pid=an_123",
                ),
                make_offer(
                    now=now,
                    source="mlhub",
                    marketplace="mercadolivre",
                    merchant_name="Mercado Livre",
                    source_record_id="m1",
                    native_product_id="MLB123456789",
                    product_name="Air fryer Mercado Livre",
                    announced_discount_pct=Decimal("20"),
                    purchase_url="https://www.mercadolivre.com.br/air-fryer/p/MLB123456789",
                    affiliate_url="https://www.mercadolivre.com.br/air-fryer/p/MLB123456789?matt_word=x",
                ),
                make_offer(
                    now=now,
                    source="pelando",
                    source_record_id="p1",
                    native_product_id="pelando-hidden",
                    product_name="SSD da comunidade",
                    purchase_url="https://www.kabum.com.br/produto/ssd-nvme-2tb",
                ),
            ],
            test_settings,
            now=now,
        )
        stats = await publish_public_catalog(test_settings, now=now, session=session)
        await session.commit()
    assert stats["eligible"] == 2
    assert stats["created"] == 2

    listed = await client.get("/api/public/v1/deals")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    names = {item["product"] for item in payload["items"]}
    assert "Fone bluetooth Shopee" in names
    assert "Air fryer Mercado Livre" in names
    assert "SSD da comunidade" not in names
    for item in payload["items"]:
        assert "destination_url" not in item
        assert "affiliate_url" not in item
        assert "purchase_url" not in item
        assert item["go_path"].startswith("/go/")

    shopee = await client.get("/api/public/v1/deals?store=shopee")
    assert shopee.json()["total"] == 1
    assert shopee.json()["items"][0]["store"] == "shopee"


async def test_go_redirects_and_expired_page(client, test_settings: Settings):
    factory = get_session_factory()
    from app.core.db import utcnow
    now = utcnow()
    test_settings.shopee_app_id = "123"
    async with factory() as session:
        await ingest_offers(
            session,
            [
                make_offer(
                    now=now,
                    source="shopee",
                    marketplace="shopee",
                    merchant_name="Shopee",
                    source_record_id="go1",
                    native_product_id="sp-go",
                    product_name="Monitor gamer Shopee",
                    announced_discount_pct=Decimal("20"),
                    purchase_url="https://shopee.com.br/product/222",
                    affiliate_url="https://shopee.com.br/product/222?mmp_pid=an_123",
                )
            ],
            test_settings,
            now=now,
        )
        await publish_public_catalog(test_settings, now=now, session=session)
        await session.commit()
        deal = (await session.execute(select(PublishedDeal))).scalars().one()
        slug = deal.slug

    live = await client.get(f"/go/{slug}", follow_redirects=False)
    assert live.status_code == 302
    assert "shopee.com.br" in live.headers["location"]

    async with factory() as session:
        deal = (await session.execute(select(PublishedDeal))).scalars().one()
        deal.status = "expired"
        deal.expired_at = now
        await session.commit()

    gone = await client.get(f"/go/{slug}", follow_redirects=False)
    assert gone.status_code == 410
    assert "Oferta encerrada" in gone.text

    missing = await client.get("/api/public/v1/deals/" + slug)
    assert missing.status_code == 404


async def test_ops_token_protects_v1_not_public(tmp_path, monkeypatch):
    db = tmp_path / "ops-auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    monkeypatch.setenv("ENABLE_CHANNEL_INBOX", "false")
    monkeypatch.setenv("OPS_API_TOKEN", "ops-secret")
    get_settings.cache_clear()
    reset_engine()
    await init_db()
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        blocked = await ac.get("/api/v1/opportunities")
        assert blocked.status_code == 401
        allowed = await ac.get(
            "/api/v1/opportunities",
            headers={"Authorization": "Bearer ops-secret"},
        )
        assert allowed.status_code == 200
        public = await ac.get("/api/public/v1/deals")
        assert public.status_code == 200
        health = await ac.get("/health")
        assert health.status_code == 200
    get_settings.cache_clear()
    reset_engine()


def test_list_price_reconstructed_from_store_discount():
    from app.models.entities import Opportunity
    from app.storefront.catalog import list_price_of

    store = Opportunity(current_price=Decimal("60.00"), announced_discount_pct=Decimal("40"), classification="ANNOUNCED")
    assert list_price_of(store) == Decimal("100.00")
    extreme = Opportunity(current_price=Decimal("5.00"), announced_discount_pct=Decimal("95"), classification="ANNOUNCED")
    assert list_price_of(extreme) is None
    historical = Opportunity(current_price=Decimal("80.00"), historical_discount_pct=Decimal("20"), historical_median=Decimal("100.00"), classification="HISTORICALLY_VALIDATED")
    assert list_price_of(historical) == Decimal("100.00")


def test_price_range_never_invents_list_price():
    from app.models.entities import Opportunity
    from app.publishing.telegram import format_deal, format_message
    from app.storefront.catalog import list_price_of

    # Monitor 24"/27": R$ 672 é o de 24", R$ 973 o de 27"; os 53% valem para alguma opção.
    ranged = Opportunity(current_price=Decimal("672"), price_max=Decimal("973"), announced_discount_pct=Decimal("53"),
                         classification="ANNOUNCED", product_name="Monitor Curvo 24/27", merchant="shopee")
    assert list_price_of(ranged) is None
    text = format_message(ranged, Settings())
    assert "A PARTIR DE R$ 672" in text and "até R$ 973" in text and "De:" not in text
    plain = format_deal(title="Mouse", price=Decimal("80"), url="https://x")
    assert "POR R$ 80" in plain and "A PARTIR" not in plain


def test_category_from_product_noun_not_accessory_words():
    from app.storefront.taxonomy import category_of

    assert category_of("Controle Sem Fio Joystick Bluetooth Compatível com celular", "Games") == "games"
    assert category_of("Mochila para Notebook 15.6 Executiva", "hub") == "moda"
    assert category_of("Cadeira Gamer Lancer Preta", "hub") == "informatica"
    assert category_of("Lanterna Militar Tática Led", "hub", "moda") == "casa"
    assert category_of("Kit Organizador Sem Palavra Conhecida", "Calçados, Roupas e Bolsas", "moda") == "casa"
    assert category_of("Produto Genérico XPTO", "Calçados, Roupas e Bolsas", None) == "moda"
    assert category_of("Produto Genérico XPTO", "hub", "pets") == "pets"
