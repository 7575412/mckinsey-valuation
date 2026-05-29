"""End-to-end CLI: ticker (or JSON) → ROIC / WACC / target price.

Examples:
  python cli.py 005930 --year 2024            # live Open DART fetch
  python cli.py --from-json sample_company.json
  python cli.py 005930 --year 2024 --price 70000 --beta 1.1
"""

from __future__ import annotations

import argparse
import json
import sys

# Korean output needs UTF-8 even on a cp949 Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional
    pass

from engine.dcf import value
from engine.drivers import compute_drivers
from engine.models import ProjectionAssumptions, RawFinancials, WaccInputs
from engine.reorg import reorganize
from engine.reverse_dcf import implied_growth
from engine.wacc import compute_wacc


def _load_base(args) -> RawFinancials:
    if args.from_json:
        with open(args.from_json, encoding="utf-8") as fh:
            return RawFinancials(**json.load(fh))
    if args.from_pdf:
        from data.pdf_parse import extract_from_pdf  # lazy: needs anthropic + pypdf

        return extract_from_pdf(args.from_pdf, args.year)
    from data.dart_client import fetch_raw_financials  # lazy: needs network/key

    return fetch_raw_financials(args.ticker, args.year, fs_div=args.fs_div)


def _build_wacc(args, base: RawFinancials) -> float:
    if args.wacc is not None:
        return args.wacc
    market_equity = (
        args.price * base.shares_outstanding if args.price else base.equity
    )
    if market_equity <= 0:
        market_equity = 1.0
    return compute_wacc(
        WaccInputs(
            risk_free_rate=args.rf,
            equity_risk_premium=args.erp,
            beta=args.beta,
            pretax_cost_of_debt=args.kd,
            tax_rate=args.tax,
            market_value_equity=market_equity,
            market_value_debt=base.total_debt,
        )
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="McKinsey-style valuation")
    p.add_argument("ticker", nargs="?", help="6-digit Korean ticker, e.g. 005930")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--fs-div", default="CFS", choices=["CFS", "OFS"])
    p.add_argument("--from-json", help="load RawFinancials from a JSON file instead")
    p.add_argument("--from-pdf", help="extract RawFinancials from an annual-report PDF (needs ANTHROPIC_API_KEY)")

    # Projection assumptions (auto-derived from base if omitted)
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--growth", type=float, help="explicit revenue growth (default 5%%)")
    p.add_argument("--margin", type=float, help="operating margin (default = base)")
    p.add_argument("--roic", type=float, help="assumed ROIC (default = base ROIC)")
    p.add_argument("--terminal-growth", type=float, default=0.025)

    # WACC
    p.add_argument("--wacc", type=float, help="use this WACC directly")
    p.add_argument("--rf", type=float, default=0.035)
    p.add_argument("--erp", type=float, default=0.06)
    p.add_argument("--beta", type=float, default=1.0)
    p.add_argument("--kd", type=float, default=0.05, help="pretax cost of debt")
    p.add_argument("--tax", type=float, default=0.22)
    p.add_argument("--price", type=float, help="current price (for market equity & reverse DCF)")
    args = p.parse_args(argv)

    if not args.ticker and not args.from_json and not args.from_pdf:
        p.error("provide a ticker, --from-json, or --from-pdf")

    base = _load_base(args)
    reorg = reorganize(base)
    [driven] = compute_drivers([reorg])
    wacc = _build_wacc(args, base)

    margin = args.margin if args.margin is not None else (
        base.operating_income / base.revenue if base.revenue else 0.0
    )
    base_roic = driven.roic or 0.10
    roic_assumed = args.roic if args.roic is not None else max(base_roic, 0.01)
    growth = args.growth if args.growth is not None else 0.05

    assumptions = ProjectionAssumptions(
        years=args.years,
        revenue_growth=growth,
        operating_margin=margin,
        tax_rate=args.tax,
        roic_assumed=roic_assumed,
        terminal_growth=args.terminal_growth,
    )
    result = value(base, assumptions, wacc)

    def fmt(x: float) -> str:
        return f"{x:,.0f}"

    print(f"\n=== {args.ticker or args.from_json}  (FY{base.year}) ===")
    print("-- Reorganized --")
    print(f"  NOPLAT             : {fmt(reorg.noplat)}")
    print(f"  Invested Capital   : {fmt(reorg.invested_capital)}")
    print(f"  Effective tax rate : {reorg.effective_tax_rate:.1%}")
    print(f"  ROIC               : {base_roic:.1%}")
    print("-- Cost of capital --")
    print(f"  WACC               : {wacc:.2%}")
    if base_roic < wacc:
        print("  ⚠️  VALUE TRAP: ROIC < WACC — 성장이 가치를 훼손합니다.")
    print("-- Valuation --")
    print(f"  Enterprise Value   : {fmt(result.enterprise_value)}")
    print(f"    PV explicit FCF  : {fmt(result.pv_explicit_fcf)}")
    print(f"    PV terminal      : {fmt(result.pv_terminal_value)}")
    print(f"  Equity Value       : {fmt(result.equity_value)}")
    print(f"  Shares outstanding : {fmt(result.shares_outstanding)}")
    print(f"  >> TARGET PRICE    : {fmt(result.target_price)}")
    if args.price:
        upside = result.target_price / args.price - 1.0
        print(f"  Current price      : {fmt(args.price)}  (upside {upside:+.1%})")
        g_imp = implied_growth(base, assumptions, wacc, args.price)
        if g_imp is not None:
            print(f"  Implied growth     : {g_imp:.2%}  (현재가 정당화에 필요한 성장률)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
