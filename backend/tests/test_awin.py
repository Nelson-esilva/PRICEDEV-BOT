from urllib.parse import urlencode

import httpx
import pytest

from app.affiliates.awin import ensure_owned_kabum, is_owned_kabum, kabum_destination
from app.affiliates.resolver import resolve_links
from app.core.config import Settings
from app.publishing.telegram import compact_affiliate_url, ensure_publish_url, should_publish, short_store_slug, store_label
from app.ingestion.identity import parse_product_url
from types import SimpleNamespace

DESTINATION = "https://www.kabum.com.br/produto/531155"


def settings(**overrides):
    return Settings(_env_file=None, **{
        "enable_awin": True, "awin_publisher_id": "123",
        "awin_kabum_advertiser_id": "456", "awin_api_token": "test-token",
        **overrides,
    })


def tracking(publisher="123", destination=DESTINATION):
    return "https://www.awin1.com/cread.php?" + urlencode({
        "awinaffid": publisher, "awinmid": "456", "ued": destination,
    })


@pytest.mark.parametrize("url", [
    "https://evilkabum.com.br/produto/531155", "https://kabum.com.br.evil.test/produto/531155",
    "https://www.kabum.com.br/busca/ssd", "http://www.kabum.com.br/produto/531155",
])
def test_rejects_non_product_and_impostor_hosts(url):
    assert kabum_destination(url) is None


def test_preserves_only_owned_awin_tracking_for_publish():
    config = settings()
    assert compact_affiliate_url(tracking(), config) == tracking()
    assert compact_affiliate_url(tracking("999"), config) is None
    assert compact_affiliate_url(DESTINATION, config) is None
    assert not is_owned_kabum(tracking(), settings(enable_awin=False))
    assert parse_product_url(tracking()) == ("kabum", "531155")
    assert short_store_slug(tracking()) == "kabum/531155"
    assert store_label("afiliado", tracking()) == "KaBuM!"


async def test_converts_foreign_tracking_with_official_api():
    calls = []

    def handler(request):
        import json

        calls.append(request)
        assert str(request.url) == "https://api.awin.com/publishers/123/linkbuilder/generate"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert json.loads(request.content) == {
            "advertiserId": 456, "destinationUrl": DESTINATION, "shorten": False,
        }
        return httpx.Response(200, json={"url": tracking()})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await resolve_links(
            original_url=tracking("999"), existing_affiliate=None, settings=settings(), http=client,
        )
        assert result.status == "converted"
        assert result.network == "awin"
        assert result.final == tracking()
        assert await ensure_publish_url(result.final, settings(), http=client) == tracking()
    assert len(calls) == 1


@pytest.mark.parametrize("status,payload", [
    (403, {}), (429, {}), (200, {"url": tracking("999")}),
    (200, {"url": tracking(destination="https://www.kabum.com.br/produto/999")}),
    (200, {"url": "https://evil.test/"}), (200, []),
])
async def test_conversion_failure_never_falls_back_to_foreign_or_direct_link(status, payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(status, json=payload)
    )) as client:
        result = await resolve_links(original_url=DESTINATION, existing_affiliate=tracking("999"),
                                     settings=settings(), http=client)
    assert result.status == "unpublishable"
    assert result.affiliate is None and result.final is None


async def test_missing_credentials_does_not_request_api():
    def unexpected(_):
        raise AssertionError("API should not be called")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        assert await ensure_owned_kabum(DESTINATION, settings(awin_api_token=""), http=client) is None


async def test_network_failure_blocks_conversion():
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        assert await ensure_owned_kabum(DESTINATION, settings(), http=client) is None


def test_direct_kabum_only_eligible_when_conversion_is_configured():
    opp = SimpleNamespace(status="active", classification="PROVISIONAL", final_purchase_url=DESTINATION)
    config = settings(enable_telegram_publish=True, telegram_bot_token="test", telegram_publish_chat="test")
    assert should_publish(opp, config) == (True, None)
    config.awin_api_token = ""
    assert should_publish(opp, config) == (False, "not_affiliate")
