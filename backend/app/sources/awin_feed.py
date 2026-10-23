"""Catálogo KaBuM! Awin: download privado, cache gzip e ingestão em lotes."""

from __future__ import annotations

import asyncio
import csv
import gzip
import hashlib
import io
import json
import re
from datetime import datetime
from itertools import islice
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.affiliates.awin import is_owned_kabum, kabum_destination
from app.core.config import Settings, runtime_data_dir
from app.core.db import as_utc, utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.core.urls import sanitize_media_url
from app.schemas.normalized import IdentityConfidence, NormalizedOffer
from app.sources.base import SourceConnector, SourceError

log = get_logger("kabum_feed")
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
REQUIRED_COLUMNS = {"merchant_product_id", "product_name", "search_price", "merchant_deep_link"}


class KabumFeedSource(SourceConnector):
    # Mantém a identidade/filtros da coleta KaBuM! existente.
    name = "kabum"

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None):
        super().__init__(settings)
        self.poll_seconds = max(10, settings.awin_kabum_feed_poll_seconds)
        self._client = client
        self._owns_client = client is None
        self._pending: dict | None = None

    def is_enabled(self) -> bool:
        return bool(self.settings.enable_kabum and self.settings.awin_kabum_feed_url.strip())

    def _paths(self) -> tuple[Path, Path]:
        root = runtime_data_dir(self.settings) / "awin"
        root.mkdir(parents=True, exist_ok=True)
        return root / "kabum.csv.gz", root / "kabum-state.json"

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def poll(self, *, now: datetime | None = None) -> list[NormalizedOffer]:
        if not self.is_enabled():
            return []
        now = now or utcnow()
        url = self.settings.awin_kabum_feed_url.strip()
        parsed = urlparse(url)
        match = re.search(r"/apikey/([^/]+)/", parsed.path)
        feed = re.search(r"/fid/(\d+)(?:/|$)", parsed.path)
        if parsed.scheme != "https" or parsed.hostname != "productdata.awin.com" or not match or not feed:
            raise SourceError("Awin KaBuM!: URL de feed inválida", retryable=False)
        cache, state_path = self._paths()
        fingerprint = hashlib.sha256(url.encode()).hexdigest()
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict) or state.get("config") != fingerprint:
            state = {"config": fingerprint, "cursor": 0}
        self._pending = None
        checked = state.get("checked_at", 0)
        if not cache.exists() or now.timestamp() - checked >= max(60, self.settings.awin_kabum_feed_check_seconds):
            # O endpoint da lista é menor e informa quando o catálogo mudou.
            marker = await self._last_imported(match.group(1), feed.group(1))
            if not cache.exists() or not state.get("downloaded_at") or not marker or marker != state.get("last_imported"):
                digest = await self._download(url, cache)
                if digest != state.get("digest"):
                    state.update(cursor=0, finished=False, downloaded_at=now.isoformat(), digest=digest)
                state["last_imported"] = marker
            state["checked_at"] = now.timestamp()
        if state.get("finished"):
            self._pending = state
            return []
        downloaded = as_utc(datetime.fromisoformat(state["downloaded_at"]))
        offers, cursor, finished = await asyncio.to_thread(
            self._read_batch, cache, int(state.get("cursor", 0)), downloaded,
        )
        state.update(cursor=cursor, finished=finished)
        self._pending = state
        log.info("batch_ready", offers=len(offers), cursor=cursor, finished=finished)
        return offers

    async def _last_imported(self, key: str, feed_id: str) -> str | None:
        try:
            response = await self._http().get(f"https://productdata.awin.com/datafeed/list/apikey/{key}")
            if response.status_code != 200:
                return None
            for row in csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))):
                if row.get("Feed ID", "").strip() == feed_id:
                    return row.get("Last Imported", "").strip() or None
        except (httpx.HTTPError, csv.Error):
            pass
        # Sem metadados, tenta o download periódico e compara o conteúdo.
        return None

    async def _download(self, url: str, cache: Path) -> str:
        temporary = cache.with_suffix(".part")
        digest = hashlib.sha256()
        size = 0
        try:
            async with self._http().stream("GET", url) as response:
                if response.status_code != 200:
                    raise SourceError(f"Awin KaBuM!: download HTTP {response.status_code}")
                with temporary.open("wb") as target:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_DOWNLOAD_BYTES:
                            raise SourceError("Awin KaBuM!: catálogo excede 100 MiB")
                        digest.update(chunk)
                        target.write(chunk)
            await asyncio.to_thread(self._validate, temporary)
            temporary.replace(cache)
            return digest.hexdigest()
        except httpx.HTTPError:
            # A URL contém a chave; nunca propagar a exceção HTTP original.
            raise SourceError("Awin KaBuM!: falha de rede no download") from None
        except (OSError, EOFError, csv.Error, UnicodeError):
            raise SourceError("Awin KaBuM!: arquivo CSV/gzip inválido") from None
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate(path: Path) -> None:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
                raise SourceError("Awin KaBuM!: colunas obrigatórias ausentes")
            # Lê até o fim para verificar integridade gzip antes de substituir o cache.
            for _ in reader:
                pass

    def _read_batch(self, path: Path, cursor: int, downloaded: datetime) -> tuple[list[NormalizedOffer], int, bool]:
        offers = []
        consumed = 0
        batch_size = max(1, self.settings.awin_kabum_feed_batch)
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            for row in islice(reader, cursor, cursor + batch_size):
                consumed += 1
                offer = normalize_row(row, self.settings, downloaded)
                if offer:
                    offers.append(offer)
        return offers, cursor + consumed, consumed < batch_size

    async def on_ingested(self) -> None:
        if self._pending is None:
            return
        _, state_path = self._paths()
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._pending))
        temporary.replace(state_path)
        self._pending = None


