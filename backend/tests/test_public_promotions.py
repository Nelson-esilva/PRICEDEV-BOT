from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from app.core.db import get_session_factory, utcnow
from app.models.entities import PublicPromotion, Opportunity, PublishedDeal
from app.storefront.promotions import fetch_awin, save_promotions
from app.storefront.catalog import qualifies, _apply_snapshot


def link(publisher='123'):
    return 'https://www.awin1.com/cread.php?' + urlencode({
        'awinaffid': publisher, 'awinmid': '17729',
        'ued': 'https://www.kabum.com.br/promocao/CUPOM10',
    })


def configure(settings):
    settings.enable_awin = True
    settings.awin_publisher_id = '123'
    settings.awin_kabum_advertiser_id = '17729'
    settings.awin_api_token = 'test'


async def test_official_voucher_import_is_separate_and_idempotent(client, test_settings):
    configure(test_settings)
    now = utcnow()
    raw = {'promotionId': 1, 'type': 'voucher', 'advertiser': {'id': 17729},
        'title': '10% em produtos participantes', 'description': '<b>Seleção especial</b>',
        'terms': 'Válido somente na seleção', 'voucher': {'code': 'CUPOM10'},
        'startDate': (now - timedelta(hours=1)).isoformat(),
        'endDate': (now + timedelta(days=1)).isoformat(), 'urlTracking': link()}
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={'data': [raw], 'pagination': {}}))) as http:
        rows = await fetch_awin(test_settings, http)
    assert rows[0]['kind'] == 'coupon'
    assert rows[0]['description'] == 'Seleção especial'
    await save_promotions('awin', rows)
    await save_promotions('awin', rows)
    result = (await client.get('/api/public/v1/promotions?kind=coupon')).json()
    assert result['total'] == 1 and result['items'][0]['code'] == 'CUPOM10'
    assert 'destination_url' not in result['items'][0]
    async with get_session_factory()() as session:
        assert len((await session.execute(select(PublicPromotion))).scalars().all()) == 1
        assert len((await session.execute(select(Opportunity))).scalars().all()) == 0
    redirect = await client.get(result['items'][0]['go_path'], follow_redirects=False)
    assert redirect.status_code == 302 and redirect.headers['location'] == link()
    home = (await client.get('/api/public/v1/home')).json()
    assert home['coupons']['total'] == 1
    await save_promotions('awin', [])
    assert (await client.get('/api/public/v1/promotions')).json()['total'] == 0


async def test_expired_stale_and_foreign_campaign_links_do_not_redirect(client, test_settings):
    configure(test_settings)
    now = utcnow()
    async with get_session_factory()() as session:
        for ident, changes in [('expired', {'expires_at': now - timedelta(seconds=1)}),
            ('stale', {'updated_at': now - timedelta(days=2)}),
            ('future', {'starts_at': now + timedelta(days=1)}),
            ('foreign', {'destination_url': link('999')})]:
            values = dict(id=ident, slug=ident, source='awin', external_id=ident, store='kabum',
                kind='campaign', title='Campanha', destination_url=link(), updated_at=now,
                expires_at=now + timedelta(days=1))
            values.update(changes)
            session.add(PublicPromotion(**values))
        await session.commit()
    for token in ['expired', 'stale', 'future', 'foreign']:
        assert (await client.get(f'/go/promotions/{token}')).status_code == 410
    assert (await client.get('/api/public/v1/promotions/expired')).status_code == 404


def test_snapshot_keeps_source_freshness_and_ignores_commission(test_settings):
    now = utcnow()
    observed = now - timedelta(hours=2)
    opp = Opportunity(source='mlhub', status='active', affiliate_status='converted',
        classification='PROVISIONAL', product_name='Monitor', product_id='p',
        acceptance_score=40, current_price=Decimal('100'), currency='BRL',
        final_purchase_url='https://www.mercadolivre.com.br/p/MLB123456789',
        announced_discount_pct=Decimal('20'), fetched_at=observed,
        payment_hint='Ganhos extras 22%')
    assert qualifies(opp, test_settings)
    deal = PublishedDeal()
    _apply_snapshot(deal, opp, now=now, ttl=timedelta(hours=36))
    assert deal.updated_at == observed and deal.expires_at == observed + timedelta(hours=36)
    assert deal.payment_hint is None
    assert deal.discount_basis == 'store' and deal.discount_pct == Decimal('20')
    opp.announced_discount_pct = None
    assert not qualifies(opp, test_settings)
    opp.coupon_code = 'CUPOM10'
    assert qualifies(opp, test_settings)
    opp.classification = 'REJECTED'
    assert not qualifies(opp, test_settings)
