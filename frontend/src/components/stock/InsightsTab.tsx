"use client";

import { useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  Cell,
} from "recharts";
import { useI18n } from "@/lib/i18n";
import { formatNumber } from "@/lib/format";
import {
  type EstimatesData,
  type TranscriptAnalysisResult,
  runTranscriptAnalysis,
} from "@/lib/api";

// ── Analyst Estimates Section ──

function AnalystEstimatesSection({ estimates }: { estimates: EstimatesData }) {
  const { t } = useI18n();

  const pastQuarters = estimates.estimates || [];
  const forwardQuarters = estimates.forward_estimates || [];

  const chartData = [...pastQuarters].reverse().map((q) => {
    const est = q.estimated_eps;
    const act = q.actual_eps;
    const isBeat = act != null && est != null && act > est;
    const surprisePct = act != null && est != null && est !== 0
      ? ((act - est) / Math.abs(est) * 100) : null;
    return { period: q.period, estimated: est, actual: act, isBeat, surprisePct };
  });

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {t.analystEstimates}
      </h3>

      <div className="space-y-5">
        {estimates.total_count != null && estimates.total_count > 0 && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {t.beatEstimates(estimates.beat_count || 0, estimates.total_count)}
          </p>
        )}
        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {(estimates as any).currency_note && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            ⚠ {String((estimates as any).currency_note)}
          </p>
        )}

        {chartData.length > 0 && (
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                <XAxis dataKey="period" tick={{ fontSize: 10, fill: "#9ca3af" }} />
                <YAxis tick={{ fontSize: 11, fill: "#9ca3af" }} />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null;
                    const cur = ((estimates as any).eps_currency) || "USD";
                    const sym = cur === "USD" ? "$" : cur + " ";
                    const d = chartData.find((c) => c.period === label);
                    return (
                      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 shadow-lg text-xs">
                        <p className="font-medium text-gray-900 dark:text-white mb-1">{label}</p>
                        {d?.estimated != null && <p className="text-gray-500">{t.estimated}: {sym}{d.estimated.toFixed(2)}</p>}
                        {d?.actual != null && (
                          <p className={d.isBeat ? "text-green-600" : "text-red-600"}>
                            {t.actual}: {sym}{d.actual.toFixed(2)}
                            {d.surprisePct != null && (
                              <span className="ml-1 font-medium">
                                ({d.surprisePct > 0 ? "+" : ""}{d.surprisePct.toFixed(1)}%)
                              </span>
                            )}
                          </p>
                        )}
                      </div>
                    );
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11 }}
                  content={() => (
                    <div className="flex justify-center gap-4 text-xs mt-1">
                      <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-gray-400 opacity-60" />{t.estimated}</span>
                      <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-green-500" />{t.actual} (Beat)</span>
                      <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-red-500" />{t.actual} (Miss)</span>
                    </div>
                  )}
                />
                <Bar dataKey="estimated" fill="#9ca3af" opacity={0.6} radius={[2, 2, 0, 0]} />
                <Bar dataKey="actual" radius={[2, 2, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.actual == null ? "transparent" : entry.isBeat ? "#22c55e" : "#ef4444"}
                      opacity={entry.actual == null ? 0 : 0.8}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {forwardQuarters.length > 0 && (() => {
          const epsCur = (estimates as any).eps_currency || "USD";
          const finCur = (estimates as any).financials_currency || "USD";
          return (
            <div>
              <h4 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">
                {t.forwardEstimates}
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-400 border-b border-gray-200 dark:border-gray-700">
                      <th className="text-left py-2 pr-4 font-medium">Period</th>
                      <th className="text-right py-2 px-3 font-medium">EPS ({epsCur})</th>
                      <th className="text-right py-2 px-3 font-medium">Revenue ({finCur})</th>
                      <th className="text-right py-2 px-3 font-medium">Rev Growth</th>
                      <th className="text-right py-2 px-3 font-medium">Net Income ({finCur})</th>
                      <th className="text-right py-2 px-3 font-medium">NI%</th>
                      <th className="text-right py-2 pl-3 font-medium">Analysts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forwardQuarters.map((q: any, i: number) => (
                      <tr key={i} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                        <td className="py-2 pr-4 font-medium text-gray-900 dark:text-white">{q.period}</td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_eps?.toFixed(2) ?? "—"}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_revenue ? formatNumber(q.estimated_revenue / 1e6, 0) + "M" : "—"}
                        </td>
                        <td className={`py-2 px-3 text-right font-medium ${
                          q.revenue_growth == null ? "text-gray-400"
                            : q.revenue_growth > 0 ? "text-green-600 dark:text-green-400"
                            : q.revenue_growth < 0 ? "text-red-600 dark:text-red-400"
                            : "text-gray-500"
                        }`}>
                          {q.revenue_growth != null ? (q.revenue_growth > 0 ? "+" : "") + q.revenue_growth + "%" : "—"}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_net_income ? formatNumber(q.estimated_net_income / 1e6, 0) + "M" : "—"}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.net_income_margin != null ? q.net_income_margin + "%" : "—"}
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
          );
        })()}
      </div>
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

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {t.earningsCallInsights}
      </h3>

      {/* Run button or loading state */}
      {!data && !loading && (
        <div>
          <button
            onClick={handleRun}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            {t.runTranscriptAnalysis}
          </button>
          {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-3">
          <svg className="animate-spin h-5 w-5 text-blue-500" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm text-gray-500 dark:text-gray-400">{progress}</span>
        </div>
      )}

      {data && (
        <div className="space-y-5">
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
                  <span key={i} className="inline-block px-2 py-0.5 rounded-full text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400">
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
                <div key={i} className="rounded-lg border border-gray-100 dark:border-gray-800 p-4">
                  <div className="flex items-center gap-3 mb-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Q{r.quarter} {r.year}</span>
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>{r.tone}</span>
                    <span className="text-xs text-gray-400">{guidanceIcon(r.guidance_direction)} {guidanceLabel(r.guidance_direction)}</span>
                    <span className="text-xs text-gray-400">{t.managementConfidence}: {r.management_confidence}/5</span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">{r.summary}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {r.key_themes.map((theme, j) => (
                      <span key={j} className="inline-block px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">{theme}</span>
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

// ── InsightsTab ──

export default function InsightsTab({
  ticker,
  estimates,
  apikey,
  deepseekKey,
}: {
  ticker: string;
  estimates?: EstimatesData | null;
  apikey?: string;
  deepseekKey?: string;
}) {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      {/* Analyst Estimates */}
      {estimates && estimates.available && estimates.estimates && estimates.estimates.length > 0 && (
        <AnalystEstimatesSection estimates={estimates} />
      )}
      {estimates && !estimates.available && estimates.reason && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <p className="text-sm text-gray-400 dark:text-gray-500">
            {estimates.reason === "FMP API key required" ? t.fmpApiRequired : t.noEstimatesAvailable}
          </p>
        </div>
      )}
      {!estimates && (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">{t.analystEstimates}</h3>
          <p className="text-sm text-gray-400">{t.fmpApiRequired}</p>
        </div>
      )}

      {/* Earnings Call Insights */}
      {apikey ? (
        <EarningsCallInsightsSection
          ticker={ticker}
          apikey={apikey}
          deepseekKey={deepseekKey || ""}
        />
      ) : (
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">{t.earningsCallInsights}</h3>
          <p className="text-sm text-gray-400">{t.fmpApiRequired}</p>
        </div>
      )}
    </div>
  );
}
