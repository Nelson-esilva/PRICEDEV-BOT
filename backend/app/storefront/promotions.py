"""Official affiliate campaigns, kept separate from product price observations."""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import as_utc, get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.urls import sanitize_media_url
from app.models.entities import PublicPromotion, SourceCheckpoint
from app.sources.shopee import ShopeeSource
from app.storefront.catalog import slugify

log = get_logger('promotions')


def plain(value):
    from html import unescape
    return unescape(re.sub(r'<[^>]+>', ' ', str(value or ''))).strip() or None


def date(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC) if value > 0 else None
    if not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(str(value).replace('Z', '+00:00')))
    except ValueError:
        return None


def owned_campaign_link(link: str | None, store: str, settings: Settings) -> bool:
    parsed = urlparse(link or '')
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        return False
    if store == 'shopee':
        return host in {'shopee.com.br', 'www.shopee.com.br', 's.shopee.com.br', 'shope.ee', 'shp.ee'}
    if store != 'kabum' or not settings.enable_awin:
        return False
    query = parse_qs(parsed.query)
    if host not in {'awin1.com', 'www.awin1.com'}:
        return False
    if parsed.path == '/pclick.php':
        return query.get('a') == [settings.awin_publisher_id] and query.get('m') == [settings.awin_kabum_advertiser_id]
    if parsed.path != '/cread.php':
        return False
    target = urlparse((query.get('ued') or [''])[0])
    return (query.get('awinaffid') == [settings.awin_publisher_id]
        and query.get('awinmid') == [settings.awin_kabum_advertiser_id]
        and target.scheme == 'https' and target.hostname in {'kabum.com.br', 'www.kabum.com.br'})


async def fetch_awin(settings: Settings, client: httpx.AsyncClient) -> list[dict]:
    rows = []
    for page in range(1, 51):
        response = await client.post(f'https://api.awin.com/publisher/{settings.awin_publisher_id}/promotions',
            headers={'Authorization': f'Bearer {settings.awin_api_token}'},
            json={'filters': {'advertiserIds': [int(settings.awin_kabum_advertiser_id)],
                  'status': 'active', 'type': 'all'}, 'pagination': {'page': page, 'pageSize': 200}})
        response.raise_for_status()
        body = response.json()
        data = body.get('data')
        if not isinstance(data, list):
            raise ValueError('Invalid Awin promotions response')
        for raw in data:
            advertiser = raw.get('advertiser') or {}
            if str(advertiser.get('id')) != settings.awin_kabum_advertiser_id:
                continue
            link = raw.get('urlTracking')
            if not owned_campaign_link(link, 'kabum', settings):
                # Some API responses use a different Awin link format; request a verified link.
                target = urlparse(raw.get('url') or '')
                if target.scheme != 'https' or target.hostname not in {'www.kabum.com.br', 'kabum.com.br'}:
                    continue
                generated = await client.post(
                    f'https://api.awin.com/publishers/{settings.awin_publisher_id}/linkbuilder/generate',
                    headers={'Authorization': f'Bearer {settings.awin_api_token}'},
                    json={'advertiserId': int(settings.awin_kabum_advertiser_id), 'destinationUrl': raw['url'], 'shorten': False})
                generated.raise_for_status()
                link = generated.json().get('url')
            if not owned_campaign_link(link, 'kabum', settings):
                continue
            code = ((raw.get('voucher') or {}).get('code') or '').strip() or None
            title = plain(raw.get('title'))
            if not title or not raw.get('promotionId'):
                continue
            rows.append(dict(source='awin', external_id=str(raw['promotionId']), store='kabum',
                kind='coupon' if raw.get('type') == 'voucher' and code else 'campaign',
                title=title, description=plain(raw.get('description')), terms=plain(raw.get('terms')),
                code=code, image_url=None, destination_url=link,
                starts_at=date(raw.get('startDate')), expires_at=date(raw.get('endDate'))))
        if len(data) < 200:
            return rows
    raise ValueError('Awin promotions exceeded pagination limit')


async def fetch_shopee(settings: Settings, client: httpx.AsyncClient) -> list[dict]:
    source = ShopeeSource(settings, client=client)
    rows = []
    for page in range(1, 21):
        payload = await source.campaigns(page=page, limit=50)
        feed = (payload.get('data') or {}).get('shopeeOfferV2')
        if not isinstance(feed, dict):
            raise ValueError('Invalid Shopee campaign response')
        for raw in feed.get('nodes') or []:
            # A Shopee prefixa coleções de categoria com "- - ".
            title = re.sub(r'^[\s\-–—]+', '', plain(raw.get('offerName')) or '')
            link = raw.get('offerLink')
            if not title or not owned_campaign_link(link, 'shopee', settings):
                continue
            rows.append(dict(source='shopee_campaign',
                external_id=str(raw.get('collectionId') or hashlib.sha256(link.encode()).hexdigest()[:24]),
                store='shopee', kind='campaign', title=title, code=None, terms=None,
                description=None, destination_url=link, image_url=sanitize_media_url(raw.get('imageUrl')),
                starts_at=date(raw.get('periodStartTime')), expires_at=date(raw.get('periodEndTime'))))
        if not (feed.get('pageInfo') or {}).get('hasNextPage'):
            return rows
    raise ValueError('Shopee campaigns exceeded pagination limit')


async def save_promotions(source: str, rows: list[dict], *, now=None):
    now = now or utcnow()
    async with get_session_factory()() as session:
        existing = (await session.execute(select(PublicPromotion).where(PublicPromotion.source == source))).scalars().all()
        by_id = {row.external_id: row for row in existing}
        seen = set()
        for values in rows:
            external_id = values['external_id']
            seen.add(external_id)
            promotion = by_id.get(external_id)
            if promotion is None:
                suffix = hashlib.sha256(f'{source}:{external_id}'.encode()).hexdigest()[:10]
                promotion = PublicPromotion(slug=slugify(values['title'], suffix), **values)
                session.add(promotion)
                by_id[external_id] = promotion
            else:
                for key, value in values.items():
                    setattr(promotion, key, value)
            promotion.updated_at = now
            promotion.status = 'active'
        for promotion in existing:
            if promotion.external_id not in seen:
                promotion.status = 'expired'
        checkpoint = await session.get(SourceCheckpoint, source)
        if checkpoint is None:
            checkpoint = SourceCheckpoint(source=source)
            session.add(checkpoint)
        checkpoint.last_success_at = now
        checkpoint.last_error = None
        await session.commit()


async def sync_promotions(settings: Settings):
    jobs = []
    if settings.enable_awin and settings.awin_api_token and settings.awin_publisher_id.isdigit() and settings.awin_kabum_advertiser_id.isdigit():
        jobs.append(('awin', fetch_awin))
    if settings.enable_shopee and settings.shopee_app_id and settings.shopee_app_secret:
        jobs.append(('shopee_campaign', fetch_shopee))
    async with httpx.AsyncClient(timeout=30) as client:
        for source, fetch in jobs:
            try:
                rows = await fetch(settings, client)
                await save_promotions(source, rows)
                log.info('promotions_synced', source=source, count=len(rows))
            except Exception as exc:
                # Keep last successful data on temporary failure; public freshness cap is 24h.
                log.warning('promotions_failed', source=source, error_type=type(exc).__name__)


async def run_promotions(settings: Settings):
    while True:
        await sync_promotions(settings)
        await asyncio.sleep(900)
