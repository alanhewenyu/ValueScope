"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { useI18n } from "@/lib/i18n";
import { formatNumber } from "@/lib/format";
import {
  getHistoryStatus,
  getHistoryFilters,
  searchValuations,
  getValuationDetail,
  deleteValuation,
  type ValuationRecord,
  type ValuationDetail,
  type HistoryFilters,
} from "@/lib/api";

// ── Helpers ──

function gapColor(pct: number | null | undefined): string {
  if (pct == null || isNaN(pct)) return "text-gray-400";
  // Positive gap = undervalued (green), negative = overvalued (red)
  return pct >= 0
    ? "text-green-600 dark:text-green-400"
    : "text-red-600 dark:text-red-400";
}

function gapStr(pct: number | null | undefined): string {
  if (pct == null || isNaN(pct)) return "—";
  const prefix = pct > 0 ? "+" : "";
  return `${prefix}${pct.toFixed(1)}%`;
}

function modeLabel(mode: string): string {
  const m: Record<string, string> = {
    manual: "Manual",
    copilot: "Copilot",
    auto: "Auto",
  };
  return m[mode] || mode;
}

function modeBadgeColor(mode: string): string {
  if (mode === "auto") return "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300";
  if (mode === "copilot") return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300";
  return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
}

// ── Detail Modal ──

