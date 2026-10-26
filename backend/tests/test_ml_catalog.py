from __future__ import annotations

from app.storefront import trends
from app.storefront.ml_enrich import details
from app.storefront.trends import load_trends, save_trends, trend_of
from app.sources import mlofficial


def test_trends_saved_filtered_and_matched(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "TRENDS_FILE", tmp_path / "trends.json")
    saved = save_trends(["Cadeira Gamer", "ps5", "h t v", "cadeira gamer", "air fryer"])
    assert saved == ["cadeira gamer", "ps5", "air fryer"]
    assert load_trends() == saved
    assert trend_of("Cadeira Gamer Ergonômica Reclinável", saved) == "cadeira gamer"
    assert trend_of("Console PlayStation 5 PS5 Slim", saved) == "ps5"
    assert trend_of("Fritadeira Elétrica Air-Fryer 4L", saved) == "air fryer"
    assert trend_of("Cadeira de escritório", saved) is None


class FakeApi:
    def __init__(self, routes):
        self.routes = routes

    async def get(self, path):
        return self.routes.get(path.split("?")[0])


async def test_enrich_details_reads_official_catalog(monkeypatch):
    monkeypatch.setattr(mlofficial, "_PATHS", {})
    api = FakeApi({
        "/products/MLB10": {"pictures": [{"url": "https://http2.mlstatic.com/a.jpg"}, {"url": "https://http2.mlstatic.com/b.jpg"}]},
        "/products/MLB10/items": {"results": [
            {"item_id": "MLB2", "category_id": "MLB99245", "shipping": {"free_shipping": False}},
            {"item_id": "MLB1", "category_id": "MLB99245", "shipping": {"free_shipping": True}},
        ]},
        "/categories/MLB99245": {"path_from_root": [{"id": "MLB1648", "name": "Informática"}, {"id": "MLB99245", "name": "Monitores"}]},
        "/highlights/MLB/product/MLB10": {"dimension": "category", "id": "MLB99245", "label": "Monitores", "position": 2},
    })
    out = await details(api, "MLB10", "MLB1")
    assert out["gallery"] == ["https://http2.mlstatic.com/a.jpg", "https://http2.mlstatic.com/b.jpg"]
    assert out["free_shipping"] is True and out["official_category"] == "informatica"
    assert (out["rank_position"], out["rank_category"], out["rank_category_id"]) == (2, "Monitores", "MLB99245")
    gone = await details(FakeApi({}), "MLB10", "MLB1")
    assert gone == {"rank_position": None, "rank_category": None, "rank_category_id": None}


def test_snapshot_uses_official_category_rank_and_trend():
    from datetime import timedelta
    from decimal import Decimal

    from app.core.db import utcnow
    from app.models.entities import Opportunity, PublishedDeal
    from app.storefront.catalog import _apply_snapshot

    opp = Opportunity(
        id="o1", product_id="p1", source="mlhub", product_name="Monitor Gamer LG 27 IPS", merchant="Mercado Livre",
        category="Destaques", current_price=Decimal("899"), announced_discount_pct=Decimal("20"), currency="BRL",
        acceptance_score=60, official_category="informatica", gallery=["https://http2.mlstatic.com/a.jpg"],
        rank_position=4, rank_category="Monitores", rank_category_id="MLB99245", affiliate_url="https://x",
    )
    plain = PublishedDeal(opportunity_id="o1", slug="s", destination_url="https://x")
    _apply_snapshot(plain, opp, now=utcnow(), ttl=timedelta(hours=6))
    hot = PublishedDeal(opportunity_id="o1", slug="s", destination_url="https://x")
    _apply_snapshot(hot, opp, now=utcnow(), ttl=timedelta(hours=6), trends=["monitor gamer"])
    assert plain.category == "informatica" and plain.gallery == ["https://http2.mlstatic.com/a.jpg"]
    assert (plain.rank_position, plain.rank_category, plain.rank_category_id) == (4, "Monitores", "MLB99245")
    assert not plain.trending and hot.trending
    assert hot.demand_score > plain.demand_score


