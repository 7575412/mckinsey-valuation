"""Phase 5 — Reverse DCF: what growth does today's price imply?

Solves for the explicit-period revenue growth rate that makes the model's
target price equal the observed market price. If the implied growth looks
implausible, that is a sell signal.
"""

from __future__ import annotations

from scipy.optimize import brentq

from .dcf import value
from .models import ProjectionAssumptions, RawFinancials


def implied_growth(
    base: RawFinancials,
    assumptions: ProjectionAssumptions,
    wacc: float,
    market_price: float,
    *,
    lo: float = -0.20,
    hi: float = 0.60,
) -> float | None:
    """현재 주가를 정당화하는 명시적 기간 매출성장률을 역산.

    [lo, hi] 구간에서 target_price(g) − market_price = 0 을 brentq로 푼다.
    구간 내 해가 없으면 None.
    """

    def diff(g: float) -> float:
        scenario = assumptions.model_copy(update={"revenue_growth": g})
        return value(base, scenario, wacc).target_price - market_price

    try:
        f_lo, f_hi = diff(lo), diff(hi)
    except ValueError:
        return None
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        # No sign change in the bracket → no root here.
        return None
    return brentq(diff, lo, hi, xtol=1e-6)
