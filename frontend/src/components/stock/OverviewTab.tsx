"use client";

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
  type RelativeValuationData,
  type ScoresData,
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

// ── OverviewTab ──

export default function OverviewTab({
  profile,
  financials,
  wacc,
  ticker,
  scores,
  relVal,
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
}) {
  const { t } = useI18n();

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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
        </div>
      )}

      {/* Disclaimer */}
      <p className="text-xs text-gray-400 dark:text-gray-500 text-left">
        ⚙️ {t.overviewDisclaimer}
      </p>
    </div>
  );
}
