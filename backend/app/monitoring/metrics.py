from __future__ import annotations

from statistics import quantiles

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import SourceCheckpoint, SourceMetricSample


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    if len(ordered) < 2:
        return ordered[0]
    try:
        pts = quantiles(ordered, n=100, method="inclusive")
        idx = min(99, max(1, int(p))) - 1
        return pts[idx]
    except Exception:
        k = int(round((p / 100) * (len(ordered) - 1)))
        return ordered[k]


async def latency_summary(session: AsyncSession, source: str) -> dict:
    rows = list(
        (
            await session.execute(
                select(SourceMetricSample)
                .where(SourceMetricSample.source == source)
                .order_by(SourceMetricSample.recorded_at.desc())
                .limit(500)
            )
        ).scalars()
    )
    total = [r.total_observable_latency_seconds for r in rows if r.total_observable_latency_seconds is not None]
    ingest = [r.source_latency_seconds for r in rows if r.source_latency_seconds is not None]
    proc = [r.processing_latency_seconds for r in rows if r.processing_latency_seconds is not None]
    within = [r.within_slo for r in rows if r.within_slo is not None]
    pct_within = (sum(1 for v in within if v) / len(within) * 100) if within else None
    return {
        "samples": len(rows),
        "source_to_ingest": {
            "p50": percentile(ingest, 50),
            "p95": percentile(ingest, 95),
            "p99": percentile(ingest, 99),
        },
        "ingest_to_analysis": {
            "p50": percentile(proc, 50),
            "p95": percentile(proc, 95),
            "p99": percentile(proc, 99),
        },
        "total_observable": {
            "p50": percentile(total, 50),
            "p95": percentile(total, 95),
            "p99": percentile(total, 99),
        },
        "pct_within_180s": pct_within,
        "note": "Métricas de amostras persistidas; não são garantia de SLO.",
    }


async def get_or_create_checkpoint(session: AsyncSession, source: str) -> SourceCheckpoint:
    row = await session.get(SourceCheckpoint, source)
    if row is None:
        row = SourceCheckpoint(source=source, state={})
        session.add(row)
        await session.flush()
    return row
