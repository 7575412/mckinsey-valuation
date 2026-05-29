"""Phase 2 — WACC via CAPM, weighted on market values."""

from __future__ import annotations

from .models import WaccInputs


def compute_wacc(inp: WaccInputs) -> float:
    """가중평균자본비용.

    WACC = (E/V)·Ke + (D/V)·Kd·(1−t)
      Ke = Rf + β·ERP
      Kd_after = pretax_cost_of_debt · (1 − tax_rate)
    가중치는 시장가치 기준.
    """
    e = inp.market_value_equity
    d = inp.market_value_debt
    v = e + d
    if v <= 0:
        raise ValueError("market_value_equity + market_value_debt must be > 0")

    ke = inp.cost_of_equity()
    kd_after = inp.after_tax_cost_of_debt()
    return (e / v) * ke + (d / v) * kd_after
