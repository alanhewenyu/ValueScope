"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { useI18n } from "@/lib/i18n";
import { formatNumber, formatCurrency } from "@/lib/format";
import {
  getPortfolioStatus,
  getPortfolioHoldings,
  type PortfolioData,
  type PortfolioHolding,
} from "@/lib/api";

// ── Helpers ──

function pnlColor(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return "text-gray-400";
  // Chinese market convention: red = positive, green = negative
  return val >= 0
    ? "text-red-600 dark:text-red-400"
    : "text-green-600 dark:text-green-400";
}

function pnlSign(val: number | null | undefined, decimals = 0): string {
  if (val == null || isNaN(val)) return "—";
  const prefix = val > 0 ? "+" : "";
  return `${prefix}${formatNumber(val, decimals)}`;
}

function pctStr(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return "—";
  const prefix = val > 0 ? "+" : "";
  return `${prefix}${val.toFixed(2)}%`;
}

// ── KPI Card ──

function KpiCard({
  label,
  value,
  sub,
  subColor,
}: {
  label: string;
  value: string;
  sub?: string;
  subColor?: string;
}) {
  return (
    <div className="flex-1 min-w-[140px] p-4 rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
      <div className="text-xs text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
        {label}
      </div>
      <div className="text-xl font-semibold font-mono text-gray-900 dark:text-white">
        {value}
      </div>
      {sub && (
        <div className={`text-xs font-mono mt-0.5 ${subColor || "text-gray-500"}`}>
          {sub}
        </div>
      )}
    </div>
  );
}

// ── FX Banner ──

function FxBanner({ fx }: { fx: Record<string, number> }) {
  const pairs: [string, string, number][] = [
    ["USD/CNY", "USD", 4],
    ["HKD/CNY", "HKD", 4],
    ["JPY/CNY", "JPY", 5],
  ];
  return (
    <div className="flex gap-6 text-xs font-mono text-gray-500 dark:text-gray-400 mb-4">
      {pairs.map(([label, cur, dec]) => (
        <span key={cur}>
          {label}:{" "}
          <span className="font-semibold text-gray-700 dark:text-gray-300">
            {fx[cur] ? fx[cur].toFixed(dec as number) : "—"}
          </span>
        </span>
      ))}
    </div>
  );
}

// ── Main Page ──

