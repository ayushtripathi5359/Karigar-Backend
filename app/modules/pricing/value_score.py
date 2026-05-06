"""
The Karigar / DIAMIND Value Score — the moat.

Formula (locked v1.0):
    total = 0.40·carat_factor
          + 0.20·color_factor
          + 0.15·clarity_factor
          + 0.15·cut_factor
          + 0.10·liquidity_factor

Each factor normalised to [0, 1].
Persistence: `value_scores` table (versioned via formula_version).
Recompute: nightly batch + on supplier upload.

Ported from /Users/mainadmin/Desktop/Karigar_Implementation/app/value_score.py — sync→async.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

# ── Lookup tables (locked v1.0) ───────────────────────────────────────
COLOR_FACTOR = {
    "D": 1.00, "E": 0.96, "F": 0.92, "G": 0.86, "H": 0.78,
    "I": 0.68, "J": 0.58, "K": 0.48, "L": 0.40, "M": 0.34,
}
CLARITY_FACTOR = {
    "FL": 1.00, "IF": 0.95, "VVS1": 0.90, "VVS2": 0.85,
    "VS1": 0.78, "VS2": 0.72, "SI1": 0.60, "SI2": 0.50,
    "I1": 0.35, "I2": 0.20, "I3": 0.10,
}
CUT_FACTOR = {
    "Excellent": 1.00, "Very Good": 0.85, "Good": 0.65,
    "Fair": 0.40, "Poor": 0.20,
}
LIQUIDITY_BENCHMARK = 0.65  # placeholder until trend_signals job lands


def carat_factor(carat: Decimal) -> float:
    """Bigger ≠ always better. Premium points are 1.0 / 2.0 / 3.0 / 5.0 ct."""
    c = float(carat)
    if c >= 5.0:
        return 1.00
    if c >= 3.0:
        return 0.95
    if c >= 2.0:
        return 0.90
    if c >= 1.0:
        return 0.85
    if c >= 0.50:
        return 0.65
    if c >= 0.30:
        return 0.45
    return 0.25


@dataclass
class ValueScoreResult:
    stone_id: UUID
    carat_factor: float
    color_factor: float
    clarity_factor: float
    cut_factor: float
    liquidity_factor: float
    total_score: float
    formula_version: str = "v1.0"


def compute_value_score(stone: dict) -> ValueScoreResult:
    """Pure — trivially unit-testable."""
    cf = carat_factor(stone["carat"])
    col = COLOR_FACTOR.get(stone["color_scale"], 0.25) if stone.get("color_scale") else 0.55
    cla = CLARITY_FACTOR.get(stone["clarity"], 0.10)
    cut = CUT_FACTOR.get(stone.get("cut") or "Good", 0.65)
    liq = LIQUIDITY_BENCHMARK

    total = round(0.40 * cf + 0.20 * col + 0.15 * cla + 0.15 * cut + 0.10 * liq, 4)

    return ValueScoreResult(
        stone_id=stone["id"],
        carat_factor=round(cf, 4),
        color_factor=round(col, 4),
        clarity_factor=round(cla, 4),
        cut_factor=round(cut, 4),
        liquidity_factor=round(liq, 4),
        total_score=total,
    )


_UPSERT = text(
    """
    INSERT INTO value_scores (
        stone_id, carat_factor, color_factor, clarity_factor,
        cut_factor, liquidity_factor, total_score, formula_version, computed_at
    ) VALUES (
        :stone_id, :carat_factor, :color_factor, :clarity_factor,
        :cut_factor, :liquidity_factor, :total_score, :formula_version, now()
    )
    ON CONFLICT (stone_id, formula_version) DO UPDATE SET
        carat_factor     = EXCLUDED.carat_factor,
        color_factor     = EXCLUDED.color_factor,
        clarity_factor   = EXCLUDED.clarity_factor,
        cut_factor       = EXCLUDED.cut_factor,
        liquidity_factor = EXCLUDED.liquidity_factor,
        total_score      = EXCLUDED.total_score,
        computed_at      = now()
    """
)


async def persist(db: AsyncSession, score: ValueScoreResult) -> None:
    await db.execute(
        _UPSERT,
        {
            "stone_id": str(score.stone_id),
            "carat_factor": score.carat_factor,
            "color_factor": score.color_factor,
            "clarity_factor": score.clarity_factor,
            "cut_factor": score.cut_factor,
            "liquidity_factor": score.liquidity_factor,
            "total_score": score.total_score,
            "formula_version": score.formula_version,
        },
    )


async def recompute_all(db: AsyncSession, batch_size: int = 1000) -> int:
    """Nightly job: rescore every active diamond."""
    rows = (
        await db.execute(
            text(
                """
                SELECT id, carat, color_scale, clarity, cut
                FROM supplier_master
                WHERE deleted_at IS NULL AND availability = 'available'
                """
            )
        )
    ).mappings().all()

    written = 0
    for row in rows:
        await persist(db, compute_value_score(dict(row)))
        written += 1
        if written % batch_size == 0:
            await db.flush()
    return written
