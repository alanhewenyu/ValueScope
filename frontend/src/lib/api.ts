/**
 * ValueScope API client — communicates with FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "valuescope_token";

function getAuthHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res.json();
}

// ── Types ──

export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string;
}

export interface CompanyProfile {
  symbol: string;
  company_name: string;
  industry: string;
  sector: string;
  country: string;
  currency: string;
  price: number;
  market_cap: number;
  beta: number;
  description: string;
  exchange: string;
  image: string;
}

export interface FinancialData {
  ticker: string;
  company_name: string;
  profile: Record<string, unknown>;
  share_info: Record<string, unknown>;
  summary: {
    columns: string[];
    index: string[];
    data: number[][];
  };
  formatted_summary: {
    columns: string[];
    index: string[];
    data: string[][];
  };
  ttm_note: string;
  ttm_latest_quarter: string;
  ttm_end_date: string;
  average_tax_rate: number;
  fy_end_month: number;
  freshness?: FreshnessInfo;
}

export interface FreshnessInfo {
  is_stale: boolean;
  expected_period?: string;
  data_source: string;
}

export interface DCFResult {
  ticker: string;
  company_name: string;
  dcf_price: number;
  dcf_price_converted: number;
  market_price: number;
  currency: string;
  reported_currency: string;
  forex_rate: number | null;
  diff_pct: number;
  valuation_params: Record<string, unknown>;
  wacc: {
    value: number;
    details: Record<string, unknown>;
  };
  results: {
    operating_value: number;
    equity_value: number;
    price_per_share: number;
    enterprise_value: number;
  };
  bridge: {
    pv_cashflows: number;
    pv_terminal_value: number;
    cash: number;
    total_investments: number;
    total_debt: number;
    minority_interest: number;
    outstanding_shares: number;
  };
  sensitivity: {
    growth_margin: {
      table: number[][];
      growth_rates: number[];
      margins: number[];
    };
    wacc: {
      results: Record<string, number>;
      base: number;
    };
  };
  ttm: {
    is_ttm: boolean;
    label: string;
    quarter: string;
  };
  forecast_table: ForecastRow[] | null;
  reverse_dcf?: {
    implied_growth_rate: number | null;
    growth_converged: boolean;
    your_growth: number;
    implied_ebit_margin: number | null;
    margin_converged: boolean;
    your_margin: number;
  } | null;
  buffett?: {
    available: boolean;
    reason?: string;
    owner_earnings?: number;
    net_income?: number;
    ni_label?: string;
    avg_wc?: number;
    discount_rate?: number;
    growth_phase1?: number;
    terminal_growth?: number;
    intrinsic_per_share?: number;
    margin_of_safety_price?: number;
    reported_currency?: string;
    avg_roe?: number;
    payout?: number;
  } | null;
}

export interface BuffettResult {
  available: boolean;
  reason?: string;
  owner_earnings?: number;
  net_income?: number;
  ni_label?: string;
  avg_wc?: number;
  da?: number;
  maintenance_capex?: number;
  discount_rate?: number;
  growth_phase1?: number;
  terminal_growth?: number;
  sustainable_growth?: number;
  avg_roe?: number;
  payout?: number;
  payout_year_offset?: number;
  intrinsic_per_share?: number;
  margin_of_safety_price?: number;
  reported_currency?: string;
  pv_cash_flows?: number;
  pv_terminal?: number;
  equity_value?: number;
  // From standalone endpoint
  forex_rate?: number | null;
  stock_currency?: string;
  market_price?: number | null;
}

export interface AIAnalysisResult {
  parameters: Record<string, { value: number; reasoning: string }>;
  reasoning: string;
  engine: string;
}

export interface GapAnalysisResult {
  analysis_text: string;
  adjusted_price: number | null;
  dcf_price: number;
  market_price: number;
  gap_pct: number;
  currency: string;
  engine: string;
}

export interface ForecastRow {
  Year: number;
  "Revenue Growth Rate": number | null;
  Revenue: number | null;
  "EBIT Margin": number | null;
  EBIT: number | null;
  "Tax to EBIT": number | null;
  "EBIT(1-t)": number | null;
  Reinvestments: number | null;
  FCFF: number | null;
  WACC: number | null;
  "Discount Factor": number | null;
  "PV (FCFF)": number | null;
}

export interface HistoryMetric {
  values: Record<string, number>;
  avg: number;
  min: number;
  max: number;
  latest: number;
}

export interface DCFDefaults {
  suggested: {
    revenue_growth_1: number;
    revenue_growth_2: number;
    ebit_margin: number;
    convergence: number;
    revenue_invested_capital_ratio_1: number;
    revenue_invested_capital_ratio_2: number;
    revenue_invested_capital_ratio_3: number;
  };
  history: {
    revenue_growth: HistoryMetric | null;
    ebit_margin: HistoryMetric | null;
    incremental_margin: HistoryMetric | null;
    revenue_ic: HistoryMetric | null;
    tax_rate: HistoryMetric | null;
  };
  average_tax_rate: number | null;
  base_year: number;
  base_year_label: string;
  forecast_year_1: number;
  fy_end_month: number;
  ttm_label: string;
  ttm_end_date: string;
}

export interface ValuationRatios {
  ticker: string;
  company_name: string;
  sector: string;
  industry: string;
  currency: string;
  price: number;
  market_cap: number;
  trailing_pe: number | null;
  forward_pe: number | null;
  price_to_book: number | null;
  price_to_sales: number | null;
  ev_to_ebitda: number | null;
  ev_to_revenue: number | null;
  enterprise_value: number;
  trailing_eps: number | null;
  forward_eps: number | null;
  book_value: number | null;
  profit_margins: number | null;
  return_on_equity: number | null;
  dividend_yield: number | null;
}

export interface HistoricalValuations {
  ticker: string;
  years: number;
  data_source?: string;
  pe_history: { date: string; value: number }[];
  pb_history: { date: string; value: number }[];
  pe_percentile: number | null;
  pb_percentile: number | null;
  pe_stats: {
    min: number;
    max: number;
    mean: number;
    median: number;
    current: number;
  } | null;
  pb_stats: {
    min: number;
    max: number;
    mean: number;
    median: number;
    current: number;
  } | null;
}

export interface RelativeValuationData {
  current: ValuationRatios;
  historical: HistoricalValuations;
}

export interface DimensionScore {
  score: number;
  weight: number;
  label: string;
}

export interface ScoresData {
  dimensions: {
    value: DimensionScore;
    quality: DimensionScore;
    growth: DimensionScore;
    momentum: DimensionScore;
  };
  total_score: number;
  has_benchmarks?: boolean;
}

// ── Transcript Analysis Types ──

export interface TranscriptQuarterResult {
  year: number;
  quarter: number;
  date: string;
  sentiment_score: number;
  tone: "bullish" | "neutral" | "cautious" | "bearish";
  key_themes: string[];
  guidance_direction: string;
  management_confidence: number;
  summary: string;
}

export interface TranscriptAnalysisResult {
  ticker: string;
  quarters_analyzed: number;
  results: TranscriptQuarterResult[];
  trend: {
    sentiment_direction: string;
    recurring_themes: string[];
    avg_confidence: number;
  };
  engine: string;
}

export interface EstimateQuarter {
  date: string;
  period: string;
  estimated_eps: number;
  actual_eps: number | null;
  eps_surprise_pct: number | null;
  estimated_revenue: number;
  number_of_analysts: number;
}

export interface EstimatesData {
  available: boolean;
  reason?: string;
  ticker?: string;
  estimates?: EstimateQuarter[];
  forward_estimates?: EstimateQuarter[];
  beat_count?: number;
  total_count?: number;
}

// ── API functions ──

export async function searchStocks(
  query: string,
  apikey = ""
): Promise<SearchResult[]> {
  const params = new URLSearchParams({ q: query });
  if (apikey) params.set("apikey", apikey);
  return fetchAPI<SearchResult[]>(`/api/stock/search?${params}`);
}

export async function getProfile(
  ticker: string,
  apikey = ""
): Promise<CompanyProfile> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI<CompanyProfile>(`/api/stock/profile/${ticker}${params}`);
}

export async function getFinancials(
  ticker: string,
  apikey = ""
): Promise<FinancialData> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI<FinancialData>(`/api/stock/financials/${ticker}${params}`);
}

export async function getWACC(
  ticker: string,
  apikey = ""
): Promise<{ wacc: number; risk_free_rate: number; details: Record<string, unknown> }> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI(`/api/valuation/wacc/${ticker}${params}`);
}

export async function runDCF(params: {
  ticker: string;
  apikey?: string;
  revenue_growth_1: number;
  revenue_growth_2: number;
  ebit_margin: number;
  convergence: number;
  revenue_invested_capital_ratio_1: number;
  revenue_invested_capital_ratio_2: number;
  revenue_invested_capital_ratio_3: number;
  tax_rate?: number;
  wacc?: number;
  ronic_match_wacc?: boolean;
}): Promise<DCFResult> {
  return fetchAPI<DCFResult>("/api/valuation/dcf", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getDCFDefaults(
  ticker: string,
  apikey = ""
): Promise<DCFDefaults> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI<DCFDefaults>(`/api/valuation/dcf-defaults/${ticker}${params}`);
}

export async function getBuffettValuation(
  ticker: string,
  apikey = ""
): Promise<BuffettResult> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI<BuffettResult>(`/api/valuation/buffett/${ticker}${params}`);
}

export async function getRelativeValuation(
  ticker: string,
  apikey = "",
  years = 5
): Promise<RelativeValuationData> {
  const params = new URLSearchParams();
  if (apikey) params.set("apikey", apikey);
  params.set("years", String(years));
  return fetchAPI<RelativeValuationData>(
    `/api/analysis/valuation/${ticker}?${params}`
  );
}

export async function getScores(
  ticker: string,
  apikey = ""
): Promise<ScoresData> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI<ScoresData>(`/api/analysis/scores/${ticker}${params}`);
}

export async function getEstimates(
  ticker: string,
  apikey = ""
): Promise<EstimatesData> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI<EstimatesData>(`/api/stock/estimates/${ticker}${params}`);
}

export async function runTranscriptAnalysis(
  ticker: string,
  apikey: string,
  deepseekKey: string,
  quarters: number = 4,
  onProgress?: (msg: string) => void,
): Promise<TranscriptAnalysisResult> {
  const res = await fetch(`${API_BASE}/api/stock/transcript-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, apikey, quarters, deepseek_key: deepseekKey }),
  });

  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch { /* ignore */ }
    throw new Error(detail);
  }

  // Check if response is JSON (cached result) or SSE stream
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }

  // SSE streaming
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let result: TranscriptAnalysisResult | null = null;
  let errorMsg = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    let eventType = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          if (eventType === "progress" && onProgress) onProgress(data.message || "");
          else if (eventType === "result") result = data as TranscriptAnalysisResult;
          else if (eventType === "error") errorMsg = data.message || "Transcript analysis failed";
        } catch { /* ignore */ }
        eventType = "";
      }
    }
  }

  if (errorMsg) throw new Error(errorMsg);
  if (!result) throw new Error("Transcript analysis returned no result");
  return result;
}

