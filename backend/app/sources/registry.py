from __future__ import annotations

from app.core.config import Settings
from app.sources.base import SourceConnector
from app.sources.community import CommunitySource
from app.sources.lomadee import LomadeeSource
from app.sources.magalu import MagaluSource
from app.sources.mercadolivre import MercadoLivreSource
from app.sources.mlhub import MlHubSource
from app.sources.mlofficial import MlOfficialSource
from app.sources.shopee import ShopeeSource
from app.sources.watchlist import WatchlistSource

RETIRED_SOURCES = frozenset({"pelando", "kabum"})


def build_connectors(settings: Settings) -> list[SourceConnector]:
    return [
        MlHubSource(settings),
        MlOfficialSource(settings),
        MercadoLivreSource(settings),
        MagaluSource(settings),
        ShopeeSource(settings),
        LomadeeSource(settings),
        WatchlistSource(settings),
        CommunitySource(settings),
    ]
