import csv
import gzip
import io
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.sources.awin_feed import KabumFeedSource, normalize_row
from app.sources.registry import build_connectors
from app.publishing.telegram import compact_affiliate_url

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def config(tmp_path, **overrides):
    return Settings(_env_file=None, **{
        "pricedev_data_dir": str(tmp_path), "enable_kabum": True,
        "enable_awin": True, "awin_publisher_id": "123",
        "awin_kabum_advertiser_id": "17729", "awin_api_token": "",
        "awin_kabum_feed_url": "https://productdata.awin.com/datafeed/download/apikey/test/fid/46967/",
        "awin_kabum_feed_batch": 1, **overrides,
    })


def row(native="283718", **overrides):
    return {
        "merchant_product_id": native, "product_name": "Processador Intel",
        "merchant_id": "17729", "currency": "BRL", "search_price": "799.90",
        "merchant_deep_link": f"https://www.kabum.com.br/produto/{native}/intel?tracking=foreign",
        "aw_deep_link": "https://www.awin1.com/pclick.php?" + urlencode({"p": native, "a": "123", "m": "17729"}),
        "in_stock": "1", "product_price_old": "999.90", **overrides,
    }


def archive(rows):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return gzip.compress(text.getvalue().encode("utf-8-sig"))


def test_feed_price_is_not_live_verification_and_link_is_preserved(tmp_path):
    settings = config(tmp_path)
    offer = normalize_row(row(), settings, NOW)
    assert offer.native_product_id == "283718"
    assert offer.effective_price == Decimal("799.90")
    assert offer.price_verified is False and offer.verified_price is None
    assert offer.purchase_url == "https://www.kabum.com.br/produto/283718"
    assert compact_affiliate_url(offer.affiliate_url, settings) == row()["aw_deep_link"]
    assert compact_affiliate_url(row()["aw_deep_link"].replace("a=123", "a=999"), settings) is None


def test_rejects_other_stores_invalid_prices_and_product_mismatch(tmp_path):
    settings = config(tmp_path)
    for overrides in [
        {"merchant_id": "999"}, {"currency": "USD"}, {"search_price": "0"},
        {"search_price": "NaN"}, {"merchant_product_id": "999"},
        {"merchant_deep_link": "https://evilkabum.com.br/produto/283718"},
    ]:
        assert normalize_row(row(**overrides), settings, NOW) is None
    unavailable = normalize_row(row(in_stock="0"), settings, NOW)
    assert unavailable.availability == "unavailable"
    foreign = normalize_row(row(aw_deep_link=row()["aw_deep_link"].replace("a=123", "a=999")), settings, NOW)
    assert foreign.affiliate_url is None


async def test_resume_only_after_ingestion_and_no_repeat_download(tmp_path):
    settings = config(tmp_path)
    downloads = []

    def handler(request):
        if "/list/" in request.url.path:
            return httpx.Response(200, text="Feed ID,Last Imported\n46967,2026-10-23 10:21:08\n")
        downloads.append(request)
        return httpx.Response(200, content=archive([row(), row("999999")]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = KabumFeedSource(settings, client=client)
        first = await source.poll(now=NOW)
        assert first[0].native_product_id == "283718"
        # Sem confirmação do lote, o cursor não foi persistido.
        assert not source._paths()[1].exists()
        await source.on_ingested()
        resumed = KabumFeedSource(settings, client=client)
        second = await resumed.poll(now=NOW)
        assert second[0].native_product_id == "999999"
        await resumed.on_ingested()
        assert await resumed.poll(now=NOW) == []
        await resumed.on_ingested()
        assert await resumed.poll(now=NOW) == []
    assert len(downloads) == 1


def test_retired_catalog_sources_are_not_registered(tmp_path):
    settings = config(tmp_path)
    settings.enable_pelando = True
    assert not {"kabum", "pelando"} & {c.name for c in build_connectors(settings)}
    settings.awin_kabum_feed_url = ""
    assert not {"kabum", "pelando"} & {c.name for c in build_connectors(settings)}