export async function getIndexMembership(
  ticker: string,
  apikey = ""
): Promise<{ ticker: string; indexes: string[] }> {
  const params = apikey ? `?apikey=${apikey}` : "";
  return fetchAPI(`/api/stock/indexes/${ticker}${params}`);
}

/**
 * Run AI analysis with SSE streaming for progress updates.
 */

export interface AIQuota {
  limit: number;
  used: number;
  remaining: number;
}

export async function getAIQuota(): Promise<AIQuota> {
  return fetchAPI<AIQuota>("/api/valuation/ai-quota");
}

/**
 * @param onProgress - called with progress message string
 * @returns final AI analysis result
 */
export async function runAIAnalysis(
  ticker: string,
  apikey = "",
  serperKey = "",
  deepseekKey = "",
  onProgress?: (message: string) => void
): Promise<AIAnalysisResult> {
  const res = await fetch(`${API_BASE}/api/valuation/ai-analyze-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, apikey, serper_key: serperKey, deepseek_key: deepseekKey }),
  });

  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let result: AIAnalysisResult | null = null;
  let errorMsg = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    const lines = buffer.split("\n");
    buffer = lines.pop() || ""; // keep incomplete line

    let eventType = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const dataStr = line.slice(6);
        try {
          const data = JSON.parse(dataStr);
          if (eventType === "progress" && onProgress) {
            onProgress(data.message || "");
          } else if (eventType === "result") {
            result = data as AIAnalysisResult;
          } else if (eventType === "error") {
            errorMsg = data.message || "AI analysis failed";
          }
        } catch { /* ignore parse errors */ }
        eventType = "";
      }
    }
  }

  if (errorMsg) throw new Error(errorMsg);
  if (!result) throw new Error("AI analysis returned no result");
  return result;
}

export async function runGapAnalysis(
  params: {
    ticker: string;
    apikey?: string;
    serper_key?: string;
    deepseek_key?: string;
    dcf_price: number;
    market_price: number;
    valuation_params: Record<string, unknown>;
    bridge: Record<string, number>;
    forex_rate?: number | null;
    reported_currency?: string;
  },
  onProgress?: (message: string) => void
): Promise<GapAnalysisResult> {
  const res = await fetch(`${API_BASE}/api/valuation/gap-analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!res.ok) {
    const text = await res.text();
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";
  let result: GapAnalysisResult | null = null;
  let errorMsg = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    let eventType = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          if (eventType === "progress" && onProgress) onProgress(data.message || "");
          else if (eventType === "result") result = data as GapAnalysisResult;
          else if (eventType === "error") errorMsg = data.message || "Gap analysis failed";
        } catch { /* ignore */ }
        eventType = "";
      }
    }
  }

  if (errorMsg) throw new Error(errorMsg);
  if (!result) throw new Error("Gap analysis returned no result");
  return result;
}

