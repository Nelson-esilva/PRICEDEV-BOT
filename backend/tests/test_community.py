from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.core.db import utcnow
from app.inbox.parse import parse_deal
from app.models.entities import Opportunity
from app.sources.community import _public_media, community_offer, kabum_facts, kabum_product
from app.storefront.catalog import qualifies, store_of


def _kabum_html(**product) -> str:
    data = {"props": {"pageProps": {"product": product}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


def test_kabum_page_confirms_price_pix_and_stock():
    product = kabum_product(_kabum_html(
        title="Controle DualSense", available=False, preOrderDate="19/11/2026", category="Games/Playstation",
        prices={"oldPrice": 618.97, "priceWithDiscount": 549.9, "price": 599, "discountPercentage": 0},
        flags={"isFreeShipping": True, "isFlash": True},
        medias=[{"images": {"m": "https://images.kabum.com.br/a_m.jpg", "gg": "https://images.kabum.com.br/a_gg.jpg"}}],
    ))
    facts = kabum_facts(product)
    assert facts["price"] == Decimal("549.90") and facts["regular"] == Decimal("599.00")
    assert facts["listed"] == Decimal("618.97") and facts["sellable"] and facts["free_shipping"]
    assert facts["gallery"] == ["https://images.kabum.com.br/a_gg.jpg"] and facts["category"] == "Games"
    sold_out = kabum_facts(kabum_product(_kabum_html(available=False, prices={"price": 10})))
    assert not sold_out["sellable"]
    assert kabum_product("<html></html>") is None


def test_community_offer_uses_store_not_group():
    row = SimpleNamespace(
        id="m1", posted_at=utcnow() - timedelta(hours=1), received_at=utcnow(),
        affiliate_url="https://www.amazon.com.br/dp/B0FK5SQZ44?tag=promodev00-20",
    )
    parsed = parse_deal("Processador Ryzen 7\nDe R$ 1.599,99 por R$ 1.399,99\nCupom: RYZEN50\nhttps://amzn.to/x")
    offer = community_offer(
        row, parsed, marketplace="amazon", native="B0FK5SQZ44", title=parsed.title,
        purchase_url="https://www.amazon.com.br/dp/B0FK5SQZ44", price=parsed.price, listed=parsed.listed_price,
        regular=None, image=None, gallery=None, free_shipping=None, verified=False, category=None,
    )
    assert offer.source == "grupos" and offer.merchant_name == "Amazon"
    assert offer.effective_price == Decimal("1399.99") and offer.coupon_code == "RYZEN50"
    assert offer.announced_discount_pct and offer.affiliate_url.endswith("tag=promodev00-20")
    assert offer.fetched_at == row.posted_at
    assert _public_media("/api/v1/inbox/media/1_2.jpg") == "/api/public/v1/media/1_2.jpg"


def test_community_deals_publish_without_reference_price(test_settings):
    opp = Opportunity(
        source="grupos", status="active", classification="PROVISIONAL", current_price=Decimal("26"),
        affiliate_status="converted", acceptance_score=50, original_purchase_url="https://www.amazon.com.br/dp/B0034W0X0I",
        affiliate_url="https://www.amazon.com.br/dp/B0034W0X0I?tag=promodev00-20",
    )
    assert store_of(opp) == "amazon" and qualifies(opp, test_settings)
    opp.original_purchase_url = "https://www.kabum.com.br/produto/1"
    assert store_of(opp) == "kabum"