function DetailModal({
  detail,
  onClose,
}: {
  detail: ValuationDetail;
  onClose: () => void;
}) {
  const { locale } = useI18n();

  const dcfPrice = detail.price_per_share || detail.gap_dcf_price;
  const marketPrice = detail.market_price || detail.gap_market_price;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-16 px-4 bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-xl max-w-3xl w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-4 flex items-center justify-between rounded-t-2xl">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
              {detail.ticker} — {detail.company_name}
            </h2>
            <p className="text-sm text-gray-500">
              {detail.valuation_date} · {modeLabel(detail.mode)}
              {detail.ai_engine && ` · ${detail.ai_engine}`}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="px-6 py-4 space-y-5">
          {/* Valuation Result */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-500 uppercase">{locale === "zh" ? "DCF估值" : "DCF Price"}</div>
              <div className="text-lg font-semibold font-mono">{dcfPrice ? dcfPrice.toFixed(2) : "—"}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500 uppercase">{locale === "zh" ? "市场价" : "Market Price"}</div>
              <div className="text-lg font-mono">{marketPrice ? marketPrice.toFixed(2) : "—"}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500 uppercase">{locale === "zh" ? "差距" : "Gap"}</div>
              <div className={`text-lg font-semibold font-mono ${gapColor(detail.gap_pct)}`}>
                {gapStr(detail.gap_pct)}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500 uppercase">{locale === "zh" ? "币种" : "Currency"}</div>
              <div className="text-lg font-mono">{detail.currency}</div>
            </div>
          </div>

          {/* Key Parameters */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-2">
              {locale === "zh" ? "估值参数" : "Valuation Parameters"}
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm font-mono">
              <div>
                <span className="text-gray-500">Rev Growth 1: </span>
                <span>{detail.revenue_growth_1 != null ? `${(detail.revenue_growth_1 * 100).toFixed(1)}%` : "—"}</span>
              </div>
              <div>
                <span className="text-gray-500">Rev Growth 2: </span>
                <span>{detail.revenue_growth_2 != null ? `${(detail.revenue_growth_2 * 100).toFixed(1)}%` : "—"}</span>
              </div>
              <div>
                <span className="text-gray-500">EBIT Margin: </span>
                <span>{detail.ebit_margin != null ? `${(detail.ebit_margin * 100).toFixed(1)}%` : "—"}</span>
              </div>
              <div>
                <span className="text-gray-500">WACC: </span>
                <span>{detail.wacc != null ? `${(detail.wacc * 100).toFixed(1)}%` : "—"}</span>
              </div>
            </div>
          </div>

          {/* Valuation Bridge */}
          {(detail.pv_cf_10yr != null || detail.enterprise_value != null) && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-2">
                {locale === "zh" ? "估值分解" : "Valuation Bridge"}
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm font-mono">
                {detail.pv_cf_10yr != null && (
                  <div><span className="text-gray-500">PV CF (10yr): </span>{formatNumber(detail.pv_cf_10yr)}</div>
                )}
                {detail.pv_terminal != null && (
                  <div><span className="text-gray-500">PV Terminal: </span>{formatNumber(detail.pv_terminal)}</div>
                )}
                {detail.enterprise_value != null && (
                  <div><span className="text-gray-500">EV: </span>{formatNumber(detail.enterprise_value)}</div>
                )}
                {detail.equity_value != null && (
                  <div><span className="text-gray-500">Equity Value: </span>{formatNumber(detail.equity_value)}</div>
                )}
                {detail.total_debt != null && (
                  <div><span className="text-gray-500">Debt: </span>{formatNumber(detail.total_debt)}</div>
                )}
                {detail.cash != null && (
                  <div><span className="text-gray-500">Cash: </span>{formatNumber(detail.cash)}</div>
                )}
              </div>
            </div>
          )}

          {/* AI Raw Text */}
          {detail.ai_raw_text && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide mb-2">
                {locale === "zh" ? "AI 分析" : "AI Analysis"}
              </h3>
              <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                {detail.ai_raw_text}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──

export default function HistoryPage() {
  const { locale } = useI18n();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [records, setRecords] = useState<ValuationRecord[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState<HistoryFilters | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search state
  const [query, setQuery] = useState("");
  const [selectedModes, setSelectedModes] = useState<string[]>([]);
  const [selectedEngines, setSelectedEngines] = useState<string[]>([]);

  // Detail view
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ValuationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const search = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await searchValuations({
        q: query || undefined,
        modes: selectedModes.length ? selectedModes.join(",") : undefined,
        engines: selectedEngines.length ? selectedEngines.join(",") : undefined,
        limit: 200,
      });
      setRecords(res.results);
      setTotalCount(res.count);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [query, selectedModes, selectedEngines]);

  // Initial load
  useEffect(() => {
    (async () => {
      try {
        const status = await getHistoryStatus();
        setAvailable(status.available);
        if (!status.available) {
          setLoading(false);
          return;
        }
        const [f] = await Promise.all([getHistoryFilters(), search()]);
        setFilters(f);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load");
        setLoading(false);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Load detail when clicked
  useEffect(() => {
    if (detailId == null) {
      setDetail(null);
      return;
    }
    (async () => {
      setDetailLoading(true);
      try {
        const d = await getValuationDetail(detailId);
        setDetail(d);
      } catch {
        setDetail(null);
      } finally {
        setDetailLoading(false);
      }
    })();
  }, [detailId]);

  async function handleDelete(id: number) {
    if (!confirm(locale === "zh" ? "确定要删除这条估值记录吗？" : "Delete this valuation record?")) return;
    try {
      await deleteValuation(id);
      setRecords((prev) => prev.filter((r) => r.id !== id));
      if (detailId === id) setDetailId(null);
    } catch {
      /* ignore */
    }
  }

  return (
    <>
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          {locale === "zh" ? "估值记录" : "Valuation History"}
        </h1>

        {available === false && !loading && (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">📊</div>
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300 mb-2">
              {locale === "zh" ? "未找到估值数据库" : "No Valuation Database Found"}
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
              {locale === "zh"
                ? "先在估值页面保存一些估值结果，然后就可以在这里查看历史记录。"
                : "Save some valuations first, then come back to view your history."}
            </p>
          </div>
        )}

        {available && (
          <>
            {/* Search & Filters */}
            <div className="flex flex-wrap gap-3 mb-5">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder={locale === "zh" ? "搜索代码或公司名..." : "Search ticker or company..."}
                className="flex-1 min-w-[200px] px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />

              {/* Mode filter */}
              {filters && filters.modes.length > 0 && (
                <div className="flex gap-1.5">
                  {filters.modes.map((m) => (
                    <button
                      key={m}
                      onClick={() =>
                        setSelectedModes((prev) =>
                          prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
                        )
                      }
                      className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                        selectedModes.includes(m)
                          ? "bg-blue-600 text-white border-blue-600"
                          : "border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                      }`}
                    >
                      {modeLabel(m)}
                    </button>
                  ))}
                </div>
              )}

              <button
                onClick={search}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                {locale === "zh" ? "搜索" : "Search"}
              </button>
            </div>

            {error && (
              <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-xl p-4 mb-4">
                {error}
              </div>
            )}

            {loading && (
              <div className="flex items-center justify-center h-32 text-gray-500">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mr-3" />
                {locale === "zh" ? "加载中..." : "Loading..."}
              </div>
            )}

            {!loading && records.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                {locale === "zh" ? "没有找到匹配的估值记录" : "No matching valuations found"}
              </div>
            )}

            {!loading && records.length > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-800 text-xs text-gray-500 dark:text-gray-400 uppercase">
                        <th className="text-left px-4 py-3">{locale === "zh" ? "股票" : "Stock"}</th>
                        <th className="text-left px-3 py-3">{locale === "zh" ? "日期" : "Date"}</th>
                        <th className="text-center px-3 py-3">{locale === "zh" ? "模式" : "Mode"}</th>
                        <th className="text-right px-3 py-3 font-mono">DCF</th>
                        <th className="text-right px-3 py-3 font-mono">{locale === "zh" ? "市价" : "Market"}</th>
                        <th className="text-right px-3 py-3 font-mono">Gap</th>
                        <th className="text-right px-3 py-3 font-mono">WACC</th>
                        <th className="text-center px-3 py-3" />
                      </tr>
                    </thead>
                    <tbody>
                      {records.map((r) => {
                        const dcfPrice = r.price_per_share || r.gap_dcf_price;
                        const mktPrice = r.market_price || r.gap_market_price;
                        return (
                          <tr
                            key={r.id}
                            className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors cursor-pointer"
                            onClick={() => setDetailId(r.id)}
                          >
                            <td className="px-4 py-2.5">
                              <Link
                                href={`/stock/${r.ticker}`}
                                onClick={(e) => e.stopPropagation()}
                                className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                              >
                                {r.ticker}
                              </Link>
                              <div className="text-[11px] text-gray-500 truncate max-w-[140px]">
                                {r.company_name}
                              </div>
                            </td>
                            <td className="px-3 py-2.5 text-gray-600 dark:text-gray-400 whitespace-nowrap">
                              {r.valuation_date}
                            </td>
                            <td className="px-3 py-2.5 text-center">
                              <span className={`inline-block px-2 py-0.5 text-[11px] rounded-full font-medium ${modeBadgeColor(r.mode)}`}>
                                {modeLabel(r.mode)}
                              </span>
                            </td>
                            <td className="text-right px-3 py-2.5 font-mono">
                              {dcfPrice ? dcfPrice.toFixed(2) : "—"}
                            </td>
                            <td className="text-right px-3 py-2.5 font-mono text-gray-600 dark:text-gray-400">
                              {mktPrice ? mktPrice.toFixed(2) : "—"}
                            </td>
                            <td className={`text-right px-3 py-2.5 font-mono font-semibold ${gapColor(r.gap_pct)}`}>
                              {gapStr(r.gap_pct)}
                            </td>
                            <td className="text-right px-3 py-2.5 font-mono text-gray-600 dark:text-gray-400">
                              {r.wacc != null ? `${(r.wacc * 100).toFixed(1)}%` : "—"}
                            </td>
                            <td className="px-3 py-2.5 text-center">
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDelete(r.id); }}
                                className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                                title={locale === "zh" ? "删除" : "Delete"}
                              >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                                </svg>
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="px-4 py-3 text-xs text-gray-500 border-t border-gray-200 dark:border-gray-800">
                  {locale === "zh" ? `共 ${records.length} 条记录` : `${records.length} records`}
                </div>
              </div>
            )}
          </>
        )}

        {/* Detail Modal */}
        {detailId != null && detail && !detailLoading && (
          <DetailModal detail={detail} onClose={() => setDetailId(null)} />
        )}
      </main>
    </>
  );
}