export async function saveValuationToServer(params: {
  ticker: string;
  company_name: string;
  mode: string;
  ai_engine?: string;
  valuation_params: Record<string, unknown>;
  dcf_results: Record<string, unknown>;
  company_profile: Record<string, unknown>;
  gap_analysis?: Record<string, unknown> | null;
  ai_result?: Record<string, unknown> | null;
  sensitivity?: Record<string, unknown> | null;
  financial_summary?: Record<string, unknown> | null;
  forex_rate?: number | null;
}): Promise<{ saved: boolean; id?: number; reason?: string }> {
  return fetchAPI("/api/valuation/save", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ── Portfolio API ──

export interface PortfolioStatus {
  available: boolean;
  db_path: string | null;
}

export interface PortfolioHolding {
  ticker: string;
  name: string;
  market: string;
  broker: string;
  quantity: number;
  cost_price: number;
  currency: string;
  status: string;
  price: number;
  price_stale: boolean;
  market_value: number;
  market_value_cny: number;
  cost_total: number;
  pnl: number;
  pnl_pct: number;
  pnl_cny: number;
  daily_pnl: number | null;
  daily_pnl_pct: number | null;
  daily_pnl_cny: number | null;
  ytd_pnl: number | null;
  ytd_pnl_pct: number | null;
  ytd_pnl_cny: number | null;
  sector: string;
  industry: string;
  dcf_price: number | null;
  mos_pct: number | null;
  weight: number;
}

export interface PortfolioSummary {
  equity_cny: number;
  cash_cny: number;
  leverage_cny: number;
  total_assets: number;
  net_assets: number;
  capital: number;
  total_pnl_cny: number;
  total_pnl_capital: number;
  total_cost_cny: number;
  total_pnl_pct: number;
  daily_pnl_cny: number;
  ytd_pnl_cny: number;
}

export interface CashBalance {
  account: string;
  currency: string;
  balance: number;
}

export interface PortfolioData {
  holdings: PortfolioHolding[];
  fx: Record<string, number>;
  cash: CashBalance[];
  summary: PortfolioSummary;
  ytd_realized_by_market?: Record<string, number>;
}

export interface NavHistoryPoint {
  date: string;
  net_asset_value: number;
  capital_invested: number;
  pnl: number;
  equity_nav: number;
  benchmark_value: number | null;
}

export interface ClosedTrade {
  id: number;
  ticker: string | null;
  name: string;
  market: string;
  broker: string;
  currency: string;
  quantity: number | null;
  cost_price: number | null;
  close_price: number | null;
  realized_pnl: number;
  realized_pnl_cny: number | null;
  close_date: string | null;
  notes: string | null;
  cost_total: number | null;
}

export interface Snapshot {
  date: string;
  total_assets: number | null;
  net_assets: number | null;
  equity_mv_cny: number | null;
  cash_cny: number | null;
  leverage_cny: number | null;
  total_pnl_cny: number | null;
  market_data: string | null;
  capital: number | null;
  market_pnl: string | null;
  realized_pnl_cny: number | null;
}

export interface MarginBalance {
  id: number;
  broker: string;
  category: string;
  currency: string;
  amount: number;
}

export interface PositionInput {
  ticker: string;
  name: string;
  market: string;
  broker: string;
  quantity: number;
  cost_price: number;
  currency: string;
}

export interface CashInput {
  account: string;
  currency: string;
  balance: number;
}

export interface ClosedTradeInput {
  ticker: string;
  name: string;
  market: string;
  broker: string;
  quantity: number;
  buy_price: number;
  sell_price: number;
  realized_pnl: number;
  realized_pnl_cny: number;
  currency: string;
}

export async function getPortfolioStatus(): Promise<PortfolioStatus> {
  return fetchAPI<PortfolioStatus>("/api/portfolio/status");
}

export interface PortfolioInfo { name: string; active: boolean; }
export async function listPortfolios(): Promise<PortfolioInfo[]> {
  return fetchAPI<PortfolioInfo[]>("/api/portfolio/portfolios");
}
export async function switchPortfolio(name: string): Promise<void> {
  await fetchAPI<unknown>(`/api/portfolio/portfolios/switch?name=${encodeURIComponent(name)}`, { method: "POST" });
}

export async function getPortfolioHoldings(): Promise<PortfolioData> {
  return fetchAPI<PortfolioData>("/api/portfolio/holdings");
}

export async function getPortfolioFxRates(): Promise<Record<string, number>> {
  return fetchAPI<Record<string, number>>("/api/portfolio/fx-rates");
}

export async function getNavHistory(): Promise<NavHistoryPoint[]> {
  return fetchAPI<NavHistoryPoint[]>("/api/portfolio/nav-history");
}

export async function getClosedTrades(): Promise<ClosedTrade[]> {
  return fetchAPI<ClosedTrade[]>("/api/portfolio/closed-trades");
}

export async function getSnapshots(limit = 90): Promise<Snapshot[]> {
  return fetchAPI<Snapshot[]>(`/api/portfolio/snapshots?limit=${limit}`);
}

export async function getMarginBalances(): Promise<MarginBalance[]> {
  return fetchAPI<MarginBalance[]>("/api/portfolio/margin");
}

export interface MarginInput {
  broker: string;
  category: string;
  currency: string;
  amount: number;
}

export async function updateMargin(data: MarginInput): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>("/api/portfolio/margin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export interface BenchmarkPoint { date: string; close: number; }

export async function getBenchmarks(start: string): Promise<Record<string, BenchmarkPoint[]>> {
  return fetchAPI<Record<string, BenchmarkPoint[]>>(`/api/portfolio/benchmarks?start=${start}`);
}

export async function upsertPosition(data: PositionInput): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>("/api/portfolio/positions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deletePosition(ticker: string, broker: string): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>(`/api/portfolio/positions/${encodeURIComponent(ticker)}/${encodeURIComponent(broker)}`, {
    method: "DELETE",
  });
}

export async function updateCash(data: CashInput): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>("/api/portfolio/cash", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteCash(account: string, currency: string): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>(`/api/portfolio/cash/${encodeURIComponent(account)}/${encodeURIComponent(currency)}`, {
    method: "DELETE",
  });
}

export async function addClosedTrade(data: ClosedTradeInput): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>("/api/portfolio/closed-trades", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// ── Account Settings (Capital Mode) ──

export interface AccountSetting {
  broker: string;
  capital_mode: string;  // 'cost' | 'deposit'
  deposit_cny: number;
  deposit_fx: number;
  notes: string | null;
  updated_at: string;
}

export interface AccountSettingInput {
  broker: string;
  capital_mode: string;
  deposit_cny?: number;
  deposit_fx?: number;
  notes?: string;
}

export async function getAccountSettings(): Promise<AccountSetting[]> {
  return fetchAPI<AccountSetting[]>("/api/portfolio/account-settings");
}

export async function upsertAccountSetting(data: AccountSettingInput): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>("/api/portfolio/account-settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteAccountSetting(broker: string): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>(`/api/portfolio/account-settings/${encodeURIComponent(broker)}`, {
    method: "DELETE",
  });
}

