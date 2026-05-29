"""Pydantic input/output schemas for the valuation engine.

All monetary values are in the same currency unit (e.g. KRW). Keep them
consistent across a single valuation; the engine does not convert units.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RawFinancials(BaseModel):
    """One fiscal year of (lightly normalized) accounting figures.

    Populated either manually or by the DART data layer. The engine
    reorganizes these into operating vs. non-operating components.
    """

    year: int

    # Income statement
    revenue: float
    operating_income: float = Field(..., description="EBIT / 영업이익")
    pretax_income: float = Field(..., description="세전이익")
    tax_expense: float = Field(..., description="법인세비용")

    # Operating working capital components
    receivables: float = 0.0
    inventory: float = 0.0
    operating_cash: float = Field(
        0.0,
        description="영업현금. 별도 입력이 없으면 0으로 두고 현금 전액을 비영업으로 본다.",
    )
    accounts_payable: float = 0.0
    accrued_liabilities: float = 0.0

    # Long-term operating assets
    net_ppe: float = Field(0.0, description="순유형자산")
    net_operating_intangibles: float = Field(0.0, description="순영업무형자산")

    # Financing / non-operating
    total_debt: float = Field(0.0, description="총차입금 (단기+장기)")
    non_operating_assets: float = Field(
        0.0, description="잉여현금 + 금융투자자산 등 비영업자산"
    )
    equity: float = Field(0.0, description="자기자본 (장부)")

    shares_outstanding: float = Field(..., gt=0, description="총발행주식수")


class ReorgStatement(BaseModel):
    """McKinsey-reorganized statement for one year."""

    year: int
    effective_tax_rate: float
    noplat: float = Field(..., description="세후영업이익 = EBIT × (1 − 실효세율)")
    operating_working_capital: float
    invested_capital: float
    non_operating_assets: float
    net_debt: float = Field(..., description="총차입금 − 비영업현금성자산은 별도. 여기선 total_debt")
    shares_outstanding: float

    # Driver fields — populated once a prior year is available
    net_investment: Optional[float] = None
    roic: Optional[float] = None
    reinvestment_rate: Optional[float] = None
    fcf: Optional[float] = None


class WaccInputs(BaseModel):
    risk_free_rate: float = Field(0.035, description="무위험수익률 Rf")
    equity_risk_premium: float = Field(0.06, description="시장위험프리미엄 ERP")
    beta: float = Field(1.0, description="베타 β")
    pretax_cost_of_debt: float = Field(0.05, description="세전 차입금리")
    tax_rate: float = Field(0.22, description="한계세율")
    market_value_equity: float = Field(..., gt=0)
    market_value_debt: float = Field(0.0, ge=0)

    def cost_of_equity(self) -> float:
        return self.risk_free_rate + self.beta * self.equity_risk_premium

    def after_tax_cost_of_debt(self) -> float:
        return self.pretax_cost_of_debt * (1.0 - self.tax_rate)


class ProjectionAssumptions(BaseModel):
    """Drivers for the explicit forecast period (Stage 1)."""

    years: int = Field(5, ge=1, le=20, description="명시적 추정 기간")
    revenue_growth: float = Field(0.05, description="연 매출성장률 g (명시적 기간)")
    operating_margin: float = Field(..., description="EBIT 마진 (매출 대비)")
    tax_rate: float = Field(0.22)
    # Reinvestment intensity: net investment = NOPLAT × (g / roic_assumed)
    roic_assumed: float = Field(..., gt=0, description="명시적 기간 신규투자 ROIC")

    # Terminal (Stage 2)
    terminal_growth: float = Field(0.025, description="영구성장률 g∞")
    terminal_ronic: Optional[float] = Field(
        None, description="영구 신규투하자본수익률. None이면 WACC로 설정(가치중립)."
    )


class ValuationResult(BaseModel):
    enterprise_value: float
    pv_explicit_fcf: float
    pv_terminal_value: float
    terminal_value: float
    equity_value: float
    target_price: float
    wacc: float
    shares_outstanding: float
    # Diagnostics
    value_trap: bool = Field(
        False, description="True면 ROIC<WACC: 성장이 가치를 훼손"
    )
    yearly_fcf: list[float] = Field(default_factory=list)
    yearly_discounted_fcf: list[float] = Field(default_factory=list)
