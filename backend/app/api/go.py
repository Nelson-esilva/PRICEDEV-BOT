from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.affiliates.resolver import stamp_owned_link
from app.core.config import Settings, get_settings
from app.core.db import get_session, utcnow
from app.core.logging import get_logger
from app.models.entities import DealClick, PublishedDeal, PublicPromotion, TrackedLink
from app.api.public import live_promotions
from app.storefront.promotions import owned_campaign_link
from app.storefront.catalog import STORE_LABELS

router = APIRouter()
log = get_logger("go")

_EXPIRED_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Oferta encerrada · PromoDev</title>
  <style>
    body {{ margin:0; font-family: Inter, Segoe UI, sans-serif; background:#f6f5f2; color:#171717; }}
    main {{ max-width: 480px; margin: 12vh auto; padding: 32px 24px; background:#fff; border-radius:20px;
            box-shadow: 0 10px 28px rgba(17,17,17,.06); text-align:center; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:-.03em; }}
    p {{ color:#6b7280; line-height:1.5; }}
    a {{ display:inline-block; margin-top:18px; padding:12px 22px; border-radius:999px; background:#1f7a4d;
         color:#fff; font-weight:800; text-decoration:none; }}
  </style>
</head>
<body>
  <main>
    <h1>Oferta encerrada</h1>
    <p>Esse preço não está mais disponível na vitrine. O valor na loja pode ter mudado.</p>
    <a href="{home}">Ver ofertas ativas</a>
  </main>
</body>
</html>
"""


def _expired(request: Request) -> HTMLResponse:
    return HTMLResponse(_EXPIRED_HTML.format(home="/"), status_code=410)


@router.get("/go/promotions/{token}")
async def go_to_promotion(token: str, request: Request,
    session: AsyncSession = Depends(get_session), settings: Settings = Depends(get_settings)):
    row = (await session.execute(select(PublicPromotion).where(
        *live_promotions(utcnow()), PublicPromotion.slug == token))).scalar_one_or_none()
    if row is None or not owned_campaign_link(row.destination_url, row.store, settings):
        return _expired(request)
    session.add(DealClick(deal_id=row.id, slug=row.slug, store=row.store,
        user_agent=(request.headers.get('user-agent') or '')[:256] or None,
        referer=(request.headers.get('referer') or '')[:512] or None))
    try:
        await session.commit()
    except Exception:
        await session.rollback()
    return RedirectResponse(row.destination_url, status_code=302)


@router.get("/go/t/{token}")
async def go_tracked(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    """Links dos posts do Telegram: registra o clique (canal telegram) e segue para o destino salvo."""
    link = await session.get(TrackedLink, token)
    if link is None or not link.destination:
        return _expired(request)
    session.add(DealClick(
        deal_id=link.opportunity_id or link.id, slug=link.id, store=link.store, channel=link.channel,
        user_agent=(request.headers.get("user-agent") or "")[:256] or None,
        referer=(request.headers.get("referer") or "")[:512] or None,
    ))
    try:
        await session.commit()
    except Exception as exc:
        log.warning("click_log_failed", error=str(exc)[:160])
        await session.rollback()
    return RedirectResponse(url=link.destination, status_code=302)


@router.get("/go/{token}")
async def go_to_store(
    token: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    now = utcnow()
    deal = (
        await session.execute(
            select(PublishedDeal).where(or_(PublishedDeal.slug == token, PublishedDeal.id == token))
        )
    ).scalar_one_or_none()
    if deal is None or deal.status != "active" or deal.expires_at <= now:
        return _expired(request)
    destination = stamp_owned_link(deal.destination_url, settings) or deal.destination_url
    if not destination:
        return _expired(request)
    session.add(
        DealClick(
            deal_id=deal.id,
            slug=deal.slug,
            store=deal.store or STORE_LABELS.get(deal.store, ""),
            user_agent=(request.headers.get("user-agent") or "")[:256] or None,
            referer=(request.headers.get("referer") or "")[:512] or None,
            clicked_at=now,
        )
    )
    try:
        await session.commit()
    except Exception as exc:
        log.warning("click_log_failed", error=str(exc)[:160])
        await session.rollback()
    return RedirectResponse(url=destination, status_code=302)