// ── Deposit History API ──

export interface DepositRecord {
  id: number;
  broker: string;
  amount_cny: number;
  fx_rate: number;
  deposit_date: string | null;
  notes: string | null;
  created_at: string;
}

export interface DepositRecordInput {
  broker: string;
  amount_cny: number;
  fx_rate?: number;
  deposit_date?: string;
  notes?: string;
}

export async function getDepositHistory(broker: string): Promise<DepositRecord[]> {
  return fetchAPI<DepositRecord[]>(`/api/portfolio/deposit-history/${encodeURIComponent(broker)}`);
}

export async function addDepositRecord(data: DepositRecordInput): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>("/api/portfolio/deposit-history", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteDepositRecord(id: number): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>(`/api/portfolio/deposit-history/${id}`, { method: "DELETE" });
}

// ── Valuation History API ──

export interface HistoryStatus {
  available: boolean;
  count: number;
}

export interface HistoryFilters {
  modes: string[];
  engines: string[];
}

export interface ValuationRecord {
  id: number;
  ticker: string;
  company_name: string;
  valuation_date: string;
  mode: string;
  ai_engine: string | null;
  source: string | null;
  currency: string;
  reported_currency: string | null;
  price_per_share: number | null;
  gap_dcf_price: number | null;
  market_price: number | null;
  gap_market_price: number | null;
  gap_pct: number | null;
  gap_adjusted_price: number | null;
  gap_adjusted_price_reporting: number | null;
  forex_rate: number | null;
  revenue_growth_1: number | null;
  revenue_growth_2: number | null;
  ebit_margin: number | null;
  wacc: number | null;
  base_year: number | null;
  ttm_label: string | null;
}

