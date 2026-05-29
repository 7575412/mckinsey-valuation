"""Valuation orchestration shared by the API (and reusable elsewhere).

Turns a base RawFinancials plus assumption/WACC overrides into a full
valuation payload: reorganization, drivers, WACC, DCF result.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from engine.dcf import value
from engine.drivers import compute_drivers
from engine.models import (
    ProjectionAssumptions,
    RawFinancials,
    ValuationResult,
    WaccInputs,
)
from engine.reorg import reorganize
from engine.reverse_dcf import implied_growth
from engine.sensitivity import sensitivity_grid
from engine.wacc import compute_wacc


class ValuationRequest(BaseModel):
    base: RawFinancials
    # Assumption overrides (None → auto-derive from base)
    years: int = 5
    revenue_growth: float = 0.05
    operating_margin: Optional[float] = None
    roic_assumed: Optional[float] = None
    terminal_growth: float = 0.025
    tax_rate: float = 0.22
    # WACC: either direct, or CAPM params
    wacc: Optional[float] = None
    risk_free_rate: float = 0.035
    equity_risk_premium: float = 0.06
    beta: float = 1.0
    pretax_cost_of_debt: float = 0.05
    current_price: Optional[float] = None


class ValuationResponse(BaseModel):
    base: RawFinancials
    noplat: float
    invested_capital: float
    effective_tax_rate: float
    roic: float
    wacc: float
    assumptions: ProjectionAssumptions
    result: ValuationResult
    upside: Optional[float] = None
    implied_growth: Optional[float] = None


def _resolve_wacc(req: ValuationRequest) -> float:
    if req.wacc is not None:
        return req.wacc
    market_equity = (
        req.current_price * req.base.shares_outstanding
        if req.current_price
        else req.base.equity
    )
    if market_equity <= 0:
        market_equity = 1.0
    return compute_wacc(
        WaccInputs(
            risk_free_rate=req.risk_free_rate,
            equity_risk_premium=req.equity_risk_premium,
            beta=req.beta,
            pretax_cost_of_debt=req.pretax_cost_of_debt,
            tax_rate=req.tax_rate,
            market_value_equity=market_equity,
            market_value_debt=req.base.total_debt,
        )
    )


def _resolve_assumptions(req: ValuationRequest, base_roic: float) -> ProjectionAssumptions:
    margin = (
        req.operating_margin
        if req.operating_margin is not None
        else (req.base.operating_income / req.base.revenue if req.base.revenue else 0.0)
    )
    roic_assumed = (
        req.roic_assumed if req.roic_assumed is not None else max(base_roic, 0.01)
    )
    return ProjectionAssumptions(
        years=req.years,
        revenue_growth=req.revenue_growth,
        operating_margin=margin,
        tax_rate=req.tax_rate,
        roic_assumed=roic_assumed,
        terminal_growth=req.terminal_growth,
    )


def run_valuation(req: ValuationRequest) -> ValuationResponse:
    reorg = reorganize(req.base)
    [driven] = compute_drivers([reorg])
    base_roic = driven.roic or 0.10
    wacc = _resolve_wacc(req)
    assumptions = _resolve_assumptions(req, base_roic)
    result = value(req.base, assumptions, wacc)

    upside = None
    g_imp = None
    if req.current_price:
        upside = result.target_price / req.current_price - 1.0
        g_imp = implied_growth(req.base, assumptions, wacc, req.current_price)

    return ValuationResponse(
        base=req.base,
        noplat=reorg.noplat,
        invested_capital=reorg.invested_capital,
        effective_tax_rate=reorg.effective_tax_rate,
        roic=base_roic,
        wacc=wacc,
        assumptions=assumptions,
        result=result,
        upside=upside,
        implied_growth=g_imp,
    )


def run_sensitivity(
    req: ValuationRequest,
    wacc_values: list[float],
    growth_values: list[float],
) -> dict:
    reorg = reorganize(req.base)
    [driven] = compute_drivers([reorg])
    base_roic = driven.roic or 0.10
    assumptions = _resolve_assumptions(req, base_roic)
    return sensitivity_grid(req.base, assumptions, wacc_values, growth_values)