def normalize_row(row: dict[str, str], settings: Settings, downloaded: datetime) -> NormalizedOffer | None:
    def field(key: str) -> str:
        return (row.get(key) or "").strip()

    destination = kabum_destination(field("merchant_deep_link"))
    name = field("product_name")
    price = money(field("search_price"))
    merchant = field("merchant_id")
    if not destination or not name or price is None or not price.is_finite() or price <= 0:
        return None
    if merchant != settings.awin_kabum_advertiser_id or field("currency").upper() != "BRL":
        return None
    native = destination.rsplit("/", 1)[-1]
    if field("merchant_product_id") != native:
        return None
    stock = field("in_stock").lower()
    unavailable = stock in {"0", "false", "no", "n"} or field("is_for_sale").lower() in {"0", "false", "no"}
    link = field("aw_deep_link")
    affiliate = link if is_owned_kabum(link, settings) else None
    reference = money(field("product_price_old")) or money(field("rrp_price"))
    if reference is not None and reference <= price:
        reference = None
    discount = None
    if reference and reference.is_finite() and reference > price:
        discount = money((reference - price) / reference * 100)
    condition = field("condition").lower()
    condition = {"novo": "new", "new": "new", "used": "used", "usado": "used", "refurbished": "refurbished"}.get(condition, "unknown")
    return NormalizedOffer(
        source="kabum", source_record_id=native, marketplace="kabum", merchant_id="",
        native_product_id=native, merchant_name="KaBuM!", product_name=name,
        brand=field("brand_name") or None, model=field("product_model") or field("model_number") or None,
        condition=condition,
        category=field("merchant_product_category_path") or field("merchant_category") or field("category_name") or None,
        effective_price=price, listed_price=reference or price, reported_price=price,
        price_verified=False, availability="unavailable" if unavailable else "in_stock" if stock in {"1", "true", "yes", "y"} else "unknown",
        fetched_at=downloaded, purchase_url=destination, affiliate_url=affiliate,
        image_url=sanitize_media_url(field("merchant_image_url") or field("aw_image_url")),
        description=field("product_short_description") or field("description") or None,
        announced_discount_pct=discount, identity_confidence=IdentityConfidence.HIGH,
        raw_payload={"via": "awin_feed", "feed_id": field("data_feed_id"),
                     "ean": field("ean"), "last_updated": field("last_updated")},
    ).quantized()
