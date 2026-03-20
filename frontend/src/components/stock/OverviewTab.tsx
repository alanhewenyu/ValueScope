"use client";

import { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  LineChart,
  BarChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ReferenceLine,
  Cell,
} from "recharts";
import { useI18n } from "@/lib/i18n";
import { formatNumber } from "@/lib/format";
import FinancialTable from "@/components/FinancialTable";
import {
  type CompanyProfile,
  type FinancialData,
  type FreshnessInfo,
  type RelativeValuationData,
  type ScoresData,
  type EstimatesData,
  type TranscriptAnalysisResult,
  runTranscriptAnalysis,
} from "@/lib/api";

// ── Helpers ──

/** Extract numeric series from financials.summary by row name, returns {year, value}[] in chronological order. */
function extractSeries(
  financials: FinancialData,
  rowName: string,
): { year: string; value: number }[] {
  const { columns, index, data } = financials.summary;
  const rowIdx = index.indexOf(rowName);
  if (rowIdx === -1) return [];
  return columns
    .map((col, i) => ({ year: col, value: data[rowIdx]?.[i] ?? 0 }))
    .reverse(); // chronological
}

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">
        {label}
      </div>
      <div className="text-lg font-semibold text-gray-900 dark:text-white">
        {value}
      </div>
    </div>
  );
}

// ── Analyst Estimates Section ──