async def test_enrich_matches_listing_by_price_when_hub_points_to_catalog(monkeypatch):
    from decimal import Decimal

    monkeypatch.setattr(mlofficial, "_PATHS", {"MLB1": [{"id": "MLB1574", "name": "Casa"}]})
    rows = {"results": [
        {"item_id": "MLB7", "price": 49.9, "category_id": "MLB1", "shipping": {"free_shipping": False}},
        {"item_id": "MLB8", "price": 39.9, "category_id": "MLB1", "shipping": {"free_shipping": True}},
    ]}
    api = FakeApi({"/products/MLB5/items": rows})
    out = await details(api, "MLB5", "MLB5", [Decimal("39.90")])
    assert out["free_shipping"] is True and out["official_category"] == "casa"
    unknown = await details(api, "MLB5", "MLB5", [Decimal("10.00")])
    assert unknown["free_shipping"] is False


async def test_ranking_label_and_brand_rankings(monkeypatch):
    from app.sources.mlofficial import ranking_label

    monkeypatch.setattr(mlofficial, "_PATHS", {})
    api = FakeApi({
        "/categories/MLB1": {"path_from_root": [{"id": "MLB5726", "name": "Eletrodomésticos"}, {"id": "MLB9", "name": "Fritadeiras"}, {"id": "MLB1", "name": "De Ar"}]},
        "/categories/MLB2": {"path_from_root": [{"id": "MLB5726", "name": "Eletrodomésticos"}, {"id": "MLB8", "name": "Fogões"}, {"id": "MLB2", "name": "Elétricos"}]},
        "/categories/MLB3": {"path_from_root": [{"id": "MLB1648", "name": "Informática"}, {"id": "MLB3", "name": "Monitores"}]},
        "/highlights/MLB/product/MLB5": {"dimension": "category_brand", "id": "MLB3", "label": "Monitores LG", "position": 1},
    })
    assert await ranking_label(api, "MLB1") == "Fritadeiras de Ar"
    assert await ranking_label(api, "MLB2") == "Fogões elétricos"
    assert await ranking_label(api, "MLB3") == "Monitores"
    brand = await details(api, "MLB5", "MLB5")
    assert brand["rank_position"] is None


async def test_mlapi_retries_429_then_gives_up(monkeypatch):
    import httpx

    from app.core.config import Settings
    from app.sources import mlapi

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"ok": True})

    async def no_sleep(_):
        return None

    async def fake_token(self):
        return "t"

    monkeypatch.setattr(mlapi.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(mlapi.MlApi, "token", fake_token)
    monkeypatch.setattr(mlapi, "_bucket", mlapi.TokenBucket(1000))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        api = mlapi.MlApi(Settings(), client=client)
        assert await api.get("/x") == {"ok": True} and calls["n"] == 3
        calls["n"] = -10
        try:
            await api.get("/y")
            raise AssertionError("deveria desistir")
        except mlapi.RateLimited:
            pass


def test_trend_match_needs_phrase_and_skips_accessories():
    terms = ["notebook", "controle bluetooth", "cadeira gamer"]
    assert trend_of("Notebook Lenovo IdeaPad 15", terms) == "notebook"
    assert trend_of("Mochila para Notebook 15.6 Executiva", terms) is None
    assert trend_of("Caixa de Som Bluetooth com controle remoto", terms) is None
    assert trend_of("Controle Bluetooth para PS4", terms) == "controle bluetooth"
    assert trend_of("Cadeira Gamer Husky Tempest", terms) == "cadeira gamer"


def test_single_word_trend_must_name_the_product():
    assert trend_of("Notebook Gamer 15,6 Intel", ["notebook"]) == "notebook"
    assert trend_of("Case Gaveta HD SSD 2.5 USB 3.0 Externo notebook", ["notebook"]) is None
