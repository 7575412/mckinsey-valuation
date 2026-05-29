"""Golden tests for the valuation engine.

Each case is hand-computable so a failure points straight at a broken
formula rather than a data issue.
"""

import math

import pytest

from engine.dcf import value
from engine.drivers import compute_drivers, fcf, net_investment, reinvestment_rate
from engine.models import ProjectionAssumptions, RawFinancials, WaccInputs
from engine.reorg import (
    effective_tax_rate,
    invested_capital,
    noplat,
    operating_working_capital,
    reorganize,
)
from engine.reverse_dcf import implied_growth
from engine.sensitivity import sensitivity_grid
from engine.wacc import compute_wacc


def make_base(**overrides) -> RawFinancials:
    data = dict(
        year=2025,
        revenue=1000.0,
        operating_income=200.0,
        pretax_income=180.0,
        tax_expense=36.0,  # 36/180 = 0.20
        receivables=200.0,
        inventory=300.0,
        operating_cash=0.0,
        accounts_payable=100.0,
        accrued_liabilities=50.0,
        net_ppe=600.0,
        net_operating_intangibles=50.0,
        total_debt=300.0,
        non_operating_assets=500.0,
        equity=800.0,
        shares_outstanding=100.0,
    )
    data.update(overrides)
    return RawFinancials(**data)


# --- Phase 1: reorganization ------------------------------------------------

def test_effective_tax_rate():
    assert effective_tax_rate(36.0, 180.0) == pytest.approx(0.20)
    # negative pretax → clamp to hi
    assert effective_tax_rate(0.0, -10.0, hi=0.35) == 0.35
    # absurd ratio clamps
    assert effective_tax_rate(100.0, 10.0, hi=0.35) == 0.35


def test_operating_working_capital_and_ic():
    f = make_base()
    # OWC = (200+300+0) - (100+50) = 350
    assert operating_working_capital(f) == pytest.approx(350.0)
    # IC = 350 + 600 + 50 = 1000
    assert invested_capital(f) == pytest.approx(1000.0)


def test_noplat():
    f = make_base()
    # EBIT 200 * (1 - 0.20) = 160
    assert noplat(f) == pytest.approx(160.0)
    r = reorganize(f)
    assert r.noplat == pytest.approx(160.0)
    assert r.invested_capital == pytest.approx(1000.0)
    assert r.effective_tax_rate == pytest.approx(0.20)


# --- Phase 2: drivers & WACC ------------------------------------------------

def test_drivers_chain():
    s0 = reorganize(make_base(year=2024))
    f1 = make_base(year=2025, operating_income=220.0, net_ppe=700.0)
    s1 = reorganize(f1)
    out = compute_drivers([s1, s0])  # unsorted input on purpose
    a, b = out[0], out[1]
    assert a.year == 2024 and b.year == 2025
    # year 2025 IC = 350 + 700 + 50 = 1100; prev IC = 1000 → net inv 100
    assert b.net_investment == pytest.approx(100.0)
    # NOPLAT 2025 = 220 * 0.8 = 176; ROIC = 176/1000 (beginning IC)
    assert b.roic == pytest.approx(0.176)
    assert b.reinvestment_rate == pytest.approx(100.0 / 176.0)
    assert b.fcf == pytest.approx(176.0 - 100.0)


def test_fcf_identity():
    # FCF == NOPLAT - net investment
    ni = net_investment(1100.0, 1000.0)
    assert fcf(176.0, ni) == pytest.approx(76.0)
    assert reinvestment_rate(ni, 176.0) == pytest.approx(100.0 / 176.0)


def test_wacc():
    w = WaccInputs(
        risk_free_rate=0.03,
        equity_risk_premium=0.05,
        beta=1.2,
        pretax_cost_of_debt=0.04,
        tax_rate=0.25,
        market_value_equity=800.0,
        market_value_debt=200.0,
    )
    # Ke = 0.03 + 1.2*0.05 = 0.09; Kd_after = 0.04*0.75 = 0.03
    # WACC = 0.8*0.09 + 0.2*0.03 = 0.078
    assert compute_wacc(w) == pytest.approx(0.078)


