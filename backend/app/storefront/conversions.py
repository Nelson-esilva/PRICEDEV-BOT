"""Relatório de conversões da Shopee → pedidos por item, usados no ranking da vitrine."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.core.config import Settings
from app.core.db import get_session_factory, utcnow
from app.core.logging import get_logger
from app.core.money import money
from app.models.entities import AffiliateConversion, SourceCheckpoint
from app.sources.shopee import ShopeeSource

log = get_logger("conversions")

CHECKPOINT = "shopee_conversions"
MAX_PAGES = 40


def rows_from_report(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Achata conversão → pedidos → itens em linhas de AffiliateConversion."""
    report = ((payload.get("data") or {}).get("conversionReport")) or {}
    rows: list[dict[str, Any]] = []
    for node in report.get("nodes") or []:
        stamp = node.get("purchaseTime")
        if not isinstance(stamp, (int, float)):
            continue
        purchased = datetime.fromtimestamp(stamp, tz=UTC)
        tags = str(node.get("utmContent") or "").strip("-")
        for order in node.get("orders") or []:
            order_id = str(order.get("orderId") or "")
            if not order_id:
                continue
            for item in order.get("items") or []:
                item_id = item.get("itemId")
                if item_id is None:
                    continue
                rows.append(dict(
                    store="shopee",
                    conversion_id=str(node.get("conversionId") or ""),
                    order_id=order_id,
                    order_status=str(order.get("orderStatus") or "")[:32],
                    item_id=str(item_id),
                    item_name=str(item.get("itemName") or "")[:512],
                    quantity=int(item.get("qty") or 1),
                    amount=money(item.get("actualAmount")),
                    commission=money(item.get("itemTotalCommission")),
                    sub_ids=tags[:256],
                    purchased_at=purchased,
                ))
    return rows


async def fetch_shopee_conversions(settings: Settings, *, now: datetime | None = None) -> list[dict[str, Any]]:
    end = now or utcnow()
    start = end - timedelta(days=max(1, settings.shopee_conversions_days))
    source = ShopeeSource(settings)
    rows: list[dict[str, Any]] = []
    scroll: str | None = None
    try:
        for _ in range(MAX_PAGES):
            payload = await source.conversion_report(
                start=int(start.timestamp()), end=int(end.timestamp()), scroll_id=scroll
            )
            rows.extend(rows_from_report(payload))
            info = (((payload.get("data") or {}).get("conversionReport") or {}).get("pageInfo")) or {}
            scroll = info.get("scrollId")
            if not info.get("hasNextPage") or not scroll:
                break
    finally:
        await source.close()
    return rows


async def save_conversions(rows: list[dict[str, Any]], *, now: datetime | None = None) -> int:
    """Upsert por (loja, pedido, item); o status do pedido muda com o tempo."""
    moment = now or utcnow()
    async with get_session_factory()() as session:
        orders = {row["order_id"] for row in rows}
        existing = {}
        if orders:
            found = await session.execute(
                select(AffiliateConversion).where(AffiliateConversion.order_id.in_(orders))
            )
            existing = {(c.store, c.order_id, c.item_id): c for c in found.scalars().all()}
        for row in rows:
            key = (row["store"], row["order_id"], row["item_id"])
            record = existing.get(key)
            if record is None:
                record = AffiliateConversion(**row)
                session.add(record)
                existing[key] = record
            else:
                for name, value in row.items():
                    setattr(record, name, value)
            record.synced_at = moment
        checkpoint = await session.get(SourceCheckpoint, CHECKPOINT)
        if checkpoint is None:
            checkpoint = SourceCheckpoint(source=CHECKPOINT)
            session.add(checkpoint)
        checkpoint.last_success_at = moment
        checkpoint.last_error = None
        await session.commit()
    return len(rows)


def conversions_enabled(settings: Settings) -> bool:
    return bool(settings.enable_shopee_conversions and settings.shopee_app_id and settings.shopee_app_secret)


async def sync_conversions(settings: Settings) -> None:
    if not conversions_enabled(settings):
        return
    try:
        saved = await save_conversions(await fetch_shopee_conversions(settings))
        log.info("conversions_synced", store="shopee", items=saved)
    except Exception as exc:
        # Sem relatório o ranking segue com vendas da loja e cliques; nada é apagado.
        log.warning("conversions_failed", store="shopee", error=str(exc)[:200])


async def run_conversions(settings: Settings) -> None:
    while True:
        await sync_conversions(settings)
        await asyncio.sleep(max(300, settings.shopee_conversions_poll_seconds))
