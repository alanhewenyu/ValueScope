"use client";

import { useState, useMemo } from "react";
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
import { type EstimatesData } from "@/lib/api";

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
                    {/* Actual base years */}
                    {((estimates as any).actual_years || []).map((q: any, i: number) => (
                      <tr key={`act-${i}`} className="border-b border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30">
                        <td className="py-2 pr-4 font-medium text-gray-900 dark:text-white">
                          {q.period} <span className="text-xs font-normal text-gray-400">(Actual)</span>
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_eps?.toFixed(2) ?? "—"}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_revenue ? formatNumber(q.estimated_revenue / 1e6, 0) + "M" : "—"}
                        </td>
                        <td className={`py-2 px-3 text-right font-medium ${
                          q.revenue_growth == null ? "text-gray-400"
                            : q.revenue_growth > 0 ? "text-green-600 dark:text-green-400"
                            : "text-red-600 dark:text-red-400"
                        }`}>
                          {q.revenue_growth != null ? (q.revenue_growth > 0 ? "+" : "") + q.revenue_growth + "%" : ""}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.estimated_net_income ? formatNumber(q.estimated_net_income / 1e6, 0) + "M" : "—"}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700 dark:text-gray-300">
                          {q.net_income_margin != null ? q.net_income_margin + "%" : "—"}
                        </td>
                        <td className="py-2 pl-3 text-right text-gray-400"></td>
                      </tr>
                    ))}
                    {/* Divider */}
                    {((estimates as any).actual_years || []).length > 0 && (
                      <tr><td colSpan={7} className="py-0.5 bg-blue-100 dark:bg-blue-900/30" /></tr>
                    )}
                    {/* Forward estimates */}
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

// ── Analyst Rating Changes Section ──

type RatingChange = { date: string; company: string; previous: string; new: string; direction: string };
type TimeRange = "3m" | "6m" | "1y" | "all";

function RatingChangesSection({ changes }: { changes: RatingChange[] }) {
  const [range, setRange] = useState<TimeRange>("3m");

  const filtered = useMemo(() => {
    if (range === "all") return changes;
    const now = new Date();
    const months = range === "3m" ? 3 : range === "6m" ? 6 : 12;
    const cutoff = new Date(now.getFullYear(), now.getMonth() - months, now.getDate());
    const cutoffStr = cutoff.toISOString().slice(0, 10);
    return changes.filter((c) => c.date >= cutoffStr);
  }, [changes, range]);

  const summary = useMemo(() => {
    let up = 0, down = 0, maintain = 0;
    for (const c of filtered) {
      if (c.direction === "upgrade") up++;
      else if (c.direction === "downgrade") down++;
      else maintain++;
    }
    return { upgrades: up, downgrades: down, maintains: maintain };
  }, [filtered]);

  const dirColor = (d: string) =>
    d === "upgrade" ? "text-green-600 dark:text-green-400"
    : d === "downgrade" ? "text-red-600 dark:text-red-400"
    : "text-gray-400";
  const dirIcon = (d: string) => d === "upgrade" ? "↑" : d === "downgrade" ? "↓" : "→";

  const ranges: { key: TimeRange; label: string }[] = [
    { key: "3m", label: "3M" },
    { key: "6m", label: "6M" },
    { key: "1y", label: "1Y" },
    { key: "all", label: "All" },
  ];

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Analyst Rating Changes
        </h3>
        <div className="flex gap-1">
          {ranges.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                range === r.key
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                  : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {/* Summary chips */}
      <div className="flex gap-3 mb-4 text-sm">
        {summary.upgrades > 0 && (
          <span className="px-2.5 py-1 rounded-full bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 font-medium">
            ↑ {summary.upgrades} Upgrade{summary.upgrades > 1 ? "s" : ""}
          </span>
        )}
        {summary.downgrades > 0 && (
          <span className="px-2.5 py-1 rounded-full bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 font-medium">
            ↓ {summary.downgrades} Downgrade{summary.downgrades > 1 ? "s" : ""}
          </span>
        )}
        {summary.maintains > 0 && (
          <span className="px-2.5 py-1 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 font-medium">
            → {summary.maintains} Maintained
          </span>
        )}
        {filtered.length === 0 && (
          <span className="text-sm text-gray-400">No rating changes in this period</span>
        )}
      </div>
      {/* Changes list */}
      {filtered.length > 0 && (
        <div className="space-y-1.5">
          {filtered.map((c, i) => (
            <div key={i} className="flex items-center gap-3 text-sm py-1 border-b border-gray-50 dark:border-gray-800 last:border-0">
              <span className="text-xs text-gray-400 w-20 shrink-0">{c.date.slice(0, 10)}</span>
              <span className="text-gray-600 dark:text-gray-300 w-28 shrink-0 truncate">{c.company}</span>
              <span className={`font-medium ${dirColor(c.direction)}`}>
                {c.previous} {dirIcon(c.direction)} {c.new}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── InsightsTab ──

export default function InsightsTab({
  estimates,
}: {
  ticker?: string;
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

      {/* Analyst Rating Changes */}
      {estimates && (estimates as any).rating_changes?.length > 0 && (
        <RatingChangesSection
          changes={(estimates as any).rating_changes}
        />
      )}

      {/* Data source note */}
      <p className="text-[10px] text-gray-400 dark:text-gray-500 text-right">
        Data source: Financial Modeling Prep (FMP) · Analyst consensus estimates & ratings
      </p>
    </div>
  );
}