# --- Phase 3: DCF identities ------------------------------------------------

def test_no_growth_equals_fcf_perpetuity():
    """g=0 everywhere → EV must equal NOPLAT / WACC exactly."""
    base = make_base()
    a = ProjectionAssumptions(
        years=5,
        revenue_growth=0.0,
        operating_margin=0.20,
        tax_rate=0.20,
        roic_assumed=0.10,
        terminal_growth=0.0,
    )
    wacc = 0.08
    res = value(base, a, wacc)
    # NOPLAT = 1000*0.2*0.8 = 160 → EV = 160/0.08 = 2000
    assert res.enterprise_value == pytest.approx(2000.0, rel=1e-9)
    # Equity = 2000 + 500 - 300 = 2200; /100 shares = 22.0
    assert res.equity_value == pytest.approx(2200.0)
    assert res.target_price == pytest.approx(22.0)


def test_constant_growth_equals_kvd_formula():
    """Constant g and roic_assumed==ronic → EV equals the single-stage KVD value."""
    base = make_base()
    g = 0.04
    roic = 0.10
    wacc = 0.08
    a = ProjectionAssumptions(
        years=5,
        revenue_growth=g,
        operating_margin=0.20,
        tax_rate=0.20,
        roic_assumed=roic,
        terminal_growth=g,
        terminal_ronic=roic,
    )
    res = value(base, a, wacc)
    noplat_1 = (1000.0 * (1 + g)) * 0.20 * 0.80  # 166.4
    expected_ev = noplat_1 * (1 - g / roic) / (wacc - g)  # 2496
    assert res.enterprise_value == pytest.approx(expected_ev, rel=1e-9)
    assert res.enterprise_value == pytest.approx(2496.0, rel=1e-9)


def test_value_trap_flag():
    base = make_base()
    a = ProjectionAssumptions(
        years=5, revenue_growth=0.05, operating_margin=0.20,
        tax_rate=0.20, roic_assumed=0.06, terminal_growth=0.02,
    )
    res = value(base, a, wacc=0.08)  # roic 0.06 < wacc 0.08
    assert res.value_trap is True


def test_terminal_requires_wacc_gt_g():
    base = make_base()
    a = ProjectionAssumptions(
        years=5, revenue_growth=0.03, operating_margin=0.20,
        tax_rate=0.20, roic_assumed=0.10, terminal_growth=0.09,
    )
    with pytest.raises(ValueError):
        value(base, a, wacc=0.08)


# --- Phase 4 & 5 ------------------------------------------------------------

def test_sensitivity_grid_shape():
    base = make_base()
    a = ProjectionAssumptions(
        years=5, revenue_growth=0.04, operating_margin=0.20,
        tax_rate=0.20, roic_assumed=0.12, terminal_growth=0.025,
    )
    grid = sensitivity_grid(base, a, [0.07, 0.08, 0.09], [0.02, 0.03])
    assert len(grid["prices"]) == 3
    assert all(len(row) == 2 for row in grid["prices"])
    # higher WACC → lower price (monotonic down each column)
    for j in range(2):
        col = [grid["prices"][i][j] for i in range(3)]
        assert col[0] > col[1] > col[2]


def test_reverse_dcf_round_trip():
    """implied_growth should recover the growth that produced a price."""
    base = make_base()
    a = ProjectionAssumptions(
        years=5, revenue_growth=0.05, operating_margin=0.20,
        tax_rate=0.20, roic_assumed=0.12, terminal_growth=0.025,
    )
    wacc = 0.08
    price = value(base, a, wacc).target_price
    g = implied_growth(base, a, wacc, price)
    assert g is not None
    assert g == pytest.approx(0.05, abs=1e-4)