export default function PortfolioPage() {
  const { t, locale } = useI18n();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<string>("weight");
  const [sortAsc, setSortAsc] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const status = await getPortfolioStatus();
      setAvailable(status.available);
      if (!status.available) {
        setLoading(false);
        return;
      }
      const holdings = await getPortfolioHoldings();
      setData(holdings);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Sort holdings
  const sorted = data?.holdings
    ? [...data.holdings].sort((a, b) => {
        const av = (a as unknown as Record<string, unknown>)[sortKey];
        const bv = (b as unknown as Record<string, unknown>)[sortKey];
        const numA = typeof av === "number" ? av : 0;
        const numB = typeof bv === "number" ? bv : 0;
        return sortAsc ? numA - numB : numB - numA;
      })
    : [];

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function SortIcon({ col }: { col: string }) {
    if (sortKey !== col) return null;
    return <span className="ml-0.5 text-[10px]">{sortAsc ? "▲" : "▼"}</span>;
  }

  return (
    <>
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          {locale === "zh" ? "投资组合" : "Portfolio"}
        </h1>

        {loading && (
          <div className="flex items-center justify-center h-64 text-gray-500">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />
            {t.loading}
          </div>
        )}

        {!loading && available === false && (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">📂</div>
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300 mb-2">
              {locale === "zh" ? "未配置投资组合" : "Portfolio Not Configured"}
            </h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-md mx-auto">
              {locale === "zh"
                ? "设置 PORTFOLIO_DB_PATH 环境变量以启用此功能。"
                : "Set the PORTFOLIO_DB_PATH environment variable to enable this feature."}
            </p>
          </div>
        )}

        {!loading && error && (
          <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-xl p-4">
            {error}
          </div>
        )}

        {!loading && data && (
          <>
            {/* FX Banner */}
            <FxBanner fx={data.fx} />

            {/* KPI Cards */}
            <div className="flex flex-wrap gap-3 mb-6">
              <KpiCard
                label={locale === "zh" ? "资产净值" : "Net Assets"}
                value={`¥${formatNumber(data.summary.net_assets)}`}
              />
              <KpiCard
                label={locale === "zh" ? "权益市值" : "Equity"}
                value={`¥${formatNumber(data.summary.equity_cny)}`}
              />
              <KpiCard
                label={locale === "zh" ? "现金" : "Cash"}
                value={`¥${formatNumber(data.summary.cash_cny)}`}
              />
              {data.summary.leverage_cny > 0 && (
                <KpiCard
                  label={locale === "zh" ? "杠杆" : "Leverage"}
                  value={`¥${formatNumber(data.summary.leverage_cny)}`}
                />
              )}
              <KpiCard
                label={locale === "zh" ? "总盈亏" : "Total P&L"}
                value={`¥${pnlSign(data.summary.total_pnl_cny)}`}
                sub={pctStr(data.summary.total_pnl_pct)}
                subColor={pnlColor(data.summary.total_pnl_cny)}
              />
              <KpiCard
                label={locale === "zh" ? "日盈亏" : "Daily P&L"}
                value={`¥${pnlSign(data.summary.daily_pnl_cny)}`}
                subColor={pnlColor(data.summary.daily_pnl_cny)}
              />
              <KpiCard
                label={locale === "zh" ? "年初至今" : "YTD P&L"}
                value={`¥${pnlSign(data.summary.ytd_pnl_cny)}`}
                subColor={pnlColor(data.summary.ytd_pnl_cny)}
              />
            </div>

            {/* Holdings Table */}
            <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden mb-6">
              <div className="overflow-x-auto">
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-800 text-xs text-gray-500 dark:text-gray-400 uppercase">
                      <th className="text-left px-4 py-3 sticky left-0 bg-white dark:bg-gray-900 z-10">
                        {locale === "zh" ? "股票" : "Stock"}
                      </th>
                      <th className="text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("market_value_cny")}>
                        {locale === "zh" ? "市值" : "MV"}<SortIcon col="market_value_cny" />
                      </th>
                      <th className="text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("weight")}>
                        {locale === "zh" ? "占比" : "Wt%"}<SortIcon col="weight" />
                      </th>
                      <th className="text-right px-3 py-3 whitespace-nowrap">
                        {locale === "zh" ? "现价" : "Price"}
                      </th>
                      <th className="text-right px-3 py-3 whitespace-nowrap">
                        {locale === "zh" ? "成本" : "Cost"}
                      </th>
                      <th className="text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("pnl_cny")}>
                        {locale === "zh" ? "盈亏" : "P&L"}<SortIcon col="pnl_cny" />
                      </th>
                      <th className="text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("pnl_pct")}>
                        {locale === "zh" ? "盈亏%" : "P&L%"}<SortIcon col="pnl_pct" />
                      </th>
                      <th className="text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("daily_pnl_cny")}>
                        {locale === "zh" ? "日盈亏" : "Day"}<SortIcon col="daily_pnl_cny" />
                      </th>
                      <th className="text-right px-3 py-3 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("ytd_pnl_pct")}>
                        YTD%<SortIcon col="ytd_pnl_pct" />
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((h) => (
                      <tr
                        key={`${h.ticker}-${h.broker}`}
                        className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors"
                      >
                        <td className="px-4 py-2.5 sticky left-0 bg-white dark:bg-gray-900 z-10">
                          <Link
                            href={`/stock/${h.ticker}`}
                            className="text-blue-600 dark:text-blue-400 hover:underline"
                          >
                            {h.ticker}
                          </Link>
                          <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate max-w-[120px]">
                            {h.name}
                          </div>
                        </td>
                        <td className="text-right px-3 py-2.5 whitespace-nowrap">
                          {formatNumber(h.market_value_cny)}
                        </td>
                        <td className="text-right px-3 py-2.5 whitespace-nowrap">
                          {h.weight.toFixed(1)}%
                        </td>
                        <td className={`text-right px-3 py-2.5 whitespace-nowrap ${h.price_stale ? "text-gray-400 italic" : ""}`}>
                          {h.price.toFixed(2)}
                        </td>
                        <td className="text-right px-3 py-2.5 whitespace-nowrap text-gray-500">
                          {h.cost_price.toFixed(2)}
                        </td>
                        <td className={`text-right px-3 py-2.5 whitespace-nowrap ${pnlColor(h.pnl_cny)}`}>
                          {pnlSign(h.pnl_cny)}
                        </td>
                        <td className={`text-right px-3 py-2.5 whitespace-nowrap ${pnlColor(h.pnl_pct)}`}>
                          {pctStr(h.pnl_pct)}
                        </td>
                        <td className={`text-right px-3 py-2.5 whitespace-nowrap ${pnlColor(h.daily_pnl_cny)}`}>
                          {pnlSign(h.daily_pnl_cny)}
                        </td>
                        <td className={`text-right px-3 py-2.5 whitespace-nowrap ${pnlColor(h.ytd_pnl_pct)}`}>
                          {pctStr(h.ytd_pnl_pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  {sorted.length > 0 && (
                    <tfoot>
                      <tr className="border-t-2 border-gray-300 dark:border-gray-700 font-semibold">
                        <td className="px-4 py-3 sticky left-0 bg-white dark:bg-gray-900 z-10">
                          {locale === "zh" ? "合计" : "Total"} ({sorted.length})
                        </td>
                        <td className="text-right px-3 py-3">
                          {formatNumber(data.summary.equity_cny)}
                        </td>
                        <td className="text-right px-3 py-3">100%</td>
                        <td />
                        <td />
                        <td className={`text-right px-3 py-3 ${pnlColor(data.summary.total_pnl_cny)}`}>
                          {pnlSign(data.summary.total_pnl_cny)}
                        </td>
                        <td className={`text-right px-3 py-3 ${pnlColor(data.summary.total_pnl_pct)}`}>
                          {pctStr(data.summary.total_pnl_pct)}
                        </td>
                        <td className={`text-right px-3 py-3 ${pnlColor(data.summary.daily_pnl_cny)}`}>
                          {pnlSign(data.summary.daily_pnl_cny)}
                        </td>
                        <td />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </div>

            {/* Cash Balances */}
            {data.cash && data.cash.length > 0 && (
              <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden mb-6">
                <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800">
                  <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                    {locale === "zh" ? "现金余额" : "Cash Balances"}
                  </h2>
                </div>
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="text-xs text-gray-500 dark:text-gray-400 uppercase border-b border-gray-200 dark:border-gray-800">
                      <th className="text-left px-4 py-2">{locale === "zh" ? "账户" : "Account"}</th>
                      <th className="text-right px-4 py-2">{locale === "zh" ? "币种" : "Currency"}</th>
                      <th className="text-right px-4 py-2">{locale === "zh" ? "余额" : "Balance"}</th>
                      <th className="text-right px-4 py-2">{locale === "zh" ? "折人民币" : "CNY Value"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.cash.map((c) => (
                      <tr key={c.account} className="border-b border-gray-100 dark:border-gray-800/50">
                        <td className="px-4 py-2">{c.account}</td>
                        <td className="text-right px-4 py-2">{c.currency}</td>
                        <td className="text-right px-4 py-2">{formatNumber(c.balance, 2)}</td>
                        <td className="text-right px-4 py-2">
                          {formatNumber(c.balance * (data.fx[c.currency] || 1))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-gray-300 dark:border-gray-700 font-semibold">
                      <td className="px-4 py-2">{locale === "zh" ? "合计" : "Total"}</td>
                      <td />
                      <td />
                      <td className="text-right px-4 py-2">¥{formatNumber(data.summary.cash_cny)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}

            {/* Refresh button */}
            <div className="flex justify-end">
              <button
                onClick={load}
                disabled={loading}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {locale === "zh" ? "刷新" : "Refresh"}
              </button>
            </div>
          </>
        )}
      </main>
    </>
  );
}
