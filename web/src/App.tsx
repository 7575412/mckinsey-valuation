import { useState } from "react";
import {
  valuateByTicker,
  valuateManual,
  sensitivity,
  type RawFinancials,
  type ValuationResponse,
  type SensitivityGrid,
  type ValuationRequestBody,
} from "./api";
import Heatmap from "./Heatmap";

const SAMPLE: RawFinancials = {
  year: 2024,
  revenue: 3000000,
  operating_income: 600000,
  pretax_income: 580000,
  tax_expense: 130000,
  receivables: 400000,
  inventory: 350000,
  operating_cash: 0,
  accounts_payable: 250000,
  accrued_liabilities: 100000,
  net_ppe: 1200000,
  net_operating_intangibles: 200000,
  total_debt: 500000,
  non_operating_assets: 600000,
  equity: 2400000,
  shares_outstanding: 100000,
};

const fmt = (x: number) => Math.round(x).toLocaleString();
const pct = (x: number) => (x * 100).toFixed(2) + "%";

export default function App() {
  const [mode, setMode] = useState<"ticker" | "manual">("manual");
  const [ticker, setTicker] = useState("005930");
  const [year, setYear] = useState(2024);
  const [growth, setGrowth] = useState(0.05);
  const [terminalGrowth, setTerminalGrowth] = useState(0.025);
  const [beta, setBeta] = useState(1.0);
  const [price, setPrice] = useState<number | "">("");
  const [base, setBase] = useState<RawFinancials>(SAMPLE);

  const [res, setRes] = useState<ValuationResponse | null>(null);
  const [grid, setGrid] = useState<SensitivityGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setError(null);
    setRes(null);
    setGrid(null);
    try {
      const priceNum = price === "" ? undefined : Number(price);
      let r: ValuationResponse;
      let body: ValuationRequestBody;
      if (mode === "ticker") {
        r = await valuateByTicker(ticker, {
          year,
          growth,
          terminal_growth: terminalGrowth,
          beta,
          price: priceNum,
        });
        body = {
          base: r.base,
          revenue_growth: growth,
          terminal_growth: terminalGrowth,
          beta,
          current_price: priceNum ?? null,
        };
      } else {
        body = {
          base,
          revenue_growth: growth,
          terminal_growth: terminalGrowth,
          beta,
          current_price: priceNum ?? null,
        };
        r = await valuateManual(body);
      }
      setRes(r);

      // Build a sensitivity grid centered on the computed WACC.
      const w = r.wacc;
      const waccs = [w - 0.01, w - 0.005, w, w + 0.005, w + 0.01].map((x) => +x.toFixed(4));
      const gs = [0.015, 0.02, 0.025, 0.03, 0.035];
      setGrid(await sensitivity(body, waccs, gs));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function field(key: keyof RawFinancials, label: string) {
    return (
      <label className="num">
        <span>{label}</span>
        <input
          type="number"
          value={base[key]}
          onChange={(e) => setBase({ ...base, [key]: Number(e.target.value) })}
        />
      </label>
    );
  }

  return (
    <div className="app">
      <h1>매킨지 가치평가 (DCF + 핵심 가치동인)</h1>

      <div className="tabs">
        <button className={mode === "manual" ? "active" : ""} onClick={() => setMode("manual")}>
          직접 입력
        </button>
        <button className={mode === "ticker" ? "active" : ""} onClick={() => setMode("ticker")}>
          DART 티커 (API 키 필요)
        </button>
      </div>

      <div className="card inputs">
        {mode === "ticker" ? (
          <div className="row">
            <label className="num">
              <span>티커</span>
              <input value={ticker} onChange={(e) => setTicker(e.target.value)} />
            </label>
            <label className="num">
              <span>연도</span>
              <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} />
            </label>
          </div>
        ) : (
          <div className="grid">
            {field("revenue", "매출액")}
            {field("operating_income", "영업이익")}
            {field("pretax_income", "세전이익")}
            {field("tax_expense", "법인세비용")}
            {field("receivables", "매출채권")}
            {field("inventory", "재고자산")}
            {field("accounts_payable", "매입채무")}
            {field("net_ppe", "유형자산")}
            {field("net_operating_intangibles", "무형자산")}
            {field("total_debt", "총차입금")}
            {field("non_operating_assets", "비영업자산")}
            {field("equity", "자기자본")}
            {field("shares_outstanding", "발행주식수")}
          </div>
        )}

        <div className="row assumptions">
          <label className="num">
            <span>매출성장률</span>
            <input type="number" step="0.01" value={growth} onChange={(e) => setGrowth(Number(e.target.value))} />
          </label>
          <label className="num">
            <span>영구성장률 g</span>
            <input type="number" step="0.005" value={terminalGrowth} onChange={(e) => setTerminalGrowth(Number(e.target.value))} />
          </label>
          <label className="num">
            <span>베타 β</span>
            <input type="number" step="0.1" value={beta} onChange={(e) => setBeta(Number(e.target.value))} />
          </label>
          <label className="num">
            <span>현재가 (선택)</span>
            <input type="number" value={price} onChange={(e) => setPrice(e.target.value === "" ? "" : Number(e.target.value))} />
          </label>
        </div>

        <button className="primary" onClick={run} disabled={loading}>
          {loading ? "계산 중…" : "가치평가 실행"}
        </button>
      </div>

      {error && <div className="card error">오류: {error}</div>}

      {res && (
        <>
          {res.result.value_trap && (
            <div className="card trap">
              ⚠️ <b>가치 함정 경고</b> — ROIC({pct(res.roic)}) &lt; WACC({pct(res.wacc)}): 성장할수록 가치를 훼손합니다.
            </div>
          )}

          <div className="cards">
            <Stat label="NOPLAT" value={fmt(res.noplat)} />
            <Stat label="투하자본" value={fmt(res.invested_capital)} />
            <Stat label="ROIC" value={pct(res.roic)} />
            <Stat label="WACC" value={pct(res.wacc)} />
            <Stat label="기업가치 (EV)" value={fmt(res.result.enterprise_value)} />
            <Stat label="주주가치" value={fmt(res.result.equity_value)} />
            <Stat label="목표주가" value={fmt(res.result.target_price)} highlight />
            {res.upside != null && (
              <Stat
                label="상승여력"
                value={(res.upside * 100).toFixed(1) + "%"}
                highlight
                positive={res.upside > 0}
              />
            )}
            {res.implied_growth != null && (
              <Stat label="내재 성장률 (역산)" value={pct(res.implied_growth)} />
            )}
          </div>

          {grid && <Heatmap grid={grid} />}
        </>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
  positive,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  positive?: boolean;
}) {
  return (
    <div className={`stat ${highlight ? "highlight" : ""}`}>
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${positive === true ? "up" : positive === false ? "down" : ""}`}>
        {value}
      </div>
    </div>
  );
}
