"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import Navbar from "@/components/Navbar";
import CompanyHeader from "@/components/CompanyHeader";
import OverviewTab from "@/components/stock/OverviewTab";
import RelativeValuationTab from "@/components/stock/RelativeValuationTab";
import ScoringTab from "@/components/stock/ScoringTab";
import InsightsTab from "@/components/stock/InsightsTab";
import {
  getProfile,
  getFinancials,
  getWACC,
  getRelativeValuation,
  getScores,
  getIndexMembership,
  runDCF,
  getDCFDefaults,
  runAIAnalysis,
  runGapAnalysis,
  saveValuationToServer,
  getEstimates,
  getAIQuota,
  type AIQuota,
  type EstimatesData,
  type CompanyProfile,
  type FinancialData,
  type RelativeValuationData,
  type ScoresData,
  type DCFResult,
  type DCFDefaults,
  type HistoryMetric,
  type AIAnalysisResult,
  type GapAnalysisResult,
  type BuffettResult,
  getBuffettValuation,
  downloadDCFExcel,
} from "@/lib/api";
import ReactMarkdown from "react-markdown";
import { formatCurrency, formatLargeNumber, formatNumber } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/lib/settings";

type TabId = "overview" | "dcf" | "relative" | "scoring" | "insights";

export default function StockPage() {
  const params = useParams();
  const ticker = (params.ticker as string) || "";
  const { t, locale } = useI18n();
  const { fmpApiKey, serperApiKey, deepseekApiKey, ready } = useSettings();

  const [profile, setProfile] = useState<CompanyProfile | null>(null);
  const [financials, setFinancials] = useState<FinancialData | null>(null);
  const [wacc, setWacc] = useState<{
    wacc: number;
    risk_free_rate: number;
    details: Record<string, unknown>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [indexes, setIndexes] = useState<string[]>([]);
  // Shared data — fetched once, used by Overview + Scoring + Relative tabs
  const [scores, setScores] = useState<ScoresData | null>(null);
  const [relVal, setRelVal] = useState<RelativeValuationData | null>(null);
  const [estimates, setEstimates] = useState<EstimatesData | null>(null);
  // Pre-fetched DCF defaults (loaded early so DCF tab opens instantly)
  const [prefetchedDefaults, setPrefetchedDefaults] = useState<DCFDefaults | null>(null);

  useEffect(() => {
    if (!ticker || !ready) return;
    const decodedTicker = decodeURIComponent(ticker);
    const apikey = fmpApiKey;
    let cancelled = false;

    setLoading(true);
    setError("");

    // Phase 1: Critical data (profile, financials) — blocks page render
    // Track whether failures are network errors (backend down) vs data not found
    let backendDown = false;
    function catchWithDetect<T>(p: Promise<T>): Promise<T | null> {
      return p.catch((e) => {
        if (e instanceof TypeError && /fetch|network/i.test(e.message)) backendDown = true;
        return null;
      });
    }

    const corePromise = Promise.all([
      catchWithDetect(getProfile(decodedTicker, apikey)),
      catchWithDetect(getFinancials(decodedTicker, apikey)),
    ]);

    // Fire ALL secondary requests in parallel with Phase 1 (backend has
    // per-ticker cache locks — only one thread fetches, rest wait for cache)
    getIndexMembership(decodedTicker, apikey)
      .then((res) => { if (!cancelled) setIndexes(res.indexes || []); })
      .catch(() => { if (!cancelled) setIndexes([]); });
    getScores(decodedTicker, apikey)
      .then((d) => { if (!cancelled) setScores(d); })
      .catch(() => {});
    getRelativeValuation(decodedTicker, apikey, 5)
      .then((d) => { if (!cancelled) setRelVal(d); })
      .catch(() => {});
    getEstimates(decodedTicker, apikey)
      .then((d) => { if (!cancelled) setEstimates(d); })
      .catch(() => {});
    // DCF tab data — fire immediately (backend caches financials for all endpoints)
    getDCFDefaults(decodedTicker, apikey)
      .then((d) => { if (!cancelled) setPrefetchedDefaults(d); })
      .catch(() => {});
    getWACC(decodedTicker, apikey)
      .then((d) => { if (!cancelled) setWacc(d); })
      .catch(() => {});

    corePromise
      .then(([p, f]) => {
        if (cancelled) return;
        if (!p && !f) {
          setError(backendDown ? "__backend_down__" : decodedTicker);
        }
        setProfile(p);
        if (p?.company_name) {
          document.title = `${p.company_name} (${decodedTicker}) | ValueScope`;
        }
        setFinancials(f);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [ticker, ready, fmpApiKey]);

  if (loading) {
    return (
      <>
        <Navbar />
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          <span className="ml-3 text-gray-500">
            {t.loadingTicker(decodeURIComponent(ticker))}
          </span>
        </div>
      </>
    );
  }

  if (error) {
    const isBackendDown = error === "__backend_down__";
    // US stocks (no dot suffix) and JP stocks (.T suffix) require FMP API key
    const decodedTicker = decodeURIComponent(ticker).toUpperCase();
    const isLikelyUS = !decodedTicker.includes(".");
    const isLikelyJP = decodedTicker.endsWith(".T");
    const needsApiKey = (isLikelyUS || isLikelyJP) && !fmpApiKey;
    return (
      <>
        <Navbar />
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center">
            {needsApiKey ? (
              <>
                <p className="text-xl text-amber-600 dark:text-amber-400 mb-2">
                  {locale === "zh"
                    ? `${isLikelyJP ? "日股" : "美股"}数据需要 FMP API Key`
                    : `${isLikelyJP ? "Japanese" : "US"} stock data requires an FMP API Key`}
                </p>
                <p className="text-sm text-gray-400">
                  {locale === "zh"
                    ? "请点击右上角 ⚙ 设置 FMP API Key"
                    : "Please set it in ⚙ Settings (top right)"}
                </p>
              </>
            ) : isBackendDown ? (
              <>
                <p className="text-xl text-gray-500 mb-2">
                  {locale === "zh" ? "无法连接后端服务" : "Cannot connect to backend service"}
                </p>
                <p className="text-sm text-gray-400">
                  {locale === "zh"
                    ? "请确认后端已启动 (uvicorn backend.main:app)"
                    : "Please make sure the backend is running (uvicorn backend.main:app)"}
                </p>
              </>
            ) : (
              <>
                <p className="text-xl text-gray-500 mb-2">{t.errorNotFound(error)}</p>
                <p className="text-sm text-gray-400">
                  {t.errorHelp}
                </p>
              </>
            )}
          </div>
        </div>
      </>
    );
  }

  const decodedTicker = decodeURIComponent(ticker);

  // Check if ticker requires FMP API key (US stocks: no suffix; JP stocks: .T suffix)
  const needsFmpKey = !decodedTicker.includes(".") || decodedTicker.endsWith(".T");
  const showFmpWarning = needsFmpKey && !fmpApiKey.trim();

  const tabs: { id: TabId; label: string }[] = [
    { id: "overview", label: t.tabOverview },
    { id: "dcf", label: t.tabDCF },
    { id: "relative", label: t.tabRelative },
    { id: "scoring", label: t.tabScoring },
    { id: "insights", label: t.tabInsights },
  ];

  return (
    <>
      <Navbar />
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Company header */}
        {profile && (
          <CompanyHeader
            companyName={profile.company_name}
            ticker={profile.symbol}
            price={profile.price}
            currency={profile.currency}
            marketCap={profile.market_cap}
            industry={profile.industry}
            sector={profile.sector}
            exchange={profile.exchange}
            country={profile.country}
            image={profile.image}
            indexes={indexes}
          />
        )}

        {/* FMP API key warning for US/JP stocks */}
        {showFmpWarning && (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/30 px-4 py-3">
            <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <p className="text-sm text-amber-800 dark:text-amber-200 flex-1">
              {t.warnFmpRequired}
            </p>
          </div>
        )}

        {/* Tab navigation */}
        <div className="border-b border-gray-200 dark:border-gray-800 mb-6">
          <div className="flex gap-1 -mb-px overflow-x-auto">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3 py-2.5 sm:px-4 sm:py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap
                  ${
                    activeTab === tab.id
                      ? "border-blue-500 text-blue-600 dark:text-blue-400"
                      : "border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                  }
                `}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        {activeTab === "overview" && (
          <OverviewTab
            profile={profile}
            financials={financials}
            wacc={wacc}
            ticker={decodedTicker}
            scores={scores}
            relVal={relVal}
            freshness={financials?.freshness}
            estimates={estimates}
            apikey={fmpApiKey}
            deepseekKey={deepseekApiKey}
          />
        )}
        {activeTab === "dcf" && <DCFTab ticker={decodedTicker} waccData={wacc} financials={financials} profile={profile} prefetchedDefaults={prefetchedDefaults} />}
        {activeTab === "relative" && (
          <RelativeValuationTab ticker={decodedTicker} initialData={relVal} />
        )}
        {activeTab === "scoring" && <ScoringTab ticker={decodedTicker} initialScores={scores} />}
        {activeTab === "insights" && (
          <InsightsTab
            ticker={decodedTicker}
            estimates={estimates}
            apikey={fmpApiKey}
            deepseekKey={deepseekApiKey}
          />
        )}
      </div>
    </>
  );
}

// ── DCF Tab helpers ──

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">{label}</div>
      <div className="text-lg font-semibold text-gray-900 dark:text-white">{value}</div>
    </div>
  );
}

function HistoryHint({ metric, t, periodLabel, label }: { metric: HistoryMetric | null; t: ReturnType<typeof useI18n>["t"]; periodLabel?: string; label?: string }) {
  if (!metric) return null;
  const years = Object.keys(metric.values).sort();
  const yearRange = years.length >= 2 ? `(${years[0]}–${years[years.length - 1]})` : "";
  // Use TTM label or latest year as the period indicator
  const period = periodLabel || (years.length > 0 ? years[years.length - 1] : "");
  return (
    <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1 leading-relaxed">
      {label && <span className="font-medium">{label}: </span>}
      {t.latestValue(period)}: <span className="font-medium text-gray-500 dark:text-gray-400">{metric.latest.toFixed(1)}</span>
      &nbsp;|&nbsp; {t.histAvg} {yearRange}: {metric.avg.toFixed(1)}
      &nbsp;|&nbsp; {t.histRange}: {metric.min.toFixed(1)} – {metric.max.toFixed(1)}
    </div>
  );
}

function DCFTab({ ticker, waccData, financials, profile, prefetchedDefaults }: {
  ticker: string;
  waccData: { wacc: number; risk_free_rate: number; details: Record<string, unknown> } | null;
  financials: FinancialData | null;
  profile: CompanyProfile | null;
  prefetchedDefaults?: DCFDefaults | null;
}) {
  const { t } = useI18n();
  const { fmpApiKey, serperApiKey, deepseekApiKey, hasAiKeys } = useSettings();
  const [defaults, setDefaults] = useState<DCFDefaults | null>(prefetchedDefaults || null);
  const [defaultsLoading, setDefaultsLoading] = useState(!prefetchedDefaults);
  const [result, setResult] = useState<DCFResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // AI analysis state
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AIAnalysisResult | null>(null);
  const [aiError, setAiError] = useState("");
  const [showAiReasoning, setShowAiReasoning] = useState(false);
  const [expandedReasons, setExpandedReasons] = useState<Set<string>>(new Set());
  const [aiQuota, setAiQuota] = useState<AIQuota | null>(null);
  const [aiProgress, setAiProgress] = useState("");
  const [resultTab, setResultTab] = useState<"summary" | "forecast" | "sensitivity" | "ai" | "buffett">("summary");

  // Gap analysis state
  const [gapLoading, setGapLoading] = useState(false);
  const [gapResult, setGapResult] = useState<GapAnalysisResult | null>(null);
  const [gapError, setGapError] = useState("");
  const [gapProgress, setGapProgress] = useState("");

  // Save state
  const [saveStatus, setSaveStatus] = useState<"" | "saving" | "saved" | "error">("");
  const [excelExporting, setExcelExporting] = useState(false);
  const [savedId, setSavedId] = useState<number | null>(null); // Current session's IndexedDB id
  const [savedDate, setSavedDate] = useState<string>(""); // original save date
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<(import("@/lib/indexeddb").SavedValuation)[]>([]);
  const [detailItem, setDetailItem] = useState<(import("@/lib/indexeddb").SavedValuation) | null>(null);

  // Form state — initialized from defaults when loaded
  const [revenueGrowth1, setRevenueGrowth1] = useState(10);
  const [revenueGrowth2, setRevenueGrowth2] = useState(5);
  const [ebitMargin, setEbitMargin] = useState(20);
  const [convergence, setConvergence] = useState(5);
  const [revIC1, setRevIC1] = useState(2.0);
  const [revIC2, setRevIC2] = useState(1.5);
  const [revIC3, setRevIC3] = useState(1.2);
  const [taxRate, setTaxRate] = useState(25);
  const [waccRate, setWaccRate] = useState(10);
  const [ronicMatchWacc, setRonicMatchWacc] = useState(false);
  const [defaultsApplied, setDefaultsApplied] = useState(false);
  const [paramsCollapsed, setParamsCollapsed] = useState(false);

  // Buffett quick estimate
  const [buffett, setBuffett] = useState<BuffettResult | null>(null);
  const [buffettLoading, setBuffettLoading] = useState(true);

  // Refs for auto-scroll and auto-run
  const resultRef = useRef<HTMLDivElement>(null);
  const autoRunTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasRunOnce = useRef(false);

  // Fetch Buffett valuation in parallel with defaults
  useEffect(() => {
    if (!ticker) return;
    setBuffettLoading(true);
    getBuffettValuation(ticker, fmpApiKey)
      .then(setBuffett)
      .catch(() => {})
      .finally(() => setBuffettLoading(false));
  }, [ticker, fmpApiKey]);

  // Fetch AI quota on mount (only when using server keys)
  useEffect(() => {
    if (!hasAiKeys) {
      getAIQuota().then(setAiQuota).catch(() => {});
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Apply prefetched defaults when they arrive from parent
  useEffect(() => {
    if (prefetchedDefaults && !defaultsApplied) {
      setDefaults(prefetchedDefaults);
      setDefaultsLoading(false);
      const s = prefetchedDefaults.suggested;
      setRevenueGrowth1(s.revenue_growth_1);
      setRevenueGrowth2(s.revenue_growth_2);
      setEbitMargin(s.ebit_margin);
      setConvergence(s.convergence);
      setRevIC1(s.revenue_invested_capital_ratio_1);
      setRevIC2(s.revenue_invested_capital_ratio_2);
      setRevIC3(s.revenue_invested_capital_ratio_3);
      if (prefetchedDefaults.average_tax_rate != null) {
        setTaxRate(parseFloat((prefetchedDefaults.average_tax_rate * 100).toFixed(1)));
      }
      setDefaultsApplied(true);
    }
  }, [prefetchedDefaults]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fallback: load defaults on mount if not prefetched
  useEffect(() => {
    if (prefetchedDefaults) return; // Already handled above
    let cancelled = false;
    const apikey = fmpApiKey;
    setDefaultsLoading(true);
    getDCFDefaults(ticker, apikey)
      .then((d) => {
        if (cancelled) return;
        setDefaults(d);
        if (!defaultsApplied) {
          const s = d.suggested;
          setRevenueGrowth1(s.revenue_growth_1);
          setRevenueGrowth2(s.revenue_growth_2);
          setEbitMargin(s.ebit_margin);
          setConvergence(s.convergence);
          setRevIC1(s.revenue_invested_capital_ratio_1);
          setRevIC2(s.revenue_invested_capital_ratio_2);
          setRevIC3(s.revenue_invested_capital_ratio_3);
          if (d.average_tax_rate != null) {
            setTaxRate(parseFloat((d.average_tax_rate * 100).toFixed(1)));
          }
          setDefaultsApplied(true);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setDefaultsLoading(false); });
    return () => { cancelled = true; };
  }, [ticker, prefetchedDefaults]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pre-fill WACC from parent data
  useEffect(() => {
    if (waccData && defaultsApplied) {
      setWaccRate(parseFloat((waccData.wacc * 100).toFixed(1)));
    }
  }, [waccData, defaultsApplied]);

  // Close history dropdown on outside click
  useEffect(() => {
    if (!historyOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-history-panel]')) {
        setHistoryOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [historyOpen]);

  // AI analysis handler
  const handleAIAnalyze = async (autoCollapse = false) => {
    setAiLoading(true);
    setAiError("");
    setAiResult(null);
    setAiProgress("");
    // If this is a one-click flow, run DCF first with defaults so results appear
    if (autoCollapse && !hasRunOnce.current) {
      await executeDCF(false);
    }
    const apikey = fmpApiKey;
    try {
      const result = await runAIAnalysis(ticker, apikey, serperApiKey, deepseekApiKey, (msg) => {
        setAiProgress(msg);
      });
      setAiResult(result);
      // Refresh quota after usage
      if (!hasAiKeys) getAIQuota().then(setAiQuota).catch(() => {});
      // Apply AI parameters to form
      const p = result.parameters;
      if (p.revenue_growth_1?.value != null) setRevenueGrowth1(p.revenue_growth_1.value);
      if (p.revenue_growth_2?.value != null) setRevenueGrowth2(p.revenue_growth_2.value);
      if (p.ebit_margin?.value != null) setEbitMargin(p.ebit_margin.value);
      if (p.convergence?.value != null) setConvergence(p.convergence.value);
      if (p.revenue_invested_capital_ratio_1?.value != null) setRevIC1(p.revenue_invested_capital_ratio_1.value);
      if (p.revenue_invested_capital_ratio_2?.value != null) setRevIC2(p.revenue_invested_capital_ratio_2.value);
      if (p.revenue_invested_capital_ratio_3?.value != null) setRevIC3(p.revenue_invested_capital_ratio_3.value);
      if (p.ronic_match_wacc?.value != null) setRonicMatchWacc(Boolean(p.ronic_match_wacc.value));
      setShowAiReasoning(true);
      // Auto-collapse to side-by-side after AI completes
      if (autoCollapse) {
        setParamsCollapsed(false);
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 200);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t.aiError;
      setAiError(msg);
    } finally {
      setAiLoading(false);
    }
  };

  const executeDCF = useCallback(async (shouldScroll: boolean) => {
    setSavedId(null);
    setSavedDate("");
    setLoading(true);
    setError("");

    const params: Parameters<typeof runDCF>[0] = {
      ticker,
      apikey: fmpApiKey,
      revenue_growth_1: revenueGrowth1,
      revenue_growth_2: revenueGrowth2,
      ebit_margin: ebitMargin,
      convergence,
      revenue_invested_capital_ratio_1: revIC1,
      revenue_invested_capital_ratio_2: revIC2,
      revenue_invested_capital_ratio_3: revIC3,
      tax_rate: taxRate,
      wacc: waccRate,
      ronic_match_wacc: ronicMatchWacc,
    };

    try {
      const data = await runDCF(params);
      setResult(data);
      hasRunOnce.current = true;
      if (shouldScroll) {
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "DCF computation failed");
    } finally {
      setLoading(false);
    }
  }, [ticker, fmpApiKey, revenueGrowth1, revenueGrowth2, ebitMargin, convergence, revIC1, revIC2, revIC3, taxRate, waccRate, ronicMatchWacc]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await executeDCF(true);
  };

  // Auto-run DCF on parameter change (debounced, only after first manual run)
  useEffect(() => {
    if (!hasRunOnce.current || !defaultsApplied) return;
    if (autoRunTimer.current) clearTimeout(autoRunTimer.current);
    autoRunTimer.current = setTimeout(() => {
      executeDCF(false);
    }, 400);
    return () => { if (autoRunTimer.current) clearTimeout(autoRunTimer.current); };
  }, [executeDCF, defaultsApplied]);

  // Gap analysis handler
  const handleGapAnalysis = async () => {
    if (!result) return;
    setGapLoading(true);
    setGapError("");
    setGapResult(null);
    setGapProgress("");
    try {
      const data = await runGapAnalysis({
        ticker,
        apikey: fmpApiKey,
        serper_key: serperApiKey,
        deepseek_key: deepseekApiKey,
        dcf_price: result.dcf_price,
        market_price: result.market_price,
        valuation_params: result.valuation_params as Record<string, unknown>,
        bridge: result.bridge as unknown as Record<string, number>,
        forex_rate: result.forex_rate,
        reported_currency: result.reported_currency,
      }, (msg) => setGapProgress(msg));
      setGapResult(data);
    } catch (err: unknown) {
      setGapError(err instanceof Error ? err.message : "Gap analysis failed");
    } finally {
      setGapLoading(false);
    }
  };

  // Save handler (upsert: update existing or create new)
  const handleSave = async () => {
    if (!result) return;
    setSaveStatus("saving");
    try {
      // Save to IndexedDB (client-side) with upsert
      try {
        const { saveValuation } = await import("@/lib/indexeddb");
        const now = new Date().toISOString();
        const dateValue = savedId && savedDate ? savedDate : now;
        const id = await saveValuation({
          ticker,
          company_name: result.company_name,
          date: dateValue,
          updated_at: now,
          mode: aiResult ? "copilot" : "manual",
          ai_engine: aiResult?.engine,
          dcf_price: result.dcf_price_converted ?? result.dcf_price,
          market_price: result.market_price,
          diff_pct: result.diff_pct,
          currency: result.currency,
          reported_currency: result.reported_currency,
          revenue_growth_1: revenueGrowth1,
          revenue_growth_2: revenueGrowth2,
          ebit_margin: ebitMargin,
          convergence,
          rev_ic_1: revIC1,
          rev_ic_2: revIC2,
          rev_ic_3: revIC3,
          tax_rate: taxRate,
          wacc: waccRate,
          ronic_match_wacc: ronicMatchWacc,
          bridge: result.bridge as unknown as Record<string, number>,
          gap_analysis: gapResult ? { analysis_text: gapResult.analysis_text, adjusted_price: gapResult.adjusted_price, gap_pct: gapResult.gap_pct } : undefined,
          ai_reasoning: aiResult?.reasoning,
        }, savedId ?? undefined);
        if (!savedId) {
          setSavedId(id);
          setSavedDate(now);
        }
      } catch { /* IndexedDB not available */ }

      // Save to server SQLite (if VS_DB_PATH configured)
      try {
        await saveValuationToServer({
          ticker,
          company_name: result.company_name,
          mode: aiResult ? "copilot" : "manual",
          ai_engine: aiResult?.engine,
          valuation_params: result.valuation_params as Record<string, unknown>,
          dcf_results: result as unknown as Record<string, unknown>,
          company_profile: {
            price: result.market_price,
            currency: result.currency,
            country: profile?.country,
            exchange: profile?.exchange,
            beta: profile?.beta,
            marketCap: profile?.market_cap,
          },
          gap_analysis: gapResult ? {
            analysis_text: gapResult.analysis_text,
            adjusted_price: gapResult.adjusted_price,
            dcf_price: gapResult.dcf_price,
            current_price: gapResult.market_price,
            gap_pct: gapResult.gap_pct,
            currency: gapResult.currency,
          } : null,
          ai_result: aiResult ? { raw_text: aiResult.reasoning, parameters: aiResult.parameters } : null,
          sensitivity: result.sensitivity ? {
            growth_margin: result.sensitivity.growth_margin,
            wacc: result.sensitivity.wacc,
          } : null,
          financial_summary: financials?.summary ?? null,
          forex_rate: result.forex_rate,
        });
      } catch { /* Server save optional */ }

      setSaveStatus("saved");
      setTimeout(() => setSaveStatus(""), 3000);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus(""), 3000);
    }
  };

  const hist = defaults?.history;
  const periodLabel = defaults?.ttm_label || "";

  return (
    <div ref={resultRef} className={`scroll-mt-20 ${!result && (buffett != null || buffettLoading) && !paramsCollapsed ? "xl:flex xl:flex-row-reverse xl:gap-6 xl:items-start" : result && !paramsCollapsed ? "xl:flex xl:gap-6 xl:items-start" : "space-y-6"}`}>
      {/* Buffett Quick Estimate — right sidebar before DCF run */}
      {!result && !paramsCollapsed && buffettLoading && (
        <div className="mb-6 xl:mb-0 xl:w-[420px] xl:flex-shrink-0 rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 p-5 animate-pulse">
          <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
          <div className="h-3 w-48 bg-gray-200 dark:bg-gray-700 rounded mb-5" />
          <div className="h-8 w-36 bg-gray-200 dark:bg-gray-700 rounded mb-3" />
          <div className="h-5 w-24 bg-gray-200 dark:bg-gray-700 rounded mb-4" />
          <div className="border-t border-gray-200 dark:border-gray-700 pt-3 grid grid-cols-2 gap-3">
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded" />
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded" />
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded" />
            <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded" />
          </div>
        </div>
      )}
      {!result && !buffettLoading && buffett && !buffett.available && !paramsCollapsed && (
        <div className="mb-6 xl:mb-0 xl:w-[420px] xl:flex-shrink-0 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-5">
          <h4 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-2">
            {t.buffettTitle}
          </h4>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            {t.buffettUnavailable}
          </p>
          {buffett.owner_earnings != null && (
            <p className="text-[11px] text-gray-400 mt-2 font-mono">
              Owner Earnings: {buffett.owner_earnings.toLocaleString(undefined, { maximumFractionDigits: 0 })}M
            </p>
          )}
        </div>
      )}
      {!result && !buffettLoading && buffett?.available && !paramsCollapsed && (() => {
        const b = buffett;
        const hasFx = b.forex_rate != null && b.stock_currency && b.reported_currency && b.stock_currency !== b.reported_currency;
        const rawIntrinsic = b.intrinsic_per_share ?? 0;
        const rawMos = b.margin_of_safety_price ?? 0;
        const bIntrinsic = hasFx ? rawIntrinsic * (b.forex_rate ?? 1) : rawIntrinsic;
        const bMos = hasFx ? rawMos * (b.forex_rate ?? 1) : rawMos;
        const displayCurrency = hasFx ? b.stock_currency! : (b.reported_currency ?? "USD");
        const marketPrice = b.market_price ?? 0;
        const diffPct = marketPrice ? ((bIntrinsic - marketPrice) / marketPrice * 100) : 0;
        const diffColor = diffPct > 10 ? "text-green-600 dark:text-green-400" : diffPct < -10 ? "text-red-600 dark:text-red-400" : "text-gray-700 dark:text-gray-300";

        return (
          <div className="mb-6 xl:mb-0 xl:w-[420px] xl:flex-shrink-0 xl:sticky xl:top-20 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 p-5">
            <h4 className="text-sm font-semibold text-amber-800 dark:text-amber-200 mb-1">
              {t.buffettTitle}
            </h4>
            <p className="text-[11px] text-gray-400 dark:text-gray-500 mb-4">{t.buffettSubtitle}</p>
            <div className="space-y-3">
              <div className="flex items-baseline gap-3">
                <div className="flex-1">
                  <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">{t.buffettIntrinsic}</div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white">{formatCurrency(bIntrinsic, displayCurrency)}</div>
                </div>
                {marketPrice > 0 && (
                  <div className="text-right">
                    <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">{t.upsideDownside}</div>
                    <div className={`text-xl font-bold ${diffColor}`}>{diffPct > 0 ? "+" : ""}{diffPct.toFixed(1)}%</div>
                  </div>
                )}
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">{t.buffettMos}</div>
                <div className="text-base font-bold text-gray-900 dark:text-white">{formatCurrency(bMos, displayCurrency)}</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px] mt-4 pt-3 border-t border-amber-200/50 dark:border-amber-800/50">
              <div>
                <span className="text-gray-400">{b.ni_label ? `NI(${b.ni_label})` : "NI"}</span>
                <div className="font-mono font-medium">{(b.net_income ?? 0).toLocaleString(undefined, {maximumFractionDigits: 0})}M</div>
              </div>
              <div>
                <span className="text-gray-400">Owner Earnings</span>
                <div className="font-mono font-medium">{(b.owner_earnings ?? 0).toLocaleString(undefined, {maximumFractionDigits: 0})}M</div>
              </div>
              <div>
                <span className="text-gray-400">{t.growthRate}</span>
                <div className="font-mono font-medium">{((b.growth_phase1 ?? 0) * 100).toFixed(1)}%</div>
              </div>
              <div>
                <span className="text-gray-400">ROE(avg) / Payout</span>
                <div className="font-mono font-medium">{(b.avg_roe ?? 0).toFixed(0)}% / {(b.payout ?? 0).toFixed(0)}%</div>
              </div>
            </div>
            <ul className="mt-4 pt-3 border-t border-amber-200/50 dark:border-amber-800/50 space-y-1.5">
              {t.buffettNotes.map((note, i) => (
                <li key={i} className="text-[10px] text-gray-400 dark:text-gray-500 leading-relaxed flex gap-1.5">
                  <span className="text-amber-400 dark:text-amber-600 mt-px shrink-0">•</span>
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })()}

      {/* Parameter Form */}
      <div className={`relative bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 ${result && !paramsCollapsed ? "mb-6 xl:mb-0 xl:w-[420px] xl:flex-shrink-0 xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto xl:flex xl:flex-col" : "p-6"}`}>
        {defaultsLoading && (
          <div className="absolute inset-0 z-20 bg-white/70 dark:bg-gray-900/70 rounded-xl flex items-center justify-center backdrop-blur-[1px]">
            <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            <span className="ml-2 text-sm text-gray-500">{t.loadingDefaults}</span>
          </div>
        )}
        <div className={`flex items-center justify-between gap-2 mb-2 flex-wrap ${result && !paramsCollapsed ? "sticky top-0 z-10 bg-white dark:bg-gray-900 px-6 pt-6 pb-2 -mb-0 rounded-t-xl" : ""}`}>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2 whitespace-nowrap">
            {t.dcfValuation}
            {result && (
              <button type="button" onClick={() => setParamsCollapsed(!paramsCollapsed)} className="p-1.5 rounded-md text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:text-blue-400 dark:hover:bg-blue-950/30 transition-colors" title={paramsCollapsed ? (t.expandParams || "切换为左右布局") : (t.collapseParams || "切换为上下布局")}>
                {paramsCollapsed ? (
                  /* Two columns icon — switch to side-by-side */
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 4.5v15m6-15v15M4.5 4.5h15a1.5 1.5 0 011.5 1.5v12a1.5 1.5 0 01-1.5 1.5h-15A1.5 1.5 0 013 18V6a1.5 1.5 0 011.5-1.5z" />
                  </svg>
                ) : (
                  /* Single column icon — switch to stacked */
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h12A2.25 2.25 0 0120.25 6v12A2.25 2.25 0 0118 20.25H6A2.25 2.25 0 013.75 18V6z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5" />
                  </svg>
                )}
              </button>
            )}
          </h3>
          {/* AI button — always top right, hidden after AI was used */}
          {!aiResult && (
            <div className="ml-auto flex flex-col items-end shrink-0">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); handleAIAnalyze(true); }}
                disabled={aiLoading}
                className="px-3 py-1.5 text-sm font-medium text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/30 hover:bg-purple-100 dark:hover:bg-purple-950/50 border border-purple-200 dark:border-purple-800 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 shrink-0"
              >
                {aiLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <span>🤖</span>
                    <span>{t.aiAnalyze}</span>
                  </>
                )}
              </button>
              {!aiLoading && (
                <span className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
                  {hasAiKeys ? t.aiUnlimited : aiQuota ? t.aiFreeQuota(aiQuota.remaining, aiQuota.limit) : ""}
                </span>
              )}
            </div>
          )}
        </div>
        <div className={result && !paramsCollapsed ? "px-6 pb-6 pt-2" : ""}>

        {/* AI progress indicator */}
        {aiLoading && (
          <div className="mb-3 flex items-center gap-2 text-sm text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/30 rounded-lg px-3 py-2 border border-purple-200 dark:border-purple-800">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" />
            <span className="truncate">{aiProgress || t.aiAnalyzing}</span>
          </div>
        )}

        {/* Intro text — changes after first run */}
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {aiLoading ? "" : result ? (t.autoUpdateHint || "调整参数后估值自动更新") : t.dcfIntro(ticker)}
          {!aiLoading && defaults?.base_year && (
            <span className="ml-1 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 text-xs text-blue-700 dark:text-blue-300 font-medium">
              {defaults.ttm_label ? t.baseYearTTM(defaults.ttm_label) : t.baseYearLabel(defaults.base_year_label || defaults.base_year)}
              {" · "}
              {t.forecastStartsFrom(defaults.forecast_year_1 ?? defaults.base_year + 1, !!defaults.ttm_label || (defaults.fy_end_month > 0 && defaults.fy_end_month <= 6))}
            </span>
          )}
        </p>

        {/* AI error */}
        {aiError && (
          <div className="mb-4 p-3 bg-red-50 dark:bg-red-950/30 rounded-lg text-sm text-red-600 dark:text-red-400">
            {aiError}
          </div>
        )}

        {/* AI success banner + parameter comparison table */}
        {aiResult && (() => {
          const paramDefs = [
            { key: "revenue_growth_1", label: t.revenueGrowthPhase1, unit: "%", decimals: 1 },
            { key: "revenue_growth_2", label: t.revenueGrowthPhase2, unit: "%", decimals: 1 },
            { key: "ebit_margin", label: t.targetEbitMargin, unit: "%", decimals: 1 },
            { key: "convergence", label: t.convergenceYears, unit: "", decimals: 0 },
            { key: "revenue_invested_capital_ratio_1", label: t.revICPhase1, unit: "x", decimals: 2 },
            { key: "revenue_invested_capital_ratio_2", label: t.revICPhase2, unit: "x", decimals: 2 },
            { key: "revenue_invested_capital_ratio_3", label: t.revICPhase3, unit: "x", decimals: 2 },
            { key: "ronic_match_wacc", label: t.ronicMatchWacc, unit: "", decimals: 0, isBool: true },
          ];
          const fmtVal = (v: number | null | undefined, d: number, u: string) =>
            v != null ? `${v.toFixed(d)}${u}` : "—";
          return (
            <div className="mb-4 bg-purple-50 dark:bg-purple-950/30 rounded-lg border border-purple-200 dark:border-purple-800">
              {/* Header — always visible, clickable to toggle */}
              <button
                type="button"
                onClick={() => setShowAiReasoning(!showAiReasoning)}
                className="w-full flex items-center justify-between p-4 text-left"
              >
                <div className="text-sm text-purple-700 dark:text-purple-300 flex-1">
                  ✓ {t.aiApplied}
                  <span className="ml-2 text-xs text-purple-500">{t.aiEngine(aiResult.engine)}</span>
                </div>
                <div className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium text-purple-600 dark:text-purple-300 bg-purple-100 dark:bg-purple-900/40 hover:bg-purple-200 dark:hover:bg-purple-900/60 transition-colors`}>
                  <span>{showAiReasoning ? t.hideFullResponse : t.showFullResponse}</span>
                  <svg className={`w-4 h-4 transition-transform ${showAiReasoning ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>
              {/* Collapsible detail */}
              {showAiReasoning && (
                <div className="px-4 pb-4">
                  {/* Parameter comparison — card layout for narrow, table for wide */}
                  <div className="space-y-2">
                    {paramDefs.map(({ key, label, unit, decimals, isBool }: { key: string; label: string; unit: string; decimals: number; isBool?: boolean }) => {
                      const aiParam = aiResult.parameters?.[key];
                      const aiVal = aiParam?.value;
                      const fmtCell = (v: unknown) => {
                        if (v == null) return "—";
                        if (isBool) return v ? "✓" : "✗";
                        return fmtVal(v as number, decimals, unit);
                      };
                      const isExpanded = expandedReasons.has(key);
                      return (
                        <div key={key} className={`border-b border-purple-100 dark:border-purple-800/50 last:border-0 ${paramsCollapsed ? "pb-3" : "pb-2"}`}>
                          <div className={`flex items-center justify-between ${paramsCollapsed ? "text-sm" : "text-xs"}`}>
                            <span className="text-purple-700 dark:text-purple-300 font-medium">{label}</span>
                            <span className="font-mono font-semibold text-purple-900 dark:text-purple-100">{fmtCell(aiVal)}</span>
                          </div>
                          {aiParam?.reasoning && (
                            <p
                              className={`${paramsCollapsed ? "text-xs" : "text-[10px]"} text-purple-500 dark:text-purple-400 mt-0.5 leading-tight cursor-pointer hover:text-purple-700 dark:hover:text-purple-300 ${isExpanded ? "" : "line-clamp-2"}`}
                              onClick={() => setExpandedReasons(prev => {
                                const next = new Set(prev);
                                if (next.has(key)) next.delete(key);
                                else next.add(key);
                                return next;
                              })}
                            >{aiParam.reasoning}</p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })()}

        </div>{/* end collapsible wrapper */}
        <div className={result && !paramsCollapsed ? "px-6 pb-6" : ""}>
          {/* Revenue Growth */}
          <div className="mb-5">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {t.revenueGrowthAssumptions}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DCFInputField
                label={t.revenueGrowthPhase1}
                desc={t.revenueGrowthPhase1Desc}
                value={revenueGrowth1}
                onChange={setRevenueGrowth1}
                step={0.5}
                historyHint={<HistoryHint metric={hist?.revenue_growth ?? null} t={t} periodLabel={periodLabel} />}
              />
              <DCFInputField
                label={t.revenueGrowthPhase2}
                desc={t.revenueGrowthPhase2Desc}
                value={revenueGrowth2}
                onChange={setRevenueGrowth2}
                step={0.5}
                historyHint={<HistoryHint metric={hist?.revenue_growth ?? null} t={t} periodLabel={periodLabel} />}
              />
            </div>
          </div>

          {/* Profitability */}
          <div className="mb-5">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {t.marginConvergence}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DCFInputField
                label={t.targetEbitMargin}
                desc={t.ebitMarginDesc}
                value={ebitMargin}
                onChange={setEbitMargin}
                step={0.5}
                historyHint={
                  <>
                    <HistoryHint metric={hist?.ebit_margin ?? null} t={t} periodLabel={periodLabel} />
                  </>
                }
              />
              <DCFInputField
                label={t.convergenceYears}
                desc={t.convergenceYearsDesc}
                value={convergence}
                onChange={setConvergence}
                step={1}
                min={1}
                max={20}
              />
            </div>
          </div>

          {/* Revenue / Invested Capital Ratios */}
          <div className="mb-5">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {t.revICRatios}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <DCFInputField
                label={t.revICPhase1}
                value={revIC1}
                onChange={setRevIC1}
                step={0.1}
                min={0.1}
                historyHint={<HistoryHint metric={hist?.revenue_ic ?? null} t={t} periodLabel={periodLabel} />}
              />
              <DCFInputField
                label={t.revICPhase2}
                value={revIC2}
                onChange={setRevIC2}
                step={0.1}
                min={0.1}
                historyHint={hist?.revenue_ic ? (
                  <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">
                    {t.defaultAvg}: {hist.revenue_ic.avg.toFixed(1)}
                  </div>
                ) : undefined}
              />
              <DCFInputField
                label={t.revICPhase3}
                value={revIC3}
                onChange={setRevIC3}
                step={0.1}
                min={0.1}
                historyHint={hist?.revenue_ic ? (
                  <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">
                    {t.defaultAvgDecay}: {(hist.revenue_ic.avg * 0.8).toFixed(1)}
                  </div>
                ) : undefined}
              />
            </div>
          </div>

          {/* Cost of Capital & Tax */}
          <div className="mb-5">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {t.costOfCapital}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <DCFInputField
                label={t.taxRate}
                desc={t.autoCalculatedEditable}
                value={taxRate}
                onChange={setTaxRate}
                step={0.5}
                historyHint={hist?.tax_rate ? <HistoryHint metric={hist.tax_rate} t={t} periodLabel={periodLabel} /> : undefined}
              />
              <div>
                <DCFInputField
                  label={t.waccRate}
                  desc={t.autoCalculatedEditable}
                  value={waccRate}
                  onChange={setWaccRate}
                  step={0.1}
                />
                {/* WACC calculation breakdown */}
                {waccData?.details && (
                  <details className="mt-2">
                    <summary className="text-[10px] text-blue-500 dark:text-blue-400 cursor-pointer hover:underline">
                      {t.waccCalculation}
                    </summary>
                    <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px]">
                      {(Array.isArray(waccData.details)
                        ? (waccData.details as [string, string][])
                        : Object.entries(waccData.details)
                      ).map(([label, val], i) => (
                        <div key={i} className="flex justify-between gap-2">
                          <span className="text-gray-400 dark:text-gray-500 truncate">{label}</span>
                          <span className="text-gray-600 dark:text-gray-400 font-mono whitespace-nowrap">{String(val)}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          </div>

          {/* RONIC checkbox */}
          <div className="mb-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={ronicMatchWacc}
                onChange={(e) => setRonicMatchWacc(e.target.checked)}
                className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">
                {t.ronicMatchWacc}
              </span>
            </label>
            <p className="mt-1 ml-6 text-[10px] text-gray-400 dark:text-gray-500 leading-relaxed max-w-xl">
              {t.ronicExplanation}
            </p>
          </div>

          {/* Submit button — shown before first run, or in stacked (full-width) mode for re-run; hidden during AI loading */}
          {(!result || paramsCollapsed) && !aiLoading && (
            <form onSubmit={handleSubmit}>
              <button
                type="submit"
                disabled={loading}
                className="w-full sm:w-auto px-6 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 rounded-lg transition-colors flex items-center justify-center gap-2 mt-4"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {loading ? t.runningDCF : result ? t.rerunDCF : t.runDCF}
              </button>
            </form>
          )}

        </div>
      </div>

      {/* ══════ Results (right side on xl when params expanded) ══════ */}
      <div className={`${result && !paramsCollapsed ? "xl:flex-1 xl:min-w-0" : ""} space-y-4`}>

      {/* Error display */}
      {error && (
        <div className="bg-red-50 dark:bg-red-950/30 rounded-xl border border-red-200 dark:border-red-800 p-6 text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {result && (() => {
        const hasFx = result.forex_rate != null && result.reported_currency !== result.currency;
        const fxRate = hasFx ? result.forex_rate! : 1;
        const sensCurrency = hasFx ? result.currency : result.reported_currency;
        const diffPct100 = result.diff_pct * 100;
        const verdictColor = result.diff_pct > 0.15
          ? "text-green-600 dark:text-green-400"
          : result.diff_pct < -0.15
            ? "text-red-600 dark:text-red-400"
            : "text-yellow-600 dark:text-yellow-400";
        const verdictBg = result.diff_pct > 0.15
          ? "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800"
          : result.diff_pct < -0.15
            ? "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800"
            : "bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800";
        return (
        <div className="space-y-4">
          {/* ── Verdict Banner + Tabs (sticky together) ── */}
          <div className="sticky top-16 z-10">
            <div className={`rounded-t-xl border border-b-0 p-4 ${verdictBg}`}>
              <div className="flex flex-wrap items-center justify-between gap-4">
                {/* Left: prices + verdict */}
                <div className="flex items-center gap-6 min-w-0">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">{t.dcfEstimate}</div>
                    <div className="text-xl font-bold text-gray-900 dark:text-white">{formatCurrency(result.dcf_price_converted, result.currency)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">{t.marketPrice}</div>
                    <div className="text-xl font-bold text-gray-900 dark:text-white">{formatCurrency(result.market_price, result.currency)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-0.5">{t.upsideDownside}</div>
                    <div className={`text-xl font-bold ${verdictColor}`}>
                      {diffPct100 > 0 ? "+" : ""}{diffPct100.toFixed(1)}%
                    </div>
                  </div>
                </div>
                {/* Right: action buttons */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => { setResultTab("ai"); if (!gapResult && !gapLoading) handleGapAnalysis(); }}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 ${
                      gapLoading ? "bg-indigo-500 text-white opacity-80" : gapResult ? "bg-indigo-100 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-200 dark:hover:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800" : "bg-indigo-600 text-white hover:bg-indigo-700"
                    }`}
                  >
                    {gapLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="max-w-[200px] truncate">{gapProgress || t.analyzingGap}</span>
                      </>
                    ) : gapResult ? (
                      <>
                        <span>✓</span>
                        <span>{t.dcfTabAI}</span>
                      </>
                    ) : (
                      <>
                        <span>🤖</span>
                        <span>{t.runGapAnalysis}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
              {result.ttm?.label && (
                <div className="mt-2 text-[10px] text-gray-500 dark:text-gray-400">
                  {result.ttm.label} · {t.dcfDisclaimer}
                </div>
              )}
            </div>

            {/* ── Sub-tab Navigation (attached to verdict) ── */}
            <div className="bg-white dark:bg-gray-900 rounded-b-xl border-x border-b border-gray-200 dark:border-gray-800">
            <div className="flex items-center border-b border-gray-200 dark:border-gray-800">
              <div className="flex flex-1">
                {(["summary", "forecast", "sensitivity", "ai", ...(buffett?.available ? ["buffett"] : [])] as ("summary" | "forecast" | "sensitivity" | "ai" | "buffett")[]).map((tab) => {
                  const labels: Record<string, string> = { summary: t.dcfTabSummary, forecast: t.dcfTabForecast, sensitivity: t.dcfTabSensitivity, ai: t.dcfTabAI, buffett: t.dcfTabBuffett };
                  const isActive = resultTab === tab;
                  const hasNotif = tab === "ai" && gapResult != null;
                  return (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setResultTab(tab)}
                      className={`relative px-5 py-3 text-sm font-medium transition-colors ${
                        isActive
                          ? "text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400 -mb-px"
                          : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                      }`}
                    >
                      {labels[tab]}
                      {hasNotif && <span className="absolute top-2 -right-0.5 w-1.5 h-1.5 bg-indigo-500 rounded-full" />}
                    </button>
                  );
                })}
              </div>
              {/* Right side: Save + History */}
              <div className="flex items-center gap-1.5 px-3">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saveStatus === "saving"}
                  className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    saveStatus === "saved"
                      ? "bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-400"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  {saveStatus === "saving" ? "..." : saveStatus === "saved" ? `✓ ${t.valuationSaved}` : `💾 ${t.saveValuation}`}
                </button>
                <button
                  type="button"
                  disabled={excelExporting}
                  onClick={async () => {
                    setExcelExporting(true);
                    try {
                      await downloadDCFExcel({
                        ticker,
                        apikey: fmpApiKey,
                        revenue_growth_1: revenueGrowth1,
                        revenue_growth_2: revenueGrowth2,
                        ebit_margin: ebitMargin,
                        convergence,
                        revenue_invested_capital_ratio_1: revIC1,
                        revenue_invested_capital_ratio_2: revIC2,
                        revenue_invested_capital_ratio_3: revIC3,
                        tax_rate: taxRate,
                        wacc: waccRate,
                        ronic_match_wacc: ronicMatchWacc,
                      });
                    } catch { alert("Export failed"); }
                    setExcelExporting(false);
                  }}
                  className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                  title="Export to Excel"
                >
                  {excelExporting ? "⏳..." : "📥 Excel"}
                </button>
                <div className="relative" data-history-panel>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!historyOpen) {
                        try {
                          const { getAllHistory } = await import("@/lib/valuation-storage");
                          const h = await getAllHistory();
                          setHistory(h);
                        } catch { setHistory([]); }
                      }
                      setHistoryOpen(!historyOpen);
                    }}
                    className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                  >
                    📋 {t.valuationHistory}
                  </button>
                  {/* History dropdown */}
                  {historyOpen && (
                    <div className="absolute right-0 top-full mt-1 w-80 max-h-64 overflow-y-auto bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50">
                      {history.length === 0 ? (
                        <div className="px-4 py-6 text-center text-sm text-gray-400">{t.noHistory}</div>
                      ) : (
                        history.map((item) => (
                          <div key={item.id} className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 last:border-0 hover:bg-gray-50 dark:hover:bg-gray-800/50 flex items-center justify-between gap-2 cursor-pointer"
                            onClick={() => { setDetailItem(item); setHistoryOpen(false); }}
                          >
                            <div className="min-w-0 flex-1">
                              <div className="text-xs text-gray-500 dark:text-gray-400">
                                <span className="font-medium text-gray-700 dark:text-gray-300">{item.company_name}</span>
                                {" · "}{new Date(item.date).toLocaleDateString()} · {item.mode === "copilot" ? "🤖 AI" : "✏️ Manual"}
                              </div>
                              <div className="text-sm font-mono font-medium text-gray-800 dark:text-gray-200">
                                DCF {item.currency} {item.dcf_price.toFixed(2)}
                                <span className={`ml-2 ${item.diff_pct > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                                  {item.diff_pct > 0 ? "+" : ""}{(item.diff_pct * 100).toFixed(1)}%
                                </span>
                              </div>
                              {item.gap_analysis?.adjusted_price != null && (
                                <div className="text-[10px] text-indigo-500 dark:text-indigo-400">
                                  AI-adjusted: {item.currency} {item.gap_analysis.adjusted_price.toFixed(2)}
                                </div>
                              )}
                            </div>
                            <button
                              type="button"
                              onClick={async (e) => {
                                e.stopPropagation();
                                if (item.id == null) return;
                                try {
                                  const { deleteHistory } = await import("@/lib/valuation-storage");
                                  await deleteHistory(item.id);
                                  setHistory((prev) => prev.filter((h) => h.id !== item.id));
                                  if (detailItem?.id === item.id) setDetailItem(null);
                                } catch {}
                              }}
                              className="text-gray-400 hover:text-red-500 dark:hover:text-red-400 transition-colors p-1 shrink-0"
                              title={t.deleteValuation}
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>{/* close tab-nav */}
          </div>{/* close sticky wrapper */}

          {/* ── Tab Content ── */}
          <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800">
            <div className="p-6">
              {/* ── Tab: Summary ── */}
              {resultTab === "summary" && (
                <div className="space-y-6">
                  {/* Key metrics row */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <MetricItem label={`${t.enterpriseValue} (${result.reported_currency} M)`} value={formatNumber(result.results.enterprise_value, 0)} />
                    <MetricItem label={`${t.equityValue} (${result.reported_currency} M)`} value={formatNumber(result.results.equity_value, 0)} />
                    <MetricItem label={t.pricePerShare + ` (${result.reported_currency})`} value={result.results.price_per_share.toFixed(2)} />
                    {hasFx && <MetricItem label={t.pricePerShare + ` (${result.currency})`} value={result.dcf_price_converted.toFixed(2)} />}
                  </div>


                  {/* Bridge to Value per Share */}
                  {result.bridge && (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
                        {t.bridgeToValue}
                      </h4>
                      <div className="max-w-md space-y-1 text-sm font-mono">
                        <BridgeRow label={t.pvCashflows} value={result.bridge.pv_cashflows} />
                        <BridgeRow label={t.pvTerminalValue} value={result.bridge.pv_terminal_value} />
                        <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                        <BridgeRow label={t.operatingValue} value={result.bridge.pv_cashflows + result.bridge.pv_terminal_value} bold />
                        <BridgeRow label={t.plusCash} value={result.bridge.cash} />
                        <BridgeRow label={t.plusInvestments} value={result.bridge.total_investments} />
                        <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                        <BridgeRow label={t.enterpriseValue} value={result.results.enterprise_value} bold />
                        <BridgeRow label={t.minusDebt} value={-result.bridge.total_debt} />
                        <BridgeRow label={t.minusMinority} value={-result.bridge.minority_interest} />
                        <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                        <BridgeRow label={t.equityValue} value={result.results.equity_value} bold />
                        <BridgeRow label={t.sharesOutstanding} value={result.bridge.outstanding_shares} isShares />
                        <div className="border-t-2 border-gray-300 dark:border-gray-600 my-1" />
                        <BridgeRow label={`${t.valuePerShare} (${result.reported_currency})`} value={result.results.price_per_share} bold highlight />
                        {hasFx && (
                          <>
                            <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                            <div className="flex justify-between items-center py-0.5 text-gray-500 dark:text-gray-400">
                              <span className="text-xs">{t.forexRate}</span>
                              <span className="text-sm font-mono">1 {result.reported_currency} = {result.forex_rate!.toFixed(4)} {result.currency}</span>
                            </div>
                            <BridgeRow label={`${t.valuePerShare} (${result.currency})`} value={result.dcf_price_converted} bold highlight />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Tab: Forecast ── */}
              {resultTab === "forecast" && result.forecast_table && result.forecast_table.length > 0 && (() => {
                const isBase = (i: number) => i === 0;
                const isTerminal = (i: number) => i === result.forecast_table!.length - 1;
                const baseLabel = result.ttm?.label || String(result.forecast_table![0]?.Year ?? "");
                const baseBg = "bg-amber-50/60 dark:bg-amber-950/15";
                const baseBgSticky = "bg-amber-50 dark:bg-amber-950/20";
                return (
                  <div>
                    <p className="text-xs text-gray-400 mb-4">{t.forecastTableCurrency(result.reported_currency)}</p>
                    <div className="overflow-x-auto">
                      <table className="text-xs w-full">
                        <thead>
                          <tr className="border-b-2 border-gray-200 dark:border-gray-700">
                            <th className="py-2 px-3 text-left font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap sticky left-0 bg-white dark:bg-gray-900 z-10">{t.metric}</th>
                            {result.forecast_table!.map((row, i) => (
                              <th key={i} className={`py-2 px-3 text-right font-semibold whitespace-nowrap ${isBase(i) ? `text-amber-700 dark:text-amber-400 ${baseBg}` : isTerminal(i) ? "text-blue-600 dark:text-blue-400" : "text-gray-500 dark:text-gray-400"}`}>
                                {isBase(i) ? (<div className="flex flex-col items-end"><span className="text-[9px] font-medium text-amber-500">{t.baseYearShort}</span><span>{baseLabel}</span></div>) : isTerminal(i) ? t.terminalYear : row.Year}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            { key: "Revenue Growth Rate", label: t.revGrowthRate, fmt: "pct", bold: false },
                            { key: "Revenue", label: t.revenueLabel, fmt: "num", bold: true },
                            { key: "EBIT Margin", label: t.ebitMarginLabel, fmt: "pct", bold: false },
                            { key: "EBIT", label: t.ebitLabel, fmt: "num", bold: false },
                            { key: "Tax to EBIT", label: t.taxToEbit, fmt: "pct", bold: false },
                            { key: "EBIT(1-t)", label: t.ebitAfterTax, fmt: "num", bold: false },
                            { key: "Reinvestments", label: t.reinvestments, fmt: "num", bold: false },
                          ].map(({ key, label, fmt, bold: isBold }) => (
                            <tr key={key} className="border-b border-gray-100 dark:border-gray-800">
                              <td className={`py-1.5 px-3 text-left whitespace-nowrap sticky left-0 bg-white dark:bg-gray-900 z-10 ${isBold ? "text-gray-700 dark:text-gray-300 font-medium" : "text-gray-600 dark:text-gray-400"}`}>{label}</td>
                              {result.forecast_table!.map((row, i) => {
                                const v = row[key as keyof typeof row] as number | null;
                                return (
                                  <td key={i} className={`py-1.5 px-3 text-right font-mono ${isBold ? "text-gray-800 dark:text-gray-200" : "text-gray-600 dark:text-gray-400"} ${isBase(i) ? baseBg : ""}`}>
                                    {v != null ? (fmt === "pct" ? `${(v * 100).toFixed(1)}%` : formatNumber(v)) : "—"}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                          {/* FCFF — emphasized */}
                          <tr className="border-b-2 border-gray-200 dark:border-gray-700">
                            <td className="py-1.5 px-3 text-left text-gray-800 dark:text-gray-200 font-semibold whitespace-nowrap sticky left-0 bg-white dark:bg-gray-900 z-10">{t.fcff}</td>
                            {result.forecast_table!.map((row, i) => (
                              <td key={i} className={`py-1.5 px-3 text-right font-mono font-semibold ${row.FCFF != null && row.FCFF < 0 ? "text-red-600 dark:text-red-400" : "text-gray-800 dark:text-gray-200"} ${isBase(i) ? baseBg : ""}`}>
                                {row.FCFF != null ? formatNumber(row.FCFF) : "—"}
                              </td>
                            ))}
                          </tr>
                          {/* WACC, Discount Factor */}
                          {[
                            { key: "WACC", label: "WACC", fmt: "pct" },
                            { key: "Discount Factor", label: t.discountFactor, fmt: "dec4" },
                          ].map(({ key, label, fmt }) => (
                            <tr key={key} className="border-b border-gray-100 dark:border-gray-800">
                              <td className="py-1.5 px-3 text-left text-gray-600 dark:text-gray-400 whitespace-nowrap sticky left-0 bg-white dark:bg-gray-900 z-10">{label}</td>
                              {result.forecast_table!.map((row, i) => {
                                const v = row[key as keyof typeof row] as number | null;
                                return (
                                  <td key={i} className={`py-1.5 px-3 text-right font-mono text-gray-600 dark:text-gray-400 ${isBase(i) ? baseBg : ""}`}>
                                    {v != null ? (fmt === "pct" ? `${(v * 100).toFixed(1)}%` : v.toFixed(4)) : "—"}
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                          {/* PV(FCFF) */}
                          <tr className="bg-blue-50/30 dark:bg-blue-950/20">
                            <td className="py-1.5 px-3 text-left text-gray-800 dark:text-gray-200 font-semibold whitespace-nowrap sticky left-0 bg-blue-50/30 dark:bg-blue-950/20 z-10">{t.pvFcff}</td>
                            {result.forecast_table!.map((row, i) => (
                              <td key={i} className={`py-1.5 px-3 text-right font-mono text-gray-800 dark:text-gray-200 font-semibold ${isBase(i) ? baseBgSticky : ""}`}>
                                {row["PV (FCFF)"] != null ? formatNumber(row["PV (FCFF)"]) : "—"}
                              </td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}

              {/* ── Tab: Sensitivity ── */}
              {resultTab === "sensitivity" && result.sensitivity && (
                <div className="space-y-6">
                  {/* Reverse DCF: What's Priced In */}
                  {result.reverse_dcf && (result.reverse_dcf.growth_converged || result.reverse_dcf.margin_converged) && (
                    <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-950/20 p-4">
                      <h4 className="text-sm font-semibold text-blue-800 dark:text-blue-200 mb-3 flex items-center gap-2">
                        <span>📊</span> {t.impliedGrowth}
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {result.reverse_dcf.growth_converged && result.reverse_dcf.implied_growth_rate != null && (
                          <div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t.revenueGrowthPA}</div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-lg text-blue-700 dark:text-blue-300">
                                {result.reverse_dcf.implied_growth_rate.toFixed(1)}%
                              </span>
                              <span className="text-gray-400 text-xs">{t.marketImplies}</span>
                              <span className="text-gray-400">vs</span>
                              <span className="font-medium text-gray-600 dark:text-gray-400">
                                {result.reverse_dcf.your_growth.toFixed(1)}%
                              </span>
                              <span className="text-gray-400 text-xs">{t.yourAssumption}</span>
                            </div>
                          </div>
                        )}
                        {result.reverse_dcf.margin_converged && result.reverse_dcf.implied_ebit_margin != null && (
                          <div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t.ebitMargin}</div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-lg text-blue-700 dark:text-blue-300">
                                {result.reverse_dcf.implied_ebit_margin.toFixed(1)}%
                              </span>
                              <span className="text-gray-400 text-xs">{t.marketImplies}</span>
                              <span className="text-gray-400">vs</span>
                              <span className="font-medium text-gray-600 dark:text-gray-400">
                                {result.reverse_dcf.your_margin.toFixed(1)}%
                              </span>
                              <span className="text-gray-400 text-xs">{t.yourAssumption}</span>
                            </div>
                          </div>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
                        {t.impliedGrowthExplain}
                      </p>
                    </div>
                  )}


                  <p className="text-[10px] text-gray-400 dark:text-gray-500 leading-relaxed">
                    {t.sensitivityLegend}
                  </p>

                  {/* Growth vs Margin heatmap */}
                  {result.sensitivity.growth_margin?.table?.length > 0 && (() => {
                    const baseRi = Math.floor(result.sensitivity.growth_margin.margins.length / 2);
                    const baseCi = Math.floor(result.sensitivity.growth_margin.growth_rates.length / 2);
                    return (
                      <div>
                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t.sensitivityGrowthMargin}</h4>
                        <div className="overflow-x-auto">
                          <table className="text-xs w-full">
                            <thead>
                              <tr>
                                <th className="py-2 px-3 text-right text-gray-400 text-[10px]">Growth \ Margin</th>
                                {result.sensitivity.growth_margin.growth_rates.map((m, ci) => (
                                  <th key={m} className={`py-2 px-3 text-right font-medium whitespace-nowrap ${ci === baseCi ? "text-blue-600 dark:text-blue-400 bg-blue-50/50 dark:bg-blue-950/20" : "text-gray-500"}`}>{m.toFixed(0)}%</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {result.sensitivity.growth_margin.margins.map((g, ri) => {
                                const isBaseRow = ri === baseRi;
                                return (
                                  <tr key={g} className={isBaseRow ? "bg-blue-50/40 dark:bg-blue-950/15" : ""}>
                                    <td className={`py-1.5 px-3 text-right font-medium whitespace-nowrap ${isBaseRow ? "text-blue-600 dark:text-blue-400" : "text-gray-500"}`}>{g.toFixed(0)}%</td>
                                    {result.sensitivity.growth_margin.table[ri]?.map((rawVal, ci) => {
                                      const val = rawVal != null ? rawVal * fxRate : null;
                                      const isBaseCell = ri === baseRi && ci === baseCi;
                                      const isBaseRowOrCol = ri === baseRi || ci === baseCi;
                                      const diff = result.market_price && val != null ? (val - result.market_price) / result.market_price : 0;
                                      let cellColor = "text-gray-700 dark:text-gray-300";
                                      if (diff > 0.15) cellColor = "text-green-600 dark:text-green-400";
                                      else if (diff < -0.15) cellColor = "text-red-600 dark:text-red-400";
                                      return (
                                        <td key={ci} className={`py-1.5 px-3 text-right font-mono tabular-nums ${cellColor} ${isBaseCell ? "font-bold bg-blue-100 dark:bg-blue-950/40 ring-1 ring-blue-300 dark:ring-blue-700 rounded" : isBaseRowOrCol ? "bg-blue-50/50 dark:bg-blue-950/20" : ""}`}>
                                          {val?.toFixed(1) ?? "—"}
                                        </td>
                                      );
                                    })}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })()}

                  {/* WACC sensitivity */}
                  {result.sensitivity.wacc?.results && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{t.sensitivityWACC}</h4>
                      <div className="overflow-x-auto">
                        <table className="text-xs w-full">
                          <thead>
                            <tr>
                              <td className="py-2 px-3 text-right text-gray-500 font-medium whitespace-nowrap">WACC</td>
                              {Object.keys(result.sensitivity.wacc.results).map((waccVal) => {
                                const isBase = Math.abs(parseFloat(waccVal) - result.sensitivity.wacc.base) < 0.01;
                                return <th key={waccVal} className={`py-2 px-3 text-right font-medium whitespace-nowrap ${isBase ? "text-blue-600 dark:text-blue-400" : "text-gray-500 dark:text-gray-400"}`}>{parseFloat(waccVal).toFixed(1)}%</th>;
                              })}
                            </tr>
                          </thead>
                          <tbody>
                            <tr>
                              <td className="py-1.5 px-3 text-right text-gray-500 font-medium whitespace-nowrap">{t.pricePerShare} ({sensCurrency})</td>
                              {Object.entries(result.sensitivity.wacc.results).map(([waccVal, price]) => {
                                const isBase = Math.abs(parseFloat(waccVal) - result.sensitivity.wacc.base) < 0.01;
                                const converted = typeof price === "number" ? price * fxRate : null;
                                return <td key={waccVal} className={`py-1.5 px-3 text-right font-mono tabular-nums ${isBase ? "font-bold text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-950/30 rounded" : "text-gray-800 dark:text-gray-200"}`}>{converted != null ? converted.toFixed(1) : "—"}</td>;
                              })}
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Tab: AI Analysis ── */}
              {resultTab === "ai" && (
                <div>
                  {/* Gap analysis trigger + status */}
                  {!gapResult && !gapLoading && !gapError && (
                    <div className="text-center py-12">
                      <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-indigo-100 dark:bg-indigo-950/40 flex items-center justify-center">
                        <span className="text-2xl">🤖</span>
                      </div>
                      <h4 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-2">{t.gapAnalysis}</h4>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-5 max-w-md mx-auto">
                        {t.gapAnalysisDesc}
                      </p>
                      <button
                        type="button"
                        onClick={handleGapAnalysis}
                        disabled={gapLoading}
                        className="px-6 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
                      >
                        🤖 {t.runGapAnalysis}
                      </button>
                    </div>
                  )}

                  {gapError && (
                    <div className="p-3 bg-red-50 dark:bg-red-950/30 rounded-lg border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-300 mb-4">
                      {gapError}
                      <button
                        type="button"
                        onClick={handleGapAnalysis}
                        className="ml-3 text-xs underline hover:no-underline"
                      >
                        Retry
                      </button>
                    </div>
                  )}

                  {gapLoading && (
                    <div className="py-12 text-center">
                      <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mx-auto mb-4" />
                      <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400 mb-1">{gapProgress || t.analyzingGap}</p>
                      <p className="text-xs text-gray-400">{t.gapAnalysisWait}</p>
                    </div>
                  )}

                  {gapResult && (
                    <div>
                      {/* Engine badge + re-run */}
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                            {gapResult.engine}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={handleGapAnalysis}
                          disabled={gapLoading}
                          className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-50"
                        >
                          ↻ {t.rerun}
                        </button>
                      </div>

                      {/* Gap summary cards */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                        <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">DCF Estimate</div>
                          <div className="text-lg font-bold text-gray-900 dark:text-white">{gapResult.dcf_price.toFixed(2)}</div>
                          <div className="text-[10px] text-gray-400">{gapResult.currency}</div>
                        </div>
                        <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{t.currentPrice}</div>
                          <div className="text-lg font-bold text-gray-900 dark:text-white">{gapResult.market_price.toFixed(2)}</div>
                          <div className="text-[10px] text-gray-400">{gapResult.currency}</div>
                        </div>
                        <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">Gap</div>
                          <div className={`text-lg font-bold ${gapResult.gap_pct > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                            {gapResult.gap_pct > 0 ? "+" : ""}{gapResult.gap_pct.toFixed(1)}%
                          </div>
                          <div className="text-[10px] text-gray-400">vs market</div>
                        </div>
                        {gapResult.adjusted_price != null && (
                          <div className="p-3 rounded-lg bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-200 dark:border-indigo-800">
                            <div className="text-[10px] uppercase tracking-wider text-indigo-500 mb-1">{t.gapAdjustedPrice}</div>
                            <div className="text-lg font-bold text-indigo-700 dark:text-indigo-300">{gapResult.adjusted_price.toFixed(2)}</div>
                            <div className="text-[10px] text-indigo-400">{gapResult.currency}</div>
                          </div>
                        )}
                      </div>

                      {/* Markdown-rendered analysis */}
                      <div className="gap-analysis-content rounded-lg border border-gray-100 dark:border-gray-800 p-5 bg-gray-50/50 dark:bg-gray-800/30">
                        <div className="prose prose-sm dark:prose-invert max-w-none
                          prose-headings:text-gray-900 dark:prose-headings:text-gray-100
                          prose-headings:font-semibold prose-headings:border-b prose-headings:border-gray-200 dark:prose-headings:border-gray-700 prose-headings:pb-2 prose-headings:mb-3
                          prose-h2:text-base prose-h3:text-sm
                          prose-p:text-gray-700 dark:prose-p:text-gray-300 prose-p:leading-relaxed prose-p:text-[13px]
                          prose-li:text-gray-700 dark:prose-li:text-gray-300 prose-li:text-[13px]
                          prose-strong:text-gray-900 dark:prose-strong:text-gray-100
                          prose-ul:my-2 prose-ol:my-2
                          prose-li:my-0.5
                          prose-table:text-xs prose-th:bg-gray-100 dark:prose-th:bg-gray-800 prose-th:px-3 prose-th:py-1.5 prose-td:px-3 prose-td:py-1.5
                          max-h-[60vh] overflow-y-auto">
                          <ReactMarkdown>{gapResult.analysis_text}</ReactMarkdown>
                        </div>
                        <p className="mt-3 text-[11px] text-gray-400 dark:text-gray-500 italic">{t.gapDisclaimer}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── Tab: Buffett Owner Earnings ── */}
              {resultTab === "buffett" && buffett?.available && (() => {
                const b = buffett;
                const hasFx = b.forex_rate != null && b.stock_currency && b.reported_currency && b.stock_currency !== b.reported_currency;
                const rawIntrinsic = b.intrinsic_per_share ?? 0;
                const rawMos = b.margin_of_safety_price ?? 0;
                const bIntrinsic = hasFx ? rawIntrinsic * (b.forex_rate ?? 1) : rawIntrinsic;
                const bMos = hasFx ? rawMos * (b.forex_rate ?? 1) : rawMos;
                const displayCurrency = hasFx ? b.stock_currency! : (b.reported_currency ?? "USD");
                const marketPrice = b.market_price ?? 0;
                const diffPct = marketPrice ? ((bIntrinsic - marketPrice) / marketPrice * 100) : 0;
                const diffColor = diffPct > 10 ? "text-green-600 dark:text-green-400" : diffPct < -10 ? "text-red-600 dark:text-red-400" : "text-gray-700 dark:text-gray-300";
                return (
                  <div className="space-y-5">
                    <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 p-5">
                      <h4 className="text-sm font-semibold text-amber-800 dark:text-amber-200 mb-1">
                        {t.buffettTitle}
                      </h4>
                      <p className="text-[11px] text-gray-400 dark:text-gray-500 mb-4">{t.buffettSubtitle}</p>
                      <div className="flex flex-wrap items-center gap-6 mb-4">
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">{t.buffettIntrinsic}</div>
                          <div className="text-2xl font-bold text-gray-900 dark:text-white">{formatCurrency(bIntrinsic, displayCurrency)}</div>
                        </div>
                        {marketPrice > 0 && (
                          <div>
                            <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">{t.upsideDownside}</div>
                            <div className={`text-xl font-bold ${diffColor}`}>{diffPct > 0 ? "+" : ""}{diffPct.toFixed(1)}%</div>
                          </div>
                        )}
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-0.5">{t.buffettMos}</div>
                          <div className="text-xl font-bold text-gray-900 dark:text-white">{formatCurrency(bMos, displayCurrency)}</div>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px] pt-3 border-t border-amber-200/50 dark:border-amber-800/50">
                        <div>
                          <span className="text-gray-400">{b.ni_label ? `NI(${b.ni_label})` : "NI"}</span>
                          <div className="font-mono font-medium">{(b.net_income ?? 0).toLocaleString(undefined, {maximumFractionDigits: 0})}M</div>
                        </div>
                        <div>
                          <span className="text-gray-400">Owner Earnings</span>
                          <div className="font-mono font-medium">{(b.owner_earnings ?? 0).toLocaleString(undefined, {maximumFractionDigits: 0})}M</div>
                        </div>
                        <div>
                          <span className="text-gray-400">{t.growthRate}</span>
                          <div className="font-mono font-medium">{((b.growth_phase1 ?? 0) * 100).toFixed(1)}%</div>
                        </div>
                        <div>
                          <span className="text-gray-400">ROE(avg) / Payout</span>
                          <div className="font-mono font-medium">{(b.avg_roe ?? 0).toFixed(0)}% / {(b.payout ?? 0).toFixed(0)}%</div>
                        </div>
                      </div>
                    </div>
                    <ul className="space-y-1.5">
                      {t.buffettNotes.map((note, i) => (
                        <li key={i} className="text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed flex gap-2">
                          <span className="text-amber-400 dark:text-amber-600 mt-px shrink-0">•</span>
                          <span>{note}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
        );
      })()}
      </div>{/* end results wrapper */}

      {/* ── History Detail Modal (viewer.py style) ── */}
      {detailItem && (
        <div className="fixed inset-0 z-[100] flex items-start justify-center bg-black/40 backdrop-blur-sm overflow-y-auto py-8 px-4"
          onClick={(e) => { if (e.target === e.currentTarget) setDetailItem(null); }}>
          <div className="bg-white dark:bg-gray-950 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 w-full max-w-3xl animate-in fade-in slide-in-from-bottom-4">
            {/* Header */}
            <div className="sticky top-0 z-10 bg-white dark:bg-gray-950 rounded-t-2xl border-b border-gray-200 dark:border-gray-700 px-6 py-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                  {detailItem.company_name} <span className="text-gray-400 font-normal text-sm">({detailItem.ticker})</span>
                </h2>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {new Date(detailItem.date).toLocaleDateString()} · {detailItem.mode === "copilot" ? "🤖 AI Copilot" : "✏️ Manual"}
                  {detailItem.ai_engine && <span> · {detailItem.ai_engine}</span>}
                  {detailItem.updated_at !== detailItem.date && (
                    <span className="ml-2 text-gray-400">({t.updated}: {new Date(detailItem.updated_at).toLocaleDateString()})</span>
                  )}
                </div>
              </div>
              <button onClick={() => setDetailItem(null)} className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
                <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Latest Assessment bar (viewer.py style) */}
            <div className={`mx-6 mt-4 p-4 rounded-xl border-l-4 font-mono text-sm flex flex-wrap gap-x-8 gap-y-3 ${
              detailItem.diff_pct > 0
                ? "border-l-green-500 bg-green-50/50 dark:bg-green-950/20"
                : "border-l-red-500 bg-red-50/50 dark:bg-red-950/20"
            }`}>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">DCF Estimate</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{detailItem.currency} {detailItem.dcf_price.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">{t.marketPrice}</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{detailItem.currency} {detailItem.market_price.toFixed(2)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">DCF vs Market</div>
                <div className={`text-lg font-bold ${detailItem.diff_pct > 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                  {detailItem.diff_pct > 0 ? "+" : ""}{(detailItem.diff_pct * 100).toFixed(1)}%
                  <span className="text-xs font-normal ml-1">{detailItem.diff_pct > 0 ? "Undervalued" : "Overvalued"}</span>
                </div>
              </div>
              {detailItem.gap_analysis?.adjusted_price != null && (
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-0.5">{t.gapAdjustedPrice}</div>
                  <div className="text-lg font-bold text-indigo-600 dark:text-indigo-400">
                    {detailItem.currency} {detailItem.gap_analysis.adjusted_price.toFixed(2)}
                    {detailItem.gap_analysis.gap_pct != null && (
                      <span className="text-xs font-normal ml-1">({(detailItem.gap_analysis.gap_pct * 100).toFixed(1)}%)</span>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="px-6 py-4 space-y-5">

              {/* ── Section: Valuation Parameters ── */}
              <div>
                <div className="text-sm font-bold text-gray-900 dark:text-white mb-2 pl-3 border-l-[3px] border-blue-500">
                  Valuation Parameters
                </div>
                <div className="font-mono text-sm divide-y divide-gray-100 dark:divide-gray-800">
                  {[
                    ["Revenue Growth Y1", `${detailItem.revenue_growth_1}%`],
                    ["Revenue Growth Y2-5", `${detailItem.revenue_growth_2}%`],
                    ["Target EBIT Margin", `${detailItem.ebit_margin}%`],
                    ["Convergence", `${detailItem.convergence} yrs`],
                    ["Rev/IC Y1-2", detailItem.rev_ic_1.toFixed(2)],
                    ["Rev/IC Y3-5", detailItem.rev_ic_2.toFixed(2)],
                    ["Rev/IC Y5-10", detailItem.rev_ic_3.toFixed(2)],
                    ["Tax Rate", `${detailItem.tax_rate}%`],
                    ["WACC", `${detailItem.wacc}%`],
                    ["RONIC = WACC", detailItem.ronic_match_wacc ? "Yes" : "No"],
                  ].map(([label, val]) => (
                    <div key={label} className="flex justify-between py-1.5 px-1 hover:bg-gray-50 dark:hover:bg-gray-900/50 rounded">
                      <span className="text-gray-600 dark:text-gray-400">{label}</span>
                      <span className="text-gray-900 dark:text-white font-medium">{val}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* ── Section: Valuation Breakdown (Bridge) ── */}
              {detailItem.bridge && Object.keys(detailItem.bridge).length > 0 && (
                <div>
                  <div className="text-sm font-bold text-gray-900 dark:text-white mb-2 pl-3 border-l-[3px] border-blue-500">
                    {t.bridgeToValue} ({detailItem.reported_currency || detailItem.currency} M)
                  </div>
                  <div className="font-mono text-sm divide-y divide-gray-100 dark:divide-gray-800">
                    {Object.entries(detailItem.bridge).map(([key, val]) => {
                      const isHighlight = key === "price_per_share" || key === "equity_value";
                      const isSubtotal = key === "enterprise_value" || key === "operating_value";
                      const isNegative = key === "total_debt" || key === "minority_interest";
                      const displayLabel = key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
                        .replace("Pv ", "PV ").replace("Outstanding Shares", "Outstanding Shares (M)")
                        .replace("Total Debt", "(−) Total Debt").replace("Minority Interest", "(−) Minority Interest")
                        .replace("Cash", "(+) Cash").replace("Total Investments", "(+) Total Investments");
                      const numVal = typeof val === "number" ? (isNegative ? -val : val) : val;
                      const displayVal = key === "outstanding_shares"
                        ? (typeof val === "number" ? (val / 1e6).toLocaleString(undefined, { maximumFractionDigits: 1 }) : val)
                        : (typeof numVal === "number" ? numVal.toLocaleString(undefined, { maximumFractionDigits: 0 }) : numVal);
                      return (
                        <div key={key} className={`flex justify-between py-1.5 px-1 rounded hover:bg-gray-50 dark:hover:bg-gray-900/50 ${
                          isHighlight ? "text-green-700 dark:text-green-400 font-bold text-base border-t-2 border-gray-200 dark:border-gray-700 pt-2" :
                          isSubtotal ? "text-blue-600 dark:text-blue-400 font-semibold" :
                          "text-gray-600 dark:text-gray-400"
                        }`}>
                          <span>{displayLabel}</span>
                          <span>{displayVal}</span>
                        </div>
                      );
                    })}
                  </div>
                  {detailItem.reported_currency && detailItem.reported_currency !== detailItem.currency && (
                    <div className="text-[11px] text-gray-400 mt-1">
                      * {t.reportedCurrency}: {detailItem.reported_currency} → {detailItem.currency}
                    </div>
                  )}
                </div>
              )}

              {/* ── Section: AI Reasoning ── */}
              {detailItem.ai_reasoning && (
                <div>
                  <div className="text-sm font-bold text-gray-900 dark:text-white mb-2 pl-3 border-l-[3px] border-blue-500">
                    AI Reasoning {detailItem.ai_engine && <span className="font-normal text-gray-400 text-xs">({detailItem.ai_engine})</span>}
                  </div>
                  <div className="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30 p-4 max-h-80 overflow-y-auto">
                    <div className="prose prose-sm dark:prose-invert max-w-none
                      prose-p:text-[13px] prose-p:leading-relaxed prose-p:text-gray-700 dark:prose-p:text-gray-300
                      prose-li:text-[13px] prose-li:text-gray-700 dark:prose-li:text-gray-300
                      prose-strong:text-gray-900 dark:prose-strong:text-gray-100
                      prose-headings:text-sm prose-headings:font-semibold">
                      <ReactMarkdown>{detailItem.ai_reasoning}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Section: Gap Analysis ── */}
              {detailItem.gap_analysis?.analysis_text && (
                <div>
                  <div className="text-sm font-bold text-gray-900 dark:text-white mb-2 pl-3 border-l-[3px] border-blue-500">
                    {t.gapAnalysis}
                  </div>
                  {/* Gap summary bar */}
                  <div className="flex flex-wrap gap-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800 mb-3 font-mono text-sm">
                    <div><span className="text-[10px] text-gray-400 uppercase">DCF</span><br/><span className="font-semibold">{detailItem.currency} {detailItem.dcf_price.toFixed(2)}</span></div>
                    <div><span className="text-[10px] text-gray-400 uppercase">Market</span><br/><span className="font-semibold">{detailItem.currency} {detailItem.market_price.toFixed(2)}</span></div>
                    {detailItem.gap_analysis.gap_pct != null && (
                      <div><span className="text-[10px] text-gray-400 uppercase">Gap</span><br/>
                        <span className={`font-semibold ${detailItem.gap_analysis.gap_pct > 0 ? "text-green-600" : "text-red-600"}`}>
                          {(detailItem.gap_analysis.gap_pct * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {detailItem.gap_analysis.adjusted_price != null && (
                      <div><span className="text-[10px] text-gray-400 uppercase">Adjusted</span><br/><span className="font-semibold text-indigo-600 dark:text-indigo-400">{detailItem.currency} {detailItem.gap_analysis.adjusted_price.toFixed(2)}</span></div>
                    )}
                  </div>
                  {/* Gap analysis text */}
                  <div className="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/30 p-4 max-h-80 overflow-y-auto">
                    <div className="prose prose-sm dark:prose-invert max-w-none
                      prose-p:text-[13px] prose-p:leading-relaxed prose-p:text-gray-700 dark:prose-p:text-gray-300
                      prose-li:text-[13px] prose-li:text-gray-700 dark:prose-li:text-gray-300
                      prose-strong:text-gray-900 dark:prose-strong:text-gray-100
                      prose-headings:text-sm prose-headings:font-semibold
                      prose-table:text-xs prose-th:bg-gray-100 dark:prose-th:bg-gray-800 prose-th:px-3 prose-th:py-1.5 prose-td:px-3 prose-td:py-1.5">
                      <ReactMarkdown>{detailItem.gap_analysis.analysis_text}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-gray-100 dark:border-gray-800 text-[11px] text-gray-400 flex justify-between">
              <span>ID: {detailItem.id} · IndexedDB</span>
              <span>{detailItem.reported_currency && detailItem.reported_currency !== detailItem.currency
                ? `${detailItem.reported_currency} → ${detailItem.currency}`
                : detailItem.currency}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Bridge Row ──

function BridgeRow({
  label,
  value,
  bold,
  highlight,
  isShares,
}: {
  label: string;
  value: number;
  bold?: boolean;
  highlight?: boolean;
  isShares?: boolean;
}) {
  const formatted = isShares
    ? formatLargeNumber(value)
    : formatNumber(value, 0);
  return (
    <div className={`flex justify-between items-center py-0.5 ${
      highlight ? "text-blue-700 dark:text-blue-300" : bold ? "text-gray-900 dark:text-white" : "text-gray-600 dark:text-gray-400"
    } ${bold || highlight ? "font-semibold" : ""}`}>
      <span className="text-xs">{label}</span>
      <span className={highlight ? "text-base" : "text-sm"}>{formatted}</span>
    </div>
  );
}

// ── DCF Input Field ──

function DCFInputField({
  label,
  desc,
  value,
  onChange,
  step = 1,
  min,
  max,
  historyHint,
}: {
  label: string;
  desc?: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
  historyHint?: React.ReactNode;
}) {
  const [localValue, setLocalValue] = useState(String(value));
  const [focused, setFocused] = useState(false);

  // Sync from parent when not focused
  useEffect(() => {
    if (!focused) setLocalValue(String(value));
  }, [value, focused]);

  return (
    <div>
      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-0.5">
        {label}
      </label>
      {desc && (
        <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 italic">
          {desc}
        </div>
      )}
      <input
        type="number"
        value={focused ? localValue : value}
        onChange={(e) => {
          setLocalValue(e.target.value);
          if (e.target.value === "" || e.target.value === "-") return;
          const num = parseFloat(e.target.value);
          if (!isNaN(num)) onChange(num);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            (e.target as HTMLInputElement).blur();
          }
        }}
        onFocus={() => { setFocused(true); setLocalValue(String(value)); }}
        onBlur={() => {
          setFocused(false);
          if (localValue === "" || localValue === "-") {
            onChange(0);
            return;
          }
          const num = parseFloat(localValue);
          if (!isNaN(num)) onChange(num);
        }}
        step={step}
        min={min}
        max={max}
        className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      />
      {historyHint}
    </div>
  );
}
