"""Phase 4 — Sensitivity analysis: target price across WACC × g grid."""

from __future__ import annotations

from .dcf import value
from .models import ProjectionAssumptions, RawFinancials


def sensitivity_grid(
    base: RawFinancials,
    assumptions: ProjectionAssumptions,
    wacc_values: list[float],
    growth_values: list[float],
) -> dict:
    """WACC(행) × 영구성장률 g(열) 2차원 목표주가 표(히트맵용).

    반환: {"wacc": [...], "growth": [...], "prices": [[...], ...]}
    prices[i][j] = wacc_values[i], growth_values[j]에서의 목표주가.
    유효하지 않은 조합(WACC<=g 등)은 None.
    """
    prices: list[list[float | None]] = []
    for w in wacc_values:
        row: list[float | None] = []
        for g in growth_values:
            scenario = assumptions.model_copy(update={"terminal_growth": g})
            try:
                row.append(round(value(base, scenario, w).target_price, 2))
            except ValueError:
                row.append(None)
        prices.append(row)
    return {
        "wacc": wacc_values,
        "growth": growth_values,
        "prices": prices,
    }
