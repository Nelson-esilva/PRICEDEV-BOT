from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import Settings
from app.core.db import utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url, sanitize_purchase_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceAuthError, SourceConnector, SourceError

log = get_logger("shopee")

GRAPHQL_URL = "https://open-api.affiliate.shopee.com.br/graphql"

# Docs oficiais 2026-10-01 (affiliateshopee.com.br/documentacao):
# productOfferV2.sortType: 1 relevância, 2 vendidos, 3 maior preço, 4 menor preço, 5 comissão.
# NÃO existe "mais recentes" em productOfferV2.
# shopeeOfferV2.sortType: 1 mais recentes, 2 maior comissão.
PRODUCT_OFFER_QUERY = """
query ProductOffers($keyword: String, $page: Int, $limit: Int) {
  productOfferV2(keyword: $keyword, page: $page, limit: $limit, listType: 0, sortType: 2) {
    nodes {
      itemId
      productName
      productLink
      offerLink
      imageUrl
      priceMin
      priceMax
      priceDiscountRate
      shopId
      shopName
      shopType
      commissionRate
    }
    pageInfo { page limit hasNextPage }
  }
}
"""

CAMPAIGN_QUERY = """
query RecentCampaigns($page: Int, $limit: Int) {
  shopeeOfferV2(sortType: 1, page: $page, limit: $limit) {
    nodes {
      offerName
      offerLink
      originalLink
      imageUrl
      offerType
      categoryId
      collectionId
      periodStartTime
      periodEndTime
      commissionRate
    }
    pageInfo { page limit hasNextPage }
  }
}
"""

SHORT_LINK_MUTATION = """
mutation ShortLink($originUrl: String!, $subIds: [String!]) {
  generateShortLink(input: { originUrl: $originUrl, subIds: $subIds }) {
    shortLink
  }
}
"""


def sign_payload(app_id: str, secret: str, payload: str, timestamp: str) -> str:
    """SHA256(AppId + Timestamp + Payload + Secret) — docs oficiais BR, não HMAC."""
    raw = f"{app_id}{timestamp}{payload}{secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compact_json(body: dict[str, Any]) -> str:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


