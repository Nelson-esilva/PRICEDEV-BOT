from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings
from app.core.urls import sanitize_purchase_url
from app.sources.base import SourceBlocked
from app.sources.pelando import PelandoSource

FIXTURE = {
    "data": {
        "deals": [
            {
                "id": "deal-1",
                "title": "SSD NVMe 1TB",
                "kind": "promotion",
                "status": "active",
                "temperature": 412,
                "price": 299.9,
                "discountPercentage": 40,
                "createdAt": "2026-10-01T12:00:00Z",
                "firstApprovedAt": "2026-10-01T12:01:00Z",
                "sourceUrl": "https://www.kabum.com.br/produto/123",
                "imageUrl": "https://media.pelando.com.br/aaa=/0x100/filters:format(webp)/s/ssd.png",
                "imageSrcset": [
                    {"url": "https://media.pelando.com.br/aaa=/0x100/filters:format(webp)/s/ssd.png", "width": 100},
                    {"url": "https://media.pelando.com.br/bbb=/0x300/filters:format(webp)/s/ssd.png", "width": 300},
                ],
                "shortDescription": "SSD em promoção",
                "couponCode": "SSD10",
                "freeShipping": True,
                "commentCount": 12,
                "redirectUrl": "https://dpl.pelando.com.br/jwt-should-be-ignored",
                "store": {"id": "s1", "name": "KaBuM!", "slug": "kabum"},
            },
            {
                "id": "deal-exp",
                "title": "Expirada",
                "kind": "promotion",
                "status": "expired",
                "temperature": 10,
                "price": 10,
                "sourceUrl": "https://www.kabum.com.br/produto/9",
                "store": {"id": "s1", "name": "KaBuM!", "slug": "kabum"},
            },
            {
                "id": "deal-ml",
                "title": "Ventilador Torre Spirit Maxximos 35W",
                "kind": "promotion",
                "status": "active",
                "price": 209.9,
                "sourceUrl": "https://www.mercadolivre.com.br/ventilador-torre-spirit/p/MLB12345678",
                "store": {"id": "921", "name": "Mercado Livre", "slug": "mercado-livre"},
            },
            {
                "id": "talk",
                "title": "Discussão",
                "kind": "discussion",
                "price": None,
            },
        ]
    }
}


def test_normalize_fixtures_never_uses_redirect_and_never_verifies_price():
    settings = Settings(enable_pelando=False)
    source = PelandoSource(settings)
    offers = source.normalize_payload(FIXTURE, fetched_at=datetime(2026, 10, 1, tzinfo=UTC))
    assert len(offers) == 3
    first = offers[0]
    assert first.price_verified is False
    assert first.verified_price is None
    assert first.reported_price is not None
    assert first.purchase_url == "https://www.kabum.com.br/produto/123"
    assert first.temperature == 412
    assert first.image_url == "https://media.pelando.com.br/bbb=/0x300/filters:format(webp)/s/ssd.png"
    assert first.coupon_code == "SSD10"
    assert first.payment_hint is None
    assert first.free_shipping is True
    assert first.description == "SSD em promoção"
    assert sanitize_purchase_url("https://dpl.pelando.com.br/abc") is None
    expired = offers[1]
    assert expired.availability == "unavailable"
    ml = offers[2]
    assert ml.marketplace == "mercadolivre"
    assert ml.merchant_name == "Mercado Livre"
    assert ml.purchase_url and "mercadolivre.com.br" in ml.purchase_url
    assert ml.effective_price is not None


def test_howto_from_deal_html_and_coupon():
    from app.sources.pelando import _merge_deal_detail, _payment_hint, _plain_text

    html = "<p>R$ 275 no Pix</p><p>Use o Cupom: MODAML + Selecione Pix</p>"
    assert _plain_text(html) == "R$ 275 no Pix Use o Cupom: MODAML + Selecione Pix"
    assert _payment_hint(_plain_text(html)) == "Pix"
    source = PelandoSource(Settings(enable_pelando=False))
    offers = source.normalize_payload(
        {
            "data": {
                "deals": [
                    {
                        "id": "nike-1",
                        "title": "Tênis Nike SB Force 58",
                        "kind": "promotion",
                        "status": "active",
                        "price": 275,
                        "sourceUrl": "https://www.mercadolivre.com.br/social/abc?forceInApp=true",
                        "store": {"id": "921", "name": "Mercado Livre", "slug": "mercado-livre"},
                    }
                ]
            }
        },
        fetched_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert offers[0].coupon_code is None
    merged = _merge_deal_detail(
        offers[0],
        {
            "couponCode": "MODAML",
            "shortDescription": html,
            "sourceUrl": "https://produto.mercadolivre.com.br/MLB-5388126802-tenis-_JM",
        },
    )
    assert merged.coupon_code == "MODAML"
    assert merged.payment_hint == "Pix"
    assert merged.purchase_url and "MLB-5388126802" in merged.purchase_url


async def test_enrich_details_fills_coupon_from_deal_endpoint():
    feed = {
        "data": {
            "deals": [
                {
                    "id": "nike-1",
                    "title": "Tênis Nike SB Force 58",
                    "kind": "promotion",
                    "status": "active",
                    "price": 275,
                    "createdAt": "2026-10-01T12:00:00Z",
                    "sourceUrl": "https://www.mercadolivre.com.br/social/abc?forceInApp=true",
                    "store": {"id": "921", "name": "Mercado Livre", "slug": "mercado-livre"},
                }
            ],
            "pageInfo": {"hasNextPage": False},
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("robots.txt"):
            return httpx.Response(404, text="missing")
        if path.endswith("/deals/nike-1"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "couponCode": "MODAML",
                        "shortDescription": "<p>R$ 275 no Pix</p><p>Use o Cupom: MODAML</p>",
                        "sourceUrl": "https://www.mercadolivre.com.br/tenis/p/MLB5388126802",
                    }
                },
            )
        if "/feed/v2/" in path:
            return httpx.Response(200, json=feed)
        if path.endswith("/stores/search"):
            return httpx.Response(200, json={"data": {"stores": []}})
        return httpx.Response(200, json={"data": {"deals": [], "pageInfo": {}}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = PelandoSource(
        Settings(enable_pelando=True, pelando_feed_pages=1, pelando_deal_details_per_poll=5),
        client=client,
    )
    offers = await source.poll()
    nike = next(item for item in offers if item.source_record_id == "nike-1")
    assert nike.coupon_code == "MODAML"
    assert nike.payment_hint == "Pix"


def test_disabled_pelando_does_not_poll():
    settings = Settings(enable_pelando=False)
    source = PelandoSource(settings)
    assert source.is_enabled() is False


async def test_challenge_opens_blocked_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("robots.txt"):
            return httpx.Response(404, text="missing")
        return httpx.Response(403, text="Sorry, you have been blocked")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    settings = Settings(enable_pelando=True, pelando_base_url="https://api-web.pelando.com.br")
    source = PelandoSource(settings, client=client)
    with pytest.raises(SourceBlocked):
        await source.fetch_recents()


async def test_http_429(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("robots.txt"):
            return httpx.Response(404)
        return httpx.Response(429, text="slow down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = PelandoSource(Settings(enable_pelando=True), client=client)
    from app.sources.base import SourceError

    with pytest.raises(SourceError) as exc:
        await source.fetch_recents()
    assert exc.value.retryable is True