export interface ValuationDetail extends ValuationRecord {
  beta: number | null;
  market_cap: number | null;
  outstanding_shares: number | null;
  pv_cf_10yr: number | null;
  pv_terminal: number | null;
  enterprise_value: number | null;
  equity_value: number | null;
  cash: number | null;
  total_debt: number | null;
  minority_interest: number | null;
  total_investments: number | null;
  convergence: number | null;
  rev_ic_ratio_1: number | null;
  rev_ic_ratio_2: number | null;
  rev_ic_ratio_3: number | null;
  tax_rate: number | null;
  terminal_wacc: number | null;
  ronic: number | null;
  risk_free_rate: number | null;
  gap_analysis_text: string | null;
  summary_json: Record<string, unknown> | null;
  dcf_table_json: Record<string, unknown> | null;
  sensitivity_json: Record<string, unknown> | null;
  wacc_sensitivity_json: Record<string, unknown> | null;
  ai_parameters_json: Record<string, unknown> | null;
  ai_raw_text: string | null;
}

export interface CompareResult {
  ticker: string;
  price_per_share: number | null;
  gap_dcf_price: number | null;
  market_price: number | null;
  gap_market_price: number | null;
  gap_pct: number | null;
  currency: string;
  valuation_date: string;
  current_price: number | null;
  current_currency: string | null;
  current_gap_pct: number | null;
}

