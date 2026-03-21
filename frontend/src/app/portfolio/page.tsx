"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { useSettings } from "@/lib/settings";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth-context";
import { formatNumber } from "@/lib/format";
import {
  getPortfolioStatus,
  getPortfolioHoldings,
  getClosedTrades,
  getSnapshots,
  getNavHistory,
  getBenchmarks,
  upsertPosition,
  deletePosition,
  updateCash,
  deleteCash,
  updateMargin,
  getMarginBalances,
  getAccountSettings,
  upsertAccountSetting,
  deleteAccountSetting,
  addClosedTrade,
  getDepositHistory,
  addDepositRecord,
  deleteDepositRecord,
  type PortfolioData,
  type PortfolioHolding,
  type ClosedTrade,
  type Snapshot,
  type NavHistoryPoint,
  type BenchmarkPoint,
  type AccountSetting,
  type MarginBalance,
  type DepositRecord,
  importCSV,
  getImportTemplateUrl,
  mergeAccounts,
  listPortfolios,
  switchPortfolio,
  getPortfolioNews,
  getPortfolioEarnings,
  getPortfolioRatings,
  type PortfolioInfo,
  type PortfolioNewsItem,
  type PortfolioEarningsEvent,
  type PortfolioRatingChange,
} from "@/lib/api";

// ══════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════

function pnlColor(val: number | null | undefined): string {
  if (val == null || isNaN(val)) return "text-gray-400";
  return val >= 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400";
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

function fmtNum(val: number | null | undefined, dec = 2): string {
  if (val == null || isNaN(val)) return "—";
  return val.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const MARKET_ORDER = ["美股", "港股", "A股", "B股", "日股", "基金"];
const MARKET_COLORS: Record<string, string> = {
  A: "#3b82f6", HK: "#f59e0b", US: "#10b981", JP: "#ef4444", B: "#6366f1", "基金": "#8b5cf6",
  "A股": "#3b82f6", "港股": "#f59e0b", "美股": "#10b981", "日股": "#ef4444", "B股": "#6366f1",
};
const MARKET_LABELS: Record<string, Record<string, string>> = {
  A: { zh: "A股", en: "A-Share" }, HK: { zh: "港股", en: "HK" }, US: { zh: "美股", en: "US" },
  JP: { zh: "日股", en: "JP" }, B: { zh: "B股", en: "B-Share" },
  "A股": { zh: "A股", en: "A" }, "港股": { zh: "港股", en: "HK" }, "美股": { zh: "美股", en: "US" },
  "日股": { zh: "日股", en: "JP" }, "B股": { zh: "B股", en: "B" }, "基金": { zh: "基金", en: "Fund" },
};
function mktLabel(m: string, locale: string) { return MARKET_LABELS[m]?.[locale] || m; }
function mktColor(m: string) { return MARKET_COLORS[m] || "#6b7280"; }
function sortMarkets(keys: string[]) {
  return [...keys].sort((a, b) => {
    const ai = MARKET_ORDER.indexOf(a); const bi = MARKET_ORDER.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
  });
}

// ══════════════════════════════════════════
// KPI Card
// ══════════════════════════════════════════

function KpiCard({ label, value, sub, subColor }: {
  label: string; value: string; sub?: string; subColor?: string;
}) {
  return (
    <div className="flex-1 min-w-[130px] p-3 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
      <div className="text-[10px] text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-0.5">{label}</div>
      <div className="text-lg font-semibold font-mono text-gray-900 dark:text-white leading-tight">{value}</div>
      {sub && <div className={`text-xs font-mono mt-0.5 ${subColor || "text-gray-500"}`}>{sub}</div>}
    </div>
  );
}

// ══════════════════════════════════════════
// FX Banner
// ══════════════════════════════════════════

function FxBanner({ fx }: { fx: Record<string, number> }) {
  const pairs: [string, string, number][] = [["USD/CNY", "USD", 4], ["HKD/CNY", "HKD", 4], ["JPY/CNY", "JPY", 5]];
  return (
    <span className="flex gap-4 text-[11px] font-mono text-gray-400 dark:text-gray-500">
      {pairs.map(([label, cur, dec]) => (
        <span key={cur}>{label} <span className="text-gray-600 dark:text-gray-400">{fx[cur] ? fx[cur].toFixed(dec as number) : "—"}</span></span>
      ))}
    </span>
  );
}

// ══════════════════════════════════════════
// Per-market P&L Strip
// ══════════════════════════════════════════

function PnlStrip({ label, items, markets, locale }: {
  label: string;
  items: { market: string; pnl: number; pct?: number }[];
  markets?: string[];
  locale: string;
}) {
  if (!items.length) return null;
  const itemMap = Object.fromEntries(items.map((it) => [it.market, it]));
  const orderedMarkets = markets || items.map((it) => it.market);
  const cols = orderedMarkets.length;
  return (
    <div className="flex items-baseline gap-2 text-xs font-mono">
      <span className="text-gray-400 opacity-60 whitespace-nowrap w-10 text-right shrink-0">{label}</span>
      <div className="grid gap-x-3 overflow-x-auto" style={{ gridTemplateColumns: `repeat(${cols}, auto)` }}>
        {orderedMarkets.map((m) => {
          const it = itemMap[m];
          const pnl = it?.pnl ?? 0;
          const pct = it?.pct ?? 0;
          return (
            <span key={m} className={`whitespace-nowrap ${pnl !== 0 ? pnlColor(pnl) : "text-gray-300 dark:text-gray-600"}`}>
              {mktLabel(m, locale)} {pnlSign(pnl)}
              <span className="opacity-70">({pnlSign(pct, 1)}%)</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Asset Allocation Bar
// ══════════════════════════════════════════

function AllocationBar({ title, items, locale }: {
  title: string;
  items: { label: string; value: number; color: string }[];
  locale: string;
}) {
  const total = items.reduce((s, i) => s + i.value, 0);
  if (total <= 0) return null;
  return (
    <div className="flex-1 min-w-[200px]">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{title}</div>
      <div className="flex rounded overflow-hidden h-5 mb-1.5">
        {items.map((it) => {
          const pct = (it.value / total) * 100;
          if (pct < 0.5) return null;
          return (
            <div key={it.label} style={{ width: `${pct}%`, backgroundColor: it.color }}
              className="relative group flex items-center justify-center text-white text-[8px] font-semibold overflow-hidden">
              {pct >= 12 && <span className="truncate px-0.5">{it.label} {pct.toFixed(0)}%</span>}
              <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block z-50 bg-gray-900 text-white rounded px-2 py-1 text-[10px] whitespace-nowrap shadow-lg">
                {it.label}: ¥{formatNumber(it.value)} ({pct.toFixed(1)}%)
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0 text-[10px] font-mono text-gray-500">
        {items.map((it) => (
          <span key={it.label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: it.color }} />
            {it.label} {((it.value / total) * 100).toFixed(0)}%
          </span>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Section Header
// ══════════════════════════════════════════

function SectionTitle({ children, note }: { children: React.ReactNode; note?: string }) {
  return (
    <div className="mt-8 mb-4">
      <div className="text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wide pb-2 border-b-2 border-gray-200 dark:border-gray-700">
        {children}
      </div>
      {note && <div className="text-[10px] text-gray-400 font-mono mt-1 leading-relaxed whitespace-pre-line">{note}</div>}
    </div>
  );
}

// ══════════════════════════════════════════
// Holdings Table
// ══════════════════════════════════════════

function HoldingsTable({ holdings, summary, locale, onEdit, compact, onShowAll }: {
  holdings: PortfolioHolding[]; summary: PortfolioData["summary"]; locale: string;
  onEdit?: (h: PortfolioHolding) => void;
  compact?: boolean;
  onShowAll?: () => void;
}) {
  const [sortKey, setSortKey] = useState<string>("market_value_cny");
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState("");
  const [filterMkt, setFilterMkt] = useState("All");
  const [filterBroker, setFilterBroker] = useState("All");
  const [filterSector, setFilterSector] = useState("All");
  // Column group toggles
  const [showDaily, setShowDaily] = useState(true);
  const [showYtd, setShowYtd] = useState(true);
  const [showTotal, setShowTotal] = useState(true);
  const [showDcf, setShowDcf] = useState(false);

  const markets = useMemo(() => ["All", ...Array.from(new Set(holdings.map((h) => h.market)))], [holdings]);
  const brokers = useMemo(() => ["All", ...Array.from(new Set(holdings.map((h) => h.broker)))], [holdings]);
  const sectors = useMemo(() => {
    const s = Array.from(new Set(holdings.map((h) => h.sector).filter(Boolean)));
    return s.length > 0 ? ["All", ...s.sort()] : [];
  }, [holdings]);
  const hasIndustry = holdings.some((h) => h.industry);
  const hasDcf = holdings.some((h) => h.dcf_price != null);

  const filtered = useMemo(() => {
    let list = holdings;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((h) => h.name.toLowerCase().includes(q) || h.ticker.toLowerCase().includes(q));
    }
    if (filterMkt !== "All") list = list.filter((h) => h.market === filterMkt);
    if (filterBroker !== "All") list = list.filter((h) => h.broker === filterBroker);
    if (filterSector !== "All") list = list.filter((h) => h.sector === filterSector);
    return [...list].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      const na = typeof av === "number" ? av : 0;
      const nb = typeof bv === "number" ? bv : 0;
      return sortAsc ? na - nb : nb - na;
    });
  }, [holdings, search, filterMkt, filterBroker, filterSector, sortKey, sortAsc]);

  function toggleSort(key: string) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  }
  const SI = ({ col }: { col: string }) => sortKey !== col ? null : <span className="ml-0.5 text-[10px]">{sortAsc ? "▲" : "▼"}</span>;
  const inputCls = "px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:ring-1 focus:ring-blue-500 focus:outline-none";
  const pillCls = (active: boolean) => `px-2 py-0.5 text-[10px] rounded-full border cursor-pointer select-none transition-colors ${active ? "bg-blue-600 text-white border-blue-600" : "bg-white dark:bg-gray-900 text-gray-500 border-gray-300 dark:border-gray-700 hover:border-blue-400"}`;

  return (
    <>
      <SectionTitle>
        Holdings
        <span className="text-[11px] font-normal normal-case tracking-normal text-gray-400 ml-3">
          {filtered.length} {locale === "zh" ? "只" : "positions"}
        </span>
      </SectionTitle>

      {/* Filters + Column Toggles */}
      {!compact && <div className="flex flex-wrap items-center gap-2 mb-3">
        <input className={`${inputCls} flex-1 min-w-[150px]`} placeholder={locale === "zh" ? "🔍 名称/代码" : "🔍 Name/Ticker"}
          value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className={inputCls} value={filterMkt} onChange={(e) => setFilterMkt(e.target.value)}>
          {markets.map((m) => <option key={m} value={m}>{m === "All" ? (locale === "zh" ? "全部市场" : "All Markets") : mktLabel(m, locale)}</option>)}
        </select>
        <select className={inputCls} value={filterBroker} onChange={(e) => setFilterBroker(e.target.value)}>
          {brokers.map((b) => <option key={b} value={b}>{b === "All" ? (locale === "zh" ? "全部账户" : "All Brokers") : b}</option>)}
        </select>
        {sectors.length > 0 && (
          <select className={inputCls} value={filterSector} onChange={(e) => setFilterSector(e.target.value)}>
            {sectors.map((s) => <option key={s} value={s}>{s === "All" ? (locale === "zh" ? "全部行业" : "All Sectors") : s}</option>)}
          </select>
        )}
        <span className="text-gray-300 dark:text-gray-700">|</span>
        <span className={pillCls(showDaily)} onClick={() => setShowDaily(!showDaily)}>Daily</span>
        <span className={pillCls(showYtd)} onClick={() => setShowYtd(!showYtd)}>YTD</span>
        <span className={pillCls(showTotal)} onClick={() => setShowTotal(!showTotal)}>Total</span>
        {hasDcf && <span className={pillCls(showDcf)} onClick={() => setShowDcf(!showDcf)}>DCF</span>}
      </div>}

      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden mb-2">
        <div className="overflow-auto max-h-[70vh]">
          <table className="w-full text-xs font-mono border-collapse">
            <thead className="sticky top-0 z-10 bg-white dark:bg-gray-900">
              {/* Header Row 1 */}
              <tr className="border-b border-gray-200 dark:border-gray-700 text-[10px] text-gray-500 dark:text-gray-400 uppercase">
                <th className="text-left px-2 py-2 sticky left-0 bg-white dark:bg-gray-900 z-20 min-w-[110px]">
                  {locale === "zh" ? "名称" : "Name"}
                </th>
                <th className="text-left px-2 py-2">{locale === "zh" ? "代码" : "Ticker"}</th>
                <th className="text-left px-2 py-2 whitespace-nowrap">{locale === "zh" ? "市场" : "Market"}</th>
                <th className="text-left px-2 py-2">{locale === "zh" ? "账户" : "Broker"}</th>
                <th className="text-left px-2 py-2">{locale === "zh" ? "币种" : "Ccy"}</th>
                {hasIndustry && <th className="text-left px-2 py-2">{locale === "zh" ? "行业" : "Industry"}</th>}
                <th className="text-right px-2 py-2 cursor-pointer select-none" onClick={() => toggleSort("quantity")}>
                  {locale === "zh" ? "持仓" : "Qty"}<SI col="quantity" />
                </th>
                <th className="text-right px-2 py-2">{locale === "zh" ? "成本" : "Cost"}</th>
                <th className="text-right px-2 py-2">{locale === "zh" ? "现价" : "Price"}</th>
                <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("market_value")}>
                  MV<SI col="market_value" />
                </th>
                <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("market_value_cny")}>
                  MV(CNY)<SI col="market_value_cny" />
                </th>
                <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("weight")}>
                  Wt%<SI col="weight" />
                </th>
                {showDaily && <>
                  <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("daily_pnl_cny")}>
                    Daily P&L<SI col="daily_pnl_cny" />
                  </th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("daily_pnl_pct")}>
                    Daily%<SI col="daily_pnl_pct" />
                  </th>
                </>}
                {showYtd && <>
                  <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("ytd_pnl_cny")}>
                    YTD P&L<SI col="ytd_pnl_cny" />
                  </th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("ytd_pnl_pct")}>
                    YTD%<SI col="ytd_pnl_pct" />
                  </th>
                </>}
                {showTotal && <>
                  <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("pnl_cny")}>
                    Total P&L<SI col="pnl_cny" />
                  </th>
                  <th className="text-right px-2 py-2 cursor-pointer select-none whitespace-nowrap" onClick={() => toggleSort("pnl_pct")}>
                    Total%<SI col="pnl_pct" />
                  </th>
                </>}
                {showDcf && <>
                  <th className="text-right px-2 py-2" title="DCF intrinsic value (ValuScope)">DCF</th>
                  <th className="text-right px-2 py-2" title="Margin of Safety = (DCF - Price) / DCF">MoS%</th>
                </>}
                {onEdit && <th className="px-2 py-2" />}
              </tr>
              {/* Header Row 2 — sub-labels */}
              <tr className="border-b border-gray-100 dark:border-gray-800 text-[9px] text-gray-400 dark:text-gray-500">
                <th className="sticky left-0 bg-white dark:bg-gray-900 z-20" />
                <th /><th /><th /><th />
                {hasIndustry && <th />}
                <th />
                <th className="text-right px-2 font-normal italic">{locale === "zh" ? "原币" : "orig"}</th>
                <th className="text-right px-2 font-normal italic">{locale === "zh" ? "原币" : "orig"}</th>
                <th className="text-right px-2 font-normal italic">{locale === "zh" ? "原币" : "orig"}</th>
                <th />
                <th />
                {showDaily && <><th className="text-right px-2 font-normal italic">CNY</th><th /></>}
                {showYtd && <><th className="text-right px-2 font-normal italic">CNY</th><th /></>}
                {showTotal && <><th className="text-right px-2 font-normal italic">CNY</th><th /></>}
                {showDcf && <><th className="text-right px-2 font-normal italic">{locale === "zh" ? "原币" : "orig"}</th><th /></>}
                {onEdit && <th />}
              </tr>
            </thead>
            <tbody>
              {(compact ? filtered.slice(0, 10) : filtered).map((h) => (
                <tr key={`${h.ticker}-${h.broker}`} className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-blue-50/30 dark:hover:bg-blue-900/10 transition-colors">
                  <td className="px-2 py-1.5 sticky left-0 bg-white dark:bg-gray-900 z-10 truncate max-w-[110px]" title={h.name}>
                    {h.name}
                    {(() => { const ua = (h as unknown as Record<string, string>).updated_at; return ua && ua.slice(0, 10) === new Date().toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 10) ? <span className="inline-block w-1.5 h-1.5 bg-red-500 rounded-full ml-1 align-middle" title={`Updated ${ua}`} /> : null; })()}
                  </td>
                  <td className="px-2 py-1.5"><Link href={`/stock/${h.ticker}`} className="text-blue-600 dark:text-blue-400 hover:underline">{h.ticker}</Link></td>
                  <td className="px-2 py-1.5 text-gray-500 whitespace-nowrap">
                    <span className="inline-block w-1.5 h-1.5 rounded-full mr-1" style={{ backgroundColor: mktColor(h.market) }} />
                    {mktLabel(h.market, locale)}
                  </td>
                  <td className="px-2 py-1.5 text-gray-500 truncate max-w-[70px]">{h.broker}</td>
                  <td className="px-2 py-1.5 text-gray-400">{h.currency}</td>
                  {hasIndustry && <td className="px-2 py-1.5 text-gray-400 truncate max-w-[90px]" title={h.industry}>{h.industry || "—"}</td>}
                  <td className="text-right px-2 py-1.5">{fmtNum(h.quantity, h.quantity % 1 === 0 ? 0 : 2)}</td>
                  <td className="text-right px-2 py-1.5 text-gray-500">{fmtNum(h.cost_price)}</td>
                  <td className={`text-right px-2 py-1.5 ${h.price_stale ? "text-gray-400 italic" : ""}`}>{fmtNum(h.price)}</td>
                  <td className="text-right px-2 py-1.5">{fmtNum(h.market_value)}</td>
                  <td className="text-right px-2 py-1.5">{formatNumber(h.market_value_cny)}</td>
                  <td className="text-right px-2 py-1.5">{h.weight.toFixed(1)}%</td>
                  {showDaily && <>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.daily_pnl_cny)}`}>{pnlSign(h.daily_pnl_cny)}</td>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.daily_pnl_pct)}`}>{pctStr(h.daily_pnl_pct)}</td>
                  </>}
                  {showYtd && <>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.ytd_pnl_cny)}`}>{h.ytd_pnl_cny != null ? pnlSign(h.ytd_pnl_cny) : "—"}</td>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.ytd_pnl_pct)}`}>{pctStr(h.ytd_pnl_pct)}</td>
                  </>}
                  {showTotal && <>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.pnl_cny)}`}>{pnlSign(h.pnl_cny)}</td>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.pnl_pct)}`}>{pctStr(h.pnl_pct)}</td>
                  </>}
                  {showDcf && <>
                    <td className="text-right px-2 py-1.5">
                      {h.dcf_price != null ? (
                        <Link href={`/stock/${h.ticker}`} className="text-blue-600 dark:text-blue-400 hover:underline border-b border-dotted border-blue-400">{fmtNum(h.dcf_price)}</Link>
                      ) : "—"}
                    </td>
                    <td className={`text-right px-2 py-1.5 ${h.mos_pct != null ? (h.mos_pct >= 0 ? "text-red-600 dark:text-red-400" : "text-green-600 dark:text-green-400") : ""}`}>
                      {h.mos_pct != null ? `${h.mos_pct > 0 ? "+" : ""}${h.mos_pct.toFixed(1)}%` : "—"}
                    </td>
                  </>}
                  {onEdit && <td className="px-1 py-1.5 text-center"><button onClick={() => onEdit(h)} className="text-gray-400 hover:text-blue-500 text-[10px]">✎</button></td>}
                </tr>
              ))}
            </tbody>
            {filtered.length > 0 && !compact && (() => {
              const fMvCny = filtered.reduce((s, h) => s + h.market_value_cny, 0);
              const fCostCny = filtered.reduce((s, h) => s + (h.market_value_cny - (h.pnl_cny ?? 0)), 0);
              const fDailyPnl = filtered.reduce((s, h) => s + (h.daily_pnl_cny ?? 0), 0);
              const fYtdPnl = filtered.reduce((s, h) => s + (h.ytd_pnl_cny ?? 0), 0);
              const fTotalPnl = filtered.reduce((s, h) => s + (h.pnl_cny ?? 0), 0);
              const fTotalPct = fCostCny !== 0 ? (fTotalPnl / fCostCny) * 100 : 0;
              const fWt = filtered.reduce((s, h) => s + h.weight, 0);
              return (
                <tfoot className="sticky bottom-0 bg-white dark:bg-gray-900 z-10">
                  <tr className="border-t-2 border-gray-300 dark:border-gray-700 font-semibold text-xs">
                    <td className="px-2 py-2 sticky left-0 bg-white dark:bg-gray-900 z-20">{locale === "zh" ? "合计" : "Total"} ({filtered.length})</td>
                    <td /><td /><td /><td />
                    {hasIndustry && <td />}
                    <td /><td /><td /><td />
                    <td className="text-right px-2 py-2">{formatNumber(fMvCny)}</td>
                    <td className="text-right px-2 py-2">{fWt.toFixed(1)}%</td>
                    {showDaily && <>
                      <td className={`text-right px-2 py-2 ${pnlColor(fDailyPnl)}`}>{pnlSign(fDailyPnl)}</td>
                      <td />
                    </>}
                    {showYtd && <>
                      <td className={`text-right px-2 py-2 ${pnlColor(fYtdPnl)}`}>{pnlSign(fYtdPnl)}</td>
                      <td />
                    </>}
                    {showTotal && <>
                      <td className={`text-right px-2 py-2 ${pnlColor(fTotalPnl)}`}>{pnlSign(fTotalPnl)}</td>
                      <td className={`text-right px-2 py-2 ${pnlColor(fTotalPct)}`}>{pctStr(fTotalPct)}</td>
                    </>}
                    {showDcf && <><td /><td /></>}
                  </tr>
                </tfoot>
              );
            })()}
          </table>
        </div>
        {compact && filtered.length > 10 && onShowAll && (
          <div className="text-center mt-2 mb-4">
            <button onClick={onShowAll} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
              {locale === "zh" ? `查看全部 ${filtered.length} 只持仓 →` : `View all ${filtered.length} positions →`}
            </button>
          </div>
        )}
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Cash Table (pivot by account × currency)
// ══════════════════════════════════════════

