/**
 * ValueScope API client — communicates with FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
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
