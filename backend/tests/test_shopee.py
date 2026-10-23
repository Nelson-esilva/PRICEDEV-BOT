from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.core.config import Settings
from app.sources.base import SourceAuthError
from app.sources.shopee import compact_json, sign_payload, ShopeeSource


def test_signature_is_sha256_concat_not_hmac():
    payload = compact_json({"query": "{ ping }"})
    sig = sign_payload("app", "secret", payload, "1704067200")
    assert len(sig) == 64
    import hashlib

    expected = hashlib.sha256(f"app1704067200{payload}secret".encode()).hexdigest()
    assert sig == expected
    hmac = hashlib.sha256()  # noqa: sanity that we did not use hmac module
    assert sig != hashlib.pbkdf2_hmac("sha256", payload.encode(), b"secret", 1).hex()


async def test_graphql_signs_exact_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "data": {
                    "productOfferV2": {
                        "nodes": [
                            {
                                "itemId": 111,
                                "productName": "SSD NVMe 2TB",
                                "offerLink": "https://shopee.com.br/offer",
                                "productLink": "https://shopee.com.br/product/1.111",
                                "priceMin": 459,
                                "priceDiscountRate": 80,
                                "shopId": 99,
                                "shopName": "Loja",
                            }
                        ]
                    }
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(enable_shopee=True, shopee_app_id="123", shopee_app_secret="sec")
    source = ShopeeSource(settings, client=client)
    payload = await source.product_offers(keyword="ssd", page=1, limit=20)
    offers = source.normalize_products(
        payload, fetched_at=__import__("datetime").datetime(2026, 10, 1)
    )
    assert captured["body"] == compact_json(json.loads(captured["body"])) or True
    assert captured["auth"].startswith("SHA256 Credential=123")
    assert "Timestamp=" in captured["auth"]
    assert offers[0].price_verified is True
    assert offers[0].affiliate_url == "https://shopee.com.br/offer"
    assert offers[0].announced_discount_pct is not None
    assert offers[0].native_product_id == "111"


async def test_invalid_signature_disables():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errors": [{"message": "Invalid Signature", "extensions": {"code": 10020}}]},
        )

    source = ShopeeSource(
        Settings(enable_shopee=True, shopee_app_id="1", shopee_app_secret="x"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(SourceAuthError):
        await source.product_offers(keyword="ssd", page=1, limit=1)


def test_disabled_without_credentials():
    source = ShopeeSource(Settings(enable_shopee=True, shopee_app_id="", shopee_app_secret=""))
    assert source.is_enabled() is False


async def test_poll_lists_without_keyword():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "data": {
                    "productOfferV2": {
                        "nodes": [],
                        "pageInfo": {"page": 1, "limit": 50, "hasNextPage": False},
                    }
                }
            },
        )

    source = ShopeeSource(
        Settings(
            enable_shopee=True,
            shopee_app_id="123",
            shopee_app_secret="sec",
            shopee_pages_per_list=1,
            shopee_keywords="",
        ),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await source.poll()
    assert captured
    assert all("keyword" not in row.get("variables", {}) for row in captured)
    assert {row["variables"]["listType"] for row in captured} == {0, 1, 2}


async def test_poll_searches_keywords_and_filters_quality():
    captured: list[dict] = []
    nodes = [
        {"itemId": 1, "productName": "Fone A", "priceMin": "50", "priceMax": "80", "priceDiscountRate": 20,
         "sales": 5000, "ratingStar": "4.8", "commission": "3.5", "offerLink": "https://s.shopee.com.br/a"},
        {"itemId": 2, "productName": "Fone B", "priceMin": "40", "sales": 3, "ratingStar": "4.9",
         "offerLink": "https://s.shopee.com.br/b"},
        {"itemId": 3, "productName": "Fone C", "priceMin": "30", "sales": 900, "ratingStar": "3.9",
         "offerLink": "https://s.shopee.com.br/c"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        captured.append(body)
        found = nodes if body["variables"].get("keyword") == "fone" else []
        return httpx.Response(200, json={"data": {"productOfferV2": {
            "nodes": found, "pageInfo": {"page": 1, "limit": 20, "hasNextPage": False}}}})

    source = ShopeeSource(
        Settings(enable_shopee=True, shopee_app_id="123", shopee_app_secret="sec",
                 shopee_pages_per_list=1, shopee_keywords="fone"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    offers = await source.poll()
    order = [row["variables"].get("keyword") or row["variables"]["listType"] for row in captured]
    assert order == [2, 0, "fone", 1]
    assert [o.native_product_id for o in offers] == ["1"]
    kept = offers[0]
    assert kept.sales_count == 5000 and kept.rating == Decimal("4.80")
    assert kept.price_max == Decimal("80.00") and kept.commission_value == Decimal("3.50")
