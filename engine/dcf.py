"""Phase 3 — DCF valuation with McKinsey continuing-value formula.

Two-stage model:
  Stage 1: explicit FCF forecast, discounted at WACC.
  Stage 2: continuing (terminal) value via the key-value-driver formula
           TV = NOPLAT_{t+1} · (1 − g/RONIC) / (WACC − g)
"""

from __future__ import annotations

from .models import ProjectionAssumptions, RawFinancials, ValuationResult
from .reorg import invested_capital


def _terminal_value(
    noplat_next: float, wacc: float, g: float, ronic: float
) -> float:
    """매킨지 영구가치 = NOPLAT_{t+1}·(1 − g/RONIC) / (WACC − g)."""
    if wacc <= g:
        raise ValueError("WACC must exceed terminal growth g for a finite terminal value")
    if ronic <= 0:
        raise ValueError("RONIC must be positive")
    return noplat_next * (1.0 - g / ronic) / (wacc - g)


def value(
    base: RawFinancials,
    assumptions: ProjectionAssumptions,
    wacc: float,
) -> ValuationResult:
    """기준 연도 재무 + 추정 가정 + WACC → 적정 목표주가.

    명시적 기간 동안 매출을 g로 성장시키고, operating_margin·tax_rate로
    NOPLAT을 산출하며, 성장 자금조달을 위한 순투자(= NOPLAT·g/ROIC)를 차감해
    FCF를 만든다. 이후 영구가치를 더해 EV→주주가치→목표주가로 환산한다.
    """
    g = assumptions.revenue_growth
    margin = assumptions.operating_margin
    tax = assumptions.tax_rate
    roic_a = assumptions.roic_assumed
    g_term = assumptions.terminal_growth
    ronic = assumptions.terminal_ronic if assumptions.terminal_ronic is not None else wacc

    revenue = base.revenue
    pv_explicit = 0.0
    yearly_fcf: list[float] = []
    yearly_disc: list[float] = []
    noplat_t = 0.0

    for t in range(1, assumptions.years + 1):
        revenue = revenue * (1.0 + g)
        ebit = revenue * margin
        noplat_t = ebit * (1.0 - tax)
        # Net investment funds growth at the assumed marginal ROIC.
        net_inv = noplat_t * (g / roic_a) if roic_a > 0 else 0.0
        fcf_t = noplat_t - net_inv
        df = 1.0 / (1.0 + wacc) ** t
        disc = fcf_t * df
        pv_explicit += disc
        yearly_fcf.append(fcf_t)
        yearly_disc.append(disc)

    # Continuing value at end of explicit horizon.
    noplat_next = noplat_t * (1.0 + g_term)
    tv = _terminal_value(noplat_next, wacc, g_term, ronic)
    pv_tv = tv / (1.0 + wacc) ** assumptions.years

    ev = pv_explicit + pv_tv
    equity_value = ev + base.non_operating_assets - base.total_debt
    target_price = equity_value / base.shares_outstanding

    return ValuationResult(
        enterprise_value=ev,
        pv_explicit_fcf=pv_explicit,
        pv_terminal_value=pv_tv,
        terminal_value=tv,
        equity_value=equity_value,
        target_price=target_price,
        wacc=wacc,
        shares_outstanding=base.shares_outstanding,
        value_trap=roic_a < wacc,
        yearly_fcf=yearly_fcf,
        yearly_discounted_fcf=yearly_disc,
    )