function CashTable({ cash, fx, locale }: { cash: PortfolioData["cash"]; fx: Record<string, number>; locale: string; }) {
  if (!cash || cash.length === 0) return null;
  const currencies = ["CNY", "USD", "HKD", "JPY"].filter((c) => cash.some((r) => r.currency === c));
  const cashOrder: Record<string, number> = { "中信": 1, "中信B股": 2, "招商": 3, "招商永隆": 4, "富途": 5, "招商银行": 10, "汇丰银行": 11, "支付宝": 12, "在途": 20 };
  const accounts = Array.from(new Set(cash.map((c) => c.account))).sort((a, b) => (cashOrder[a] || 50) - (cashOrder[b] || 50));
  const lookup: Record<string, Record<string, number>> = {};
  for (const c of cash) {
    if (!lookup[c.account]) lookup[c.account] = {};
    lookup[c.account][c.currency] = c.balance;
  }
  return (
    <>
      <SectionTitle>{locale === "zh" ? "现金余额" : "Cash Balances"}</SectionTitle>
      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden mb-2">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b-2 border-gray-200 dark:border-gray-700 text-[10px] text-gray-500 uppercase">
              <th className="text-left px-3 py-1.5">{locale === "zh" ? "账户" : "Account"}</th>
              {currencies.map((c) => <th key={c} className="text-right px-3 py-1.5">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {accounts.map((acct) => (
              <tr key={acct} className="border-b border-gray-100 dark:border-gray-800/50">
                <td className="px-3 py-1.5">{acct}</td>
                {currencies.map((c) => {
                  const v = lookup[acct]?.[c] || 0;
                  return <td key={c} className={`text-right px-3 py-1.5 ${v === 0 ? "text-gray-300 dark:text-gray-600" : ""}`}>{v !== 0 ? fmtNum(v, 0) : "—"}</td>;
                })}
              </tr>
            ))}
            <tr className="border-t-2 border-gray-200 dark:border-gray-700 font-semibold">
              <td className="px-3 py-1.5">{locale === "zh" ? "合计" : "Total"}</td>
              {currencies.map((c) => {
                const total = accounts.reduce((s, acct) => s + (lookup[acct]?.[c] || 0), 0);
                return <td key={c} className="text-right px-3 py-1.5">{total !== 0 ? fmtNum(total, 0) : "—"}</td>;
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Performance & Risk Analytics
// ══════════════════════════════════════════

function PerformanceSection({ locale, hideChart, hideRisk }: { locale: string; hideChart?: boolean; hideRisk?: boolean }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [navHistory, setNavHistory] = useState<NavHistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getSnapshots(365), getNavHistory()])
      .then(([s, n]) => { setSnapshots(s); setNavHistory(n); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-center py-4 text-gray-500 text-sm">{locale === "zh" ? "加载中..." : "Loading..."}</div>;

  // Extend navHistory with recent snapshots (after last nav_history date)
  const navSorted = (() => {
    const sorted = [...navHistory].sort((a, b) => a.date.localeCompare(b.date));
    const lastNavDate = sorted.length > 0 ? sorted[sorted.length - 1].date : "";
    const lastCap = sorted.length > 0 ? sorted[sorted.length - 1].capital_invested : 0;
    const snapAfterNav = snapshots
      .filter((s) => s.date > lastNavDate && s.net_assets != null && s.net_assets > 0)
      .sort((a, b) => a.date.localeCompare(b.date));
    for (const s of snapAfterNav) {
      const cap = s.capital ?? lastCap;
      sorted.push({
        date: s.date,
        net_asset_value: s.net_assets!,
        capital_invested: cap,
        pnl: s.net_assets! - cap,
        equity_nav: cap > 0 ? s.net_assets! / cap : 1,
        benchmark_value: null,
      });
    }
    return sorted;
  })();

  const snapshotsSorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const navValues = snapshotsSorted.map((s) => s.net_assets).filter((v): v is number => v != null && v > 0);

  // Compute capital values from snapshots
  const capitalValues = snapshotsSorted.map((s) => s.capital).filter((v): v is number => v != null);

  // Risk metrics
  let maxDrawdown = 0, peak = 0, ddStart = "", ddEnd = "", ddPeakValue = 0;
  const dailyReturns: number[] = [];
  for (let i = 0; i < navValues.length; i++) {
    if (navValues[i] > peak) { peak = navValues[i]; ddStart = snapshotsSorted[i]?.date || ""; }
    const dd = (peak - navValues[i]) / peak;
    if (dd > maxDrawdown) {
      maxDrawdown = dd;
      ddEnd = snapshotsSorted[i]?.date || "";
      ddPeakValue = peak;
    }
    if (i > 0 && navValues[i - 1] > 0) dailyReturns.push((navValues[i] - navValues[i - 1]) / navValues[i - 1]);
  }
  const pnlLost = maxDrawdown * ddPeakValue;
  const avgReturn = dailyReturns.length > 0 ? dailyReturns.reduce((s, r) => s + r, 0) / dailyReturns.length : 0;
  const variance = dailyReturns.length > 1 ? dailyReturns.reduce((s, r) => s + (r - avgReturn) ** 2, 0) / (dailyReturns.length - 1) : 0;
  const dailyVol = Math.sqrt(variance);
  const annualVol = dailyVol * Math.sqrt(252);
  const annualReturn = avgReturn * 252;
  const riskFreeRate = 0.015; // 1.5% CNY
  const sharpe = annualVol > 0 ? (annualReturn - riskFreeRate) / annualVol : 0;
  const calmar = maxDrawdown > 0 ? annualReturn / maxDrawdown : 0;
  const winDays = dailyReturns.filter((r) => r > 0).length;
  const lossDays = dailyReturns.filter((r) => r < 0).length;
  const winRate = dailyReturns.length > 0 ? (winDays / dailyReturns.length) * 100 : 0;

  // Time range
  const firstDate = snapshotsSorted[0]?.date || "";
  const lastDate = snapshotsSorted[snapshotsSorted.length - 1]?.date || "";
  const daySpan = firstDate && lastDate ? Math.round((new Date(lastDate).getTime() - new Date(firstDate).getTime()) / 86400000) : 0;
  const yearsSpan = daySpan / 365;
  const timeLabel = yearsSpan >= 1 ? `${yearsSpan.toFixed(1)}yr` : `${Math.round(yearsSpan * 12)}mo`;

  const riskNote = [
    `* ${snapshotsSorted.length}条快照 (${firstDate} – ${lastDate})`,
    `* 收益率已剔除出入金影响: return = ΔPnL / (Capital_t + PnL_prev)`,
    `* Drawdown: 累计收益指数相对峰值的跌幅。最大回撤 ${(maxDrawdown * 100).toFixed(2)}%，期间亏损 ¥${formatNumber(Math.abs(pnlLost), 0)}`,
    `* Sharpe >1 = 每承担1单位风险获得>1单位超额收益 (rf=1.5% CNY)`,
    `* Calmar = 年化收益 / 最大回撤。衡量单位最大亏损下的收益能力，>3 为优秀`,
  ].join("\n");

  return (
    <>
      {/* Performance Chart (NAV + Capital) */}
      {!hideChart && navSorted.length > 2 && <PerformanceChart navHistory={navSorted} locale={locale} />}

      {/* Risk Analytics */}
      {!hideRisk && (<>
      <SectionTitle note={riskNote}>
        {locale === "zh" ? "风险指标" : "Risk Analytics"}
      </SectionTitle>
      <div className="grid grid-cols-3 md:grid-cols-7 gap-3 mb-6">
        {[
          { label: locale === "zh" ? "年化收益" : "Ann. Return", value: `${(annualReturn * 100).toFixed(2)}%`,
            sub: `${firstDate.slice(0, 10)}–${lastDate.slice(0, 10)} (${timeLabel})`, color: pnlColor(annualReturn) },
          { label: locale === "zh" ? "年化波动率" : "Ann. Volatility", value: `${(annualVol * 100).toFixed(2)}%`,
            sub: `daily σ=${(dailyVol * 100).toFixed(3)}%` },
          { label: locale === "zh" ? "最大回撤" : "Max Drawdown", value: `${(maxDrawdown * 100).toFixed(2)}%`,
            sub: ddStart && ddEnd ? `¥${formatNumber(Math.abs(pnlLost), 0)} · ${ddStart.slice(5)}→${ddEnd.slice(5)}` : undefined,
            color: "text-red-600 dark:text-red-400" },
          { label: locale === "zh" ? "夏普比率" : "Sharpe Ratio", value: sharpe.toFixed(2),
            sub: "rf=1.5% (CNY)" },
          { label: locale === "zh" ? "胜率" : "Win Rate", value: `${winRate.toFixed(0)}%`,
            sub: `${winDays}W / ${lossDays}L (daily)` },
          { label: locale === "zh" ? "卡玛比率" : "Calmar Ratio", value: calmar.toFixed(2),
            sub: `ret=${(annualReturn * 100).toFixed(1)}%/yr` },
          { label: locale === "zh" ? "交易日" : "Trading Days", value: String(navValues.length) },
        ].map((m) => (
          <div key={m.label} className="p-2 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
            <div className="text-[9px] text-gray-400 uppercase">{m.label}</div>
            <div className={`text-base font-mono font-semibold ${m.color || ""}`}>{m.value}</div>
            {m.sub && <div className="text-[10px] text-gray-400 font-mono">{m.sub}</div>}
          </div>
        ))}
      </div></>)}
    </>
  );
}

// ══════════════════════════════════════════
// Performance Chart (SVG line chart)
// ══════════════════════════════════════════

function PerformanceChart({ navHistory, locale }: { navHistory: NavHistoryPoint[]; locale: string }) {
  const [range, setRange] = useState<string>("2Y");
  const [showBenchmarks, setShowBenchmarks] = useState(false);
  const [benchData, setBenchData] = useState<Record<string, BenchmarkPoint[]>>({});
  const [benchLoading, setBenchLoading] = useState(false);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = React.useRef<SVGSVGElement>(null);

  const rangeOptions = ["YTD", "1Y", "2Y", "3Y", "All"];
  const pillCls = (active: boolean) => `px-2 py-0.5 text-[10px] rounded-full border cursor-pointer select-none transition-colors ${active ? "bg-blue-600 text-white border-blue-600" : "bg-white dark:bg-gray-900 text-gray-500 border-gray-300 dark:border-gray-700 hover:border-blue-400"}`;

  // Fetch benchmarks when toggled on (fetch once per navHistory change)
  const benchFetchedRef = React.useRef(false);
  useEffect(() => { benchFetchedRef.current = false; setBenchData({}); }, [navHistory]);
  useEffect(() => {
    if (!showBenchmarks || benchFetchedRef.current || navHistory.length === 0) return;
    benchFetchedRef.current = true;
    setBenchLoading(true);
    const earliest = navHistory[0]?.date || "2024-01-01";
    getBenchmarks(earliest).then(setBenchData).catch(() => {}).finally(() => setBenchLoading(false));
  }, [showBenchmarks, navHistory]);

  const filteredNav = useMemo(() => {
    if (range === "All") return navHistory;
    const now = new Date();
    let cutoff: Date;
    if (range === "YTD") cutoff = new Date(now.getFullYear(), 0, 1);
    else if (range === "1Y") cutoff = new Date(now.getTime() - 365 * 86400000);
    else if (range === "2Y") cutoff = new Date(now.getTime() - 730 * 86400000);
    else cutoff = new Date(now.getTime() - 1095 * 86400000);
    return navHistory.filter((p) => new Date(p.date) >= cutoff);
  }, [navHistory, range]);

  if (filteredNav.length < 2) return null;

  const W = 800, H = 240, PAD = { t: 15, r: 15, b: 25, l: 60 };
  const cw = W - PAD.l - PAD.r, ch = H - PAD.t - PAD.b;

  const lastNav = filteredNav[filteredNav.length - 1].net_asset_value;
  const lastCap = filteredNav[filteredNav.length - 1].capital_invested;
  const lastPnl = filteredNav[filteredNav.length - 1].pnl;

  // Benchmark mode: indexed return chart (base=100)
  const benchColors: Record<string, string> = { "CSI 300": "#ef4444", "S&P 500": "#22c55e", "Hang Seng": "#f59e0b" };

  if (showBenchmarks && Object.keys(benchData).length > 0) {
    // Build indexed portfolio return
    const startEnav = filteredNav[0].net_asset_value / filteredNav[0].capital_invested;
    const portIndexed = filteredNav.map((p) => ({
      date: p.date,
      indexed: (p.net_asset_value / p.capital_invested) / startEnav * 100,
    }));

    // Build indexed benchmark returns (filter to date range)
    const startDate = filteredNav[0].date;
    const endDate = filteredNav[filteredNav.length - 1].date;
    const benchIndexed: Record<string, { date: string; indexed: number }[]> = {};
    for (const [name, points] of Object.entries(benchData)) {
      const inRange = points.filter((p) => p.date >= startDate && p.date <= endDate);
      if (inRange.length < 2) continue;
      const base = inRange[0].close;
      if (base <= 0) continue;
      benchIndexed[name] = inRange.map((p) => ({ date: p.date, indexed: (p.close / base) * 100 }));
    }

    // Compute Y range across all series
    const allIndexed = [...portIndexed.map((p) => p.indexed)];
    for (const pts of Object.values(benchIndexed)) allIndexed.push(...pts.map((p) => p.indexed));
    const yMin = Math.min(...allIndexed) * 0.98;
    const yMax = Math.max(...allIndexed) * 1.02;
    const yRange = yMax - yMin || 1;

    const toX = (i: number, len: number) => PAD.l + (i / Math.max(len - 1, 1)) * cw;
    const toY = (v: number) => PAD.t + (1 - (v - yMin) / yRange) * ch;

    const portPath = portIndexed.map((p, i) => `${i === 0 ? "M" : "L"}${toX(i, portIndexed.length).toFixed(1)},${toY(p.indexed).toFixed(1)}`).join(" ");

    const yTicks = 5;
    const yLabels = Array.from({ length: yTicks + 1 }, (_, i) => yMin + (yRange * i) / yTicks);
    const xCount = Math.min(6, portIndexed.length);
    const xLabels = Array.from({ length: xCount }, (_, i) => {
      const idx = Math.round((i / (xCount - 1)) * (portIndexed.length - 1));
      return { x: toX(idx, portIndexed.length), label: portIndexed[idx]?.date.slice(2, 10) };
    });

    // Alpha
    const portRet = portIndexed[portIndexed.length - 1].indexed - 100;
    const alphas: string[] = [];
    for (const [name, pts] of Object.entries(benchIndexed)) {
      const benchRet = pts[pts.length - 1].indexed - 100;
      const alpha = portRet - benchRet;
      alphas.push(`vs ${name}: ${alpha > 0 ? "+" : ""}${alpha.toFixed(1)}%`);
    }

    return (
      <>
        <SectionTitle
          note={locale === "zh"
            ? "* 标准化收益对比 (起始=100)，使用 equity_nav (NAV/Capital) 消除出入金影响"
            : "* Indexed return comparison (base=100), using equity_nav to eliminate capital flow distortion"}>
          {locale === "zh" ? "业绩走势" : "Performance"}
        </SectionTitle>
        <div className="flex items-center gap-2 mb-3">
          {rangeOptions.map((r) => <button key={r} onClick={() => setRange(r)} className={pillCls(range === r)}>{r}</button>)}
          <span className="text-gray-300 dark:text-gray-700">|</span>
          <label className="flex items-center gap-1 text-[10px] text-gray-500 cursor-pointer select-none">
            <input type="checkbox" checked={showBenchmarks} onChange={(e) => setShowBenchmarks(e.target.checked)} className="w-3 h-3" />
            Benchmarks
          </label>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 mb-2">
          <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full cursor-crosshair" style={{ maxHeight: 300 }}
            onMouseMove={(e) => {
              const svg = svgRef.current; if (!svg) return;
              const rect = svg.getBoundingClientRect();
              const svgX = ((e.clientX - rect.left) / rect.width) * W;
              const idx = Math.round(((svgX - PAD.l) / cw) * (portIndexed.length - 1));
              setHoverIdx(Math.max(0, Math.min(portIndexed.length - 1, idx)));
            }}
            onMouseLeave={() => setHoverIdx(null)}>
            {yLabels.map((v) => (
              <g key={v}>
                <line x1={PAD.l} y1={toY(v)} x2={W - PAD.r} y2={toY(v)} stroke="#e5e7eb" strokeWidth="0.3" strokeDasharray="3,3" opacity="0.5" />
                <text x={PAD.l - 5} y={toY(v) + 3} textAnchor="end" fill="#9ca3af" fontSize="8" fontFamily="monospace">{v.toFixed(0)}</text>
              </g>
            ))}
            {/* 100 baseline */}
            {yMin < 100 && yMax > 100 && (
              <line x1={PAD.l} y1={toY(100)} x2={W - PAD.r} y2={toY(100)} stroke="#9ca3af" strokeWidth="0.5" strokeDasharray="4,3" opacity="0.6" />
            )}
            {xLabels.map(({ x, label }) => (
              <text key={label} x={x} y={H - 5} textAnchor="middle" fill="#9ca3af" fontSize="8" fontFamily="monospace">{label}</text>
            ))}
            {/* Benchmark lines */}
            {Object.entries(benchIndexed).map(([name, pts]) => {
              const path = pts.map((p, i) => {
                // Map benchmark dates to x positions by finding closest portfolio date index
                const navIdx = portIndexed.findIndex((pp) => pp.date >= p.date);
                const x = navIdx >= 0 ? toX(navIdx, portIndexed.length) : toX(i, pts.length);
                return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${toY(p.indexed).toFixed(1)}`;
              }).join(" ");
              return <path key={name} d={path} fill="none" stroke={benchColors[name] || "#8b949e"} strokeWidth="1.5" strokeDasharray="4,3" />;
            })}
            {/* Portfolio line */}
            <path d={portPath} fill="none" stroke="#3b82f6" strokeWidth="2.5" />
            <circle cx={toX(portIndexed.length - 1, portIndexed.length)} cy={toY(portIndexed[portIndexed.length - 1].indexed)} r="3" fill="#3b82f6" />
            {/* Hover crosshair + tooltip */}
            {hoverIdx != null && (() => {
              const hp = portIndexed[hoverIdx];
              const hx = toX(hoverIdx, portIndexed.length);
              const portVal = hp.indexed;
              // Build benchmark values at this date
              const benchVals: { name: string; val: number; color: string }[] = [];
              for (const [name, pts] of Object.entries(benchIndexed)) {
                // Find closest benchmark point by matching portfolio date
                const targetDate = hp.date;
                let closest = pts[0];
                for (const p of pts) {
                  if (p.date <= targetDate) closest = p;
                }
                benchVals.push({ name, val: closest.indexed, color: benchColors[name] || "#8b949e" });
              }
              const tipW = 160;
              const tipH = 16 + 11 * (1 + benchVals.length);
              const tipX = hx < W / 2 ? hx + 8 : hx - tipW - 8;
              return (
                <g>
                  <line x1={hx} y1={PAD.t} x2={hx} y2={H - PAD.b} stroke="#6b7280" strokeWidth="0.8" strokeDasharray="3,2" />
                  <circle cx={hx} cy={toY(portVal)} r="3" fill="#3b82f6" stroke="white" strokeWidth="1" />
                  {benchVals.map((b) => (
                    <circle key={b.name} cx={hx} cy={toY(b.val)} r="2.5" fill={b.color} stroke="white" strokeWidth="1" />
                  ))}
                  <rect x={tipX} y={PAD.t + 2} width={tipW} height={tipH} rx="4" fill="rgba(17,24,39,0.9)" />
                  <text x={tipX + 6} y={PAD.t + 14} fill="#d1d5db" fontSize="8" fontFamily="monospace">{hp.date}</text>
                  <text x={tipX + 6} y={PAD.t + 25} fill="#93c5fd" fontSize="8" fontFamily="monospace">
                    Portfolio {(portVal - 100) >= 0 ? "+" : ""}{(portVal - 100).toFixed(1)}%
                  </text>
                  {benchVals.map((b, i) => (
                    <text key={b.name} x={tipX + 6} y={PAD.t + 36 + i * 11} fill={b.color} fontSize="8" fontFamily="monospace">
                      {b.name} {(b.val - 100) >= 0 ? "+" : ""}{(b.val - 100).toFixed(1)}%
                    </text>
                  ))}
                </g>
              );
            })()}
          </svg>
          {/* Legend */}
          <div className="flex flex-wrap gap-4 mt-2 text-xs font-mono">
            <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-blue-500 inline-block" /> Portfolio {portRet > 0 ? "+" : ""}{portRet.toFixed(1)}%</span>
            {Object.entries(benchIndexed).map(([name, pts]) => (
              <span key={name} className="flex items-center gap-1.5">
                <span className="w-4 h-0.5 inline-block" style={{ borderTop: `1.5px dashed ${benchColors[name]}`, height: 0 }} />
                {name} {((pts[pts.length - 1].indexed - 100) > 0 ? "+" : "")}{(pts[pts.length - 1].indexed - 100).toFixed(1)}%
              </span>
            ))}
          </div>
          {alphas.length > 0 && (
            <div className="text-[10px] font-mono text-gray-400 mt-1">
              Alpha (excess return): {alphas.join(" · ")}
            </div>
          )}
        </div>
      </>
    );
  }

  // ── Absolute NAV mode (no benchmarks) ──
  const navVals = filteredNav.map((p) => p.net_asset_value);
  const capVals = filteredNav.map((p) => p.capital_invested);
  const allVals = [...navVals, ...capVals];
  const yMin = Math.min(...allVals) * 0.98;
  const yMax = Math.max(...allVals) * 1.02;
  const yRange = yMax - yMin || 1;

  const toX = (i: number) => PAD.l + (i / (filteredNav.length - 1)) * cw;
  const toY = (v: number) => PAD.t + (1 - (v - yMin) / yRange) * ch;

  const navPath = filteredNav.map((_, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(navVals[i]).toFixed(1)}`).join(" ");
  const capPath = filteredNav.map((_, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(capVals[i]).toFixed(1)}`).join(" ");

  const pnlFillPath = [
    ...filteredNav.map((_, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(navVals[i]).toFixed(1)}`),
    ...filteredNav.map((_, i) => `L${toX(filteredNav.length - 1 - i).toFixed(1)},${toY(capVals[filteredNav.length - 1 - i]).toFixed(1)}`),
    "Z"
  ].join(" ");

  const yTicks = 5;
  const yLabels = Array.from({ length: yTicks + 1 }, (_, i) => yMin + (yRange * i) / yTicks);
  const xCount = Math.min(6, filteredNav.length);
  const xLabels = Array.from({ length: xCount }, (_, i) => {
    const idx = Math.round((i / (xCount - 1)) * (filteredNav.length - 1));
    return { x: toX(idx), label: filteredNav[idx]?.date.slice(2, 10) };
  });

  return (
    <>
      <SectionTitle
        note={locale === "zh"
          ? "* Portfolio NAV = 净资产值 (资产总值 − 杠杆)。Capital = 累计投入资金。Net P&L = NAV − Capital\n* Capital = 入金账户固定额 + 成本账户(持仓成本 + 现金) − 场外杠杆 − 成本账户已平仓盈亏\n* 阴影区域 = Net P&L (NAV 与 Capital 之间差值)"
          : "* Portfolio NAV = Net Asset Value (Total Assets − Leverage). Net P&L = NAV − Capital\n* Capital = Deposit accounts (fixed CNY) + Cost accounts (position cost + cash) − OTC leverage − cost-account realized P&L\n* Shaded area = Net P&L (gap between NAV and Capital)"}>
        {locale === "zh" ? "业绩走势" : "Performance"}
      </SectionTitle>

      <div className="flex items-center gap-2 mb-3">
        {rangeOptions.map((r) => <button key={r} onClick={() => setRange(r)} className={pillCls(range === r)}>{r}</button>)}
        <span className="text-gray-300 dark:text-gray-700">|</span>
        <label className="flex items-center gap-1 text-[10px] text-gray-500 cursor-pointer select-none">
          <input type="checkbox" checked={showBenchmarks} onChange={(e) => setShowBenchmarks(e.target.checked)} className="w-3 h-3" />
          Benchmarks{benchLoading ? " ..." : ""}
        </label>
      </div>

      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-4 mb-2">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full cursor-crosshair" style={{ maxHeight: 300 }}
          onMouseMove={(e) => {
            const svg = svgRef.current; if (!svg) return;
            const rect = svg.getBoundingClientRect();
            const svgX = ((e.clientX - rect.left) / rect.width) * W;
            const idx = Math.round(((svgX - PAD.l) / cw) * (filteredNav.length - 1));
            setHoverIdx(Math.max(0, Math.min(filteredNav.length - 1, idx)));
          }}
          onMouseLeave={() => setHoverIdx(null)}>
          {yLabels.map((v) => (
            <g key={v}>
              <line x1={PAD.l} y1={toY(v)} x2={W - PAD.r} y2={toY(v)} stroke="#e5e7eb" strokeWidth="0.3" strokeDasharray="3,3" opacity="0.5" />
              <text x={PAD.l - 5} y={toY(v) + 3} textAnchor="end" fill="#9ca3af" fontSize="8" fontFamily="monospace">
                {v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` : v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v.toFixed(0)}
              </text>
            </g>
          ))}
          {xLabels.map(({ x, label }) => (
            <text key={label} x={x} y={H - 5} textAnchor="middle" fill="#9ca3af" fontSize="8" fontFamily="monospace">{label}</text>
          ))}
          <path d={pnlFillPath} fill={lastPnl >= 0 ? "rgba(239,68,68,0.08)" : "rgba(34,197,94,0.08)"} />
          <path d={capPath} fill="none" stroke="#9ca3af" strokeWidth="1" strokeDasharray="4,3" opacity="0.7" />
          <path d={navPath} fill="none" stroke="#3b82f6" strokeWidth="2" />
          <circle cx={toX(filteredNav.length - 1)} cy={toY(lastNav)} r="3" fill="#3b82f6" />
          <circle cx={toX(filteredNav.length - 1)} cy={toY(lastCap)} r="2.5" fill="#9ca3af" />
          {/* Hover crosshair + tooltip */}
          {hoverIdx != null && (() => {
            const hp = filteredNav[hoverIdx];
            const hx = toX(hoverIdx);
            const hNav = hp.net_asset_value;
            const hCap = hp.capital_invested;
            const hPnl = hNav - hCap;
            const hPct = hCap > 0 ? (hPnl / hCap) * 100 : 0;
            const tipX = hx < W / 2 ? hx + 8 : hx - 155;
            return (
              <g>
                <line x1={hx} y1={PAD.t} x2={hx} y2={H - PAD.b} stroke="#6b7280" strokeWidth="0.8" strokeDasharray="3,2" />
                <circle cx={hx} cy={toY(hNav)} r="3" fill="#3b82f6" stroke="white" strokeWidth="1" />
                <circle cx={hx} cy={toY(hCap)} r="2.5" fill="#9ca3af" stroke="white" strokeWidth="1" />
                <rect x={tipX} y={PAD.t + 2} width="148" height="52" rx="4" fill="rgba(17,24,39,0.9)" />
                <text x={tipX + 6} y={PAD.t + 14} fill="#d1d5db" fontSize="8" fontFamily="monospace">{hp.date}</text>
                <text x={tipX + 6} y={PAD.t + 25} fill="#93c5fd" fontSize="8" fontFamily="monospace">NAV ¥{formatNumber(hNav)}</text>
                <text x={tipX + 6} y={PAD.t + 36} fill="#d1d5db" fontSize="8" fontFamily="monospace">Capital ¥{formatNumber(hCap)}</text>
                <text x={tipX + 6} y={PAD.t + 47} fill={hPnl >= 0 ? "#fca5a5" : "#86efac"} fontSize="8" fontFamily="monospace">
                  P&L ¥{pnlSign(hPnl)} ({hPct > 0 ? "+" : ""}{hPct.toFixed(1)}%)
                </text>
              </g>
            );
          })()}
        </svg>

        <div className="flex flex-wrap gap-4 mt-2 text-xs font-mono">
          <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-blue-500 inline-block" /> Portfolio NAV: ¥{formatNumber(lastNav)}</span>
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-gray-400 inline-block" style={{ borderTop: "1.5px dashed #9ca3af", height: 0 }} /> Capital: ¥{formatNumber(lastCap)}
          </span>
          <span className={`${pnlColor(lastPnl)}`}>
            Net P&L: ¥{pnlSign(lastPnl)} ({lastCap > 0 ? pctStr((lastPnl / lastCap) * 100) : "—"})
          </span>
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Return Attribution
// ══════════════════════════════════════════

function ReturnAttribution({ holdings, closedTrades, locale }: {
  holdings: PortfolioHolding[]; closedTrades: ClosedTrade[]; locale: string;
}) {
  const [tab, setTab] = useState<"daily" | "ytd" | "unrealised" | "total">("unrealised");

  const tabDef = useMemo(() => {
    const tabs: { key: string; label: string; pnlKey: string; pnlCnyKey: string }[] = [];
    const hasDaily = holdings.some((h) => h.daily_pnl_cny != null);
    const hasYtd = holdings.some((h) => h.ytd_pnl_cny != null);
    if (hasDaily) tabs.push({ key: "daily", label: "Daily P&L", pnlKey: "daily_pnl_cny", pnlCnyKey: "daily_pnl_cny" });
    if (hasYtd) tabs.push({ key: "ytd", label: "YTD P&L", pnlKey: "ytd_pnl_cny", pnlCnyKey: "ytd_pnl_cny" });
    tabs.push({ key: "unrealised", label: "Unrealised P&L", pnlKey: "pnl_cny", pnlCnyKey: "pnl_cny" });
    tabs.push({ key: "total", label: "Total P&L", pnlKey: "pnl_cny", pnlCnyKey: "pnl_cny" });
    return tabs;
  }, [holdings]);

  const activeTabDef = tabDef.find((t) => t.key === tab) || tabDef[0];

  // Compute by market
  const byMarket = useMemo(() => {
    const map: Record<string, number> = {};
    for (const h of holdings) {
      const val = (h as unknown as Record<string, number | null>)[activeTabDef.pnlKey] ?? 0;
      map[h.market] = (map[h.market] || 0) + (val as number);
    }
    // For "total" tab, add closed trades
    if (tab === "total") {
      for (const t of closedTrades) {
        map[t.market] = (map[t.market] || 0) + (t.realized_pnl_cny || 0);
      }
    }
    return sortMarkets(Object.keys(map)).map((m) => ({ market: m, pnl: map[m] }));
  }, [holdings, closedTrades, tab, activeTabDef]);

  // Compute by stock (top contributors)
  const byStock = useMemo(() => {
    const map: Record<string, { name: string; pnl: number }> = {};
    for (const h of holdings) {
      const val = (h as unknown as Record<string, number | null>)[activeTabDef.pnlKey] ?? 0;
      const key = h.ticker;
      if (!map[key]) map[key] = { name: h.name, pnl: 0 };
      map[key].pnl += val as number;
    }
    if (tab === "total") {
      for (const t of closedTrades) {
        const key = t.ticker || t.name;
        if (!map[key]) map[key] = { name: t.name, pnl: 0 };
        map[key].pnl += t.realized_pnl_cny || 0;
      }
    }
    const sorted = Object.entries(map).sort((a, b) => b[1].pnl - a[1].pnl);
    const top10 = sorted.filter(([, v]) => v.pnl > 0).slice(0, 10);
    const bottom5 = sorted.filter(([, v]) => v.pnl < 0).slice(-5).reverse();
    return [...top10, ...bottom5];
  }, [holdings, closedTrades, tab, activeTabDef]);

  const totalPnl = byMarket.reduce((s, m) => s + m.pnl, 0);

  // Simple horizontal bar chart renderer
  function HBar({ items, labelFn }: { items: { key: string; label: string; pnl: number }[]; labelFn?: (k: string) => string }) {
    if (items.length === 0) return <div className="text-xs text-gray-400 py-4 text-center">No data</div>;
    const maxAbs = Math.max(...items.map((i) => Math.abs(i.pnl)), 1);
    return (
      <div className="space-y-1">
        {items.map((it) => {
          const pct = (Math.abs(it.pnl) / maxAbs) * 100;
          const isPos = it.pnl >= 0;
          return (
            <div key={it.key} className="flex items-center gap-2 text-xs font-mono">
              <span className="w-16 text-right text-gray-500 truncate text-[10px]">{it.label}</span>
              <div className="flex-1 flex items-center" style={{ direction: isPos ? "ltr" : "rtl" }}>
                <div className={`h-4 rounded-sm ${isPos ? "bg-red-400/60" : "bg-green-400/60"}`} style={{ width: `${Math.max(2, pct)}%` }} />
              </div>
              <span className={`w-20 text-right text-[10px] ${pnlColor(it.pnl)}`}>{pnlSign(it.pnl)}</span>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <>
      <SectionTitle
        note={locale === "zh"
          ? `* Total P&L 合并了未实现P&L与已平仓P&L\n* Contribution = 单市场/个股P&L占总P&L比重`
          : `* Total P&L merges unrealized + closed trade P&L\n* Contribution = single market/stock P&L as % of total`}>
        {locale === "zh" ? "收益归因" : "Return Attribution"}
      </SectionTitle>

      {/* Tab pills */}
      <div className="flex gap-2 mb-4">
        {tabDef.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key as typeof tab)}
            className={`px-2.5 py-0.5 text-[10px] rounded-full border transition-colors ${tab === t.key ? "bg-blue-600 text-white border-blue-600" : "bg-white dark:bg-gray-900 text-gray-500 border-gray-300 dark:border-gray-700 hover:border-blue-400"}`}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
        {/* By Market */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">{activeTabDef.label} by Market</div>
          <HBar items={byMarket.map((m) => ({ key: m.market, label: mktLabel(m.market, locale), pnl: m.pnl }))} />
        </div>
        {/* Top Contributors */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">{activeTabDef.label} Top Contributors</div>
          <HBar items={byStock.map(([k, v]) => ({ key: k, label: v.name.length > 8 ? v.name.slice(0, 8) + "…" : v.name, pnl: v.pnl }))} />
        </div>
      </div>

      {/* Contribution strip */}
      <div className="text-[10px] font-mono text-gray-400 mb-2">
        Contribution: {byMarket.map((m) => {
          const contrib = totalPnl !== 0 ? (m.pnl / totalPnl * 100).toFixed(1) : "0.0";
          return `${mktLabel(m.market, locale)} ${pnlSign(m.pnl)}(${contrib}%)`;
        }).join(" · ")}
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Net P&L Journal (Daily Snapshots)
// ══════════════════════════════════════════

function PnlJournal({ locale }: { locale: string }) {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { getSnapshots(90).then(setSnapshots).finally(() => setLoading(false)); }, []);

  if (loading || snapshots.length === 0) return null;

  const sorted = [...snapshots].sort((a, b) => b.date.localeCompare(a.date));

  // Compute ΔNet P&L from snapshots
  type JournalRow = {
    date: string;
    net_assets: number | null;
    capital: number | null;
    net_pnl: number | null;
    delta_pnl: number | null;
    delta_pnl_pct: number | null;
  };

  const rows: JournalRow[] = [];
  const byDateAsc = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  // Only show entries from the last 30 calendar days
  const cutoffDate = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  for (let i = 0; i < byDateAsc.length; i++) {
    const s = byDateAsc[i];
    const na = s.net_assets;
    const cap = s.capital;
    const netPnl = (na != null && cap != null) ? na - cap : s.total_pnl_cny;
    let deltaPnl: number | null = null;
    let deltaPnlPct: number | null = null;
    if (i > 0) {
      const prev = byDateAsc[i - 1];
      const prevNa = prev.net_assets;
      const prevCap = prev.capital;
      const prevNetPnl = (prevNa != null && prevCap != null) ? prevNa - prevCap : prev.total_pnl_cny;
      if (netPnl != null && prevNetPnl != null) {
        deltaPnl = netPnl - prevNetPnl;
        const denom = cap ?? prevNa ?? 1;
        deltaPnlPct = denom > 0 ? (deltaPnl / denom) * 100 : null;
      }
    }
    if (s.date >= cutoffDate) {
      rows.push({ date: s.date, net_assets: na, capital: cap, net_pnl: netPnl, delta_pnl: deltaPnl, delta_pnl_pct: deltaPnlPct });
    }
  }
  const display = rows.reverse();

  const journalNote = locale === "zh"
    ? `* Net P&L = Net Assets − Capital。ΔNet P&L = 当日净收益变动\n* Capital = 入金账户固定额 + 成本账户(持仓成本 + 现金) − 场外杠杆 − 成本账户已平仓盈亏`
    : `* Net P&L = Net Assets − Capital. ΔNet P&L = daily change in net P&L\n* Capital = Deposit accounts (fixed) + Cost accounts (cost + cash) − OTC leverage − cost-account realized P&L`;

  return (
    <>
      <SectionTitle note={journalNote}>
        {locale === "zh" ? "Net P&L 日志" : "Net P&L Journal"}
        <span className="text-[11px] font-normal normal-case tracking-normal text-gray-400 ml-3">
          last 30 days · {display.length} entries
        </span>
      </SectionTitle>

      <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden mb-2">
        <div className="overflow-auto max-h-[35vh]">
          <table className="w-full text-xs font-mono">
            <thead className="sticky top-0 bg-white dark:bg-gray-900 text-[10px] text-gray-500 uppercase border-b border-gray-200 dark:border-gray-800">
              <tr>
                <th className="text-left px-2 py-1.5">Date</th>
                <th className="text-right px-2 py-1.5">Net Assets</th>
                <th className="text-right px-2 py-1.5">Capital</th>
                <th className="text-right px-2 py-1.5">Net P&L</th>
                <th className="text-right px-2 py-1.5">ΔNet P&L</th>
                <th className="text-right px-2 py-1.5">ΔNet P&L%</th>
              </tr>
            </thead>
            <tbody>
              {display.map((r) => (
                <tr key={r.date} className="border-b border-gray-100 dark:border-gray-800/50">
                  <td className="px-2 py-1">{r.date}</td>
                  <td className="text-right px-2 py-1">{r.net_assets != null ? `¥${fmtNum(r.net_assets, 0)}` : "—"}</td>
                  <td className="text-right px-2 py-1">{r.capital != null ? `¥${fmtNum(r.capital, 0)}` : "—"}</td>
                  <td className={`text-right px-2 py-1 ${pnlColor(r.net_pnl)}`}>{r.net_pnl != null ? `¥${pnlSign(r.net_pnl)}` : "—"}</td>
                  <td className={`text-right px-2 py-1 ${pnlColor(r.delta_pnl)}`}>{r.delta_pnl != null ? pnlSign(r.delta_pnl) : "—"}</td>
                  <td className={`text-right px-2 py-1 ${pnlColor(r.delta_pnl_pct)}`}>{r.delta_pnl_pct != null ? pctStr(r.delta_pnl_pct) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ══════════════════════════════════════════
// Closed Trades Section
// ══════════════════════════════════════════

function ClosedTradesSection({ locale }: { locale: string }) {
  const [trades, setTrades] = useState<ClosedTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => { getClosedTrades().then(setTrades).finally(() => setLoading(false)); }, []);

  if (loading || trades.length === 0) return null;

  // Summary by (market, broker)
  const summary: Record<string, { count: number; pnl: number }> = {};
  for (const t of trades) {
    const key = `${t.market}|${t.broker}`;
    if (!summary[key]) summary[key] = { count: 0, pnl: 0 };
    summary[key].count += 1;
    summary[key].pnl += t.realized_pnl_cny || 0;
  }
  const totalPnl = trades.reduce((s, t) => s + (t.realized_pnl_cny || 0), 0);
  const hasQty = trades.some((t) => t.quantity != null && t.quantity > 0);

  return (
    <>
      <div className="mt-8 mb-2">
        <button onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white uppercase tracking-wide pb-2 border-b-2 border-gray-200 dark:border-gray-700 w-full text-left">
          <span className={`transition-transform ${expanded ? "rotate-90" : ""}`}>▶</span>
          {locale === "zh" ? "已平仓交易" : "Closed Trades"}
          <span className="text-[11px] font-normal normal-case tracking-normal text-gray-400 ml-1">
            (historical P&L)
          </span>
          <span className={`text-xs font-mono font-normal normal-case ${pnlColor(totalPnl)}`}>
            ({trades.length} trades · ¥{pnlSign(totalPnl)})
          </span>
        </button>
      </div>

      {expanded && (
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden mb-2">
          {/* Summary table */}
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b-2 border-gray-200 dark:border-gray-700 text-[10px] text-gray-500 uppercase">
                <th className="text-left px-3 py-1.5">{locale === "zh" ? "市场" : "Market"}</th>
                <th className="text-left px-3 py-1.5">{locale === "zh" ? "账户" : "Broker"}</th>
                <th className="text-right px-3 py-1.5">{locale === "zh" ? "交易数" : "Trades"}</th>
                <th className="text-right px-3 py-1.5">P&L (¥)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary).sort().map(([key, s]) => {
                const [mkt, broker] = key.split("|");
                return (
                  <tr key={key} className="border-b border-gray-100 dark:border-gray-800/50">
                    <td className="px-3 py-1">{mktLabel(mkt, locale)}</td>
                    <td className="px-3 py-1">{broker}</td>
                    <td className="text-right px-3 py-1">{s.count}</td>
                    <td className={`text-right px-3 py-1 font-semibold ${pnlColor(s.pnl)}`}>{pnlSign(s.pnl)}</td>
                  </tr>
                );
              })}
              <tr className="border-t-2 border-gray-300 dark:border-gray-700 font-semibold">
                <td className="px-3 py-1.5">{locale === "zh" ? "合计" : "Total"}</td>
                <td /><td className="text-right px-3 py-1.5">{trades.length}</td>
                <td className={`text-right px-3 py-1.5 ${pnlColor(totalPnl)}`}>¥{pnlSign(totalPnl)}</td>
              </tr>
            </tbody>
          </table>

          {/* Detail table */}
          <div className="border-t border-gray-200 dark:border-gray-800 overflow-auto max-h-[40vh]">
            <table className="w-full text-xs font-mono">
              <thead className="sticky top-0 bg-white dark:bg-gray-900 text-[10px] text-gray-500 uppercase border-b border-gray-200 dark:border-gray-800">
                <tr>
                  <th className="text-left px-2 py-1">{locale === "zh" ? "名称" : "Name"}</th>
                  <th className="text-left px-2 py-1">{locale === "zh" ? "市场" : "Mkt"}</th>
                  <th className="text-left px-2 py-1">{locale === "zh" ? "账户" : "Broker"}</th>
                  {hasQty && <>
                    <th className="text-right px-2 py-1">Qty</th>
                    <th className="text-right px-2 py-1">{locale === "zh" ? "买入" : "Cost"}</th>
                    <th className="text-right px-2 py-1">{locale === "zh" ? "卖出" : "Close"}</th>
                  </>}
                  <th className="text-left px-2 py-1">{locale === "zh" ? "原币" : "Original Ccy"}</th>
                  <th className="text-right px-2 py-1">{locale === "zh" ? "P&L(原币)" : "P&L(orig)"}</th>
                  <th className="text-right px-2 py-1">P&L in CNY</th>
                  <th className="text-left px-2 py-1">{locale === "zh" ? "日期" : "Date"}</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr key={t.id} className="border-b border-gray-100 dark:border-gray-800/50">
                    <td className="px-2 py-0.5 truncate max-w-[100px]">{t.name}</td>
                    <td className="px-2 py-0.5 text-gray-500">{mktLabel(t.market, locale)}</td>
                    <td className="px-2 py-0.5 text-gray-500">{t.broker}</td>
                    {hasQty && <>
                      <td className="text-right px-2 py-0.5">{t.quantity != null ? fmtNum(t.quantity, 0) : "—"}</td>
                      <td className="text-right px-2 py-0.5">{t.cost_price != null ? fmtNum(t.cost_price) : "—"}</td>
                      <td className="text-right px-2 py-0.5">{t.close_price != null ? fmtNum(t.close_price) : "—"}</td>
                    </>}
                    <td className="px-2 py-0.5 text-gray-400">{t.currency !== "CNY" ? t.currency : "—"}</td>
                    <td className={`text-right px-2 py-0.5 ${pnlColor(t.realized_pnl)}`}>
                      {t.currency !== "CNY" ? pnlSign(t.realized_pnl, 0) : "—"}
                    </td>
                    <td className={`text-right px-2 py-0.5 ${pnlColor(t.realized_pnl_cny)}`}>
                      {t.realized_pnl_cny != null ? `¥${pnlSign(t.realized_pnl_cny)}` : "—"}
                    </td>
                    <td className="px-2 py-0.5 text-gray-500">{t.close_date || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

// ══════════════════════════════════════════
// Onboarding — Simplified empty state for new users (1-step)
// ══════════════════════════════════════════

function OnboardingCard({ locale, onRefresh, onOpenPanel }: { locale: string; onRefresh: () => void; onOpenPanel: (tab?: "edit" | "close" | "cash" | "settings") => void }) {
  const zh = locale === "zh";
  const [importing, setImporting] = useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);

  async function handleImport(file: File) {
    setImporting(true);
    try {
      const result = await importCSV(file);
      // Store flags in sessionStorage so SetupTipsBanner can display tips
      sessionStorage.setItem("vs_just_imported", "1");
      if (result.warnings && result.warnings.length > 0) {
        sessionStorage.setItem("vs_import_warnings", JSON.stringify(result.warnings));
      }
      onRefresh();
    } catch (e) {
      alert(zh ? "导入失败，请检查文件格式" : "Import failed. Check file format.");
    } finally {
      setImporting(false);
    }
  }

  // Mini demo data for preview
  const demoKpis = zh
    ? [{ l: "资产总值", v: "¥2,582,918" }, { l: "未实现盈亏", v: "+¥656,476", c: "text-red-500" }, { l: "日盈亏", v: "+¥8,759", c: "text-red-500" }, { l: "持仓数", v: "45" }]
    : [{ l: "Total Assets", v: "¥2,582,918" }, { l: "Unrealized P&L", v: "+¥656,476", c: "text-red-500" }, { l: "Daily P&L", v: "+¥8,759", c: "text-red-500" }, { l: "Positions", v: "45" }];
  const demoAlloc = [
    { label: zh ? "A股" : "A-Share", pct: 42, color: "bg-blue-500" },
    { label: zh ? "港股" : "HK", pct: 28, color: "bg-emerald-500" },
    { label: zh ? "美股" : "US", pct: 22, color: "bg-amber-500" },
    { label: zh ? "日股" : "JP", pct: 8, color: "bg-purple-500" },
  ];

  return (
    <div className="max-w-2xl mx-auto mt-10 mb-8">
      {/* Hero */}
      <div className="text-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          Portfolio Tracker
        </h2>
        <p className="text-sm text-gray-500 max-w-md mx-auto">
          {zh
            ? "跨市场投资组合追踪工具 — 一站式管理你在 A股、港股、美股、日股的所有持仓"
            : "Cross-market portfolio tracker — manage A-shares, HK, US & JP stocks in one place"}
        </p>
      </div>

      {/* Mini dashboard preview */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm overflow-hidden mb-6">
        <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800 flex items-center gap-2">
          <div className="flex gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-400" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-400" />
          </div>
          <span className="text-[10px] text-gray-400 ml-1">Portfolio Tracker</span>
        </div>
        <div className="p-4 space-y-3">
          {/* KPI row */}
          <div className="grid grid-cols-4 gap-2">
            {demoKpis.map((k) => (
              <div key={k.l} className="text-center">
                <div className="text-[10px] text-gray-400 truncate">{k.l}</div>
                <div className={`text-sm font-semibold font-mono ${k.c || "text-gray-800 dark:text-gray-200"}`}>{k.v}</div>
              </div>
            ))}
          </div>
          {/* Allocation bar */}
          <div>
            <div className="text-[10px] text-gray-400 mb-1">{zh ? "资产配置" : "Asset Allocation"}</div>
            <div className="flex h-3 rounded-full overflow-hidden">
              {demoAlloc.map((a) => (
                <div key={a.label} className={`${a.color} transition-all`} style={{ width: `${a.pct}%` }} />
              ))}
            </div>
            <div className="flex justify-between mt-1">
              {demoAlloc.map((a) => (
                <span key={a.label} className="text-[9px] text-gray-400">{a.label} {a.pct}%</span>
              ))}
            </div>
          </div>
          {/* Mini chart placeholder */}
          <div className="h-12 flex items-end gap-[2px]">
            {[30,35,28,40,38,45,42,50,48,55,52,60,58,65,62,70,68,72,65,75,78,74,80,85,82,88,84,90].map((h, i) => (
              <div key={i} className="flex-1 bg-blue-400/40 dark:bg-blue-500/30 rounded-t-sm" style={{ height: `${h}%` }} />
            ))}
          </div>
          <div className="text-[9px] text-gray-400 text-center">{zh ? "净值走势（含基准对比）" : "NAV trend (with benchmark)"}</div>
        </div>
      </div>

      {/* Feature highlights */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 mb-8 px-4">
        {(zh ? [
          { icon: "🌏", text: "A股 / 港股 / 美股 / 日股 / B股，多市场实时行情" },
          { icon: "📈", text: "未实现 & 已实现盈亏、日 / 周 / YTD 收益追踪" },
          { icon: "🎯", text: "资产配置分析（按市场 / 币种 / 行业）" },
          { icon: "📊", text: "净值曲线 + 沪深300 / 恒指 / 标普 基准对比" },
          { icon: "⚡", text: "风险分析 & 收益归因，量化投资表现" },
          { icon: "📰", text: "持仓相关新闻、财报日历、评级变动推送" },
        ] : [
          { icon: "🌏", text: "A-share / HK / US / JP / B-share, real-time quotes" },
          { icon: "📈", text: "Unrealized & realized P&L, daily / weekly / YTD" },
          { icon: "🎯", text: "Allocation analysis by market / currency / sector" },
          { icon: "📊", text: "NAV chart + CSI300 / HSI / S&P500 benchmarks" },
          { icon: "⚡", text: "Risk analysis & return attribution, quantify performance" },
          { icon: "📰", text: "News, earnings calendar & rating changes feed" },
        ]).map((f, i) => (
          <div key={i} className="flex items-start gap-2">
            <span className="text-base shrink-0 mt-0.5">{f.icon}</span>
            <span className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">{f.text}</span>
          </div>
        ))}
      </div>

      {/* CTA */}
      <div className="max-w-sm mx-auto space-y-3">
        <input ref={fileRef} type="file" accept=".csv" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImport(f); }} />
        <button onClick={() => fileRef.current?.click()} disabled={importing}
          className="w-full px-6 py-3 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 font-medium transition-colors">
          {importing ? (zh ? "导入中..." : "Importing...") : (zh ? "上传 CSV 开始使用" : "Upload CSV to Start")}
        </button>

        <div className="flex items-center justify-center gap-4">
          <a href={getImportTemplateUrl("portfolio")} download
            className="text-xs text-gray-400 hover:text-blue-500 underline underline-offset-2">
            {zh ? "下载模板" : "Download template"}
          </a>
          <span className="text-gray-300 dark:text-gray-700">|</span>
          <button onClick={() => onOpenPanel("edit")}
            className="text-xs text-gray-400 hover:text-blue-500 underline underline-offset-2">
            {zh ? "手动添加" : "Add manually"}
          </button>
        </div>
      </div>
    </div>
  );
}


// ══════════════════════════════════════════
// Setup Tips Banner — shown after import, dismissible
// ══════════════════════════════════════════

function SetupTipsBanner({ locale, data, onOpenPanel }: {
  locale: string; data: PortfolioData;
  onOpenPanel: (tab: "cash" | "settings") => void;
}) {
  const zh = locale === "zh";
  const [dismissedCash, setDismissedCash] = useState(false);
  const [dismissedMode, setDismissedMode] = useState(false);
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  const [dismissedWarnings, setDismissedWarnings] = useState(false);

  // Restore dismissed state from localStorage + import warnings from sessionStorage
  useEffect(() => {
    setDismissedCash(localStorage.getItem("vs_tip_cash") === "1");
    setDismissedMode(localStorage.getItem("vs_tip_mode") === "1");
    const w = sessionStorage.getItem("vs_import_warnings");
    if (w) { try { setImportWarnings(JSON.parse(w)); } catch {} }
  }, []);

  function dismissCash() { setDismissedCash(true); localStorage.setItem("vs_tip_cash", "1"); }
  function dismissMode() { setDismissedMode(true); localStorage.setItem("vs_tip_mode", "1"); }
  function dismissWarning() { setDismissedWarnings(true); sessionStorage.removeItem("vs_import_warnings"); }

  // Show cash tip if total cash is 0
  const showCash = !dismissedCash && data.summary.cash_cny === 0;
  // Show mode tip only right after an import (sessionStorage flag), not for returning users
  const justImported = typeof window !== "undefined" && sessionStorage.getItem("vs_just_imported") === "1";
  const showMode = !dismissedMode && justImported;
  // Show import warnings (similar account names)
  const showWarnings = !dismissedWarnings && importWarnings.length > 0;

  if (!showCash && !showMode && !showWarnings) return null;

  return (
    <div className="space-y-2 mb-4">
      {showCash && (
        <div className="flex items-start gap-3 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800">
          <span className="text-lg shrink-0">💰</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-amber-800 dark:text-amber-200">
              {zh
                ? "还没有设置现金余额。添加各账户的现金，让资产总值和收益率计算更准确。"
                : "Cash balances not set. Add cash for each account for accurate total assets and returns."}
            </p>
            <button onClick={() => onOpenPanel("cash")}
              className="text-xs text-amber-700 dark:text-amber-300 hover:underline font-medium mt-1">
              {zh ? "去设置 →" : "Set up →"}
            </button>
          </div>
          <button onClick={dismissCash} className="text-amber-400 hover:text-amber-600 text-lg leading-none shrink-0" title="Dismiss">×</button>
        </div>
      )}

      {showWarnings && (
        <div className="flex items-start gap-3 p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800">
          <span className="text-lg shrink-0">⚠️</span>
          <div className="flex-1 min-w-0">
            {importWarnings.map((w, i) => (
              <p key={i} className="text-sm text-orange-800 dark:text-orange-200">{w}</p>
            ))}
            <button onClick={() => onOpenPanel("settings")}
              className="text-xs text-orange-700 dark:text-orange-300 hover:underline font-medium mt-1">
              {zh ? "去「设置」检查 →" : "Check in Settings →"}
            </button>
          </div>
          <button onClick={dismissWarning} className="text-orange-400 hover:text-orange-600 text-lg leading-none shrink-0" title="Dismiss">×</button>
        </div>
      )}

      {showMode && (
        <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
          <span className="text-lg shrink-0">📋</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-blue-800 dark:text-blue-200 mb-1">
              {zh
                ? "所有账户默认使用「成本模式」。如有外币或封闭账户，建议切换为「入金模式」。"
                : "All accounts default to Cost mode. Switch to Deposit mode for foreign-currency or closed accounts."}
            </p>
            <div className="text-xs text-blue-700/80 dark:text-blue-300/80 space-y-1 mb-2">
              <p>{zh
                ? "📊 成本模式：Capital = 持仓成本 + 现金 − 已实现盈亏。适合大部分账户，Capital 始终等于原始投入。"
                : "📊 Cost mode: Capital = cost + cash − realized P&L. Suits most accounts — Capital always equals original investment."}</p>
              <p>{zh
                ? "💰 入金模式：用固定入金金额作为 Capital，忽略汇率波动。例如：汇入 100 万人民币到港股账户，无论汇率变化 Capital 始终 100 万。"
                : "💰 Deposit mode: Use fixed deposit amount as Capital, ignoring FX changes. E.g., ¥1M remitted to HK account stays ¥1M Capital regardless of exchange rate."}</p>
            </div>
            <button onClick={() => onOpenPanel("settings")}
              className="text-xs text-blue-700 dark:text-blue-300 hover:underline font-medium">
              {zh ? "去设置 →" : "Set up →"}
            </button>
          </div>
          <button onClick={dismissMode} className="text-blue-400 hover:text-blue-600 text-lg leading-none shrink-0" title="Dismiss">×</button>
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════════
// Sidebar — Data Management (slide-out panel)
// ══════════════════════════════════════════

function DataPanel({ holdings, data, locale, onRefresh, open, onClose, editHolding, initialTab = "edit" }: {
  holdings: PortfolioHolding[]; data: PortfolioData | null; locale: string;
  onRefresh: () => void; open: boolean; onClose: () => void;
  editHolding?: PortfolioHolding | null;
  initialTab?: "edit" | "close" | "cash" | "settings";
}) {
  const [tab, setTab] = useState<"edit" | "close" | "cash" | "settings">(initialTab);

  // Sync tab when panel opens with a specific initialTab
  useEffect(() => {
    if (open) setTab(initialTab);
  }, [open, initialTab]);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // ── Edit tab state ──
  const [posSearch, setPosSearch] = useState("");
  const [editTicker, setEditTicker] = useState("");
  const [editName, setEditName] = useState("");
  const [editMarket, setEditMarket] = useState("A股");
  const [editBroker, setEditBroker] = useState("");
  const [editQty, setEditQty] = useState("");
  const [editCost, setEditCost] = useState("");
  const [editCurrency, setEditCurrency] = useState("CNY");
  const [isEditing, setIsEditing] = useState(false);

  // ── Close tab state ──
  const [closeSearch, setCloseSearch] = useState("");
  const [closeTarget, setCloseTarget] = useState<PortfolioHolding | null>(null);
  const [closeQty, setCloseQty] = useState("");
  const [closePrice, setClosePrice] = useState("");

  // ── Cash & Margin tab state ──
  const [cashEdits, setCashEdits] = useState<Record<string, string>>({});
  const [marginEdits, setMarginEdits] = useState<Record<string, string>>({});
  const [marginData, setMarginData] = useState<MarginBalance[]>([]);
  const [newCashAccount, setNewCashAccount] = useState("");
  const [newCashCustomName, setNewCashCustomName] = useState("");
  const [newCashCurrency, setNewCashCurrency] = useState("CNY");

  // ── Settings tab state ──
  const [acctSettings, setAcctSettings] = useState<AccountSetting[]>([]);
  const [acctBroker, setAcctBroker] = useState("");
  const [newAcctName, setNewAcctName] = useState("");
  const [isNewAcct, setIsNewAcct] = useState(false);
  const [acctMode, setAcctMode] = useState<"cost" | "deposit">("cost");
  const [acctDeposit, setAcctDeposit] = useState("");
  const [acctFx, setAcctFx] = useState("1.0");
  const [depositAction, setDepositAction] = useState<"update" | "add">("update");
  const [depositDate, setDepositDate] = useState("");
  const [depositNotes, setDepositNotes] = useState("");
  const [depositHistory, setDepositHistory] = useState<DepositRecord[]>([]);
  const [expandedBroker, setExpandedBroker] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      getAccountSettings().then(setAcctSettings).catch(() => {});
      getMarginBalances().then(setMarginData).catch(() => {});
    }
  }, [open]);

  const inputCls = "w-full px-2 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:ring-1 focus:ring-blue-500 focus:outline-none";
  const zh = locale === "zh";

  // ── Pre-fill from external edit request ──
  useEffect(() => {
    if (editHolding && open) {
      setTab("edit");
      fillForm(editHolding);
    }
  }, [editHolding, open]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Edit handlers ──
  function fillForm(h: PortfolioHolding) {
    setEditTicker(h.ticker); setEditName(h.name); setEditMarket(h.market);
    setEditBroker(h.broker); setEditQty(String(h.quantity)); setEditCost(String(h.cost_price)); setEditCurrency(h.currency);
    setIsEditing(true);
  }

  function clearForm() {
    setEditTicker(""); setEditName(""); setEditMarket("A股"); setEditBroker("");
    setEditQty(""); setEditCost(""); setEditCurrency("CNY"); setIsEditing(false);
  }

  async function handleSave() {
    if (!editTicker || !editName) return;
    if (!editBroker) { setMsg(zh ? "⚠️ 请先选择账户，如需新账户请到「设置」添加" : "⚠️ Select an account first. Add new accounts in Settings tab"); return; }
    setSaving(true); setMsg(null);
    try {
      await upsertPosition({ ticker: editTicker, name: editName, market: editMarket, broker: editBroker,
        quantity: parseFloat(editQty) || 0, cost_price: parseFloat(editCost) || 0, currency: editCurrency });
      setMsg("✅ Saved"); clearForm(); onRefresh();
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  async function handleDelete(ticker: string, broker: string) {
    if (!confirm(zh ? `确认删除 ${ticker} (${broker})？此操作不可恢复。` : `Confirm delete ${ticker} (${broker})? This cannot be undone.`)) return;
    try { await deletePosition(ticker, broker); onRefresh(); setMsg("✅ Deleted"); } catch { setMsg("❌ Error"); }
  }

  const filteredPositions = useMemo(() => {
    if (!posSearch) return holdings;
    const q = posSearch.toLowerCase();
    return holdings.filter((h) => h.name.toLowerCase().includes(q) || h.ticker.toLowerCase().includes(q) || h.broker.toLowerCase().includes(q));
  }, [holdings, posSearch]);

  // ── Close handlers ──
  function selectCloseTarget(h: PortfolioHolding) {
    setCloseTarget(h);
    setCloseQty(String(h.quantity));
    setClosePrice(h.price ? String(h.price) : "");
  }

  const closePnl = useMemo(() => {
    if (!closeTarget) return null;
    const qty = parseFloat(closeQty) || 0;
    const sellPrice = parseFloat(closePrice) || 0;
    const costPrice = closeTarget.cost_price;
    const pnl = (sellPrice - costPrice) * qty;
    const rate = data?.fx?.[closeTarget.currency] || 1.0;
    const pnlCny = pnl * rate;
    return { pnl, pnlCny, currency: closeTarget.currency, qty, sellPrice, costPrice };
  }, [closeTarget, closeQty, closePrice, data]);

  async function handleClose() {
    if (!closeTarget || !closePnl) return;
    const qty = closePnl.qty;
    const fullClose = qty >= closeTarget.quantity;
    const confirmMsg = zh
      ? `${fullClose ? "清仓" : "部分卖出"} ${closeTarget.name}\n数量: ${qty}\n卖出价: ${closePnl.sellPrice}\n盈亏: ${closePnl.pnl >= 0 ? "+" : ""}${closePnl.pnl.toFixed(2)} ${closePnl.currency}\n盈亏(¥): ${closePnl.pnlCny >= 0 ? "+" : ""}${closePnl.pnlCny.toFixed(0)}`
      : `${fullClose ? "Close" : "Partial sell"} ${closeTarget.name}\nQty: ${qty}\nSell: ${closePnl.sellPrice}\nP&L: ${closePnl.pnl >= 0 ? "+" : ""}${closePnl.pnl.toFixed(2)} ${closePnl.currency}\nP&L(¥): ${closePnl.pnlCny >= 0 ? "+" : ""}${closePnl.pnlCny.toFixed(0)}`;
    if (!confirm(confirmMsg)) return;
    setSaving(true);
    try {
      // Record closed trade
      await addClosedTrade({
        ticker: closeTarget.ticker, name: closeTarget.name, market: closeTarget.market,
        broker: closeTarget.broker, quantity: qty, buy_price: closePnl.costPrice,
        sell_price: closePnl.sellPrice, realized_pnl: closePnl.pnl,
        realized_pnl_cny: closePnl.pnlCny, currency: closePnl.currency,
      });
      if (fullClose) {
        // Delete position entirely
        await deletePosition(closeTarget.ticker, closeTarget.broker);
      } else {
        // Update remaining quantity
        await upsertPosition({
          ticker: closeTarget.ticker, name: closeTarget.name, market: closeTarget.market,
          broker: closeTarget.broker, quantity: closeTarget.quantity - qty,
          cost_price: closeTarget.cost_price, currency: closeTarget.currency,
        });
      }
      setCloseTarget(null); setCloseSearch("");
      setMsg(`✅ ${zh ? "已平仓" : "Closed"}`); onRefresh();
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  const filteredClose = useMemo(() => {
    if (!closeSearch) return holdings;
    const q = closeSearch.toLowerCase();
    return holdings.filter((h) => h.name.toLowerCase().includes(q) || h.ticker.toLowerCase().includes(q));
  }, [holdings, closeSearch]);

  // ── Cash & Margin handlers ──
  async function handleCashSaveAll() {
    setSaving(true);
    try {
      for (const [key, val] of Object.entries(cashEdits)) {
        const [account, currency] = key.split("|");
        await updateCash({ account, currency, balance: parseFloat(val) || 0 });
      }
      setCashEdits({}); onRefresh(); setMsg("✅ Saved");
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  async function handleAddCashAccount() {
    const acctName = newCashAccount === "__other__" ? newCashCustomName.trim() : newCashAccount;
    if (!acctName) return;
    try {
      await updateCash({ account: acctName, currency: newCashCurrency, balance: 0 });
      setNewCashAccount(""); setNewCashCustomName(""); onRefresh();
    } catch { alert("Error"); }
  }

  async function handleMarginSaveAll() {
    setSaving(true);
    try {
      for (const [key, val] of Object.entries(marginEdits)) {
        const [category, currency] = key.split("|");
        await updateMargin({ broker: "合计", category, currency, amount: parseFloat(val) || 0 });
      }
      setMarginEdits({}); setMarginData(await getMarginBalances()); onRefresh(); setMsg("✅ Saved");
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  // ── Settings handlers ──
  async function handleAcctSave() {
    const broker = isNewAcct ? newAcctName.trim() : acctBroker;
    if (!broker) return;
    setSaving(true);
    try {
      if (acctMode === "deposit" && depositAction === "add") {
        // Append deposit record → backend auto-recalculates totals in account_settings
        await addDepositRecord({
          broker,
          amount_cny: parseFloat(acctDeposit) || 0,
          fx_rate: parseFloat(acctFx) || 1.0,
          deposit_date: depositDate,
          notes: depositNotes,
        });
      } else {
        // Direct update (overwrite totals)
        await upsertAccountSetting({ broker, capital_mode: acctMode,
          deposit_cny: parseFloat(acctDeposit) || 0, deposit_fx: parseFloat(acctFx) || 1.0 });
      }
      setAcctSettings(await getAccountSettings());
      setAcctBroker(""); setNewAcctName(""); setIsNewAcct(false);
      setAcctDeposit(""); setAcctFx("1.0"); setAcctMode("cost");
      setDepositAction("update"); setDepositDate(""); setDepositNotes("");
      if (expandedBroker) {
        setDepositHistory(await getDepositHistory(expandedBroker));
      }
      onRefresh(); setMsg("✅ Saved");
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  const [mergeSource, setMergeSource] = useState<string | null>(null);
  const [mergeTarget, setMergeTarget] = useState("");

  async function handleAcctDelete(broker: string) {
    // Check if this account has positions — warn about data loss
    const hasPositions = holdings.some((h) => h.broker === broker);
    if (hasPositions) {
      const msg = zh
        ? `「${broker}」下有持仓记录。\n• 直接删除会丢失持仓数据\n• 建议先合并到其他账户\n\n选择「确定」打开合并，「取消」放弃`
        : `"${broker}" has positions.\n• Deleting will lose position data\n• Consider merging first\n\nOK to open merge, Cancel to abort`;
      if (confirm(msg)) {
        setMergeSource(broker);
        setMergeTarget("");
        return;
      }
      return;
    }
    if (!confirm(`${zh ? "删除" : "Delete"} ${broker}?`)) return;
    try { await deleteAccountSetting(broker); setAcctSettings(await getAccountSettings()); onRefresh(); } catch { alert("Error"); }
  }

  async function handleMerge() {
    if (!mergeSource || !mergeTarget) return;
    const msg = zh
      ? `确认将「${mergeSource}」的所有数据合并到「${mergeTarget}」？\n合并后「${mergeSource}」将被删除。`
      : `Merge all data from "${mergeSource}" into "${mergeTarget}"?\n"${mergeSource}" will be deleted after merge.`;
    if (!confirm(msg)) return;
    try {
      await mergeAccounts(mergeSource, mergeTarget);
      setMergeSource(null);
      setMergeTarget("");
      setAcctSettings(await getAccountSettings());
      onRefresh();
      setMsg(zh ? "✅ 合并成功" : "✅ Merge complete");
    } catch (e: unknown) {
      setMsg(`❌ ${e instanceof Error ? e.message : "Merge failed"}`);
    }
  }

  // ── Tab style ──
  const tabCls = (t2: string) => `flex-1 text-center py-1.5 text-xs font-medium cursor-pointer transition-colors ${tab === t2 ? "text-blue-600 border-b-2 border-blue-600" : "text-gray-400 hover:text-gray-600 border-b border-gray-200 dark:border-gray-800"}`;

  // ── Cash rows from data (sorted: 券商 → 银行 → 在途) ──
  const cashRows = useMemo(() => {
    const rows: { account: string; currency: string; balance: number }[] = data?.cash || [];
    const order: Record<string, number> = { "中信": 1, "中信B股": 2, "招商": 3, "招商永隆": 4, "富途": 5, "招商银行": 10, "汇丰银行": 11, "支付宝": 12, "在途": 20 };
    return [...rows].sort((a, b) => (order[a.account] || 50) - (order[b.account] || 50));
  }, [data]);

  // ── Broker accounts for settings dropdown (from positions + existing settings) ──
  const knownAccounts = useMemo(() => {
    const names = new Set<string>();
    holdings.forEach((h) => names.add(h.broker));
    acctSettings.forEach((s) => names.add(s.broker));
    return [...names].sort();
  }, [holdings, acctSettings]);

  // ── Existing mode for the selected account (prevents mode conflicts) ──
  const existingMode = useMemo(() => {
    if (!acctBroker) return null;
    const s = acctSettings.find((s) => s.broker === acctBroker);
    return s ? (s.capital_mode as "cost" | "deposit") : null;
  }, [acctBroker, acctSettings]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div className="relative ml-auto w-[400px] max-w-full h-full bg-white dark:bg-gray-950 shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide">{zh ? "数据管理" : "Data Management"}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">✕</button>
        </div>

        {/* Tabs */}
        <div className="flex px-4 mb-3">
          <div className={tabCls("edit")} onClick={() => { setTab("edit"); setMsg(null); }}>{zh ? "持仓" : "Positions"}</div>
          <div className={tabCls("close")} onClick={() => { setTab("close"); setMsg(null); }}>{zh ? "平仓" : "Close"}</div>
          <div className={tabCls("cash")} onClick={() => { setTab("cash"); setMsg(null); }}>{zh ? "现金/杠杆" : "Cash/Margin"}</div>
          <div className={tabCls("settings")} onClick={() => { setTab("settings"); setMsg(null); }}>{zh ? "设置" : "Settings"}</div>
        </div>

        {/* Message bar */}
        {msg && <div className="mx-4 mb-2 text-xs text-center py-1 rounded bg-gray-50 dark:bg-gray-900">{msg}</div>}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 pb-4">

          {/* ═══════ EDIT TAB ═══════ */}
          {tab === "edit" && (
            <>
              {/* Search & select position */}
              <div className="mb-3">
                <input className={inputCls} placeholder={zh ? "🔍 搜索持仓 (名称/代码/账户)" : "🔍 Search (name/ticker/broker)"}
                  value={posSearch} onChange={(e) => setPosSearch(e.target.value)} />
              </div>

              {/* Position list (compact, click to edit) */}
              <div className="mb-3 max-h-[25vh] overflow-auto border border-gray-200 dark:border-gray-800 rounded">
                {filteredPositions.map((h) => (
                  <div key={`${h.ticker}-${h.broker}`}
                    onClick={() => fillForm(h)}
                    className={`flex items-center justify-between px-2 py-1.5 border-b border-gray-100 dark:border-gray-800/50 text-xs font-mono cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/10 transition-colors ${isEditing && editTicker === h.ticker && editBroker === h.broker ? "bg-blue-50 dark:bg-blue-900/20 border-l-2 border-l-blue-500" : ""}`}>
                    <div className="truncate flex-1">
                      <span className="font-medium">{h.ticker}</span> <span className="text-gray-400">{h.name}</span>
                      <div className="text-[10px] text-gray-400">{h.broker} · {fmtNum(h.quantity, 0)} @ {fmtNum(h.cost_price)}</div>
                    </div>
                  </div>
                ))}
                {filteredPositions.length === 0 && <div className="text-center text-gray-400 text-xs py-3">{zh ? "无匹配持仓" : "No matching positions"}</div>}
              </div>

              {/* Edit form */}
              <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] text-gray-500 uppercase">{isEditing ? (zh ? "编辑持仓" : "Edit Position") : (zh ? "新增持仓" : "Add Position")}</div>
                  {isEditing && <button onClick={clearForm} className="text-[10px] text-blue-500 hover:text-blue-700">{zh ? "清空 / 新增" : "Clear / New"}</button>}
                </div>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <input className={inputCls} placeholder="Ticker" value={editTicker} onChange={(e) => setEditTicker(e.target.value.toUpperCase())} disabled={isEditing} />
                  <input className={inputCls} placeholder={zh ? "名称" : "Name"} value={editName} onChange={(e) => setEditName(e.target.value)} />
                  <select className={inputCls} value={editMarket} onChange={(e) => setEditMarket(e.target.value)}>
                    {["A股", "港股", "美股", "日股", "B股", "基金"].map((m) => <option key={m} value={m}>{mktLabel(m, locale)}</option>)}
                  </select>
                  {isEditing ? (
                    <input className={inputCls} value={editBroker} disabled />
                  ) : (
                    <div>
                      <select className={inputCls} value={editBroker} onChange={(e) => setEditBroker(e.target.value)}>
                        <option value="">{zh ? "— 选择账户 —" : "— Select account —"}</option>
                        {acctSettings.map((s) => <option key={s.broker} value={s.broker}>{s.broker}</option>)}
                      </select>
                      {acctSettings.length === 0 && <div className="text-[9px] text-amber-500 mt-0.5">{zh ? "请先到「设置」添加账户" : "Add accounts in Settings first"}</div>}
                    </div>
                  )}
                  <input className={inputCls} placeholder={zh ? "数量" : "Quantity"} inputMode="decimal" value={editQty} onChange={(e) => setEditQty(e.target.value)} />
                  <input className={inputCls} placeholder={zh ? "成本价" : "Cost price"} inputMode="decimal" value={editCost} onChange={(e) => setEditCost(e.target.value)} />
                  <select className={inputCls} value={editCurrency} onChange={(e) => setEditCurrency(e.target.value)}>
                    {["CNY", "HKD", "USD", "JPY"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <button onClick={handleSave} disabled={saving} className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                  {saving ? "..." : (zh ? "保存" : "Save")}
                </button>
              </div>
            </>
          )}

          {/* ═══════ CLOSE TAB ═══════ */}
          {tab === "close" && (
            <>
              <div className="text-[10px] text-gray-400 mb-3 leading-relaxed">
                {zh ? "选择要平仓的持仓，输入卖出价格，系统自动计算盈亏并记录到已平仓交易。" : "Select a position to close. Enter sell price and the system will calculate P&L automatically."}
              </div>

              {!closeTarget ? (
                <>
                  <input className={`${inputCls} mb-2`} placeholder={zh ? "🔍 搜索持仓" : "🔍 Search positions"}
                    value={closeSearch} onChange={(e) => setCloseSearch(e.target.value)} />
                  <div className="max-h-[50vh] overflow-auto border border-gray-200 dark:border-gray-800 rounded">
                    {filteredClose.map((h) => (
                      <div key={`${h.ticker}-${h.broker}`} onClick={() => selectCloseTarget(h)}
                        className="flex items-center justify-between px-2 py-2 border-b border-gray-100 dark:border-gray-800/50 text-xs font-mono cursor-pointer hover:bg-red-50 dark:hover:bg-red-900/10 transition-colors">
                        <div className="truncate flex-1">
                          <span className="font-medium">{h.ticker}</span> <span className="text-gray-400">{h.name}</span>
                          <div className="text-[10px] text-gray-400">{h.broker} · {fmtNum(h.quantity, 0)} @ {fmtNum(h.cost_price)} · {zh ? "现价" : "now"} {h.price ? fmtNum(h.price) : "—"}</div>
                        </div>
                        <span className={`text-[10px] font-mono ${pnlColor(h.pnl)}`}>{pnlSign(h.pnl, 0)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                  {/* Selected position info */}
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <div className="text-sm font-semibold">{closeTarget.ticker} <span className="text-gray-400 font-normal">{closeTarget.name}</span></div>
                      <div className="text-[10px] text-gray-400 font-mono">{closeTarget.broker} · {closeTarget.currency} · {zh ? "持仓" : "Qty"}: {fmtNum(closeTarget.quantity, 0)} @ {fmtNum(closeTarget.cost_price)}</div>
                    </div>
                    <button onClick={() => setCloseTarget(null)} className="text-xs text-blue-500 hover:text-blue-700">{zh ? "← 返回" : "← Back"}</button>
                  </div>

                  {/* Sell inputs */}
                  <div className="grid grid-cols-2 gap-2 mb-3">
                    <div>
                      <div className="text-[10px] text-gray-500 mb-1">{zh ? "卖出数量" : "Sell Qty"}</div>
                      <input className={inputCls} inputMode="decimal" value={closeQty} onChange={(e) => setCloseQty(e.target.value)} />
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-500 mb-1">{zh ? "卖出价格" : "Sell Price"}</div>
                      <input className={inputCls} inputMode="decimal" value={closePrice} onChange={(e) => setClosePrice(e.target.value)} />
                    </div>
                  </div>

                  {/* P&L preview */}
                  {closePnl && closePnl.qty > 0 && closePnl.sellPrice > 0 && (
                    <div className="mb-3 p-2 rounded bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-700">
                      <div className="flex justify-between text-xs mb-1">
                        <span className="text-gray-500">{zh ? "盈亏" : "P&L"} ({closePnl.currency})</span>
                        <span className={`font-mono font-semibold ${pnlColor(closePnl.pnl)}`}>{pnlSign(closePnl.pnl, 2)}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">{zh ? "盈亏" : "P&L"} (¥)</span>
                        <span className={`font-mono font-semibold ${pnlColor(closePnl.pnlCny)}`}>{pnlSign(closePnl.pnlCny, 0)}</span>
                      </div>
                      {closePnl.qty < closeTarget.quantity && (
                        <div className="text-[10px] text-amber-600 mt-1">{zh ? `部分卖出 ${closePnl.qty}/${closeTarget.quantity}` : `Partial: ${closePnl.qty}/${closeTarget.quantity}`}</div>
                      )}
                    </div>
                  )}

                  <button onClick={handleClose} disabled={saving || !closePnl || closePnl.qty <= 0 || closePnl.sellPrice <= 0}
                    className="w-full px-3 py-2 text-sm rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 font-medium">
                    {saving ? "..." : (zh ? (closePnl && closePnl.qty < closeTarget.quantity ? "部分卖出" : "确认平仓") : (closePnl && closePnl.qty < closeTarget.quantity ? "Partial Sell" : "Close Position"))}
                  </button>
                </div>
              )}
            </>
          )}

          {/* ═══════ CASH & MARGIN TAB ═══════ */}
          {tab === "cash" && (
            <>
              {/* Cash balances — batch edit */}
              <div className="mb-4">
                <div className="text-[10px] text-gray-500 uppercase mb-2">{zh ? "现金余额" : "Cash Balances"}</div>
                <div className="border border-gray-200 dark:border-gray-800 rounded overflow-hidden mb-2">
                  {cashRows.map((r) => {
                    const key = `${r.account}|${r.currency}`;
                    const val = key in cashEdits ? cashEdits[key] : String(r.balance);
                    return (
                      <div key={key} className="flex items-center gap-2 px-2 py-1.5 border-b border-gray-100 dark:border-gray-800/50 last:border-b-0">
                        <span className="text-xs font-mono text-gray-600 dark:text-gray-300 w-16 truncate">{r.account}</span>
                        <span className="text-[10px] text-gray-400 w-8">{r.currency}</span>
                        <input className={`${inputCls} flex-1 text-right text-xs`} inputMode="decimal" value={val}
                          onChange={(e) => setCashEdits((prev) => ({ ...prev, [key]: e.target.value }))} />
                        <button onClick={async () => {
                          if (!confirm(zh ? `删除 ${r.account} ${r.currency}？` : `Delete ${r.account} ${r.currency}?`)) return;
                          try { await deleteCash(r.account, r.currency); onRefresh(); } catch { setMsg("❌ Error"); }
                        }} className="text-red-300 hover:text-red-500 text-xs shrink-0">✕</button>
                      </div>
                    );
                  })}
                  {cashRows.length === 0 && <div className="text-center text-gray-400 text-xs py-3">{zh ? "暂无现金账户" : "No cash accounts"}</div>}
                </div>
                {/* Add new cash row */}
                <div className="flex gap-2 mb-2">
                  <select className={`${inputCls} flex-1`} value={newCashAccount} onChange={(e) => setNewCashAccount(e.target.value)}>
                    <option value="">{zh ? "— 选择账户 —" : "— Select account —"}</option>
                    {acctSettings.map((s) => <option key={s.broker} value={s.broker}>{s.broker}</option>)}
                    <option value="__other__">{zh ? "其他（银行/在途等）" : "Other (bank, etc.)"}</option>
                  </select>
                  <select className={inputCls} style={{ width: 70 }} value={newCashCurrency} onChange={(e) => setNewCashCurrency(e.target.value)}>
                    {["CNY", "HKD", "USD", "JPY"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <button onClick={handleAddCashAccount} disabled={!newCashAccount || (newCashAccount === "__other__" && !newCashCustomName.trim())} className="px-3 py-1.5 text-sm rounded bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 disabled:opacity-50">+</button>
                </div>
                {newCashAccount === "__other__" && (
                  <input className={`${inputCls} mb-2`} placeholder={zh ? "输入账户名称" : "Account name"} value={newCashCustomName} onChange={(e) => setNewCashCustomName(e.target.value)} />
                )}
                <button onClick={handleCashSaveAll} disabled={saving || Object.keys(cashEdits).length === 0} className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 mb-2">
                  {saving ? "..." : (zh ? "保存现金" : "Save Cash")}
                </button>
              </div>

              {/* Margin / Leverage — batch edit */}
              <div>
                <div className="text-[10px] text-gray-500 uppercase mb-2">{zh ? "杠杆/融资" : "Leverage / Margin"}</div>

                {/* In-house margin */}
                <div className="mb-2 p-2 rounded bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                  <div className="text-[10px] text-gray-400 mb-1.5">{zh ? "场内融资 (券商保证金)" : "In-house Margin"}</div>
                  <div className="grid grid-cols-2 gap-2">
                    {["USD", "HKD", "JPY", "CNY"].map((cur) => {
                      const key = `in_house|${cur}`;
                      const existing = marginData.find((m) => m.category === "in_house" && m.currency === cur);
                      const val = key in marginEdits ? marginEdits[key] : String(existing?.amount || 0);
                      return (
                        <div key={key} className="flex items-center gap-1">
                          <span className="text-[10px] text-gray-400 w-8">{cur}</span>
                          <input className={`${inputCls} flex-1 text-right text-xs`} inputMode="decimal" value={val}
                            onChange={(e) => setMarginEdits((prev) => ({ ...prev, [key]: e.target.value }))} />
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Off-exchange leverage */}
                <div className="mb-3 p-2 rounded bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                  <div className="text-[10px] text-gray-400 mb-1.5">{zh ? "场外杠杆 (影响 Capital)" : "Off-exchange Leverage (affects Capital)"}</div>
                  {["CNY"].map((cur) => {
                    const key = `off_exchange|${cur}`;
                    const existing = marginData.find((m) => m.category === "off_exchange" && m.currency === cur);
                    const val = key in marginEdits ? marginEdits[key] : String(existing?.amount || 0);
                    return (
                      <div key={key} className="flex items-center gap-1">
                        <span className="text-[10px] text-gray-400 w-8">{cur}</span>
                        <input className={`${inputCls} flex-1 text-right text-xs`} inputMode="decimal" value={val}
                          onChange={(e) => setMarginEdits((prev) => ({ ...prev, [key]: e.target.value }))} />
                      </div>
                    );
                  })}
                </div>

                <button onClick={handleMarginSaveAll} disabled={saving || Object.keys(marginEdits).length === 0} className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                  {saving ? "..." : (zh ? "保存杠杆" : "Save Margin")}
                </button>
              </div>
            </>
          )}

          {/* ═══════ SETTINGS TAB ═══════ */}
          {tab === "settings" && (
            <>
              <div className="text-[10px] text-gray-400 mb-3 leading-relaxed space-y-1.5">
                <p>{zh
                  ? "💰 入金模式：适合封闭/跨币种账户，用固定人民币金额替代该账户的持仓成本和现金，避免汇率波动影响 Capital。该账户的已实现盈亏也不参与 Capital 计算。"
                  : "💰 Deposit mode: Replace this account's position costs, cash and realized P&L with a fixed CNY deposit amount. Suitable for closed or cross-currency accounts to avoid FX fluctuation on Capital."}</p>
                <p>{zh
                  ? "📊 成本模式：Capital = 持仓成本 + 现金 − 已平仓盈亏。Capital 始终等于原始投入金额。"
                  : "📊 Cost mode: Capital = position cost + cash − realized P&L. Capital always equals original invested amount."}</p>
                <p>{zh
                  ? "ℹ️ 所有账户都需要在此注册。新增持仓时，账户选项来自此列表。"
                  : "ℹ️ All accounts must be registered here. The account dropdown in Positions tab is sourced from this list."}</p>
              </div>

              {/* Existing settings */}
              {acctSettings.length > 0 && (
                <div className="mb-3 border border-gray-200 dark:border-gray-800 rounded overflow-hidden">
                  {[...acctSettings].sort((a, b) => {
                    if (a.capital_mode !== b.capital_mode) return a.capital_mode === "deposit" ? -1 : 1;
                    return a.broker.localeCompare(b.broker, "zh");
                  }).map((s) => (
                    <div key={s.broker} className="border-b border-gray-100 dark:border-gray-800/50 last:border-b-0">
                      <div className="flex items-center justify-between px-2 py-1.5 text-xs font-mono">
                        <div className="flex-1">
                          <span className="font-medium">{s.broker}</span>
                          <span className={`ml-2 px-1.5 py-0.5 rounded text-[9px] font-semibold ${s.capital_mode === "deposit" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"}`}>
                            {s.capital_mode === "deposit" ? (zh ? "入金" : "Deposit") : (zh ? "成本" : "Cost")}
                          </span>
                          {s.capital_mode === "deposit" && s.deposit_cny > 0 && <span className="ml-2 text-gray-400">¥{formatNumber(s.deposit_cny, 0)}</span>}
                          {s.capital_mode === "deposit" && s.deposit_fx > 1 && <span className="ml-1 text-gray-400 text-[10px]">@{s.deposit_fx}</span>}
                        </div>
                        <div className="flex gap-1 ml-2">
                          {s.capital_mode === "deposit" && (
                            <button onClick={async () => {
                              if (expandedBroker === s.broker) { setExpandedBroker(null); return; }
                              setExpandedBroker(s.broker);
                              try { setDepositHistory(await getDepositHistory(s.broker)); } catch { setDepositHistory([]); }
                            }} className="text-gray-400 hover:text-gray-600 text-[10px]">{expandedBroker === s.broker ? "▼" : "▶"}</button>
                          )}
                          <button onClick={() => { setAcctBroker(s.broker); setAcctMode(s.capital_mode as "cost" | "deposit"); setAcctDeposit(s.deposit_cny > 0 ? String(s.deposit_cny) : ""); setAcctFx(String(s.deposit_fx)); setDepositAction("update"); }} className="text-blue-500 hover:text-blue-700">✎</button>
                          <button onClick={() => handleAcctDelete(s.broker)} className="text-red-400 hover:text-red-600">✕</button>
                        </div>
                      </div>
                      {/* Expanded deposit history */}
                      {expandedBroker === s.broker && (
                        <div className="px-2 pb-2">
                          {depositHistory.length === 0 ? (
                            <div className="text-[10px] text-gray-400 py-1">{zh ? "暂无入金记录。可点击下方「追加入金」添加。" : "No deposit records. Use 'Add Deposit' below to add."}</div>
                          ) : (
                            <div className="space-y-1">
                              {depositHistory.map((d) => (
                                <div key={d.id} className="flex items-center justify-between text-[10px] font-mono bg-gray-50 dark:bg-gray-900 rounded px-2 py-1">
                                  <div className="flex-1">
                                    <span className="text-gray-600 dark:text-gray-300">¥{formatNumber(d.amount_cny, 0)}</span>
                                    {d.fx_rate > 1 && <span className="ml-1 text-gray-400">@{d.fx_rate}</span>}
                                    {d.deposit_date && <span className="ml-2 text-gray-400">{d.deposit_date}</span>}
                                    {d.notes && <span className="ml-1 text-gray-400">({d.notes})</span>}
                                  </div>
                                  <button onClick={async () => {
                                    if (!confirm(zh ? "确认删除此入金记录？" : "Delete this deposit record?")) return;
                                    try { await deleteDepositRecord(d.id); setDepositHistory(await getDepositHistory(s.broker)); setAcctSettings(await getAccountSettings()); onRefresh(); } catch { setMsg("❌ Error"); }
                                  }} className="text-red-400 hover:text-red-600 ml-1">✕</button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Merge panel — shown when user tries to delete an account with data */}
              {mergeSource && (
                <div className="mb-3 p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 space-y-2">
                  <div className="text-xs font-medium text-orange-800 dark:text-orange-200">
                    🔀 {zh ? `合并「${mergeSource}」到：` : `Merge "${mergeSource}" into:`}
                  </div>
                  <div className="flex gap-2">
                    <select className={`${inputCls} flex-1`} value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)}>
                      <option value="">{zh ? "— 选择目标账户 —" : "— Select target —"}</option>
                      {knownAccounts.filter((n) => n !== mergeSource).map((n) => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                    <button onClick={handleMerge} disabled={!mergeTarget}
                      className="px-3 py-1 text-xs bg-orange-600 text-white rounded hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed">
                      {zh ? "合并" : "Merge"}
                    </button>
                    <button onClick={() => setMergeSource(null)}
                      className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700">
                      {zh ? "取消" : "Cancel"}
                    </button>
                  </div>
                  <p className="text-[10px] text-orange-600 dark:text-orange-400">
                    {zh
                      ? "合并后，所有持仓、平仓记录、入金记录和现金余额将转移到目标账户。"
                      : "All positions, closed trades, deposits and cash will be moved to the target account."}
                  </p>
                </div>
              )}

              {/* Add/Edit form */}
              <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 space-y-2">
                {!isNewAcct ? (
                  /* ── Select existing account ── */
                  <div className="flex gap-2">
                    <select className={`${inputCls} flex-1`} value={acctBroker} onChange={(e) => {
                      const name = e.target.value;
                      setAcctBroker(name);
                      const existing = acctSettings.find((s) => s.broker === name);
                      if (existing) {
                        setAcctMode(existing.capital_mode as "cost" | "deposit");
                        setAcctDeposit(existing.deposit_cny > 0 ? String(existing.deposit_cny) : "");
                        setAcctFx(String(existing.deposit_fx));
                      } else {
                        setAcctMode("cost"); setAcctDeposit(""); setAcctFx("1.0");
                      }
                      setDepositAction("update");
                    }}>
                      <option value="">{zh ? "— 选择账户 —" : "— Select account —"}</option>
                      {knownAccounts.map((n) => {
                        const s = acctSettings.find((st) => st.broker === n);
                        const tag = s ? (s.capital_mode === "deposit" ? " [入金]" : " [成本]") : "";
                        return <option key={n} value={n}>{n}{tag}</option>;
                      })}
                    </select>
                    <button onClick={() => { setIsNewAcct(true); setAcctBroker(""); setAcctMode("cost"); setAcctDeposit(""); setAcctFx("1.0"); }}
                      className="px-2 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-700 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 whitespace-nowrap">
                      {zh ? "➕ 新增" : "➕ New"}
                    </button>
                  </div>
                ) : (
                  /* ── New account name input ── */
                  <div className="flex gap-2">
                    <input className={`${inputCls} flex-1`} placeholder={zh ? "输入账户名称" : "Enter account name"} autoFocus
                      value={newAcctName} onChange={(e) => setNewAcctName(e.target.value)} />
                    <select className={inputCls} style={{ width: 90 }} value={acctMode}
                      onChange={(e) => setAcctMode(e.target.value as "cost" | "deposit")}>
                      <option value="cost">{zh ? "成本" : "Cost"}</option>
                      <option value="deposit">{zh ? "入金" : "Deposit"}</option>
                    </select>
                    <button onClick={() => { setIsNewAcct(false); setNewAcctName(""); }}
                      className="px-2 py-1.5 text-xs text-gray-400 hover:text-gray-600">✕</button>
                  </div>
                )}

                {/* Mode badge for selected existing account */}
                {!isNewAcct && acctBroker && existingMode && (
                  <div className="text-[10px] text-gray-500 flex items-center gap-1.5">
                    <span className={`px-1.5 py-0.5 rounded font-semibold ${existingMode === "deposit" ? "bg-amber-100 text-amber-700" : "bg-gray-200 text-gray-600"}`}>
                      {existingMode === "deposit" ? (zh ? "入金模式" : "Deposit mode") : (zh ? "成本模式" : "Cost mode")}
                    </span>
                    {existingMode === "cost" && <span className="text-gray-400">{zh ? "此模式不需要配置入金参数" : "No deposit config needed"}</span>}
                  </div>
                )}

                {/* Mode selector for existing account without settings yet */}
                {!isNewAcct && acctBroker && !existingMode && (
                  <div className="flex gap-2 items-center">
                    <span className="text-[10px] text-gray-400 whitespace-nowrap">{zh ? "模式" : "Mode"}</span>
                    <select className={inputCls} style={{ width: 100 }} value={acctMode}
                      onChange={(e) => setAcctMode(e.target.value as "cost" | "deposit")}>
                      <option value="cost">{zh ? "成本" : "Cost"}</option>
                      <option value="deposit">{zh ? "入金" : "Deposit"}</option>
                    </select>
                  </div>
                )}
                {acctMode === "deposit" && (
                  <div className="space-y-2">
                    {/* Update vs Add toggle */}
                    <div className="flex rounded overflow-hidden border border-gray-300 dark:border-gray-700">
                      <button onClick={() => setDepositAction("update")}
                        className={`flex-1 text-[10px] py-1 font-medium transition-colors ${depositAction === "update" ? "bg-blue-600 text-white" : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-100"}`}>
                        {zh ? "直接更新总额" : "Update Total"}
                      </button>
                      <button onClick={() => setDepositAction("add")}
                        className={`flex-1 text-[10px] py-1 font-medium transition-colors ${depositAction === "add" ? "bg-blue-600 text-white" : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-100"}`}>
                        {zh ? "追加入金记录" : "Add Deposit"}
                      </button>
                    </div>
                    <div className="text-[10px] text-gray-400 leading-relaxed bg-white dark:bg-gray-950 rounded px-2 py-1 border border-gray-200 dark:border-gray-800">
                      {depositAction === "update"
                        ? (zh ? "直接覆盖该账户的入金总额和平均汇率。" : "Directly overwrite total deposit and avg FX rate.")
                        : (zh ? "新增一笔入金记录，系统自动汇总计算入金总额和加权平均汇率。" : "Add a new deposit entry. The system auto-calculates the total and weighted avg FX rate.")}
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">
                        {depositAction === "add"
                          ? (zh ? "本次入金金额 (人民币)" : "This Deposit Amount (CNY)")
                          : (zh ? "入金总额 (人民币)" : "Total Deposit (CNY)")}
                      </div>
                      <input className={inputCls} placeholder={zh ? "例如：1029203" : "e.g. 1029203"} inputMode="decimal"
                        value={acctDeposit} onChange={(e) => setAcctDeposit(e.target.value)} />
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-400 mb-0.5">
                        {depositAction === "add"
                          ? (zh ? "本次购汇汇率 (1=人民币账户)" : "This FX Rate (1 = CNY account)")
                          : (zh ? "平均购汇汇率 (1=人民币账户)" : "Avg FX Rate (1 = CNY account)")}
                      </div>
                      <input className={inputCls} placeholder={zh ? "例如：6.915" : "e.g. 6.915"} inputMode="decimal"
                        value={acctFx} onChange={(e) => setAcctFx(e.target.value)} />
                    </div>
                    {depositAction === "add" && (
                      <>
                        <div>
                          <div className="text-[10px] text-gray-400 mb-0.5">{zh ? "入金日期（可选）" : "Date (optional)"}</div>
                          <input className={inputCls} type="date" value={depositDate} onChange={(e) => setDepositDate(e.target.value)} />
                        </div>
                        <div>
                          <div className="text-[10px] text-gray-400 mb-0.5">{zh ? "备注（可选）" : "Notes (optional)"}</div>
                          <input className={inputCls} placeholder={zh ? "例如：第二笔入金" : "e.g. 2nd deposit"} value={depositNotes} onChange={(e) => setDepositNotes(e.target.value)} />
                        </div>
                      </>
                    )}
                  </div>
                )}
                <button onClick={handleAcctSave} disabled={saving || (isNewAcct ? !newAcctName.trim() : !acctBroker)}
                  className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                  {saving ? "..." : depositAction === "add" && acctMode === "deposit" ? (zh ? "追加入金" : "Add Deposit") : (zh ? "保存" : "Save")}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Earnings Calendar (month grid)
// ══════════════════════════════════════════

/** Extract short display name: "Xiaomi Corporation" → "Xiaomi", "安踏体育用品有限公司" → "安踏体育" */
function shortName(name: string, ticker: string): string {
  if (!name || name === ticker) return ticker;
  // Chinese names: keep first 2-4 chars (before 集团/公司/有限/控股/股份 etc.)
  const zhCut = name.match(/^([\u4e00-\u9fff]{2,4})/);
  if (zhCut) return zhCut[1];
  // English: take first word (skip generic prefixes), limit length
  const word = name.replace(/^(The|the)\s+/, "").split(/[\s,.(]+/)[0];
  return word.length > 10 ? word.slice(0, 9) : word;
}

function EarningsCalendar({ earnings, zh }: { earnings: PortfolioEarningsEvent[]; zh: boolean }) {
  const eventsByDate = useMemo(() => {
    const map: Record<string, PortfolioEarningsEvent[]> = {};
    for (const e of earnings) {
      const d = e.date?.slice(0, 10);
      if (!d) continue;
      if (!map[d]) map[d] = [];
      map[d].push(e);
    }
    return map;
  }, [earnings]);

  const months = useMemo(() => {
    const dates = earnings.map((e) => e.date?.slice(0, 7)).filter(Boolean);
    const unique = [...new Set(dates)].sort();
    if (unique.length === 0) {
      const now = new Date();
      return [`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`];
    }
    return unique;
  }, [earnings]);

  const [activeMonth, setActiveMonth] = useState(() => {
    const upcomingMonth = earnings.find((e) => e.status === "upcoming")?.date?.slice(0, 7);
    return upcomingMonth && months.includes(upcomingMonth) ? upcomingMonth : months[0];
  });

  const monthIdx = months.indexOf(activeMonth);
  const canPrev = monthIdx > 0;
  const canNext = monthIdx < months.length - 1;

  const calendarDays = useMemo(() => {
    const [y, m] = activeMonth.split("-").map(Number);
    const firstDay = new Date(y, m - 1, 1);
    const startDow = (firstDay.getDay() + 6) % 7; // Monday=0
    const daysInMonth = new Date(y, m, 0).getDate();
    const cells: { day: number; dateStr: string; events: PortfolioEarningsEvent[] }[] = [];
    for (let i = 0; i < startDow; i++) cells.push({ day: 0, dateStr: "", events: [] });
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${activeMonth}-${String(d).padStart(2, "0")}`;
      cells.push({ day: d, dateStr, events: eventsByDate[dateStr] || [] });
    }
    // Pad to fill last row
    while (cells.length % 7 !== 0) cells.push({ day: 0, dateStr: "", events: [] });
    return cells;
  }, [activeMonth, eventsByDate]);

  const today = new Date().toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 10);
  const dayHeaders = zh
    ? ["一", "二", "三", "四", "五", "六", "日"]
    : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

  const formatMonth = (ym: string) => {
    const [y, m] = ym.split("-").map(Number);
    if (zh) return `${y}年${m}月`;
    const names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    return `${names[m - 1]} ${y}`;
  };

  // Color palette for earnings tags — cycle through
  const tagColors = [
    "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300",
    "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300",
    "bg-violet-100 dark:bg-violet-900/40 text-violet-700 dark:text-violet-300",
    "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300",
    "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300",
    "bg-cyan-100 dark:bg-cyan-900/40 text-cyan-700 dark:text-cyan-300",
  ];
  // Assign stable colors by ticker
  const tickerColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    const tickers = [...new Set(earnings.map((e) => e.ticker))];
    tickers.forEach((t, i) => { map[t] = tagColors[i % tagColors.length]; });
    return map;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [earnings]);

  const daysUntil = (dateStr: string) => {
    const diff = new Date(dateStr).getTime() - Date.now();
    const days = Math.ceil(diff / 86400000);
    if (days < 0) return "";
    if (days === 0) return zh ? "今天" : "Today";
    return zh ? `${days}天后` : `in ${days}d`;
  };

  return (
    <div>
      {/* Month navigation */}
      <div className="flex items-center justify-center gap-6 mb-4">
        <button onClick={() => canPrev && setActiveMonth(months[monthIdx - 1])}
          disabled={!canPrev}
          className="w-7 h-7 rounded-full flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-20 disabled:hover:bg-transparent transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <span className="text-[15px] font-semibold text-gray-800 dark:text-gray-200 min-w-[150px] text-center">
          {formatMonth(activeMonth)}
        </span>
        <button onClick={() => canNext && setActiveMonth(months[monthIdx + 1])}
          disabled={!canNext}
          className="w-7 h-7 rounded-full flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-20 disabled:hover:bg-transparent transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 6 15 12 9 18"/></svg>
        </button>
      </div>

      {/* Day headers */}
      <div className="grid grid-cols-7 bg-gray-100 dark:bg-gray-800 rounded-t-lg">
        {dayHeaders.map((d, i) => (
          <div key={d} className={`text-center text-xs font-semibold py-2 ${
            i >= 5 ? "text-gray-400 dark:text-gray-500" : "text-gray-600 dark:text-gray-300"
          }`}>{d}</div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 rounded-b-lg border border-gray-100 dark:border-gray-800 border-t-0 divide-x divide-gray-100 dark:divide-gray-800">
        {calendarDays.map((cell, i) => {
          const isToday = cell.dateStr === today;
          const isWeekend = i % 7 >= 5;
          const isFirstRow = i < 7;
          return (
            <div key={i} className={`min-h-[72px] p-1.5 ${
              !isFirstRow ? "border-t border-gray-100 dark:border-gray-800" : ""
            } ${
              cell.day === 0
                ? ""
                : isToday
                  ? "bg-blue-50/60 dark:bg-blue-950/20"
                  : ""
            }`}>
              {cell.day > 0 && (
                <>
                  {isToday ? (
                    <span className="inline-flex w-5.5 h-5.5 rounded-full bg-blue-600 text-white text-[11px] font-bold items-center justify-center mb-1">
                      {cell.day}
                    </span>
                  ) : (
                    <span className={`block text-xs mb-1 ${isWeekend ? "text-gray-300 dark:text-gray-600" : "text-gray-400 dark:text-gray-500"}`}>
                      {cell.day}
                    </span>
                  )}
                  <div className="space-y-0.5">
                    {cell.events.map((ev, j) => (
                      <div key={j}
                        className={`text-[11px] leading-snug px-1.5 py-[3px] rounded-md truncate font-medium cursor-default ${
                          ev.status === "upcoming"
                            ? tickerColorMap[ev.ticker]
                            : "bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 line-through"
                        }`}
                        title={`${ev.ticker} — ${ev.name}${ev.eps_actual != null ? ` | EPS: ${ev.eps_actual}` : ev.eps_estimated != null ? ` | Est: ${ev.eps_estimated}` : ""}`}>
                        {shortName(ev.name, ev.ticker)}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Upcoming detail list */}
      {earnings.some((e) => e.status === "upcoming") && (
        <div className="mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
          <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">{zh ? "即将发布" : "Upcoming Earnings"}</p>
          <div className="space-y-1.5">
            {earnings.filter((e) => e.status === "upcoming").map((e, i) => (
              <div key={i} className="flex items-center gap-3 text-[13px]">
                <span className="text-gray-400 w-14 shrink-0">{e.date?.slice(5, 10)}</span>
                <span className={`px-1.5 py-0.5 rounded text-[11px] font-medium shrink-0 ${tickerColorMap[e.ticker]}`}>
                  {e.ticker}
                </span>
                <span className="font-medium text-gray-700 dark:text-gray-300 truncate flex-1">{e.name}</span>
                {e.eps_estimated != null && (
                  <span className="text-[11px] text-gray-400 shrink-0">Est EPS: {e.eps_estimated}</span>
                )}
                <span className="text-[11px] text-amber-500 shrink-0">{daysUntil(e.date)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ══════════════════════════════════════════
// Events Tab
// ══════════════════════════════════════════

function EventsSection({ locale, fmpApiKey }: { locale: string; fmpApiKey: string }) {
  const zh = locale === "zh";
  const [news, setNews] = useState<PortfolioNewsItem[]>([]);
  const [earnings, setEarnings] = useState<PortfolioEarningsEvent[]>([]);
  const [ratings, setRatings] = useState<PortfolioRatingChange[]>([]);
  const [loading, setLoading] = useState(true);
  const [tickerFilter, setTickerFilter] = useState("");
  const [subTab, setSubTab] = useState<"news" | "earnings" | "ratings">("news");

  useEffect(() => {
    setLoading(true);
    Promise.all([getPortfolioNews(fmpApiKey), getPortfolioEarnings(fmpApiKey), getPortfolioRatings(fmpApiKey)])
      .then(([n, e, r]) => { setNews(n); setEarnings(e); setRatings(r); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [fmpApiKey]);

  const filterMatch = (ticker: string) =>
    !tickerFilter || ticker.toLowerCase().includes(tickerFilter.toLowerCase());

  const filteredNews = news.filter((n) => filterMatch(n.ticker));
  const filteredEarnings = earnings.filter((e) => filterMatch(e.ticker));
  const filteredRatings = ratings.filter((r) => filterMatch(r.ticker));

  const dirColor = (d: string) =>
    d === "upgrade" ? "text-green-600 dark:text-green-400"
    : d === "downgrade" ? "text-red-600 dark:text-red-400"
    : "text-gray-400";
  const dirIcon = (d: string) => d === "upgrade" ? "↑" : d === "downgrade" ? "↓" : "→";

  const timeAgo = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return zh ? "刚刚" : "just now";
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    return `${days}d`;
  };

  const daysUntil = (dateStr: string) => {
    const diff = new Date(dateStr).getTime() - Date.now();
    const days = Math.ceil(diff / 86400000);
    if (days < 0) return "";
    if (days === 0) return zh ? "今天" : "Today";
    return zh ? `${days} 天后` : `in ${days}d`;
  };

  const subTabs = [
    { key: "news" as const, label: zh ? "新闻" : "News", count: filteredNews.length },
    { key: "earnings" as const, label: zh ? "财报日历" : "Earnings", count: filteredEarnings.length },
    { key: "ratings" as const, label: zh ? "评级变动" : "Ratings", count: filteredRatings.length },
  ];

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800">
      {/* Header: sub-tabs + filter */}
      <div className="flex items-center justify-between px-4 pt-3 pb-0">
        <div className="flex gap-0">
          {subTabs.map((tab) => (
            <button key={tab.key}
              onClick={() => setSubTab(tab.key)}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                subTab === tab.key
                  ? "border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              }`}>
              {tab.label}
              {!loading && <span className="ml-1 text-[10px] opacity-60">({tab.count})</span>}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder={zh ? "按代码过滤..." : "Filter ticker..."}
          className="text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-700 bg-transparent text-gray-600 dark:text-gray-400 w-28"
          value={tickerFilter}
          onChange={(e) => setTickerFilter(e.target.value)}
        />
      </div>

      <div className="border-t border-gray-100 dark:border-gray-800" />

      {/* Content */}
      <div className="p-4">
        {loading ? (
          <div className="space-y-3 animate-pulse">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-4 bg-gray-200 dark:bg-gray-700 rounded" style={{ width: `${85 - i * 8}%` }} />
            ))}
          </div>
        ) : !fmpApiKey && news.length === 0 && earnings.length === 0 && ratings.length === 0 ? (
          <div className="text-center py-10">
            <div className="text-3xl mb-3 opacity-60">🔑</div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {zh ? "需要 FMP API Key" : "FMP API Key Required"}
            </p>
            <p className="text-xs text-gray-400 max-w-sm mx-auto">
              {zh
                ? "新闻、财报日历和评级变动数据来自 Financial Modeling Prep (FMP)。请点击右上角 ⚙️ 设置图标配置 API Key。"
                : "News, earnings calendar, and rating changes are powered by Financial Modeling Prep (FMP). Click the ⚙️ icon in the top-right corner to configure your API key."}
            </p>
          </div>
        ) : (
          <>
            {/* News */}
            {subTab === "news" && (
              filteredNews.length === 0 ? (
                <p className="text-sm text-gray-400 py-4">{zh ? "暂无新闻" : "No news available"}</p>
              ) : (
                <div className="space-y-1 max-h-[480px] overflow-y-auto">
                  {filteredNews.map((item, i) => (
                    <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                      className="block p-2.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                      <div className="flex items-start gap-2">
                        <span className="inline-block px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 shrink-0 mt-0.5">
                          {item.ticker}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-800 dark:text-gray-200 line-clamp-2 leading-snug">{item.title}</p>
                          <p className="text-[10px] text-gray-400 mt-1">{item.source} · {timeAgo(item.date)}</p>
                        </div>
                      </div>
                    </a>
                  ))}
                </div>
              )
            )}

            {/* Earnings Calendar */}
            {subTab === "earnings" && (
              filteredEarnings.length === 0 ? (
                <p className="text-sm text-gray-400 py-4">{zh ? "暂无财报日程" : "No earnings data"}</p>
              ) : (
                <EarningsCalendar earnings={filteredEarnings} zh={zh} />
              )
            )}

            {/* Rating Changes */}
            {subTab === "ratings" && (
              filteredRatings.length === 0 ? (
                <p className="text-sm text-gray-400 py-4">{zh ? "暂无评级变动" : "No rating changes"}</p>
              ) : (
                <div className="space-y-1">
                  {filteredRatings.map((r, i) => (
                    <div key={i} className="flex items-center gap-3 text-sm py-1.5 border-b border-gray-50 dark:border-gray-800 last:border-0">
                      <span className="text-xs text-gray-400 w-20 shrink-0">{r.date.slice(0, 10)}</span>
                      <span className="font-medium text-gray-700 dark:text-gray-300 w-16 shrink-0">{r.ticker}</span>
                      <span className="text-gray-500 dark:text-gray-400 w-24 shrink-0 truncate">{r.company}</span>
                      <span className={`font-medium ${dirColor(r.direction)}`}>
                        {r.previous} {dirIcon(r.direction)} {r.new}
                      </span>
                    </div>
                  ))}
                </div>
              )
            )}
          </>
        )}
      </div>

      <div className="px-4 pb-2">
        <p className="text-[10px] text-gray-400 text-right">
          {zh ? "数据来源: FMP (美股/港股) · 东方财富 (A股)" : "Data: FMP (US/HK) · Eastmoney (A-shares)"}
        </p>
      </div>
    </div>
  );
}


// ══════════════════════════════════════════
// Main Page
// ══════════════════════════════════════════

export default function PortfolioPage() {
  const { t, locale } = useI18n();
  const { fmpApiKey } = useSettings();
  const { user, loading: authLoading } = useAuth();

  // On production, require login for portfolio
  const [isLocal, setIsLocal] = useState(false);
  useEffect(() => {
    const h = window.location.hostname;
    setIsLocal(h === "localhost" || h === "127.0.0.1");
  }, []);
  const needsLogin = !authLoading && !user && !isLocal;

  const [available, setAvailable] = useState<boolean | null>(null);
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelInitialTab, setPanelInitialTab] = useState<"edit" | "close" | "cash" | "settings">("edit");
  const [panelEditHolding, setPanelEditHolding] = useState<PortfolioHolding | null>(null);
  const [portfolios, setPortfolios] = useState<PortfolioInfo[]>([]);
  const activePortfolio = portfolios.find((p) => p.active)?.name || "";
  const [refreshKey, setRefreshKey] = useState(0);
  const [pageTab, setPageTab] = useState<"overview" | "holdings" | "performance" | "trades" | "events">("overview");

  const load = useCallback(async () => {
    try { setLoading(true); setError(null);
      const [status, pList] = await Promise.all([getPortfolioStatus(), listPortfolios()]);
      setAvailable(status.available);
      setPortfolios(pList);
      if (!status.available) { setLoading(false); return; }
      setData(await getPortfolioHoldings());
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Failed to load"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSwitchPortfolio = useCallback(async (name: string) => {
    if (name === activePortfolio) return;
    try {
      setLoading(true);
      await switchPortfolio(name);
      setPortfolios((prev) => prev.map((p) => ({ ...p, active: p.name === name })));
      setData(await getPortfolioHoldings());
      setRefreshKey((k) => k + 1);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Switch failed"); }
    finally { setLoading(false); }
  }, [activePortfolio]);

  // ── Derived async state: snapshots + closed trades (single fetch on data change) ──
  const [weeklyPnl, setWeeklyPnl] = useState<number | null>(null);
  const [weeklyLabel, setWeeklyLabel] = useState<string>("");
  const [weeklyByMkt, setWeeklyByMkt] = useState<{ market: string; pnl: number; pct?: number }[]>([]);
  const [allClosedTrades, setAllClosedTrades] = useState<ClosedTrade[]>([]);
  const [realizedPnl, setRealizedPnl] = useState<number | null>(null);
  const closedCount = allClosedTrades.length;

  useEffect(() => {
    if (!data) return;
    let cancelled = false;

    // Single consolidated fetch: snapshots(20) covers both weekly(14) and weeklyByMkt(20)
    const fetchDerived = async () => {
      const [snaps, trades] = await Promise.all([getSnapshots(20), getClosedTrades()]);
      if (cancelled) return;

      // ── Closed trades ──
      setAllClosedTrades(trades);
      setRealizedPnl(trades.reduce((s, t) => s + (t.realized_pnl_cny || 0), 0));

      // ── Compute last Friday in Beijing time ──
      const sorted = [...snaps].sort((a, b) => a.date.localeCompare(b.date));
      const now = new Date();
      const bjNow = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
      const dow = bjNow.getDay();
      const daysBack = dow === 0 ? 2 : dow === 6 ? 1 : dow + 2;
      const lastFri = new Date(bjNow.getTime() - daysBack * 86400000);
      const lastFriStr = lastFri.toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 10);
      const weekCandidates = sorted.filter((s) => s.date <= lastFriStr);

      // ── KPI Weekly P&L ──
      const currentNetAssets = data.summary.net_assets;
      const currentCapital = data.summary.capital;
      if (currentNetAssets != null && currentCapital != null && weekCandidates.length > 0) {
        const weekTarget = weekCandidates[weekCandidates.length - 1];
        if (weekTarget.net_assets != null && weekTarget.capital != null) {
          const currentPnl = currentNetAssets - currentCapital;
          const basePnl = weekTarget.net_assets - weekTarget.capital;
          setWeeklyPnl(currentPnl - basePnl);
          setWeeklyLabel(locale === "zh" ? "本周" : "This Week");
        }
      }

      // ── Weekly per-market P&L ──
      if (weekCandidates.length > 0) {
        const currentMp: Record<string, number> = {};
        for (const h of data.holdings) {
          currentMp[h.market] = (currentMp[h.market] || 0) + (h.pnl_cny ?? 0);
        }
        const parseMarketPnl = (s: Snapshot): Record<string, number> | null => {
          if (!s.market_pnl) return null;
          try { return JSON.parse(s.market_pnl); } catch { return null; }
        };
        let baseMp: Record<string, number> | null = null;
        for (let i = weekCandidates.length - 1; i >= 0; i--) {
          baseMp = parseMarketPnl(weekCandidates[i]);
          if (baseMp) break;
        }
        if (baseMp) {
          const allMkts = new Set([...Object.keys(currentMp), ...Object.keys(baseMp)]);
          const items: { market: string; pnl: number }[] = [];
          for (const m of sortMarkets([...allMkts])) {
            items.push({ market: m, pnl: (currentMp[m] || 0) - (baseMp[m] || 0) });
          }
          if (!cancelled) setWeeklyByMkt(items);
        }
      }
    };
    fetchDerived().catch(() => {});
    return () => { cancelled = true; };
  }, [data, locale]);

  // YTD per-market — unrealized P&L from holdings + realized P&L from closed trades
  const ytdByMkt = useMemo(() => {
    if (!data) return [];
    const map: Record<string, { pnl: number; cost: number }> = {};
    for (const h of data.holdings) {
      if (h.ytd_pnl_cny == null) continue;
      if (!map[h.market]) map[h.market] = { pnl: 0, cost: 0 };
      map[h.market].pnl += h.ytd_pnl_cny;
      map[h.market].cost += h.market_value_cny - h.ytd_pnl_cny;
    }
    // Add YTD realized P&L from closed trades (by market)
    const ytdRealized = data.ytd_realized_by_market;
    if (ytdRealized) {
      for (const [mkt, rpl] of Object.entries(ytdRealized)) {
        if (!map[mkt]) map[mkt] = { pnl: 0, cost: 0 };
        map[mkt].pnl += rpl;
      }
    }
    return sortMarkets(Object.keys(map)).map((m) => ({
      market: m, pnl: map[m].pnl, pct: map[m].cost !== 0 ? (map[m].pnl / map[m].cost) * 100 : 0,
    }));
  }, [data]);

  // Compute per-market daily breakdown
  const dayByMkt = useMemo(() => {
    if (!data) return [];
    const map: Record<string, { pnl: number; base: number }> = {};
    for (const h of data.holdings) {
      if (h.daily_pnl_cny == null) continue;
      if (!map[h.market]) map[h.market] = { pnl: 0, base: 0 };
      map[h.market].pnl += h.daily_pnl_cny;
      map[h.market].base += h.market_value_cny - h.daily_pnl_cny;
    }
    return sortMarkets(Object.keys(map)).map((m) => ({
      market: m, pnl: map[m].pnl, pct: map[m].base !== 0 ? (map[m].pnl / map[m].base) * 100 : 0,
    }));
  }, [data]);

  // Allocation data
  const allocByMkt = useMemo(() => {
    if (!data) return [];
    const map: Record<string, number> = {};
    for (const h of data.holdings) { map[h.market] = (map[h.market] || 0) + h.market_value_cny; }
    return sortMarkets(Object.keys(map)).map((m) => ({ label: mktLabel(m, locale), value: map[m], color: mktColor(m) }));
  }, [data, locale]);

  const allocByCur = useMemo(() => {
    if (!data) return [];
    const curColors: Record<string, string> = { CNY: "#3b82f6", USD: "#10b981", HKD: "#f59e0b", JPY: "#ef4444" };
    const map: Record<string, number> = {};
    for (const h of data.holdings) { map[h.currency] = (map[h.currency] || 0) + h.market_value_cny; }
    return Object.entries(map).sort((a, b) => b[1] - a[1]).map(([c, v]) => ({ label: c, value: v, color: curColors[c] || "#6b7280" }));
  }, [data]);

  const allocBySector = useMemo(() => {
    if (!data) return [];
    const sectorColors: Record<string, string> = {
      "Consumer Cyclical": "#3b82f6", "Consumer Defensive": "#6366f1", "Technology": "#10b981",
      "Financial Services": "#f59e0b", "Industrials": "#8b5cf6", "Basic Materials": "#ef4444",
      "Energy": "#f97316", "Communication Services": "#ec4899", "Healthcare": "#14b8a6",
      "Real Estate": "#a855f7", "Utilities": "#64748b",
    };
    const map: Record<string, number> = {};
    for (const h of data.holdings) {
      const s = h.sector || (locale === "zh" ? "未分类" : "Other");
      map[s] = (map[s] || 0) + h.market_value_cny;
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1]).map(([s, v], i) => ({
      label: s, value: v, color: sectorColors[s] || ["#6b7280", "#94a3b8", "#78716c", "#a1a1aa"][i % 4],
    }));
  }, [data, locale]);

  // Net Assets breakdown: Stock / ETF / Cash — percentages of net_assets, sum = 100%
  const netAssetsSub = useMemo(() => {
    if (!data) return "";
    const na = data.summary.net_assets;
    if (!na || na <= 0) return "";
    const stockVal = data.holdings.filter((h) => !["ETF", "基金"].includes(h.sector)).reduce((s, h) => s + h.market_value_cny, 0);
    const etfVal = data.holdings.filter((h) => ["ETF", "基金"].includes(h.sector)).reduce((s, h) => s + h.market_value_cny, 0);
    // Cash = net_assets - stock - etf (ensures sum = 100%)
    const cashVal = na - stockVal - etfVal;
    const parts: string[] = [];
    const pct = (v: number) => `${(v / na * 100).toFixed(0)}%`;
    if (stockVal > 0) parts.push(`Stock ${pct(stockVal)}`);
    if (etfVal > 0) parts.push(`ETF ${pct(etfVal)}`);
    parts.push(`Cash ${pct(cashVal)}`);
    return parts.join(" · ");
  }, [data]);

  if (needsLogin) {
    return (
      <>
        <Navbar />
        <main className="max-w-7xl mx-auto px-4 py-20 text-center">
          <div className="max-w-md mx-auto">
            <div className="text-5xl mb-4">🔒</div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
              {t.authLoginRequired}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              {t.authLoginRequiredDesc}
            </p>
            <Link
              href="/auth"
              className="inline-block px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
            >
              {t.authLogin}
            </Link>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <main className="max-w-[1400px] mx-auto px-4 py-4">
        {/* Header */}
        <div className="flex items-baseline gap-4 mb-1">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white m-0">Portfolio Tracker</h2>
          {portfolios.length > 1 && (
            <select value={activePortfolio}
              onChange={(e) => handleSwitchPortfolio(e.target.value)}
              className="text-[11px] px-2 py-0.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 cursor-pointer">
              {portfolios.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
          )}
          <span className="text-[11px] text-gray-400 italic">in CNY, unless otherwise noted</span>
          <span className="text-xs text-gray-400 font-mono">{new Date().toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 16)}</span>
          {data && data.fx && <FxBanner fx={data.fx} />}
          <div className="ml-auto flex gap-2">
            <button onClick={() => { setPanelEditHolding(null); setPanelOpen(true); }} className="px-3 py-1 text-xs border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">
              {locale === "zh" ? "管理" : "Manage"}
            </button>
            <button onClick={load} disabled={loading} className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {loading ? "..." : (locale === "zh" ? "刷新" : "Refresh")}
            </button>
          </div>
        </div>
        {/* Tab Navigation */}
        {data && data.holdings.length > 0 && (
          <div className="flex gap-0 border-b border-gray-200 dark:border-gray-700 mb-3">
            {([
              { key: "overview", zh: "概览", en: "Overview" },
              { key: "holdings", zh: "持仓", en: "Holdings" },
              { key: "performance", zh: "分析", en: "Analysis" },
              { key: "trades", zh: "日志", en: "Journals" },
              { key: "events", zh: "动态", en: "Events" },
            ] as const).map((tab) => (
              <button key={tab.key}
                onClick={() => setPageTab(tab.key)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  pageTab === tab.key
                    ? "border-blue-600 text-blue-600 dark:text-blue-400 dark:border-blue-400"
                    : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300"
                }`}>
                {locale === "zh" ? tab.zh : tab.en}
              </button>
            ))}
          </div>
        )}

        {loading && !data && (
          <div className="flex items-center justify-center h-64 text-gray-500">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mr-3" />{t.loading}
          </div>
        )}

        {!loading && available === false && (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">📂</div>
            <h2 className="text-xl font-semibold text-gray-700 dark:text-gray-300 mb-2">{locale === "zh" ? "未配置投资组合" : "Portfolio Not Configured"}</h2>
            <p className="text-gray-500 max-w-md mx-auto">{locale === "zh" ? "设置 PORTFOLIO_DB_PATH 环境变量以启用此功能。" : "Set PORTFOLIO_DB_PATH env var to enable."}</p>
          </div>
        )}

        {error && <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-xl p-4 mb-4">{error}</div>}

        {data && data.holdings.length === 0 && (
          <OnboardingCard locale={locale} onRefresh={load} onOpenPanel={(tab) => { setPanelInitialTab(tab || "edit"); setPanelOpen(true); }} />
        )}

        {data && data.holdings.length > 0 && (
          <>
            {/* Setup tips banner — shown after import until dismissed */}
            <SetupTipsBanner locale={locale} data={data} onOpenPanel={(tab) => { setPanelInitialTab(tab); setPanelOpen(true); }} />

            {/* ════════ OVERVIEW TAB ════════ */}
            {pageTab === "overview" && (
              <>
                {/* ── KPI Row 1: Asset Overview ── */}
                <div className="flex flex-wrap gap-2 mb-2">
                  <KpiCard label={locale === "zh" ? "资产总值" : "Total Assets"} value={`¥${formatNumber(data.summary.equity_cny + data.summary.cash_cny)}`}
                    sub={locale === "zh" ? "权益 + 现金" : "Equity + Cash"} />
                  <KpiCard label={locale === "zh" ? "资产净值" : "Net Assets"} value={`¥${formatNumber(data.summary.net_assets)}`}
                    sub={netAssetsSub} />
                  {data.summary.leverage_cny > 0 && (
                    <KpiCard label={locale === "zh" ? "杠杆" : "Leverage"} value={`¥${formatNumber(data.summary.leverage_cny)}`} subColor="text-red-500" />
                  )}
                  <KpiCard label={locale === "zh" ? "现金" : "Cash"} value={`¥${formatNumber(data.summary.cash_cny)}`} />
                  <KpiCard label={locale === "zh" ? "持仓数" : "Positions"} value={String(data.holdings.length)}
                    sub={`${new Set(data.holdings.map((h) => h.market)).size} ${locale === "zh" ? "个市场" : "markets"}`} />
                </div>

                {/* ── KPI Row 2: P&L Metrics ── */}
                <div className="flex flex-wrap gap-2 mb-2">
                  <KpiCard label={locale === "zh" ? "未实现盈亏" : "Unrealized P&L"} value={`¥${pnlSign(data.summary.total_pnl_cny)}`}
                    sub={pctStr(data.summary.total_pnl_pct)} subColor={pnlColor(data.summary.total_pnl_cny)} />
                  {realizedPnl != null && (
                    <KpiCard label={locale === "zh" ? "已实现盈亏" : "Realized P&L"} value={`¥${pnlSign(realizedPnl)}`}
                      sub={`${closedCount} trades`} subColor={pnlColor(realizedPnl)} />
                  )}
                  <KpiCard label={locale === "zh" ? "日盈亏" : "Daily P&L"} value={`¥${pnlSign(data.summary.daily_pnl_cny)}`}
                    subColor={pnlColor(data.summary.daily_pnl_cny)} />
                  {weeklyPnl != null && (
                    <KpiCard label={weeklyLabel || (locale === "zh" ? "本周" : "This Week")}
                      value={`¥${pnlSign(weeklyPnl)}`} subColor={pnlColor(weeklyPnl)} />
                  )}
                  <KpiCard label={locale === "zh" ? "年初至今" : "YTD Return"} value={`¥${pnlSign(data.summary.ytd_pnl_cny)}`}
                    subColor={pnlColor(data.summary.ytd_pnl_cny)} />
                </div>

                {/* ── Per-market P&L Strips ── */}
                {(() => {
                  const allMkts = sortMarkets([...new Set([...dayByMkt.map(x => x.market), ...ytdByMkt.map(x => x.market)])]);
                  const rows: { label: string; items: typeof dayByMkt }[] = [
                    { label: "Daily", items: dayByMkt },
                  ];
                  if (ytdByMkt.length > 0) rows.push({ label: "YTD", items: ytdByMkt });
                  return (
                    <div className="mb-4 overflow-x-auto">
                      <table className="text-xs font-mono">
                        <tbody>
                          {rows.map((row) => {
                            const map = Object.fromEntries(row.items.map((it) => [it.market, it]));
                            return (
                              <tr key={row.label}>
                                <td className="text-gray-400 opacity-60 whitespace-nowrap w-10 text-right pr-3 py-0.5">{row.label}</td>
                                {allMkts.map((m) => {
                                  const it = map[m];
                                  const pnl = it?.pnl ?? 0;
                                  const pct = it?.pct ?? 0;
                                  return (
                                    <td key={m} className={`whitespace-nowrap pr-4 py-0.5 ${pnl !== 0 ? pnlColor(pnl) : "text-gray-300 dark:text-gray-600"}`}>
                                      {mktLabel(m, locale)} {pnlSign(pnl)}
                                      <span className="opacity-70">({pnlSign(pct, 1)}%)</span>
                                    </td>
                                  );
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}

                {/* ── Asset Allocation ── */}
                <SectionTitle>{locale === "zh" ? "资产配置" : "Asset Allocation"}</SectionTitle>
                <div className="flex flex-wrap gap-6 mb-2">
                  <AllocationBar title={locale === "zh" ? "按市场" : "By Market"} items={allocByMkt} locale={locale} />
                  <AllocationBar title={locale === "zh" ? "按币种" : "By Currency"} items={allocByCur} locale={locale} />
                  {allocBySector.length > 1 && <AllocationBar title={locale === "zh" ? "按行业" : "By Sector"} items={allocBySector} locale={locale} />}
                </div>

                {/* ── Performance Chart (no risk) ── */}
                <PerformanceSection key={`perf-${refreshKey}`} locale={locale} hideRisk />

              </>
            )}

            {/* ════════ HOLDINGS TAB ════════ */}
            {pageTab === "holdings" && (
              <>
                <HoldingsTable holdings={data.holdings} summary={data.summary} locale={locale}
                  onEdit={(h) => { setPanelEditHolding(h); setPanelOpen(true); }} />
                <CashTable cash={data.cash} fx={data.fx} locale={locale} />
              </>
            )}

            {/* ════════ ANALYSIS TAB ════════ */}
            {pageTab === "performance" && (
              <>
                <PerformanceSection key={`risk-${refreshKey}`} locale={locale} hideChart />
                <ReturnAttribution holdings={data.holdings} closedTrades={allClosedTrades} locale={locale} />
              </>
            )}

            {/* ════════ JOURNALS TAB ════════ */}
            {pageTab === "trades" && (
              <>
                <PnlJournal key={`journal-${refreshKey}`} locale={locale} />
                <ClosedTradesSection key={`trades-${refreshKey}`} locale={locale} />
              </>
            )}

            {pageTab === "events" && (
              <EventsSection key={`events-${refreshKey}`} locale={locale} fmpApiKey={fmpApiKey} />
            )}

          </>
        )}

        {/* ── Data Management Panel (sidebar) — always available when data loaded ── */}
        {data && <DataPanel holdings={data.holdings} data={data} locale={locale} onRefresh={load} open={panelOpen} onClose={() => { setPanelOpen(false); setPanelEditHolding(null); }} editHolding={panelEditHolding} initialTab={panelInitialTab} />}
      </main>
    </>
  );
}
