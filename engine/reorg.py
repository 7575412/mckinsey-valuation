"""Phase 1 — Reorganize accounting statements into economic form.

Splits the balance sheet into operating vs. non-operating and derives
NOPLAT and Invested Capital, the two inputs every McKinsey driver needs.
"""

from __future__ import annotations

from .models import RawFinancials, ReorgStatement


def effective_tax_rate(
    tax_expense: float, pretax_income: float, *, lo: float = 0.0, hi: float = 0.35
) -> float:
    """실효세율 = 법인세비용 / 세전이익, 이상치 클램프.

    세전이익이 0 이하이거나 비율이 비정상이면 [lo, hi]로 클램프한다.
    """
    if pretax_income <= 0:
        return hi
    rate = tax_expense / pretax_income
    return max(lo, min(hi, rate))


def operating_working_capital(f: RawFinancials) -> float:
    """영업운전자본 = 영업유동자산 − 무이자 영업유동부채."""
    operating_current_assets = f.receivables + f.inventory + f.operating_cash
    operating_current_liabilities = f.accounts_payable + f.accrued_liabilities
    return operating_current_assets - operating_current_liabilities


def invested_capital(f: RawFinancials) -> float:
    """투하자본 = 영업운전자본 + 순유형자산 + 순영업무형자산."""
    return (
        operating_working_capital(f)
        + f.net_ppe
        + f.net_operating_intangibles
    )


def noplat(f: RawFinancials, tax_rate: float | None = None) -> float:
    """세후영업이익 = EBIT × (1 − 실효세율)."""
    rate = (
        tax_rate
        if tax_rate is not None
        else effective_tax_rate(f.tax_expense, f.pretax_income)
    )
    return f.operating_income * (1.0 - rate)


def reorganize(f: RawFinancials) -> ReorgStatement:
    """단일 연도 회계 재무제표 → 매킨지식 재구성 명세."""
    rate = effective_tax_rate(f.tax_expense, f.pretax_income)
    return ReorgStatement(
        year=f.year,
        effective_tax_rate=rate,
        noplat=f.operating_income * (1.0 - rate),
        operating_working_capital=operating_working_capital(f),
        invested_capital=invested_capital(f),
        non_operating_assets=f.non_operating_assets,
        net_debt=f.total_debt,
        shares_outstanding=f.shares_outstanding,
    )
