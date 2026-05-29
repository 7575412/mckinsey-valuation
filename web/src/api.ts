// Typed client for the valuation API. In dev, "/api/*" is proxied to :8000.

export interface RawFinancials {
  year: number;
  revenue: number;
  operating_income: number;
  pretax_income: number;
  tax_expense: number;
  receivables: number;
  inventory: number;
  operating_cash: number;
  accounts_payable: number;
  accrued_liabilities: number;
  net_ppe: number;
  net_operating_intangibles: number;
  total_debt: number;
  non_operating_assets: number;
  equity: number;
  shares_outstanding: number;
}

export interface ValuationResult {
  enterprise_value: number;
  pv_explicit_fcf: number;
  pv_terminal_value: number;
  terminal_value: number;
  equity_value: number;
  target_price: number;
  wacc: number;
  shares_outstanding: number;
  value_trap: boolean;
  yearly_fcf: number[];
  yearly_discounted_fcf: number[];
}

export interface ValuationResponse {
  base: RawFinancials;
  noplat: number;
  invested_capital: number;
  effective_tax_rate: number;
  roic: number;
  wacc: number;
  assumptions: Record<string, number>;
  result: ValuationResult;
  upside: number | null;
  implied_growth: number | null;
}

export interface SensitivityGrid {
  wacc: number[];
  growth: number[];
  prices: (number | null)[][];
}

export interface ValuationRequestBody {
  base: RawFinancials;
  years?: number;
  revenue_growth?: number;
  operating_margin?: number | null;
  roic_assumed?: number | null;
  terminal_growth?: number;
  tax_rate?: number;
  wacc?: number | null;
  beta?: number;
  current_price?: number | null;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

export async function valuateByTicker(
  ticker: string,
  params: { year: number; growth: number; terminal_growth: number; beta: number; price?: number }
): Promise<ValuationResponse> {
  const q = new URLSearchParams({
    year: String(params.year),
    growth: String(params.growth),
    terminal_growth: String(params.terminal_growth),
    beta: String(params.beta),
  });
  if (params.price) q.set("price", String(params.price));
  const r = await fetch(`/api/valuation/${ticker}?${q.toString()}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

export async function valuateManual(body: ValuationRequestBody): Promise<ValuationResponse> {
  return postJson<ValuationResponse>("/api/valuation", body);
}

export async function sensitivity(
  valuation: ValuationRequestBody,
  wacc_values: number[],
  growth_values: number[]
): Promise<SensitivityGrid> {
  return postJson<SensitivityGrid>("/api/sensitivity", {
    valuation,
    wacc_values,
    growth_values,
  });
}
