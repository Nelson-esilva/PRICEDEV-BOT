from __future__ import annotations

from decimal import Decimal

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.entities import Opportunity, PublicationLog
from app.schemas.normalized import Classification

log = get_logger("telegram")


def format_message(opp: Opportunity) -> str:
    price = _brl(opp.current_price)
    median = _brl(opp.historical_median)
    discount = f"{opp.historical_discount_pct}%" if opp.historical_discount_pct is not None else "n/d"
    status = _status_label(opp.classification)
    url = opp.final_purchase_url or "indisponível"
    lines = [
        "OFERTA DETECTADA",
        "",
        f"Produto: {opp.product_name}",
        f"Loja: {opp.merchant or 'n/d'}",
        "",
        f"Preço atual: {price}",
        f"Mediana histórica: {median}",
        "",
        f"Desconto histórico: {discount}",
        f"Qualidade da oportunidade: {opp.acceptance_score}/100",
        "",
        f"Status: {status}",
        "",
        "Comprar:",
        url,
    ]
    if opp.classification == Classification.PROVISIONAL.value:
        lines.append("")
        lines.append("Oferta reportada — preço ou histórico não confirmado.")
    if not opp.price_verified:
        lines.append("Preço não confirmado na loja.")
    if opp.affiliate_status == "direct":
        lines.append("Link direto (sem afiliado).")
    return "\n".join(lines)


def _status_label(classification: str) -> str:
    return {
        Classification.HISTORICALLY_VALIDATED.value: "Histórico validado",
        Classification.PRICE_ANOMALY_CANDIDATE.value: "Candidato a anomalia de preço",
        Classification.PROVISIONAL.value: "Oferta provisória",
        Classification.INSUFFICIENT_HISTORY.value: "Histórico insuficiente",
        Classification.EXPIRED.value: "Oferta expirada",
        Classification.REJECTED.value: "Rejeitada",
    }.get(classification, classification)


def _brl(value: Decimal | None) -> str:
    if value is None:
        return "n/d"
    quantized = value.quantize(Decimal("0.01"))
    return f"R$ {quantized:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def should_publish(opp: Opportunity, settings: Settings) -> tuple[bool, str | None]:
    if not settings.enable_telegram_publish:
        return False, "telegram_disabled"
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False, "missing_credentials"
    if opp.status != "active":
        return False, "inactive"
    if not opp.final_purchase_url:
        return False, "invalid_url"
    if opp.classification == Classification.EXPIRED.value:
        return False, "expired"
    if opp.classification == Classification.PROVISIONAL.value:
        if not settings.allow_provisional_auto_publish:
            return False, "provisional_blocked"
    if opp.classification == Classification.REJECTED.value:
        return False, "rejected"
    if opp.acceptance_score < settings.min_acceptance_score:
        return False, "score"
    if (
        opp.classification
        in {
            Classification.HISTORICALLY_VALIDATED.value,
            Classification.PRICE_ANOMALY_CANDIDATE.value,
        }
        and opp.historical_discount_pct is not None
        and opp.historical_discount_pct < Decimal(str(settings.min_historical_discount_pct))
    ):
        return False, "discount"
    return True, None


def dedup_key(opp: Opportunity) -> str:
    price = str(opp.current_price)
    return f"{opp.product_id}:{price}:{opp.classification}"


async def publish_opportunity(session, opp: Opportunity, settings: Settings, *, http=None) -> str:
    import httpx

    allowed, reason = should_publish(opp, settings)
    key = dedup_key(opp)
    if not allowed:
        session.add(
            PublicationLog(
                opportunity_id=opp.id,
                channel="telegram",
                dedup_key=f"skip:{key}:{reason}",
                skipped_reason=reason,
            )
        )
        return reason or "skipped"
    from sqlalchemy import select

    existing = (
        await session.execute(
            select(PublicationLog).where(
                PublicationLog.channel == "telegram",
                PublicationLog.dedup_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return "duplicate"
    body = format_message(opp)
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": settings.telegram_chat_id, "text": body}
    client = http or httpx.AsyncClient(timeout=15.0)
    close = http is None
    try:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
    finally:
        if close:
            await client.aclose()
    session.add(
        PublicationLog(
            opportunity_id=opp.id,
            channel="telegram",
            dedup_key=key,
            body=body,
        )
    )
    from app.core.db import utcnow

    opp.published_at = utcnow()
    return "published"
