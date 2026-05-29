"""Phase 2 — Key value drivers: ROIC, reinvestment rate, FCF.

These convert reorganized statements into the economic ratios that drive
value. Driver fields require a prior year for the net-investment delta.
"""

from __future__ import annotations

from .models import ReorgStatement


def roic(noplat: float, invested_capital: float, *, beginning: bool = True) -> float:
    """투하자본수익률 = NOPLAT / 투하자본.

    beginning=True면 기초(전기말) 투하자본을 분모로 쓴다(매킨지 권장).
    """
    if invested_capital == 0:
        return 0.0
    return noplat / invested_capital


def net_investment(curr_ic: float, prev_ic: float) -> float:
    """순투자 = 당기 투하자본 − 전기 투하자본 (투하자본 증가분)."""
    return curr_ic - prev_ic


def reinvestment_rate(net_investment: float, noplat: float) -> float:
    """재투자율 = 순투자 / NOPLAT (= g / ROIC)."""
    if noplat == 0:
        return 0.0
    return net_investment / noplat


def fcf(noplat: float, net_investment: float) -> float:
    """잉여현금흐름 = NOPLAT − 순투자."""
    return noplat - net_investment


def compute_drivers(statements: list[ReorgStatement]) -> list[ReorgStatement]:
    """연속 연도 명세에 ROIC/재투자율/FCF를 채워 반환한다.

    가장 오래된 연도가 먼저 오도록 정렬되어 있다고 가정한다. 첫 해는
    전기 투하자본이 없어 driver 필드가 None으로 남는다.
    """
    ordered = sorted(statements, key=lambda s: s.year)
    out: list[ReorgStatement] = []
    for i, s in enumerate(ordered):
        updated = s.model_copy()
        if i == 0:
            # ROIC against own (current) invested capital as a fallback.
            updated.roic = roic(s.noplat, s.invested_capital)
        else:
            prev = ordered[i - 1]
            ni = net_investment(s.invested_capital, prev.invested_capital)
            updated.net_investment = ni
            updated.roic = roic(s.noplat, prev.invested_capital)
            updated.reinvestment_rate = reinvestment_rate(ni, s.noplat)
            updated.fcf = fcf(s.noplat, ni)
        out.append(updated)
    return out