export async function getHistoryStatus(): Promise<HistoryStatus> {
  return fetchAPI<HistoryStatus>("/api/history/status");
}

export async function getHistoryFilters(): Promise<HistoryFilters> {
  return fetchAPI<HistoryFilters>("/api/history/filters");
}

export async function searchValuations(params: {
  q?: string;
  modes?: string;
  engines?: string;
  date_start?: string;
  date_end?: string;
  limit?: number;
  offset?: number;
}): Promise<{ results: ValuationRecord[]; count: number }> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.modes) qs.set("modes", params.modes);
  if (params.engines) qs.set("engines", params.engines);
  if (params.date_start) qs.set("date_start", params.date_start);
  if (params.date_end) qs.set("date_end", params.date_end);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  return fetchAPI(`/api/history/search?${qs}`);
}

export async function getValuationDetail(id: number): Promise<ValuationDetail> {
  return fetchAPI<ValuationDetail>(`/api/history/${id}`);
}

export async function deleteValuation(id: number): Promise<{ ok: boolean }> {
  return fetchAPI(`/api/history/${id}`, { method: "DELETE" });
}

export async function compareValuation(id: number): Promise<CompareResult> {
  return fetchAPI<CompareResult>(`/api/history/${id}/compare`);
}

// ── Portfolio Import / Export ──

