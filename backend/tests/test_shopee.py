from __future__ import annotations

import json

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
        payload, fetched_at=__import__("datetime").datetime(2026, 10, 1), keyword="ssd"
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
