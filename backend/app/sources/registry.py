from __future__ import annotations

from app.core.config import Settings
from app.sources.base import SourceConnector
from app.sources.kabum import KabumSource
from app.sources.lomadee import LomadeeSource
from app.sources.magalu import MagaluSource
from app.sources.mercadolivre import MercadoLivreSource
from app.sources.mlhub import MlHubSource
from app.sources.pelando import PelandoSource
from app.sources.shopee import ShopeeSource
from app.sources.watchlist import WatchlistSource


def build_connectors(settings: Settings) -> list[SourceConnector]:
    return [
        MlHubSource(settings),
        PelandoSource(settings),
        MercadoLivreSource(settings),
        MagaluSource(settings),
        KabumSource(settings),
        ShopeeSource(settings),
        LomadeeSource(settings),
        WatchlistSource(settings),
    ]