function AnalystEstimatesSection({ estimates }: { estimates: EstimatesData }) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(false);

  const pastQuarters = estimates.estimates || [];
  const forwardQuarters = estimates.forward_estimates || [];

  // Prepare chart data: reverse so oldest is on left
  const chartData = [...pastQuarters].reverse().map((q) => ({
    period: q.period,
    estimated: q.estimated_eps,
    actual: q.actual_eps,
    isBeat: q.actual_eps != null && q.estimated_eps != null && q.actual_eps > q.estimated_eps,
  }));

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => setCollapsed(!collapsed)}
      >
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          {t.analystEstimates}
        </h3>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform ${collapsed ? "" : "rotate-180"}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {!collapsed && (
        <div className="mt-4 space-y-5">
          {/* Beat summary */}
          {estimates.total_count != null && estimates.total_count > 0 && (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t.beatEstimates(estimates.beat_count || 0, estimates.total_count)}
            </p>
          )}

          {/* EPS Chart */}
          {chartData.length > 0 && (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                  <XAxis dataKey="period" tick={{ fontSize: 10, fill: "#9ca3af" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(255,255,255,0.96)",
                      border: "1px solid #e5e7eb",
                      borderRadius: "8px",
                      fontSize: "12px",
                      color: "#1f2937",
                      boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                    }}
                    formatter={(value, name) => {
                      const v = Number(value);
                      const label = name === "estimated" ? t.estimated : t.actual;
                      return [v != null && !isNaN(v) ? `$${v.toFixed(2)}` : "—", label];
                    }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11, color: "#9ca3af" }}
                    formatter={(value: string) => (value === "estimated" ? t.estimated : t.actual)}
                  />
                  <Bar dataKey="estimated" fill="#9ca3af" opacity={0.6} radius={[2, 2, 0, 0]} />
                  <Bar dataKey="actual" radius={[2, 2, 0, 0]}>
                    {chartData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={entry.actual == null ? "#9ca3af" : entry.isBeat ? "#22c55e" : "#ef4444"}
                        opacity={0.8}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Forward Estimates table */}
          {forwardQuarters.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                {t.forwardEstimates}
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-400 border-b border-gray-200 dark:border-gray-700">
                      <th className="text-left py-2 pr-4 font-medium">Period</th>
                      <th className="text-right py-2 px-3 font-medium">EPS ({t.estimated})</th>
                      <th className="text-right py-2 px-3 font-medium">Revenue ({t.estimated})</th>
                      <th className="text-right py-2 pl-3 font-medium">Analysts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forwardQuarters.map((q, i) => (
                      <tr
                        key={i}
                        className="border-b border-gray-100 dark:border-gray-800 last:border-0"
                      >
                        <td className="py-2 pr-4 text-gray-700 dark:text-gray-300">{q.period}</td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          ${q.estimated_eps.toFixed(2)}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_revenue ? formatNumber(q.estimated_revenue / 1e6, 0) + "M" : "—"}
                        </td>
                        <td className="py-2 pl-3 text-right text-gray-400">
                          {q.number_of_analysts || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Earnings Call Insights Section ──

const toneColors: Record<string, { bg: string; text: string }> = {
  bullish: { bg: "bg-green-100 dark:bg-green-900/30", text: "text-green-700 dark:text-green-400" },
  neutral: { bg: "bg-gray-100 dark:bg-gray-800", text: "text-gray-600 dark:text-gray-400" },
  cautious: { bg: "bg-yellow-100 dark:bg-yellow-900/30", text: "text-yellow-700 dark:text-yellow-400" },
  bearish: { bg: "bg-red-100 dark:bg-red-900/30", text: "text-red-700 dark:text-red-400" },
};

const sentimentDot = (score: number) => {
  if (score > 0.3) return "bg-green-500";
  if (score > 0) return "bg-green-300";
  if (score > -0.3) return "bg-yellow-400";
  return "bg-red-500";
};

function EarningsCallInsightsSection({
  ticker,
  apikey,
  deepseekKey,
}: {
  ticker: string;
  apikey: string;
  deepseekKey: string;
}) {
  const { t } = useI18n();
  const [collapsed, setCollapsed] = useState(true);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState("");
  const [data, setData] = useState<TranscriptAnalysisResult | null>(null);
  const [error, setError] = useState("");

  const handleRun = async () => {
    setLoading(true);
    setError("");
    setProgress(t.analyzingTranscripts);
    try {
      const result = await runTranscriptAnalysis(
        ticker,
        apikey,
        deepseekKey,
        4,
        (msg) => setProgress(msg),
      );
      setData(result);
      setCollapsed(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
      setProgress("");
    }
  };

  const guidanceLabel = (dir: string) => {
    switch (dir) {
      case "raised": return t.guidanceRaised;
      case "maintained": return t.guidanceMaintained;
      case "lowered": return t.guidanceLowered;
      default: return t.guidanceNotGiven;
    }
  };

  const guidanceIcon = (dir: string) => {
    switch (dir) {
      case "raised": return "↑";
      case "lowered": return "↓";
      case "maintained": return "→";
      default: return "—";
    }
  };

  const sentimentLabel = (dir: string) => {
    switch (dir) {
      case "improving": return t.sentimentImproving;
      case "declining": return t.sentimentDeclining;
      default: return t.sentimentStable;
    }
  };

  const sentimentColor = (dir: string) => {
    switch (dir) {
      case "improving": return "text-green-600 dark:text-green-400";
      case "declining": return "text-red-600 dark:text-red-400";
      default: return "text-gray-600 dark:text-gray-400";
    }
  };

  if (!apikey || !deepseekKey) return null;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => data && setCollapsed(!collapsed)}
      >
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          {t.earningsCallInsights}
        </h3>
        {data && (
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${collapsed ? "" : "rotate-180"}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* Run button or loading state */}
      {!data && !loading && (
        <div className="mt-4">
          <button
            onClick={handleRun}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            {t.runTranscriptAnalysis}
          </button>
          {error && (
            <p className="mt-2 text-sm text-red-500">{error}</p>
          )}
        </div>
      )}

      {/* Loading spinner with progress */}
      {loading && (
        <div className="mt-4 flex items-center gap-3">
          <svg className="animate-spin h-5 w-5 text-blue-500" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm text-gray-500 dark:text-gray-400">{progress}</span>
        </div>
      )}

      {/* Results */}
      {data && !collapsed && (
        <div className="mt-4 space-y-5">
          {/* Trend Summary */}
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500 dark:text-gray-400">{t.sentimentTrend}:</span>
              <span className={`font-medium ${sentimentColor(data.trend.sentiment_direction)}`}>
                {sentimentLabel(data.trend.sentiment_direction)}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500 dark:text-gray-400">{t.managementConfidence}:</span>
              <span className="font-medium text-gray-700 dark:text-gray-300">
                {data.trend.avg_confidence}/5
              </span>
            </div>
            {data.trend.recurring_themes.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-gray-500 dark:text-gray-400">{t.recurringThemes}:</span>
                {data.trend.recurring_themes.map((theme, i) => (
                  <span
                    key={i}
                    className="inline-block px-2 py-0.5 rounded-full text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400"
                  >
                    {theme}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Sentiment dots */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">{t.sentimentTrend}</span>
            <div className="flex items-center gap-1.5">
              {[...data.results].reverse().map((r, i) => (
                <div key={i} className="flex flex-col items-center gap-0.5">
                  <div className={`w-3 h-3 rounded-full ${sentimentDot(r.sentiment_score)}`} title={`Q${r.quarter} ${r.year}: ${r.sentiment_score.toFixed(2)}`} />
                  <span className="text-[9px] text-gray-400">Q{r.quarter}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Per-quarter cards */}
          <div className="space-y-3">
            {data.results.map((r, i) => {
              const colors = toneColors[r.tone] || toneColors.neutral;
              return (
                <div
                  key={i}
                  className="rounded-lg border border-gray-100 dark:border-gray-800 p-4"
                >
                  <div className="flex items-center gap-3 mb-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Q{r.quarter} {r.year}
                    </span>
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
                      {r.tone}
                    </span>
                    <span className="text-xs text-gray-400">
                      {guidanceIcon(r.guidance_direction)} {guidanceLabel(r.guidance_direction)}
                    </span>
                    <span className="text-xs text-gray-400">
                      {t.managementConfidence}: {r.management_confidence}/5
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {r.summary}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {r.key_themes.map((theme, j) => (
                      <span
                        key={j}
                        className="inline-block px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400"
                      >
                        {theme}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── OverviewTab ──

export default function OverviewTab({
  profile,
  financials,
  wacc,
  ticker,
  scores,
  relVal,
  freshness,
  estimates,
  apikey,
  deepseekKey,
}: {
  profile: CompanyProfile | null;
  financials: FinancialData | null;
  wacc: {
    wacc: number;
    risk_free_rate: number;
    details: Record<string, unknown>;
  } | null;
  ticker: string;
  scores: ScoresData | null;
  relVal: RelativeValuationData | null;
  freshness?: FreshnessInfo;
  estimates?: EstimatesData | null;
  apikey?: string;
  deepseekKey?: string;
}) {
  const { t, locale } = useI18n();

  // ── Extract chart data from financials ──
  const chartData = (() => {
    if (!financials) return null;
    const revenue = extractSeries(financials, "Revenue");
    const revenueGrowth = extractSeries(financials, "Revenue Growth (%)");
    const ebitMargin = extractSeries(financials, "EBIT Margin (%)");
    const roic = extractSeries(financials, "ROIC (%)");
    const roe = extractSeries(financials, "ROE (%)");
    const ebit = extractSeries(financials, "EBIT");
    const taxRate = extractSeries(financials, "Tax Rate (%)");
    const reinvestment = extractSeries(financials, "Total Reinvestment");

    // Revenue & Growth combined — first year has no prior year, so growth is null
    const revenueGrowthData = revenue.map((r, i) => {
      const g = revenueGrowth.find((g) => g.year === r.year);
      return { year: r.year, revenue: r.value, growth: i === 0 ? null : (g?.value ?? null) };
    });

    // EBIT Margin with average
    const marginVals = ebitMargin.map((m) => m.value).filter((v) => v != null && isFinite(v));
    const marginAvg = marginVals.length > 0 ? marginVals.reduce((a, b) => a + b, 0) / marginVals.length : 0;

    // ROIC & ROE combined — show all valid values (no cap filter)
    const roicRoeData = roic.map((r) => {
      const roeItem = roe.find((e) => e.year === r.year);
      const roeVal = roeItem?.value != null && isFinite(roeItem.value) ? roeItem.value : null;
      const roicVal = r.value != null && isFinite(r.value) ? r.value : null;
      return { year: r.year, roic: roicVal, roe: roeVal };
    });

    // FCF = EBIT × (1 - Tax Rate) - Total Reinvestment (FCFF)
    const fcfData = ebit.map((e) => {
      const tax = taxRate.find((t) => t.year === e.year);
      const reinv = reinvestment.find((r) => r.year === e.year);
      const taxR = (tax?.value ?? 0) / 100;
      const nopat = e.value * (1 - taxR);
      const fcf = nopat - (reinv?.value ?? 0);
      return { year: e.year, fcf: isFinite(fcf) ? fcf : 0 };
    });

    // Balance sheet: latest values (first column in summary = most recent)
    const getLatest = (row: string): number | null => {
      const { index, data } = financials.summary;
      const idx = index.indexOf(row);
      if (idx === -1) return null;
      // columns[0] is most recent
      const val = data[idx]?.[0];
      return val != null && isFinite(val) ? val : null;
    };

    // Reported currency (from the summary row)
    const currencyRowIdx = financials.summary.index.indexOf("Reported Currency");
    const reportedCurrency = currencyRowIdx >= 0
      ? String(financials.formatted_summary.data[currencyRowIdx]?.[0] || "")
      : "";

    // Period label: use column header which may be "2025" for TTM, annotate with TTM quarter
    const latestCol = financials.summary.columns[0] || "";
    const ttmQ = financials.ttm_latest_quarter;
    const latestPeriodLabel = ttmQ ? `${latestCol} (${ttmQ} TTM)` : latestCol;

    // Map chart year labels: annotate latest (last after reverse) with TTM quarter
    // Use index-based mapping (not string match) to handle non-Dec fiscal years
    // where TTM year may equal the prior FY's calendar year
    const ttmYearLabel = ttmQ ? `${latestCol}(${ttmQ} TTM)` : latestCol;
    const applyYearMap = <T extends { year: string }>(arr: T[]) =>
      ttmQ
        ? arr.map((d, i) => i === arr.length - 1 ? { ...d, year: ttmYearLabel } : d)
        : arr;

    // FCF average
    const fcfVals = fcfData.map((d) => d.fcf).filter((v) => isFinite(v));
    const fcfAvg =
      fcfVals.length > 0
        ? fcfVals.reduce((a, b) => a + b, 0) / fcfVals.length
        : 0;

    return {
      revenueGrowth: applyYearMap(revenueGrowthData),
      ebitMargin: applyYearMap(ebitMargin),
      marginAvg,
      roicRoe: applyYearMap(roicRoeData),
      fcf: applyYearMap(fcfData),
      fcfAvg,
      balance: {
        cash: getLatest("(-) Cash & Equivalents"),
        investments: getLatest("(-) Total Investments"),
        debt: getLatest("(+) Total Debt"),
        debtToAssets: getLatest("Debt to Assets (%)"),
      },
      latestPeriod: latestPeriodLabel,
      reportedCurrency,
    };
  })();

  const tooltipStyle = {
    contentStyle: {
      backgroundColor: "rgba(255,255,255,0.96)",
      border: "1px solid #e5e7eb",
      borderRadius: "8px",
      fontSize: "12px",
      color: "#1f2937",
      boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    },
    labelStyle: { color: "#6b7280", fontWeight: 500 },
    itemStyle: { color: "#1f2937" },
  };

  return (
    <div className="space-y-8">
      {/* Quick Summary Cards — PE → PB → Score */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* PE percentile card */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <div className="text-xs text-gray-400 mb-2">{t.pePercentile5Y}</div>
          {relVal?.historical?.pe_percentile != null ? (
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-gray-900 dark:text-white">
                {relVal.historical.pe_percentile.toFixed(0)}
                <span className="text-sm font-normal text-gray-400">{t.percentileSuffix}</span>
              </span>
              <span className="text-sm text-gray-500">
                PE {relVal.historical.pe_stats?.current?.toFixed(1)}x
              </span>
            </div>
          ) : (
            <div className="text-sm text-gray-400">{t.na}</div>
          )}
        </div>

        {/* PB percentile card */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <div className="text-xs text-gray-400 mb-2">{t.pbPercentile5Y}</div>
          {relVal?.historical?.pb_percentile != null ? (
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-gray-900 dark:text-white">
                {relVal.historical.pb_percentile.toFixed(0)}
                <span className="text-sm font-normal text-gray-400">{t.percentileSuffix}</span>
              </span>
              <span className="text-sm text-gray-500">
                PB {relVal.historical.pb_stats?.current?.toFixed(1)}x
              </span>
            </div>
          ) : (
            <div className="text-sm text-gray-400">{t.na}</div>
          )}
        </div>

        {/* ValueScope Score card */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-5">
          <div className="text-xs text-gray-400 mb-2">{t.valueScopeScore}</div>
          {scores ? (
            <div className="flex items-baseline gap-1">
              <span
                className="text-3xl font-bold"
                style={{
                  color:
                    scores.total_score >= 75
                      ? "#22c55e"
                      : scores.total_score >= 50
                      ? "#3b82f6"
                      : scores.total_score >= 25
                      ? "#eab308"
                      : "#ef4444",
                }}
              >
                {scores.total_score}
              </span>
              <span className="text-sm text-gray-400">/100</span>
            </div>
          ) : (
            <div className="text-sm text-gray-400">{t.loading}</div>
          )}
        </div>
      </div>

      {/* ── Key Drivers: 4 charts in 2×2 grid ── */}
      {chartData && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-5">
            {t.keyDrivers}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* 1. Revenue & Growth */}
            <div>
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                {t.revenueAndGrowth}
                {chartData.reportedCurrency && (
                  <span className="text-xs font-normal text-gray-400 ml-1">({t.inMillions(chartData.reportedCurrency)})</span>
                )}
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData.revenueGrowth} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#9ca3af" }} />
                    <YAxis yAxisId="left" tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v: number) => formatNumber(v, 0)} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                    <Tooltip
                      {...tooltipStyle}
                      formatter={(value, name) => {
                        const v = Number(value);
                        return name === "growth"
                          ? [`${v.toFixed(1)}%`, t.growthLabel]
                          : [formatNumber(v, 0), t.revenueLabel];
                      }}
                    />
                    <Bar yAxisId="left" dataKey="revenue" fill="#3b82f6" opacity={0.7} radius={[2, 2, 0, 0]} />
                    <Line yAxisId="right" dataKey="growth" type="monotone" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3, fill: "#f59e0b" }} connectNulls />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* 2. EBIT Margin */}
            <div>
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
                {t.ebitMargin}
                <span className="block text-[10px] font-normal text-gray-400">{t.ebitMarginNote}</span>
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData.ebitMargin} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#9ca3af" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                    <Tooltip
                      {...tooltipStyle}
                      formatter={(value) => [`${Number(value).toFixed(1)}%`, t.ebitMargin]}
                    />
                    <ReferenceLine y={chartData.marginAvg} stroke="#6b7280" strokeDasharray="4 4" label={{ value: `Avg ${chartData.marginAvg.toFixed(1)}%`, position: "right", fontSize: 10, fill: "#9ca3af" }} />
                    <Line dataKey="value" type="monotone" stroke="#10b981" strokeWidth={2} dot={{ r: 3, fill: "#10b981" }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* 3. ROIC & ROE */}
            <div>
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">
                {t.roicAndRoe}
                <span className="block text-[10px] font-normal text-gray-400">{t.roicNote}</span>
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData.roicRoe} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#9ca3af" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                    <Tooltip
                      {...tooltipStyle}
                      formatter={(value, name) => [
                        value != null ? `${Number(value).toFixed(1)}%` : "—",
                        String(name).toUpperCase(),
                      ]}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, color: "#9ca3af" }} />
                    <Line dataKey="roic" name="ROIC" type="monotone" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3, fill: "#8b5cf6" }} connectNulls />
                    <Line dataKey="roe" name="ROE" type="monotone" stroke="#06b6d4" strokeWidth={2} dot={{ r: 3, fill: "#06b6d4" }} connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* 4. Free Cash Flow */}
            <div>
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                {t.freeCashFlow}
                {chartData.reportedCurrency && (
                  <span className="text-xs font-normal text-gray-400 ml-1">({t.inMillions(chartData.reportedCurrency)})</span>
                )}
              </div>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData.fcf} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                    <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#9ca3af" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} tickFormatter={(v: number) => formatNumber(v, 0)} />
                    <Tooltip
                      {...tooltipStyle}
                      formatter={(value) => [formatNumber(Number(value), 0), "FCFF"]}
                    />
                    <ReferenceLine y={0} stroke="#6b7280" />
                    <ReferenceLine y={chartData.fcfAvg} stroke="#6b7280" strokeDasharray="4 4" label={{ value: t.mean(formatNumber(chartData.fcfAvg, 0)), position: "insideTopRight", fontSize: 10, fill: "#9ca3af" }} />
                    <Bar dataKey="fcf" radius={[2, 2, 0, 0]}>
                      {chartData.fcf.map((entry, i) => (
                        <Cell key={i} fill={entry.fcf >= 0 ? "#22c55e" : "#ef4444"} opacity={0.8} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Balance Sheet Highlights ── */}
      {chartData?.balance && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h3 className="text-sm font-semibold text-gray-500 dark:text-gray-400 mb-3">
            {t.balanceSheetHighlights}
            <span className="font-normal text-xs text-gray-400 ml-2">
              {chartData.latestPeriod}
              {chartData.reportedCurrency && ` · ${t.inMillions(chartData.reportedCurrency)}`}
            </span>
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            <MetricItem
              label={t.cashEquivalents}
              value={chartData.balance.cash != null ? formatNumber(chartData.balance.cash, 0) : "—"}
            />
            <MetricItem
              label={t.totalInvestments}
              value={chartData.balance.investments != null ? formatNumber(chartData.balance.investments, 0) : "—"}
            />
            <MetricItem
              label={t.interestBearingDebt}
              value={chartData.balance.debt != null ? formatNumber(chartData.balance.debt, 0) : "—"}
            />
            <MetricItem
              label={t.interestBearingDebtRatio}
              value={chartData.balance.debtToAssets != null ? `${chartData.balance.debtToAssets.toFixed(1)}%` : "—"}
            />
          </div>
        </div>
      )}

      {financials && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          {/* Freshness indicator */}
          {freshness?.is_stale && freshness.data_source === "api" && (
            <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
                {locale === "zh" ? "数据滞后" : "Data Lag"}
              </span>
              <span className="text-gray-500 dark:text-gray-400">
                {locale === "zh"
                  ? `${freshness.expected_period} 财报已披露，当前数据尚未更新。请参阅公司最新公告。`
                  : `${freshness.expected_period} earnings released but data not yet updated. Please refer to the latest company announcement.`}
              </span>
            </div>
          )}
          {freshness?.is_stale && freshness.data_source !== "api" && (
            <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">
                {locale === "zh" ? "已补充最新数据" : "Supplemented"}
              </span>
              <span className="text-gray-500 dark:text-gray-400">
                {locale === "zh"
                  ? `${freshness.expected_period} 数据来源: 东方财富。API 更新后将自动切换至原数据源。`
                  : `${freshness.expected_period} data from EastMoney. Will auto-switch to primary source once API updates.`}
              </span>
            </div>
          )}
          <FinancialTable
            title={t.historicalFinancials(financials.company_name)}
            columns={financials.formatted_summary.columns}
            index={financials.formatted_summary.index}
            data={financials.formatted_summary.data}
          />
          {financials.ttm_note && (
            <p className="text-xs text-gray-400 mt-3">
              {financials.ttm_note}
            </p>
          )}
          {financials.formatted_summary.index.includes("Incremental Margin (%)") && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
              ⓘ {t.fin_incrementalMarginNote}
            </p>
          )}
          {financials.formatted_summary.index.includes("Net Income") && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
              ⓘ {t.fin_netIncomeNote}
            </p>
          )}
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-xs text-gray-400 dark:text-gray-500 text-left">
        ⚙️ {t.overviewDisclaimer}
      </p>
    </div>
  );
}