export interface ImportResult {
  ok: boolean;
  type: string;
  imported: number;
  imported_positions?: number;
  imported_cash?: number;
  accounts_created: string[];
  errors: string[];
  warnings?: string[];
}

export function getImportTemplateUrl(type: "positions" | "cash" | "portfolio"): string {
  return `${API_BASE}/api/portfolio/import-template/${type}`;
}

export async function importCSV(file: File): Promise<ImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  return fetchAPI<ImportResult>("/api/portfolio/import", {
    method: "POST",
    body: formData,
  });
}

export async function exportPortfolio(): Promise<Record<string, unknown[]>> {
  return fetchAPI<Record<string, unknown[]>>("/api/portfolio/export");
}

// ── Portfolio Event Feeds ──

export interface PortfolioNewsItem {
  title: string;
  url: string;
  source: string;
  date: string;
  ticker: string;
  image: string;
}

export interface PortfolioEarningsEvent {
  ticker: string;
  name: string;
  date: string;
  eps_estimated: number | null;
  eps_actual: number | null;
  revenue_estimated: number | null;
  revenue_actual: number | null;
  status: "upcoming" | "reported";
}

export interface PortfolioRatingChange {
  ticker: string;
  name: string;
  date: string;
  company: string;
  previous: string;
  new: string;
  direction: "upgrade" | "downgrade" | "maintain";
}

export async function getPortfolioNews(apikey = ""): Promise<PortfolioNewsItem[]> {
  return fetchAPI<PortfolioNewsItem[]>(`/api/portfolio/news?apikey=${apikey}`);
}

export async function getPortfolioEarnings(apikey = ""): Promise<PortfolioEarningsEvent[]> {
  return fetchAPI<PortfolioEarningsEvent[]>(`/api/portfolio/earnings-calendar?apikey=${apikey}`);
}

export async function getPortfolioRatings(apikey = ""): Promise<PortfolioRatingChange[]> {
  return fetchAPI<PortfolioRatingChange[]>(`/api/portfolio/rating-changes?apikey=${apikey}`);
}

// ── Admin API ──

export interface AdminStats {
  total_users: number;
  total_valuations: number;
  today_signups: number;
  db_size_mb: { valuations: number; portfolio: number };
  disk: { total_gb: number | null; free_gb: number | null; used_pct: number | null };
}

export interface AdminUser {
  id: string;
  email: string;
  created_at: string;
  valuation_count: number;
  portfolio_count: number;
}

export interface AdminSystem {
  python_version: string;
  api_keys: Record<string, boolean>;
  data_dir: string;
  disk: { total_gb: number | null; free_gb: number | null };
}

export async function getAdminStats(): Promise<AdminStats> {
  return fetchAPI<AdminStats>("/api/admin/stats");
}

export async function getAdminUsers(): Promise<{ users: AdminUser[] }> {
  return fetchAPI<{ users: AdminUser[] }>("/api/admin/users");
}

export async function deleteAdminUser(userId: string): Promise<{ ok: boolean }> {
  return fetchAPI<{ ok: boolean }>(`/api/admin/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
}

export async function getAdminSystem(): Promise<AdminSystem> {
  return fetchAPI<AdminSystem>("/api/admin/system");
}