class ShopeeSource(SourceConnector):
    name = "shopee"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(settings)
        self.poll_seconds = settings.shopee_poll_seconds
        self._client = client
        self._owns_client = client is None

    def is_enabled(self) -> bool:
        return bool(
            self.settings.enable_shopee
            and self.settings.shopee_app_id
            and self.settings.shopee_app_secret
        )

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        fetched_at = now or utcnow()
        offers: list[NormalizedOffer] = []
        for keyword in self.settings.shopee_keyword_list[:5]:
            payload = await self.product_offers(keyword=keyword, page=1, limit=20)
            offers.extend(self.normalize_products(payload, fetched_at=fetched_at, keyword=keyword))
        try:
            await self.campaigns(page=1, limit=10)
        except SourceError as exc:
            log.warning("shopee_campaigns_unavailable", error=str(exc))
        return offers

    async def product_offers(self, *, keyword: str, page: int, limit: int) -> dict[str, Any]:
        body = {
            "query": PRODUCT_OFFER_QUERY,
            "operationName": "ProductOffers",
            "variables": {"keyword": keyword, "page": page, "limit": limit},
        }
        return await self._graphql(body)

    async def campaigns(self, *, page: int, limit: int) -> dict[str, Any]:
        body = {
            "query": CAMPAIGN_QUERY,
            "operationName": "RecentCampaigns",
            "variables": {"page": page, "limit": limit},
        }
        return await self._graphql(body)

    async def generate_short_link(self, origin_url: str) -> str | None:
        body = {
            "query": SHORT_LINK_MUTATION,
            "operationName": "ShortLink",
            "variables": {"originUrl": origin_url, "subIds": ["pricedev"]},
        }
        payload = await self._graphql(body)
        data = (payload.get("data") or {}).get("generateShortLink") or {}
        link = data.get("shortLink")
        return sanitize_purchase_url(link) if isinstance(link, str) else None

    async def _graphql(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = compact_json(body)
        timestamp = str(int(utcnow().timestamp()))
        signature = sign_payload(
            self.settings.shopee_app_id,
            self.settings.shopee_app_secret,
            payload,
            timestamp,
        )
        headers = {
            "Content-Type": "application/json",
            "Authorization": (
                f"SHA256 Credential={self.settings.shopee_app_id}, "
                f"Timestamp={timestamp}, Signature={signature}"
            ),
        }
        resp = await self._http().post(GRAPHQL_URL, content=payload.encode("utf-8"), headers=headers)
        if resp.status_code == 429:
            raise SourceError("Shopee HTTP 429", retryable=True)
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError(f"JSON inválido Shopee HTTP {resp.status_code}") from exc
        errors = data.get("errors") or []
        if errors:
            code = (errors[0].get("extensions") or {}).get("code")
            message = errors[0].get("message") or str(errors)
            if code in {10020, 10035}:
                raise SourceAuthError(f"Shopee auth/access: {message}")
            if code == 10030:
                raise SourceError("Shopee rate limit 10030", retryable=True)
            raise SourceError(f"Shopee GraphQL: {message}", retryable=code in {10000})
        return data

    def normalize_products(
        self, payload: dict[str, Any], *, fetched_at: datetime, keyword: str
    ) -> list[NormalizedOffer]:
        nodes = (((payload.get("data") or {}).get("productOfferV2") or {}).get("nodes")) or []
        offers: list[NormalizedOffer] = []
        for node in nodes:
            try:
                offer = self._product_node(node, fetched_at, keyword)
            except Exception as exc:
                log.warning("shopee_product_skip", error=str(exc))
                continue
            if offer:
                offers.append(offer)
        return offers

    def _product_node(self, node: dict[str, Any], fetched_at: datetime, keyword: str) -> NormalizedOffer | None:
        item_id = node.get("itemId")
        if item_id is None:
            return None
        native = str(item_id)
        price = money(node.get("priceMin") or node.get("price") or node.get("priceMax"))
        if price is None:
            return None
        offer_link = sanitize_purchase_url(node.get("offerLink"))
        product_link = sanitize_purchase_url(node.get("productLink"))
        announced = node.get("priceDiscountRate")
        announced_pct = money(announced) if announced is not None else None
        shop_id = str(node.get("shopId") or "")
        if self.settings.shopee_official_shops_only:
            shop_type = node.get("shopType")
            types = shop_type if isinstance(shop_type, list) else [shop_type]
            official = {1, "1", "mall", "official"}
            if not any(item in official for item in types):
                return None
        return NormalizedOffer(
            source=self.name,
            source_record_id=native,
            marketplace="shopee",
            merchant_id=shop_id,
            merchant_name=node.get("shopName"),
            native_product_id=native,
            offer_id=native,
            product_name=str(node.get("productName") or "Produto Shopee"),
            category=keyword,
            listed_price=price,
            verified_price=price,
            effective_price=price,
            currency="BRL",
            availability="in_stock",
            source_created_at=None,
            source_updated_at=None,
            fetched_at=fetched_at,
            purchase_url=product_link or offer_link,
            affiliate_url=offer_link,
            image_url=sanitize_media_url(node.get("imageUrl")),
            announced_discount_pct=announced_pct,
            identity_confidence=IdentityConfidence.HIGH,
            price_verified=True,
            raw_payload={"itemId": native, "keyword": keyword},
        ).quantized()

    def normalize_campaigns(self, payload: dict[str, Any], *, fetched_at: datetime) -> list[NormalizedOffer]:
        nodes = (((payload.get("data") or {}).get("shopeeOfferV2") or {}).get("nodes")) or []
        offers: list[NormalizedOffer] = []
        for node in nodes:
            name = node.get("offerName")
            link = sanitize_purchase_url(node.get("offerLink") or node.get("originalLink"))
            if not name or not link:
                continue
            collection = str(node.get("collectionId") or node.get("offerName"))
            start = node.get("periodStartTime")
            created = datetime.fromtimestamp(start) if isinstance(start, int) else None
            offers.append(
                NormalizedOffer(
                    source=self.name,
                    source_record_id=f"campaign-{collection}",
                    marketplace="shopee",
                    merchant_id="shopee",
                    merchant_name="Shopee",
                    native_product_id=f"campaign-{collection}",
                    product_name=str(name),
                    listed_price=money("0") or Decimal("0"),
                    verified_price=None,
                    effective_price=money("0") or Decimal("0"),
                    currency="BRL",
                    availability="unknown",
                    source_created_at=created,
                    fetched_at=fetched_at,
                      purchase_url=link,
                      affiliate_url=sanitize_purchase_url(node.get("offerLink")),
                      image_url=sanitize_media_url(node.get("imageUrl")),
                    identity_confidence=IdentityConfidence.LOW,
                    price_verified=False,
                    raw_payload={"campaign": True, "collectionId": collection},
                )
            )
        return offers
