from __future__ import annotations

import json

import httpx

from app.affiliates.resolver import stamp_mercadolivre_page
from app.core.config import Settings
from app.storefront.promotions import (
    _attach_official_images,
    ml_banner_title,
    ml_home_banners,
    owned_campaign_link,
)


def _home(elements: list[dict]) -> str:
    state = {"pageProps": {"atf": {"components": [{"type": "exhibitor", "elements": elements}]}}}
    return f'<script>window.__x = {{"appProps":{json.dumps(state, separators=(",", ":"))}}}</script>'


def _slide(source: str, campaign: int, title: str) -> dict:
    return {
        "type": "image", "source": source, "title": title,
        "picture": {"src": f"https://http2.mlstatic.com/D_NQ_2X_{campaign}-OO.webp"},
        "actions": {"content_link": {"link": f"https://click1.mercadolivre.com.br/display/clicks/MLB/count?a={campaign}"}},
        "track": {"merch_data": {"campaign_id": campaign}},
    }


def test_ml_home_banners_keep_only_merch_campaigns():
    html = _home([
        _slide("SAM", 1, "Anúncio pago"),
        _slide("MERCH", 369010, "11.11. Supermercado. 60% OFF. Consulte termos e condições"),
    ])
    [banner] = ml_home_banners(html)
    assert banner["campaign_id"] == "369010"
    assert banner["title"] == "11.11 · Supermercado · 60% OFF"
    assert banner["image"].endswith("369010-OO.webp")
    assert ml_home_banners("<html></html>") == []


def test_ml_banner_title_drops_legal_text():
    assert ml_banner_title("Sua casa mais completa. Até 60% OFF. Consulte termos e condições.") == \
        "Sua casa mais completa · Até 60% OFF"


def test_ml_campaign_link_is_stamped_and_owned():
    settings = Settings(ml_affiliate_matt_word="promodev", ml_affiliate_matt_tool="123")
    url = stamp_mercadolivre_page("https://lista.mercadolivre.com.br/_Container_LPSM?x=1#origin=ads", settings)
    assert url and "#" not in url and "matt_word=promodev" in url and "matt_tool=123" in url
    assert owned_campaign_link(url, "mercadolivre", settings)
    assert not owned_campaign_link("https://lista.mercadolivre.com.br/_Container_LPSM", "mercadolivre", settings)
    assert stamp_mercadolivre_page("https://evil.example/ml", settings) is None
    assert stamp_mercadolivre_page(url, Settings(ml_affiliate_matt_word="", ml_affiliate_matt_tool="")) is None


async def test_kabum_promotion_gets_official_image(db):
    pages = {"https://www.kabum.com.br/produto/1": '<meta property="og:image" content="https://images.kabum.com.br/p1.jpg"/>'}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pages.get(str(request.url), ""))

    rows = [
        dict(external_id="a", image_url=None, _landing="https://www.kabum.com.br/produto/1"),
        dict(external_id="b", image_url=None, _landing="https://evil.example/produto/2"),
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await _attach_official_images("awin", rows, client)
    assert rows[0]["image_url"] == "https://images.kabum.com.br/p1.jpg"
    assert rows[1]["image_url"] is None
    assert all("_landing" not in row for row in rows)
