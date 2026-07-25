"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import PortfolioPreview from "@/components/PortfolioPreview";
import { useSettings } from "@/lib/settings";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth-context";
import { formatNumber } from "@/lib/format";
import { trackEvent } from "@/lib/gtag";
import {
  getPortfolioStatus,
  getPortfolioHoldings,
  getClosedTrades,
  getSnapshots,
  getNavHistory,
  getBenchmarks,
  getFxImpact,
  type FxImpact,
  getIbkrRecon,
  applyIbkrRecon,
  ignoreIbkrRecon,
  clearIbkrReconIgnores,
  getDividends,
  type DividendLedger,
  type IbkrRecon,
  getRisk,
  type RiskData,
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
  getAllFlows,
  triggerSnapshot,
  searchStocks,
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
  downloadPortfolioExcel,
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

/** Shared fields for dated cash-flow entry (deposit/withdrawal). The date is
 *  mandatory because the TWR unit engine prices flows at that day's NAV. */
function FlowFields({ zh, inputCls, flowDirection, setFlowDirection, flowCurrency, setFlowCurrency,
  flowUpdateCash, setFlowUpdateCash, depositDate, setDepositDate, depositNotes, setDepositNotes,
  amountCny, fxRate }: {
  zh: boolean; inputCls: string;
  flowDirection: "in" | "out"; setFlowDirection: (d: "in" | "out") => void;
  flowCurrency: string; setFlowCurrency: (c: string) => void;
  flowUpdateCash: boolean; setFlowUpdateCash: (b: boolean) => void;
  depositDate: string; setDepositDate: (d: string) => void;
  depositNotes: string; setDepositNotes: (n: string) => void;
  amountCny?: string; fxRate?: string;
}) {
  // Original-currency preview: what the cash balance will actually move by
  const _amt = parseFloat(amountCny || "") || 0;
  const _fx = flowCurrency === "CNY" ? 1 : parseFloat(fxRate || "") || 0;
  const _orig = _fx > 0 ? _amt / _fx : 0;
  return (
    <>
      <div className="flex rounded overflow-hidden border border-gray-300 dark:border-gray-700">
        <button type="button" onClick={() => setFlowDirection("in")}
          className={`flex-1 text-[10px] py-1 font-medium transition-colors ${flowDirection === "in" ? "bg-green-600 text-white" : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-100"}`}>
          {zh ? "入金" : "Deposit"}
        </button>
        <button type="button" onClick={() => setFlowDirection("out")}
          className={`flex-1 text-[10px] py-1 font-medium transition-colors ${flowDirection === "out" ? "bg-red-600 text-white" : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-100"}`}>
          {zh ? "出金" : "Withdraw"}
        </button>
      </div>
      <div>
        <div className="text-[10px] text-gray-400 mb-0.5">
          {zh ? "日期（必填，用于净值折算）" : "Date (required for unit NAV)"}
        </div>
        <input className={inputCls} type="date" value={depositDate} onChange={(e) => setDepositDate(e.target.value)} />
      </div>
      <div className="flex gap-2 items-center">
        <span className="text-[10px] text-gray-400 whitespace-nowrap">{zh ? "现金币种" : "Cash currency"}</span>
        <select className={inputCls} style={{ width: 90 }} value={flowCurrency} onChange={(e) => setFlowCurrency(e.target.value)}>
          {["CNY", "USD", "HKD", "JPY"].map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer">
        <input type="checkbox" checked={flowUpdateCash} onChange={(e) => setFlowUpdateCash(e.target.checked)} />
        {zh ? "同步更新该账户现金余额（推荐）" : "Also update this account's cash balance (recommended)"}
      </label>
      {flowUpdateCash && _amt > 0 && flowCurrency !== "CNY" && _orig > 0 && (
        <div className="text-[10px] font-mono text-blue-600 dark:text-blue-400">
          {zh ? "将计入现金：" : "Cash will move by: "}
          {flowDirection === "in" ? "+" : "−"}{_orig.toLocaleString(undefined, { maximumFractionDigits: 2 })} {flowCurrency}
        </div>
      )}
      <div className="text-[10px] text-gray-400 leading-relaxed">
        {zh ? "注意：股息、利息到账不是入金——直接改现金余额即可，它们会体现为收益。" : "Note: dividends/interest are NOT deposits — just edit the cash balance; they count as returns."}
      </div>
      <div>
        <div className="text-[10px] text-gray-400 mb-0.5">{zh ? "备注（可选）" : "Notes (optional)"}</div>
        <input className={inputCls} placeholder={zh ? "例如：第二笔入金" : "e.g. 2nd deposit"} value={depositNotes} onChange={(e) => setDepositNotes(e.target.value)} />
      </div>
    </>
  );
}

/** Hero: the 3-second answer — one sentence + one clean YTD curve vs CSI 300.
 *  Details live in the Performance tab; clicking the hero jumps there. */
function HeroSummary({ locale, onGoPerformance, unitNav, unitNavEst, unitNavDate, ytdMwr }: {
  locale: string; onGoPerformance: () => void;
  unitNav?: number | null; unitNavEst?: number | null; unitNavDate?: string | null; ytdMwr?: number | null;
}) {
  const zh = locale === "zh";
  const [series, setSeries] = useState<{ date: string; val: number }[]>([]);
  const [benchData, setBenchData] = useState<Record<string, BenchmarkPoint[]>>({});
  const [benchName, setBenchName] = useState<string>(() =>
    (typeof window !== "undefined" && localStorage.getItem("vs_hero_bench")) || "CSI 300");
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [fxImpact, setFxImpact] = useState<FxImpact | null>(null);
  const heroSvgRef = React.useRef<SVGSVGElement>(null);

  useEffect(() => {
    const ytdStart = `${new Date().getFullYear()}-01-01`;
    getSnapshots(365).then((snaps) => {
      const pts = [...snaps]
        .sort((a, b) => a.date.localeCompare(b.date))
        .filter((s) => s.date >= ytdStart)
        .map((s) => ({
          date: s.date,
          // TWR unit NAV after T0; legacy NAV/Capital ratio before (seed
          // makes them continuous, same convention as PerformanceChart)
          val: s.unit_nav != null && s.unit_nav > 0 ? s.unit_nav
            : (s.capital && s.capital > 0 && s.net_assets != null ? s.net_assets / s.capital : NaN),
        }))
        .filter((p) => Number.isFinite(p.val));
      // Fold in the intraday estimate (same rule as PerformanceChart): the
      // YTD % and sparkline then track the live session, not yesterday's
      // close. Official unit NAV stays untouched in the rows below. The
      // divergence gate keeps weekends/holidays on the pure official series
      // (closed markets ⇒ estimate == official).
      if (unitNavEst && pts.length
          && Math.abs(unitNavEst - pts[pts.length - 1].val) >= 0.0001) {
        const today = new Intl.DateTimeFormat("sv-SE").format(new Date());
        const last = pts[pts.length - 1];
        if (today > last.date) pts.push({ date: today, val: unitNavEst });
        else if (today === last.date) last.val = unitNavEst;
      }
      setSeries(pts);
      if (pts.length >= 2) {
        getBenchmarks(pts[0].date).then(setBenchData).catch(() => {});
      }
    }).catch(() => {});
    getFxImpact().then((r) => { if (r && r.fx_pp != null) setFxImpact(r as FxImpact); }).catch(() => {});
  }, [unitNavEst]);

  if (series.length < 2) return null;

  const benchLabels: Record<string, string> = zh
    ? { "CSI 300": "沪深300", "S&P 500": "标普500", "Nasdaq 100": "纳指100", "Hang Seng": "恒生" }
    : { "CSI 300": "CSI 300", "S&P 500": "S&P 500", "Nasdaq 100": "NDX 100", "Hang Seng": "HSI" };
  // Rebase at the last index close ON OR BEFORE the portfolio's first
  // snapshot (the endpoint returns a 10-day lead-in for exactly this):
  // snapshots exist on Saturdays pricing Friday's close, so taking the
  // first close AFTER the start used to swallow a full session (~1pp).
  const benchRaw = benchData[benchName] || [];
  const benchLead = benchRaw.filter((p) => p.date <= series[0].date);
  const benchBase = benchLead.length ? benchLead[benchLead.length - 1].close : null;
  const bench = benchBase && benchBase > 0
    ? [{ date: series[0].date, val: benchBase },
       ...benchRaw.filter((p) => p.date > series[0].date).map((p) => ({ date: p.date, val: p.close }))]
    : [];

  const officialNav = unitNav ?? series[series.length - 1].val;
  const liveEst = unitNavEst != null && Math.abs(unitNavEst - officialNav) >= 0.0001 ? unitNavEst : null;

  const portRet = (series[series.length - 1].val / series[0].val - 1) * 100;
  const benchRet = bench.length >= 2 ? (bench[bench.length - 1].val / bench[0].val - 1) * 100 : null;
  // Same-window guard for the vs-benchmark line: the live portfolio can run
  // ahead of the benchmark's newest close (Monday evening: portfolio carries
  // today's A-share close + US pre-market while ^NDX hasn't opened). Compare
  // at the BENCHMARK's end date — truncate the portfolio side to the point
  // priced on/before it (snapshot dated D prices D-1's close; the live point,
  // priced "now", only qualifies when the benchmark itself reaches today).
  const _todayStr = new Intl.DateTimeFormat("sv-SE").format(new Date());
  const benchEndDate = bench.length >= 2 ? bench[bench.length - 1].date : null;
  const portEndVal = (() => {
    if (!benchEndDate) return series[series.length - 1].val;
    const c = new Date(benchEndDate + "T12:00:00Z");
    c.setUTCDate(c.getUTCDate() + 1);
    const cut = c.toISOString().slice(0, 10);
    for (let i = series.length - 1; i >= 0; i--) {
      const p = series[i];
      const isLivePt = liveEst != null && p.date === _todayStr;
      if (isLivePt ? benchEndDate >= _todayStr : p.date <= cut) return p.val;
    }
    return series[series.length - 1].val;
  })();
  const diff = benchRet != null ? (portEndVal / series[0].val - 1) * 100 - benchRet : null;
  const diffTruncated = portEndVal !== series[series.length - 1].val;

  // Indexed to 100 for the mini chart
  const norm = (pts: { val: number }[]) => pts.map((p) => (p.val / pts[0].val) * 100);
  const pv = norm(series);
  const bv = bench.length >= 2 ? norm(bench) : [];
  const all = [...pv, ...bv];
  const _lo = Math.min(...all), _hi = Math.max(...all);
  const _pad = (_hi - _lo) * 0.08 || 1;
  const yMin = _lo - _pad, yMax = _hi + _pad, yr = yMax - yMin;
  const W = 800, H = 220, PAD = 6;
  // Time-based x axis: both series positioned by DATE, not index — the two
  // calendars differ (snapshots skip Sun/Mon, indices have their own
  // holidays), index-scaling made the crosshair dots visibly misaligned
  const t0 = Date.parse(series[0].date);
  const t1 = Date.parse(series[series.length - 1].date) || t0 + 1;
  const Xd = (date: string) => PAD + ((Date.parse(date) - t0) / Math.max(t1 - t0, 1)) * (W - 2 * PAD);
  const Y = (v: number) => H - PAD - ((v - yMin) / yr) * (H - 2 * PAD);
  // Sparse series (short YTD window) render as smooth beziers instead of
  // jagged segments; crosshair anchors to data points so it's unaffected
  const smooth = series.length < 40;
  const segPath = (pts: { date: string }[], vals: number[]) => {
    if (!pts.length) return "";
    let d = `M${Xd(pts[0].date).toFixed(1)},${Y(vals[0]).toFixed(1)}`;
    for (let i = 1; i < pts.length; i++) {
      const x1 = Xd(pts[i].date), y1 = Y(vals[i]);
      if (smooth) {
        const mx = ((Xd(pts[i - 1].date) + x1) / 2).toFixed(1);
        d += ` C${mx},${Y(vals[i - 1]).toFixed(1)} ${mx},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
      } else {
        d += ` L${x1.toFixed(1)},${y1.toFixed(1)}`;
      }
    }
    return d;
  };
  const areaPath = `${segPath(series, pv)} L${Xd(series[series.length - 1].date).toFixed(1)},${H - PAD} L${Xd(series[0].date).toFixed(1)},${H - PAD} Z`;
  const hoverPt = hoverIdx != null && hoverIdx >= 0 && hoverIdx < series.length ? hoverIdx : null;
  // Nearest benchmark value on/before the hovered date (different trading calendars)
  const benchIdxFor = (date: string) => {
    let k = -1;
    for (let i = 0; i < bench.length; i++) { if (bench[i].date <= date) k = i; else break; }
    return k;
  };

  // The snapshot dated D prices D-1's close — surface that close date on the
  // official row ("07-18收") instead of a relative "prev close", which reads
  // wrong on weekends (Sunday's official NAV is Friday's close, not
  // yesterday's). Noon-UTC anchor sidesteps timezone/DST edge cases.
  const navCloseDate = (() => {
    if (!unitNavDate) return null;
    const d = new Date(unitNavDate + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() - 1);
    return d.toISOString().slice(5, 10);
  })();
  return (
    <div onClick={onGoPerformance}
      className="mb-4 p-4 rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 cursor-pointer hover:border-blue-300 dark:hover:border-blue-700 transition-colors">
      <div className="grid grid-cols-1 sm:grid-cols-[180px_1fr] gap-3 sm:gap-5">
      <div className="flex flex-col sm:justify-between gap-2 sm:gap-0">
        <div>
          <div className="text-[11px] text-gray-400">
            {zh ? `今年（净值 TWR，自 ${series[0].date.slice(5)}）` : `YTD (TWR, since ${series[0].date.slice(5)})`}
          </div>
          <div className={`text-2xl sm:text-3xl font-semibold leading-tight ${pnlColor(portRet)}`}>
            {portRet >= 0 ? "+" : ""}{portRet.toFixed(1)}%
            {liveEst != null && (
              <span
                className="ml-1.5 align-middle text-[10px] font-medium text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950/50 px-1.5 py-0.5 rounded-full"
                title={zh
                  ? "含实时估算（各市场最新可得行情），随刷新变动；官方净值以每日快照为准"
                  : "Includes the live estimate (latest available prices per market, moves with refresh); official unit NAV is the daily snapshot"}>
                {zh ? "实时" : "live"}
              </span>
            )}
          </div>
          {diff != null && (
            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5"
              title={zh
                ? `基准同窗口（自 ${series[0].date}${diffTruncated && benchEndDate ? `，截至 ${benchEndDate} 收盘——该基准尚无更新交易日，组合侧也截断到同一时点` : ""}）、已折算人民币口径——与行情软件的"年初至今/本币"数字不可比`
                : `Benchmark over the same window (since ${series[0].date}${diffTruncated && benchEndDate ? `, through ${benchEndDate}'s close — the portfolio side is truncated to match` : ""}), converted to CNY — not comparable to quote-app YTD figures`}>
              {zh
                ? `${diff >= 0 ? "跑赢" : "跑输"}${benchLabels[benchName]} ${Math.abs(diff).toFixed(1)}pp（同窗口·¥口径${diffTruncated && benchEndDate ? `·截至${benchEndDate.slice(5)}收` : ""}）`
                : `${diff >= 0 ? "beating" : "trailing"} ${benchLabels[benchName]} by ${Math.abs(diff).toFixed(1)}pp (same window${diffTruncated && benchEndDate ? ` to ${benchEndDate.slice(5)} close` : ""}, CNY)`}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 sm:block sm:space-y-1 sm:border-t sm:border-gray-100 sm:dark:border-gray-800 sm:pt-2 sm:mt-2">
          <div className="flex gap-1.5 sm:gap-0 sm:justify-between text-[11px] text-gray-500 dark:text-gray-400"
            title={unitNavDate ? (zh ? `官方净值，快照 ${unitNavDate}（定价前一交易日收盘）` : `Official NAV from the ${unitNavDate} snapshot (prices the prior session's close)`) : undefined}>
            <span>
              {zh ? "单位净值" : "Unit NAV"}
              {navCloseDate && <span className="text-gray-400 dark:text-gray-500">{zh ? ` · ${navCloseDate}收` : ` · ${navCloseDate} cl.`}</span>}
            </span>
            <span className="font-mono">{officialNav.toFixed(4)}</span>
          </div>
          {liveEst != null && (
            <div className="flex gap-1.5 sm:gap-0 sm:justify-between text-[11px] text-gray-500 dark:text-gray-400">
              <span>{zh ? "实时估算" : "Live est."}</span>
              <span className={`font-mono ${pnlColor(liveEst - officialNav)}`}>{liveEst.toFixed(4)}</span>
            </div>
          )}
          {ytdMwr != null && (
            <div className="flex gap-1.5 sm:gap-0 sm:justify-between text-[11px] text-gray-500 dark:text-gray-400">
              <span>{zh ? "资金加权" : "Money-wtd"}</span>
              <span className="font-mono">{ytdMwr >= 0 ? "+" : ""}{ytdMwr.toFixed(1)}%</span>
            </div>
          )}
          {fxImpact && (
            <div className="flex gap-1.5 sm:gap-0 sm:justify-between text-[11px] text-gray-500 dark:text-gray-400"
              title={zh
                ? `剔除汇率后本币收益约 ${fxImpact.local_pct >= 0 ? "+" : ""}${fxImpact.local_pct.toFixed(1)}%。按币种净敞口（资产−同币种融资）计算；2026-07 前历史无分币种负债记录、仅按持仓估算，外币融资期影响略被高估`
                : `Currency-hedged return ≈ ${fxImpact.local_pct >= 0 ? "+" : ""}${fxImpact.local_pct.toFixed(1)}%. Net exposure (assets − same-currency loans); pre-2026-07 history is equity-only and slightly overstates FX drag`}>
              <span>{zh ? "汇率影响" : "FX impact"}</span>
              <span className={`font-mono ${pnlColor(fxImpact.fx_pp)}`}>{fxImpact.fx_pp >= 0 ? "+" : ""}{fxImpact.fx_pp.toFixed(1)}pp</span>
            </div>
          )}
          <div className="hidden sm:block text-[10px] text-gray-400 pt-0.5">{zh ? "详情 →" : "details →"}</div>
        </div>
      </div>
      <div className="min-w-0">
      <div className="flex items-center justify-end gap-2 mb-1" onClick={(e) => e.stopPropagation()}>
        {Object.keys(benchLabels).map((name) => (
          <button key={name}
            onClick={() => { setBenchName(name); try { localStorage.setItem("vs_hero_bench", name); } catch {} }}
            className={`px-1.5 py-0.5 text-[10px] rounded-full border transition-colors ${benchName === name ? "bg-blue-600 text-white border-blue-600" : "bg-white dark:bg-gray-900 text-gray-400 border-gray-200 dark:border-gray-700 hover:border-blue-400"}`}>
            {benchLabels[name]}
          </button>
        ))}
      </div>
      <svg ref={heroSvgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-32 sm:h-36" preserveAspectRatio="none"
        onMouseMove={(e) => {
          const rect = heroSvgRef.current?.getBoundingClientRect();
          if (!rect) return;
          const frac = (e.clientX - rect.left) / rect.width;
          const targetT = t0 + frac * (t1 - t0);
          let best = 0, bestDist = Infinity;
          for (let i = 0; i < series.length; i++) {
            const d = Math.abs(Date.parse(series[i].date) - targetT);
            if (d < bestDist) { bestDist = d; best = i; }
          }
          setHoverIdx(best);
        }}
        onMouseLeave={() => setHoverIdx(null)}>
        <defs>
          <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#heroFill)" />
        {bv.length >= 2 && <path d={segPath(bench, bv)} fill="none" stroke="#9ca3af" strokeWidth="1.5" strokeDasharray="4 3" />}
        <path d={segPath(series, pv)} fill="none" stroke="#3b82f6" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {hoverPt != null && (() => {
          const x = Xd(series[hoverPt].date);
          const bIdx = benchIdxFor(series[hoverPt].date);
          return (
            <g>
              <line x1={x} y1={PAD} x2={x} y2={H - PAD} stroke="#9ca3af" strokeWidth="1" strokeDasharray="3 3" />
              <circle cx={x} cy={Y(pv[hoverPt])} r="3.5" fill="#3b82f6" />
              {bIdx >= 0 && <circle cx={Xd(bench[bIdx].date)} cy={Y(bv[bIdx])} r="3" fill="#9ca3af" />}
            </g>
          );
        })()}
      </svg>
      {hoverPt != null && (() => {
        const pRet = pv[hoverPt] - 100;
        const bIdx = benchIdxFor(series[hoverPt].date);
        const bRet = bIdx >= 0 ? bv[bIdx] - 100 : null;
        return (
          <div className="flex items-center gap-3 text-[11px] font-mono mt-1">
            <span className="text-gray-400">{series[hoverPt].date}</span>
            <span className={pnlColor(pRet)}>{zh ? "组合" : "Port"} {pRet >= 0 ? "+" : ""}{pRet.toFixed(1)}%</span>
            <span className="text-gray-500">{zh ? "净值" : "NAV"} {series[hoverPt].val.toFixed(4)}</span>
            {bRet != null && <span className="text-gray-400">{benchLabels[benchName]} {bRet >= 0 ? "+" : ""}{bRet.toFixed(1)}%</span>}
          </div>
        );
      })()}
      <div className="flex justify-between text-[10px] text-gray-400 font-mono mt-0.5">
        <span>{series[0].date}{zh && series[0].date.slice(5, 7) !== "01" ? "（记账起点）" : ""}</span>
        <span>{series[series.length - 1].date}</span>
      </div>
      </div>
      </div>
    </div>
  );
}

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

function HoldingsTable({ holdings, summary, locale, onEdit, onTrade, compact, onShowAll }: {
  holdings: PortfolioHolding[]; summary: PortfolioData["summary"]; locale: string;
  onEdit?: (h: PortfolioHolding) => void;
  onTrade?: (h: PortfolioHolding, dir: "buy" | "sell") => void;
  compact?: boolean;
  onShowAll?: () => void;
}) {
  const [sortKey, setSortKey] = useState<string>("market_value_cny");
  const [sortAsc, setSortAsc] = useState(false);
  const [search, setSearch] = useState("");
  const [filterMkt, setFilterMkt] = useState("All");
  const [filterBroker, setFilterBroker] = useState("All");
  const [filterSector, setFilterSector] = useState("All");
  const [filterIndustry, setFilterIndustry] = useState("All");
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
  // Industry is a filter dimension (Risk-Navigator style), not a column
  const industries = useMemo(() => {
    const s = Array.from(new Set(holdings.map((h) => h.industry).filter(Boolean)));
    return s.length > 0 ? ["All", ...s.sort()] : [];
  }, [holdings]);
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
    if (filterIndustry !== "All") list = list.filter((h) => h.industry === filterIndustry);
    return [...list].sort((a, b) => {
      const av = (a as unknown as Record<string, unknown>)[sortKey];
      const bv = (b as unknown as Record<string, unknown>)[sortKey];
      const na = typeof av === "number" ? av : 0;
      const nb = typeof bv === "number" ? bv : 0;
      return sortAsc ? na - nb : nb - na;
    });
  }, [holdings, search, filterMkt, filterBroker, filterSector, filterIndustry, sortKey, sortAsc]);

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
            {sectors.map((s) => <option key={s} value={s}>{s === "All" ? (locale === "zh" ? "全部板块" : "All Sectors") : s}</option>)}
          </select>
        )}
        {industries.length > 0 && (
          <select className={inputCls} value={filterIndustry} onChange={(e) => setFilterIndustry(e.target.value)}>
            {industries.map((s) => <option key={s} value={s}>{s === "All" ? (locale === "zh" ? "全部行业" : "All Industries") : s}</option>)}
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
            <thead className="sticky top-0 z-10">
              <tr className="border-b-2 border-gray-300 dark:border-gray-600 text-[11px] font-semibold text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 whitespace-nowrap">
                <th className="text-left px-2 py-2.5 sticky left-0 bg-gray-100 dark:bg-gray-800 z-20 min-w-[110px]">
                  {locale === "zh" ? "名称" : "Name"}
                </th>
                <th className="text-left px-2 py-2.5">{locale === "zh" ? "代码" : "Ticker"}</th>
                <th className="text-left px-2 py-2.5">{locale === "zh" ? "市场" : "Market"}</th>
                <th className="text-left px-2 py-2.5">{locale === "zh" ? "账户" : "Broker"}</th>
                <th className="text-left px-2 py-2.5">{locale === "zh" ? "币种" : "Currency"}</th>
                <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("quantity")}>
                  {locale === "zh" ? "持仓量" : "Qty"}<SI col="quantity" />
                </th>
                <th className="text-right px-2 py-2.5">{locale === "zh" ? "成本价" : "Cost"}</th>
                <th className="text-right px-2 py-2.5">{locale === "zh" ? "现价" : "Price"}</th>
                <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("market_value")}>
                  {locale === "zh" ? "市值" : "Market Value"}<SI col="market_value" />
                </th>
                <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("market_value_cny")}>
                  {locale === "zh" ? "市值(CNY)" : "MV(CNY)"}<SI col="market_value_cny" />
                </th>
                <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("weight")}>
                  {locale === "zh" ? "占比" : "Weight"}<SI col="weight" />
                </th>
                {showDaily && <>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("daily_pnl_cny")}>
                    {locale === "zh" ? "日盈亏" : "Daily P&L"}<SI col="daily_pnl_cny" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("daily_pnl_pct")}>
                    {locale === "zh" ? "日涨幅" : "Daily%"}<SI col="daily_pnl_pct" />
                  </th>
                </>}
                {showYtd && <>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("ytd_pnl_cny")}>
                    {locale === "zh" ? "年初至今" : "YTD P&L"}<SI col="ytd_pnl_cny" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("ytd_pnl_pct")}>
                    {locale === "zh" ? "YTD%" : "YTD%"}<SI col="ytd_pnl_pct" />
                  </th>
                </>}
                {showTotal && <>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("pnl_cny")}>
                    {locale === "zh" ? "未实现" : "Unrealised"}<SI col="pnl_cny" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none" onClick={() => toggleSort("pnl_pct")}>
                    {locale === "zh" ? "未实现%" : "Unrl.%"}<SI col="pnl_pct" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none"
                    title={locale === "zh" ? "该票在该账户的历史已实现盈亏（closed_trades）" : "Lifetime realized P&L for this ticker+broker"}
                    onClick={() => toggleSort("realized_cny")}>
                    {locale === "zh" ? "已实现" : "Realized"}<SI col="realized_cny" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none"
                    title={locale === "zh" ? "税后分红净额（分红台账，盈透 Flex 自动积累）" : "Net dividends (Flex-fed ledger)"}
                    onClick={() => toggleSort("dividends_cny")}>
                    {locale === "zh" ? "分红" : "Dividends"}<SI col="dividends_cny" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none"
                    title={locale === "zh" ? "累计收益 = 未实现 + 已实现 + 分红" : "Total return = unrealized + realized + dividends"}
                    onClick={() => toggleSort("total_return_cny")}>
                    {locale === "zh" ? "累计收益" : "Total Return"}<SI col="total_return_cny" />
                  </th>
                  <th className="text-right px-2 py-2.5 cursor-pointer select-none"
                    title={locale === "zh" ? "累计收益 ÷ 当前持仓成本" : "Total return ÷ current cost basis"}
                    onClick={() => toggleSort("total_return_pct")}>
                    {locale === "zh" ? "累计%" : "TR%"}<SI col="total_return_pct" />
                  </th>
                </>}
                {showDcf && <>
                  <th className="text-right px-2 py-2.5" title="DCF intrinsic value (ValuScope)">DCF</th>
                  <th className="text-right px-2 py-2.5" title="Margin of Safety = (DCF - Price) / DCF">{locale === "zh" ? "安全边际" : "MoS%"}</th>
                </>}
                {onEdit && <th className="px-2 py-2.5" />}
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
                    <td className={`text-right px-2 py-1.5 ${h.realized_cny ? pnlColor(h.realized_cny) : "text-gray-300 dark:text-gray-700"}`}>
                      {h.realized_cny ? pnlSign(h.realized_cny) : "—"}
                    </td>
                    <td className={`text-right px-2 py-1.5 ${h.dividends_cny ? pnlColor(h.dividends_cny) : "text-gray-300 dark:text-gray-700"}`}>
                      {h.dividends_cny ? pnlSign(h.dividends_cny) : "—"}
                    </td>
                    <td className={`text-right px-2 py-1.5 font-semibold ${pnlColor(h.total_return_cny ?? h.pnl_cny)}`}>
                      {pnlSign(h.total_return_cny ?? h.pnl_cny)}
                    </td>
                    <td className={`text-right px-2 py-1.5 ${pnlColor(h.total_return_pct ?? h.pnl_pct)}`}>
                      {pctStr(h.total_return_pct ?? h.pnl_pct)}
                    </td>
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
                  {onEdit && <td className="px-1 py-1.5 text-center whitespace-nowrap">
                    {onTrade && <button onClick={() => onTrade(h, "buy")} title={locale === "zh" ? "买入/加仓" : "Buy"} className="text-gray-400 hover:text-red-500 text-[10px] mr-1.5">买</button>}
                    {onTrade && <button onClick={() => onTrade(h, "sell")} title={locale === "zh" ? "卖出/减仓" : "Sell"} className="text-gray-400 hover:text-green-600 text-[10px] mr-1.5">卖</button>}
                    <button onClick={() => onEdit(h)} className="text-gray-400 hover:text-blue-500 text-[10px]">✎</button>
                  </td>}
                </tr>
              ))}
            </tbody>
            {filtered.length > 0 && !compact && (() => {
              const fMvCny = filtered.reduce((s, h) => s + h.market_value_cny, 0);
              const fCostCny = filtered.reduce((s, h) => s + (h.market_value_cny - (h.pnl_cny ?? 0)), 0);
              const fDailyPnl = filtered.reduce((s, h) => s + (h.daily_pnl_cny ?? 0), 0);
              const fYtdPnl = filtered.reduce((s, h) => s + (h.ytd_pnl_cny ?? 0), 0);
              const fTotalPnl = filtered.reduce((s, h) => s + (h.pnl_cny ?? 0), 0);
              const fRealized = filtered.reduce((s, h) => s + (h.realized_cny ?? 0), 0);
              const fDividends = filtered.reduce((s, h) => s + (h.dividends_cny ?? 0), 0);
              const fTotalReturn = filtered.reduce((s, h) => s + (h.total_return_cny ?? h.pnl_cny ?? 0), 0);
              const fTotalPct = fCostCny !== 0 ? (fTotalPnl / fCostCny) * 100 : 0;
              const fWt = filtered.reduce((s, h) => s + h.weight, 0);
              return (
                <tfoot className="sticky bottom-0 bg-white dark:bg-gray-900 z-10">
                  <tr className="border-t-2 border-gray-300 dark:border-gray-700 font-semibold text-xs">
                    <td className="px-2 py-2 sticky left-0 bg-white dark:bg-gray-900 z-20">{locale === "zh" ? "合计" : "Total"} ({filtered.length})</td>
                    <td /><td /><td /><td />
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
                      <td className={`text-right px-2 py-2 ${pnlColor(fRealized)}`}>{fRealized ? pnlSign(fRealized) : "—"}</td>
                      <td className={`text-right px-2 py-2 ${pnlColor(fDividends)}`}>{fDividends ? pnlSign(fDividends) : "—"}</td>
                      <td className={`text-right px-2 py-2 font-semibold ${pnlColor(fTotalReturn)}`}>{pnlSign(fTotalReturn)}</td>
                      <td className={`text-right px-2 py-2 ${pnlColor(fCostCny !== 0 ? (fTotalReturn / fCostCny) * 100 : 0)}`}>
                        {pctStr(fCostCny !== 0 ? (fTotalReturn / fCostCny) * 100 : null)}
                      </td>
                    </>}
                    {showDcf && <><td /><td /></>}
                    {onEdit && <td />}
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
// Risk: leverage stress test + withdrawal sustainability
// ══════════════════════════════════════════

const covColor = (c: number | null | undefined) =>
  c == null ? "" : c < 1.3 ? "text-red-600 dark:text-red-400"
    : c < 1.5 ? "text-amber-600 dark:text-amber-400" : "text-green-600 dark:text-green-400";
const covBg = (c: number | null | undefined) =>
  c == null ? "" : c < 1.3 ? "bg-red-50 dark:bg-red-900/30"
    : c < 1.5 ? "bg-amber-50 dark:bg-amber-900/20" : "";

function RiskAlertBanner({ risk, locale, onGoRisk }: {
  risk: Partial<RiskData> | null; locale: string; onGoRisk: () => void;
}) {
  const zh = locale === "zh";
  if (!risk || risk.worst_coverage == null || risk.worst_coverage >= 1.5) return null;
  const danger = risk.worst_coverage < 1.3;
  const worst = (risk.brokers || []).filter((b) => b.coverage != null)
    .sort((a, b) => (a.coverage as number) - (b.coverage as number))[0];
  return (
    <div className={`mb-3 rounded-lg border px-4 py-2 text-sm ${danger
      ? "border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20"
      : "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20"}`}>
      <button onClick={onGoRisk} className="w-full text-left flex items-center gap-2">
        <span>{danger ? "🚨" : "⚠️"}</span>
        <span className={`font-medium ${danger ? "text-red-800 dark:text-red-300" : "text-amber-800 dark:text-amber-300"}`}>
          {zh
            ? `保证金预警：「${worst?.broker}」维持担保比例 ${(risk.worst_coverage * 100).toFixed(0)}%${danger ? "，已逼近强平区间" : "，安全垫偏薄"}`
            : `Margin alert: "${worst?.broker}" coverage ${(risk.worst_coverage * 100).toFixed(0)}%${danger ? " — approaching liquidation zone" : " — cushion is thin"}`}
        </span>
        <span className="ml-auto text-xs underline">{zh ? "查看风险面板 →" : "View risk panel →"}</span>
      </button>
    </div>
  );
}

function RiskStressSection({ locale, risk }: { locale: string; risk: Partial<RiskData> | null }) {
  const zh = locale === "zh";
  if (!risk || risk.nav == null) {
    return <div className="text-center py-8 text-gray-500 text-sm">{zh ? "风险数据加载中..." : "Loading risk data..."}</div>;
  }
  const finBrokers = (risk.brokers || []).filter((b) => b.financing > 0);
  const fxCols = [-0.10, -0.05, 0.0, 0.05];
  const eqRows = [0.0, -0.10, -0.20, -0.30, -0.40];
  const cell = (e: number, f: number) => (risk.grid || []).find((g) => g.equity_shock === e && g.fx_shock === f);
  const note = zh
    ? [
      "* 维持担保比例 = (持仓市值 + 正现金) / 场内融资，与国内券商两融口径一致；盈透/富途实际维持保证金按品种逐仓计算，此处为组合级近似，阈值仅作参考（<150% 警示 / <130% 危险）。",
      "* 压力网格：股票冲击同时作用于所有市场；汇率冲击 = 所有外币兑人民币同向变动（日元融资与日股资产自然对冲已计入）。",
      "* 场外借款计入净资产与负债率，但不参与券商担保比例（不会被强平，但要还）。",
      "* 持仓按最新缓存价估值（EOD 级别近似）。",
    ].join("\n")
    : "* Coverage = (MV + positive cash) / in-broker financing. Brokers compute true maintenance margin per position — treat thresholds (<150% warn / <130% danger) as indicative.\n* Grid: equity shock hits all markets; FX shock moves all foreign currencies vs CNY together.\n* Off-exchange borrowing counts toward NAV/debt but not broker coverage.";
  return (
    <>
      <SectionTitle note={note}>{zh ? "杠杆与压力测试" : "Leverage & Stress Test"}</SectionTitle>
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-4">
        {[
          { label: zh ? "净资产" : "NAV", value: `¥${formatNumber(risk.nav, 0)}` },
          { label: zh ? "总负债" : "Total Debt", value: `¥${formatNumber(risk.debt || 0, 0)}`,
            sub: zh ? `场外 ${formatNumber(risk.off_exchange || 0, 0)} + 融资 ${formatNumber((risk.debt || 0) - (risk.off_exchange || 0), 0)}` : `off-exch + margin` },
          { label: zh ? "负债/净资产" : "Debt / NAV", value: risk.debt_to_nav != null ? `${(risk.debt_to_nav * 100).toFixed(1)}%` : "—" },
          { label: zh ? "总资产/净资产" : "Gross / NAV", value: risk.gross_to_nav != null ? `${risk.gross_to_nav.toFixed(2)}×` : "—",
            sub: zh ? "杠杆倍数" : "gross leverage" },
          { label: zh ? "最差担保比例" : "Worst Coverage", value: risk.worst_coverage != null ? `${(risk.worst_coverage * 100).toFixed(0)}%` : "—",
            color: covColor(risk.worst_coverage), sub: finBrokers.length ? finBrokers.sort((a, b) => (a.coverage ?? 99) - (b.coverage ?? 99))[0].broker : undefined },
          { label: zh ? "外币净敞口" : "FX Net Exposure",
            value: `${((risk.currency_exposure || []).filter((c) => c.ccy !== "CNY").reduce((s, c) => s + (c.pct_nav || 0), 0)).toFixed(0)}%`,
            sub: (risk.currency_exposure || []).filter((c) => c.ccy !== "CNY").map((c) => `${c.ccy} ${c.pct_nav}%`).join(" · ") },
        ].map((m) => (
          <div key={m.label} className="p-2 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
            <div className="text-[9px] text-gray-400 uppercase">{m.label}</div>
            <div className={`text-base font-mono font-semibold ${m.color || ""}`}>{m.value}</div>
            {m.sub && <div className="text-[10px] text-gray-400 font-mono truncate">{m.sub}</div>}
          </div>
        ))}
      </div>

      {/* Per-broker margin detail */}
      {finBrokers.length > 0 && (
        <div className="mb-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] text-gray-400 uppercase border-b border-gray-200 dark:border-gray-800">
                <th className="text-left py-1.5">{zh ? "融资账户" : "Account"}</th>
                <th className="text-right">{zh ? "持仓市值" : "MV"}</th>
                <th className="text-right">{zh ? "正现金" : "Cash+"}</th>
                <th className="text-right">{zh ? "融资" : "Financing"}</th>
                <th className="text-right">{zh ? "担保比例" : "Coverage"}</th>
                <th className="text-right">{zh ? "距150%" : "To 150%"}</th>
                <th className="text-right">{zh ? "距130%" : "To 130%"}</th>
              </tr>
            </thead>
            <tbody>
              {finBrokers.map((b) => (
                <tr key={b.broker} className="border-b border-gray-100 dark:border-gray-800/50 font-mono">
                  <td className="py-1.5 font-sans">{b.broker}</td>
                  <td className="text-right">¥{formatNumber(b.mv, 0)}</td>
                  <td className="text-right">¥{formatNumber(b.pos_cash, 0)}</td>
                  <td className="text-right">¥{formatNumber(b.financing, 0)}</td>
                  <td className={`text-right font-semibold ${covColor(b.coverage)}`}>{b.coverage != null ? `${(b.coverage * 100).toFixed(0)}%` : "—"}</td>
                  <td className="text-right">{b.drop_to_150 != null ? `${(b.drop_to_150 * 100).toFixed(0)}%` : "—"}</td>
                  <td className="text-right">{b.drop_to_130 != null ? `${(b.drop_to_130 * 100).toFixed(0)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Stress grid */}
      <div className="mb-6 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[10px] text-gray-400 uppercase border-b border-gray-200 dark:border-gray-800">
              <th className="text-left py-1.5">{zh ? "股票 \\ 汇率" : "Equity \\ FX"}</th>
              {fxCols.map((f) => (
                <th key={f} className="text-right">{zh ? "外币" : "FX"} {f > 0 ? "+" : ""}{(f * 100).toFixed(0)}%</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {eqRows.map((e) => (
              <tr key={e} className="border-b border-gray-100 dark:border-gray-800/50">
                <td className="py-1.5 font-mono">{zh ? "股票" : "Eq"} {e === 0 ? "0" : `${(e * 100).toFixed(0)}`}%</td>
                {fxCols.map((f) => {
                  const g = cell(e, f);
                  return (
                    <td key={f} className={`text-right font-mono px-1 py-1 align-top ${covBg(g?.worst_coverage)}`}>
                      {g ? (
                        <>
                          <div className={pnlColor(g.nav_pct || 0)}>{(g.nav_pct || 0) > 0 ? "+" : ""}{g.nav_pct}%</div>
                          {Object.entries(g.coverages || {}).map(([b, c]) => (
                            <div key={b} className={`text-[10px] ${covColor(c)}`}>
                              {b.replace(/U\d+$/, "")} {(c * 100).toFixed(0)}%
                            </div>
                          ))}
                        </>
                      ) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="text-[10px] text-gray-400 mt-1">
          {zh ? "单元格：净资产变动% + 各融资账户在该情景下的担保比例（黄底 = 有账户 <150%，红底 = 有账户 <130%）" : "Cell: NAV change % + each financing account's coverage under that scenario (amber bg = any account <150%, red = <130%)"}
        </div>
      </div>
    </>
  );
}

function SustainabilitySection({ locale }: { locale: string }) {
  const zh = locale === "zh";
  const T0 = "2026-07-04"; // flow discipline start — outflows recorded from here
  const [flows, setFlows] = useState<DepositRecord[]>([]);
  const [snaps, setSnaps] = useState<Snapshot[]>([]);
  const [navHist, setNavHist] = useState<NavHistoryPoint[]>([]);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    Promise.all([getAllFlows(500), getSnapshots(365), getNavHistory()])
      .then(([f, s, n]) => { setFlows(f); setSnaps(s); setNavHist(n); })
      .finally(() => setLoaded(true));
  }, []);

  // Monthly Capital deltas — under 方案A every consumption withdrawal cuts
  // Capital directly, so historical Capital declines mirror spending even
  // before T0's explicit flow records. Positive deltas = injections; only
  // negative ones estimate consumption.
  const capMonthly = useMemo(() => {
    const eom: Record<string, number> = {};
    const put = (date: string, cap: number | null | undefined) => {
      if (cap == null || cap <= 0) return;
      const m = date.slice(0, 7);
      eom[m] = cap; // rows arrive date-asc per source; last write wins as EOM
    };
    [...navHist].sort((a, b) => a.date.localeCompare(b.date))
      .forEach((n) => put(n.date, n.capital_invested));
    [...snaps].sort((a, b) => a.date.localeCompare(b.date))
      .forEach((s) => put(s.date, s.capital));
    const months = Object.keys(eom).sort();
    const deltas: { month: string; delta: number }[] = [];
    for (let i = 1; i < months.length; i++) {
      deltas.push({ month: months[i], delta: eom[months[i]] - eom[months[i - 1]] });
    }
    const recent = deltas.slice(-12);
    const draws = recent.filter((d) => d.delta < 0).map((d) => -d.delta);
    const avgDraw = draws.length ? draws.reduce((s, v) => s + v, 0) / draws.length : null;
    return { recent, avgDraw };
  }, [navHist, snaps]);

  // Observed consumption: recorded outflows since T0, grouped by month
  const outByMonth = useMemo(() => {
    const m: Record<string, number> = {};
    for (const f of flows) {
      const d = f.deposit_date || f.created_at?.slice(0, 10) || "";
      if (d >= T0 && f.amount_cny < 0) m[d.slice(0, 7)] = (m[d.slice(0, 7)] || 0) + (-f.amount_cny);
    }
    return m;
  }, [flows]);
  const observedMonthly = useMemo(() => {
    const total = Object.values(outByMonth).reduce((s, v) => s + v, 0);
    if (total <= 0) return null;
    const days = Math.max(15, (Date.now() - new Date(T0).getTime()) / 86400000);
    return total / (days / 30.44);
  }, [outByMonth]);

  // Realized TWR stats (same splice as risk metrics) as reference
  const realized = useMemo(() => {
    const pts = [...snaps].sort((a, b) => a.date.localeCompare(b.date))
      .filter((s) => s.net_assets != null && s.net_assets > 0
        && ((s.unit_nav != null && s.unit_nav > 0) || (s.capital != null && s.capital > 0)))
      .map((s) => ({
        date: s.date,
        val: s.unit_nav != null && s.unit_nav > 0 ? s.unit_nav : (s.net_assets as number) / (s.capital as number),
      }));
    if (pts.length < 10) return null;
    const rets = pts.slice(1).map((p, i) => p.val / pts[i].val - 1);
    const avg = rets.reduce((s, r) => s + r, 0) / rets.length;
    const varc = rets.reduce((s, r) => s + (r - avg) ** 2, 0) / (rets.length - 1);
    // Short windows are shown as-is (cumulative YTD) — annualizing months
    // of equity returns just extrapolates the streak, which is meaningless
    // for anything that isn't a yield. Only the multi-year span gets
    // annualized (CAGR). YTD baseline = last point of the previous year
    // when available (resets every Jan 1), else the year's first point.
    const curYear = pts[pts.length - 1].date.slice(0, 4);
    let baseIdx = 0;
    for (let i = 0; i < pts.length && pts[i].date.slice(0, 4) < curYear; i++) baseIdx = i;
    const cumRecent = (pts[pts.length - 1].val / pts[baseIdx].val - 1) * 100;
    const cumStart = pts[baseIdx].date;
    let longRun: number | null = null;
    const hist = [...navHist].sort((a, b) => a.date.localeCompare(b.date))
      .filter((n) => n.capital_invested > 0 && n.net_asset_value > 0);
    if (hist.length > 0) {
      const r0 = hist[0].net_asset_value / hist[0].capital_invested;
      const last = pts[pts.length - 1];
      const days = (new Date(last.date).getTime() - new Date(hist[0].date).getTime()) / 86400000;
      if (days > 365 && r0 > 0) {
        longRun = (Math.pow(last.val / r0, 365 / days) - 1) * 100;
      }
    }
    return {
      cumRecent, cumStart, vol: Math.sqrt(varc) * Math.sqrt(252) * 100,
      longRun, longRunStart: hist[0]?.date,
    };
  }, [snaps, navHist]);
  const nav = useMemo(() => {
    const s = [...snaps].sort((a, b) => a.date.localeCompare(b.date));
    for (let i = s.length - 1; i >= 0; i--) if (s[i].net_assets) return s[i].net_assets as number;
    return null;
  }, [snaps]);

  // Assumptions (all hand-editable — this is a what-if calculator).
  // Spend splits in two: base living costs (grow with inflation, forever)
  // vs the mortgage payment — fixed nominal and gone after its term, so
  // inflating it or extending it past payoff would distort everything.
  const [navStr, setNavStr] = useState("");
  const [spendStr, setSpendStr] = useState("");   // base, ex-mortgage
  const [mortStr, setMortStr] = useState("9000");
  const [mortYearsStr, setMortYearsStr] = useState("9");
  const [retStr, setRetStr] = useState("8");
  const [volStr, setVolStr] = useState("25");
  const [inflStr, setInflStr] = useState("3");
  useEffect(() => {
    if (nav && !navStr) setNavStr(String(Math.round(nav)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nav]);
  const navVal = parseFloat(navStr) || 0;
  const spend = parseFloat(spendStr) || 0;        // base living costs
  const mort = parseFloat(mortStr) || 0;
  const mortMonths = Math.max(0, Math.round((parseFloat(mortYearsStr) || 0) * 12));
  useEffect(() => {
    if (!spendStr) {
      const est = observedMonthly || capMonthly.avgDraw;
      if (est) setSpendStr(String(Math.max(0, Math.round((est - mort) / 100) * 100)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [observedMonthly, capMonthly.avgDraw]);
  const ret = parseFloat(retStr) || 0;
  const vol = parseFloat(volStr) || 0;
  const infl = parseFloat(inflStr) || 0;
  const totalSpend = spend + mort;

  const mc = useMemo(() => {
    const nav = navVal;
    if (!nav || !(totalSpend > 0)) return null;
    const mu = ret / 100, sig = vol / 100, inf = infl / 100;
    const PATHS = 500, MONTHS = 480; // 40 years
    let surv30 = 0;
    const dep: number[] = [];
    const navAtPayoff: number[] = []; // per-path NAV when the mortgage ends
    // deterministic-ish seed not needed; Box-Muller on Math.random
    for (let p = 0; p < PATHS; p++) {
      let v = nav, sp = spend, dead = MONTHS + 1;
      for (let m = 1; m <= MONTHS; m++) {
        const u1 = Math.random() || 1e-9, u2 = Math.random();
        const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
        v = v * Math.exp((mu - sig * sig / 2) / 12 + sig * Math.sqrt(1 / 12) * z)
          - sp - (m <= mortMonths ? mort : 0);
        sp *= Math.pow(1 + inf, 1 / 12); // base inflates; mortgage stays fixed
        if (m === mortMonths) navAtPayoff.push(Math.max(0, v));
        if (v <= 0) { dead = m; break; }
      }
      if (dead > 360) surv30++;
      if (dead < mortMonths) navAtPayoff.push(0); // depleted before payoff
      dep.push(dead);
    }
    dep.sort((a, b) => a - b);
    navAtPayoff.sort((a, b) => a - b);
    const med = dep[Math.floor(PATHS / 2)];
    const p10 = dep[Math.floor(PATHS * 0.1)];
    return {
      surv30: (surv30 / PATHS) * 100,
      medYears: med > MONTHS ? null : med / 12,
      p10Years: p10 > MONTHS ? null : p10 / 12,
      medNavAtPayoff: mortMonths > 0 && navAtPayoff.length
        ? navAtPayoff[Math.floor(navAtPayoff.length / 2)] : null,
    };
  }, [navVal, spend, mort, mortMonths, ret, vol, infl]);

  const wdRate = navVal && totalSpend > 0 ? (totalSpend * 12) / navVal * 100 : null;
  // Post-mortgage rate at the payoff point: inflated base spend over the
  // simulated MEDIAN NAV at that time — dividing by today's NAV would
  // pretend nine years of withdrawals never happened
  const baseAtPayoff = spend * Math.pow(1 + infl / 100, mortMonths / 12);
  const wdRateAfter = mc?.medNavAtPayoff != null && mc.medNavAtPayoff > 0 && spend > 0
    ? (baseAtPayoff * 12) / mc.medNavAtPayoff * 100 : null;
  // Static runway honours the mortgage step-down (zero return, zero inflation)
  const staticRunway = (() => {
    if (!navVal || !(totalSpend > 0)) return null;
    let v = navVal, m = 0;
    while (v > 0 && m < 1200) {
      m += 1;
      v -= spend + (m <= mortMonths ? mort : 0);
    }
    return m >= 1200 ? null : m / 12;
  })();

  if (!loaded) return <div className="text-center py-8 text-gray-500 text-sm">{zh ? "加载中..." : "Loading..."}</div>;

  const note = zh
    ? [
      `* 支取率经验参考：≤4% 长期稳健（Trinity 研究），4–6% 需盯紧收益，>6% 在消耗本金。`,
      `* 月支出默认取 T0(${T0}) 起已记录出金的月均值——出金纪律执行越久越准；也可手动改。`,
      `* 蒙特卡洛：500 条路径 × 40 年，月度对数正态收益，支出随通胀增长。假设可调，结果是量级参考不是预言。`,
      realized ? `* 实测参考：${realized.longRun != null ? `长期年化 ${realized.longRun.toFixed(1)}%（净值自 ${realized.longRunStart || ""} 复合年化）；` : ""}今年以来累计 ${realized.cumRecent >= 0 ? "+" : ""}${realized.cumRecent.toFixed(1)}%（基准 ${realized.cumStart || ""}，每年1月1日重置）——短窗口刻意不年化：把几个月股票收益年化等于假设势头延续一年，只有利率型收入才能这么算。波动实测 ${realized.vol.toFixed(1)}%（日频）。长期假设建议以长期年化打折使用。` : "",
    ].filter(Boolean).join("\n")
    : "* ≤4% withdrawal = sustainable (Trinity study); >6% is eating principal.\n* Monthly spend defaults to recorded outflows since T0; editable.\n* Monte Carlo: 500 paths × 40y, lognormal monthly returns, inflation-growing spend.";

  return (
    <>
      <SectionTitle note={note}>{zh ? "支取可持续性" : "Withdrawal Sustainability"}</SectionTitle>
      <div className="text-[10px] text-gray-400 mb-2 leading-relaxed">
        {zh
          ? "这是一个 what-if 测算器：下面五个假设都可以手动改，改完结果实时重算。"
          : "A what-if calculator: all five assumptions below are editable; results recompute live."}
      </div>
      {/* Assumptions */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
        {[
          { label: zh ? "净资产 ¥" : "NAV ¥", v: navStr, set: setNavStr,
            sub: nav ? (zh ? `当前实际 ¥${formatNumber(nav, 0)}` : `actual ¥${formatNumber(nav, 0)}`) : undefined },
          { label: zh ? "基础月支出 ¥（不含房贷）" : "Base monthly spend ¥ (ex-mortgage)", v: spendStr, set: setSpendStr, spendFill: true,
            placeholder: zh ? "手动输入，如 10000" : "e.g. 10000",
            sub: zh ? "随通胀逐年增长；点下方按钮自动减房贷填入" : "grows with inflation; buttons auto-subtract mortgage" },
          { label: zh ? "房贷月供 ¥" : "Mortgage ¥/mo", v: mortStr, set: setMortStr,
            sub: zh ? "固定名义金额，不随通胀" : "fixed nominal, no inflation" },
          { label: zh ? "房贷剩余年限" : "Mortgage years left", v: mortYearsStr, set: setMortYearsStr,
            sub: zh ? `到期后月支出降为基础支出` : "spend steps down at payoff" },
          { label: zh ? "预期年化收益 %" : "Expected return %", v: retStr, set: setRetStr,
            sub: realized ? (zh
              ? `实测：${realized.longRun != null ? `长期年化 ${realized.longRun.toFixed(1)}%（自${realized.longRunStart?.slice(0, 7) || ""}）· ` : ""}今年以来累计 ${realized.cumRecent >= 0 ? "+" : ""}${realized.cumRecent.toFixed(1)}%（自${realized.cumStart?.slice(5) || ""}，未年化）`
              : `realized: ${realized.longRun != null ? `long-run CAGR ${realized.longRun.toFixed(1)}% · ` : ""}YTD +${realized.cumRecent.toFixed(1)}% since ${realized.cumStart} (not annualized)`) : undefined },
          { label: zh ? "年化波动 %" : "Volatility %", v: volStr, set: setVolStr,
            sub: realized ? (zh ? `实测 ${realized.vol.toFixed(1)}%` : `realized ${realized.vol.toFixed(1)}%`) : undefined },
          { label: zh ? "通胀 %" : "Inflation %", v: inflStr, set: setInflStr,
            sub: zh ? "支出逐年按此增长" : "spend grows at this rate" },
        ].map((f) => (
          <div key={f.label}>
            <div className="text-[10px] text-gray-500 mb-1">{f.label}</div>
            <input className="w-full px-2 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 font-mono"
              inputMode="decimal" value={f.v} placeholder={f.placeholder} onChange={(e) => f.set(e.target.value)} />
            {f.sub && <div className="text-[9px] text-gray-400 mt-0.5">{f.sub}</div>}
            {f.spendFill && (
              <div className="flex flex-wrap gap-1 mt-0.5">
                {observedMonthly && (
                  <button onClick={() => setSpendStr(String(Math.max(0, Math.round((observedMonthly - mort) / 100) * 100)))}
                    className="text-[9px] px-1 py-0.5 rounded border border-gray-300 dark:border-gray-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20">
                    {zh ? `出金实测 ¥${formatNumber(observedMonthly, 0)}` : `flows ¥${formatNumber(observedMonthly, 0)}`}
                  </button>
                )}
                {capMonthly.avgDraw && (
                  <button onClick={() => setSpendStr(String(Math.max(0, Math.round((capMonthly.avgDraw! - mort) / 100) * 100)))}
                    className="text-[9px] px-1 py-0.5 rounded border border-gray-300 dark:border-gray-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20">
                    {zh ? `Capital估算 ¥${formatNumber(capMonthly.avgDraw, 0)}` : `capital est. ¥${formatNumber(capMonthly.avgDraw, 0)}`}
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      {/* Results */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        {[
          (() => {
            // At payoff the "% rate" stops being readable once the pot is
            // nearly gone (100%+ = under a year of spend left) — switch to
            // "years of spend remaining", which is what it really means
            const medNav = mc?.medNavAtPayoff;
            const yearsLeft = medNav != null && medNav > 0 && baseAtPayoff > 0
              ? medNav / (baseAtPayoff * 12) : null;
            const afterTxt = medNav === 0 ? (zh ? "已耗尽" : "depleted")
              : yearsLeft != null && yearsLeft < 3
                ? (zh ? `仅剩≈${yearsLeft.toFixed(1)}年支出` : `≈${yearsLeft.toFixed(1)}y of spend left`)
                : wdRateAfter != null ? `${wdRateAfter.toFixed(1)}%` : "—";
            return {
              label: zh ? "年支取率（当前 → 房贷结清时）" : "Withdrawal Rate (now → at payoff)",
              value: wdRate != null ? `${wdRate.toFixed(1)}% → ${afterTxt}` : "—",
              color: wdRate == null ? "" : wdRate <= 4 ? "text-green-600 dark:text-green-400" : wdRate <= 6 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400",
              sub: medNav != null && medNav > 0
                ? (zh
                  ? `结清时中位净资产 ¥${formatNumber(medNav, 0)}${wdRateAfter != null ? `，支取率 ${wdRateAfter.toFixed(1)}%` : ""}，基础支出含通胀 ¥${formatNumber(baseAtPayoff, 0)}/月`
                  : `median NAV at payoff ¥${formatNumber(medNav, 0)}${wdRateAfter != null ? `, rate ${wdRateAfter.toFixed(1)}%` : ""}`)
                : (zh ? `含房贷 ¥${formatNumber(totalSpend, 0)}/月` : `incl. mortgage ¥${formatNumber(totalSpend, 0)}/mo`),
            };
          })(),
          { label: zh ? "静态跑道" : "Static Runway",
            value: staticRunway != null ? (zh ? `${staticRunway.toFixed(1)} 年` : `${staticRunway.toFixed(1)}y`) : "—",
            color: "",
            sub: zh ? "假设组合零收益还能花几年" : "years of spend at zero return" },
          { label: zh ? "30年存活率" : "Survives 30y",
            value: mc ? `${mc.surv30.toFixed(0)}%` : "—",
            color: !mc ? "" : mc.surv30 >= 90 ? "text-green-600 dark:text-green-400" : mc.surv30 >= 70 ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400",
            sub: zh ? "模拟中 30 年后没花光的概率" : "P(not depleted after 30y)" },
          { label: zh ? "耗尽年限（中位 / 悲观）" : "Depletion (median / p10)",
            value: mc ? `${mc.medYears ? mc.medYears.toFixed(0) + (zh ? "年" : "y") : (zh ? ">40年" : ">40y")} / ${mc.p10Years ? mc.p10Years.toFixed(0) + (zh ? "年" : "y") : (zh ? ">40年" : ">40y")}` : "—",
            color: "",
            sub: zh ? "一般情况 / 最差10%的情况" : "typical / worst-10% case" },
        ].map((m) => (
          <div key={m.label} className="p-2 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
            <div className="text-[9px] text-gray-400 uppercase">{m.label}</div>
            <div className={`text-base font-mono font-semibold ${m.color || ""}`}>{m.value}</div>
            {m.sub && <div className="text-[10px] text-gray-400">{m.sub}</div>}
          </div>
        ))}
      </div>
      {/* Plain-language explanations */}
      <div className="mb-4 p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-[11px] text-gray-600 dark:text-gray-400 leading-relaxed space-y-1">
        <div className="text-[10px] text-gray-400 uppercase mb-1">{zh ? "指标说明" : "How to read these"}</div>
        {zh ? (
          <>
            <div><b>年支取率</b>：每年花掉组合的百分之几。经验法则（Trinity 研究）：≤4% 时组合大概率永续；4–6% 要靠收益撑着；&gt;6% 是在消耗本金。箭头后是<b>房贷结清那一刻</b>的状态——分母用模拟路径在那个时点的<b>中位净资产</b>（不是今天的），分子用通胀调整后的基础支出。当结清时余额不足 3 年支出时，百分比失去意义（100% = 只够一年），直接改显"仅剩≈N年支出"。</div>
            <div><b>房贷的建模方式</b>：月供是固定名义金额（不随通胀涨），且只扣到剩余年限结束——之后所有路径的月支出自动降为基础支出。房贷对应的房产不在组合净资产内，所以只在现金流层面建模，不进资产负债。</div>
            <div><b>静态跑道</b>：最保守的底线——假设从今天起组合收益为零，现有净资产 ÷ 年支出 = 还能撑几年。真实结果几乎必然好于它，它回答的是"最差也有多少年"。</div>
            <div><b>30年存活率</b>：用你设定的收益/波动假设，随机模拟 500 种可能的未来（每月收益有好有坏），看其中多少比例到 30 年后钱还没花光。≥90% 绿色 = 稳；&lt;70% 红色 = 危险。</div>
            <div><b>耗尽年限</b>：这 500 种未来按耗尽时间排序——中位数 = 一半情况比它好一半比它差；悲观(P10) = 运气最差的 10% 情况（比如开局就遇到大熊市）也能撑这么久。&gt;40年 表示模拟期内没耗尽。</div>
            <div><b>为什么波动率重要</b>：同样 8% 年化，波动越大越危险——下跌年份里你照常支取，卖在低点的份额永远回不来（序列风险）。这就是模拟比"平均收益算术题"悲观的原因。</div>
          </>
        ) : (
          <>
            <div><b>Withdrawal rate</b>: annual spend as % of NAV. Rule of thumb (Trinity study): ≤4% is likely perpetual; &gt;6% eats principal.</div>
            <div><b>Static runway</b>: worst-case floor — years of spending if returns were zero from today.</div>
            <div><b>Survives 30y</b>: of 500 simulated futures under your assumptions, the share still solvent after 30 years.</div>
            <div><b>Depletion</b>: median = typical case; p10 = the unlucky-decile case (e.g. a bear market up front). &gt;40y = never depleted in-simulation.</div>
            <div><b>Why volatility matters</b>: withdrawing through drawdowns sells at lows permanently (sequence risk) — that&apos;s why simulation is gloomier than average-return arithmetic.</div>
          </>
        )}
      </div>
      {/* Historical capital trend (consumption mirror) */}
      {capMonthly.recent.length > 0 && (
        <div className="mb-3 text-xs">
          <div className="text-[10px] text-gray-400 uppercase mb-1">
            {zh ? "Capital 月度变化（近12个月）——负值≈当月净支取，是 T0 前消费的镜像" : "Monthly capital deltas (last 12mo) — negatives ≈ net withdrawals"}
          </div>
          <div className="flex flex-wrap gap-2 font-mono">
            {capMonthly.recent.map((d) => (
              <span key={d.month} className={`px-2 py-1 rounded border ${d.delta < 0
                ? "bg-red-50 dark:bg-red-900/10 border-red-200 dark:border-red-900 text-red-700 dark:text-red-400"
                : "bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-800 text-gray-500"}`}>
                {d.month}: {d.delta >= 0 ? "+" : ""}{formatNumber(d.delta, 0)}
              </span>
            ))}
          </div>
          {capMonthly.avgDraw && (
            <div className="text-[10px] text-gray-400 mt-1">
              {zh ? `支取月份的月均支取 ≈ ¥${formatNumber(capMonthly.avgDraw, 0)}（可点上方按钮填入月支出）` : `avg monthly draw ≈ ¥${formatNumber(capMonthly.avgDraw, 0)}`}
            </div>
          )}
        </div>
      )}
      {/* Recent recorded outflows */}
      {Object.keys(outByMonth).length > 0 && (
        <div className="mb-6 text-xs">
          <div className="text-[10px] text-gray-400 uppercase mb-1">{zh ? "已记录出金（月度，T0 起）" : "Recorded outflows (monthly, since T0)"}</div>
          <div className="flex flex-wrap gap-2 font-mono">
            {Object.entries(outByMonth).sort().map(([m, v]) => (
              <span key={m} className="px-2 py-1 rounded bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                {m}: ¥{formatNumber(v, 0)}
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// ══════════════════════════════════════════
// Performance & Risk Analytics
// ══════════════════════════════════════════

function PerformanceSection({ locale, hideChart, hideRisk, liveUnitNav, liveNetAssets }: {
  locale: string; hideChart?: boolean; hideRisk?: boolean;
  /** Intraday unit-NAV estimate + live net assets from the summary payload.
      When today has no official snapshot yet, the performance chart gets a
      synthetic "today" point (盘中估值) — replaced by the real snapshot at
      the next 06:10 run. Heatmap/risk keep official snapshots only. */
  liveUnitNav?: number | null; liveNetAssets?: number | null;
}) {
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

  // Chart-only live extension (盘中估值): if today has no official snapshot
  // yet, append a "today" point; if today's snapshot exists (06:10 run,
  // priced at yesterday's close), replace its value with the live estimate
  // so the curve tracks the current session either way. Next morning's
  // snapshot restores the official value. Local date (not UTC) — snapshots
  // are Beijing-dated and an evening session would otherwise lag a day.
  // Divergence gate: with markets closed the estimate equals the official
  // value — skip the live point then, so weekends don't grow a flat tail
  // dated on non-trading days and the 盘中 note only shows mid-session.
  const today = new Intl.DateTimeFormat("sv-SE").format(new Date());
  const lastSnap = snapshotsSorted[snapshotsSorted.length - 1];
  const lastSnapVal = lastSnap
    ? (lastSnap.unit_nav != null && lastSnap.unit_nav > 0 ? lastSnap.unit_nav
       : (lastSnap.capital && lastSnap.capital > 0 && lastSnap.net_assets != null
          ? lastSnap.net_assets / lastSnap.capital : null))
    : null;
  const hasLive = !!(liveUnitNav && liveNetAssets && lastSnap && today >= lastSnap.date
    && lastSnapVal != null && Math.abs(liveUnitNav - lastSnapVal) >= 0.0001);
  const chartSnapshots = hasLive
    ? [...snapshotsSorted.slice(0, today === lastSnap.date ? -1 : undefined),
       { ...lastSnap, date: today, unit_nav: liveUnitNav!, net_assets: liveNetAssets! }]
    : snapshotsSorted;
  const chartNav = hasLive
    ? (() => {
        const base = navSorted[navSorted.length - 1]?.date === today
          ? navSorted.slice(0, -1) : navSorted;
        const cap = lastSnap.capital ?? base[base.length - 1]?.capital_invested ?? 0;
        return [...base, {
          date: today,
          net_asset_value: liveNetAssets!,
          capital_invested: cap,
          pnl: liveNetAssets! - cap,
          equity_nav: cap > 0 ? liveNetAssets! / cap : 1,
          benchmark_value: null,
        }];
      })()
    : navSorted;

  // Flow-adjusted return index: TWR unit NAV after T0, NAV/Capital ratio
  // before — the same splice as MonthlyHeatmap. Raw net_assets would count
  // every living-expense withdrawal as a loss day, inflating vol/drawdown
  // and depressing Sharpe.
  const riskPts = snapshotsSorted
    .filter((s) => s.net_assets != null && s.net_assets > 0
      && ((s.unit_nav != null && s.unit_nav > 0) || (s.capital != null && s.capital > 0)))
    .map((s) => ({
      date: s.date,
      val: s.unit_nav != null && s.unit_nav > 0 ? s.unit_nav : (s.net_assets as number) / (s.capital as number),
      na: s.net_assets as number,
    }));

  // Full-history flow-adjusted index: nav_history's NAV/Capital ratio
  // (weekly-ish, from 2023-12) chains seamlessly into the snapshot-era
  // series — same construction the TWR seed used. Long-horizon stats
  // (CAGR, max drawdown, Calmar) come from this; higher-frequency stats
  // (vol, Sharpe, win rate) stay on the daily-snapshot era only, since
  // mixing weekly and daily intervals would corrupt them.
  const firstSnapDate = riskPts[0]?.date || "9999";
  const fullPts = [
    ...[...navHistory].sort((a, b) => a.date.localeCompare(b.date))
      .filter((n) => n.capital_invested > 0 && n.net_asset_value > 0 && n.date < firstSnapDate)
      .map((n) => ({ date: n.date, val: n.net_asset_value / n.capital_invested, na: n.net_asset_value })),
    ...riskPts,
  ];

  let longCagr: number | null = null, cumRet: number | null = null;
  if (fullPts.length > 1) {
    const a = fullPts[0], b = fullPts[fullPts.length - 1];
    const days = (new Date(b.date).getTime() - new Date(a.date).getTime()) / 86400000;
    cumRet = (b.val / a.val - 1) * 100;
    if (days > 90) longCagr = (Math.pow(b.val / a.val, 365 / days) - 1) * 100;
  }

  // Max drawdown over the full index; ¥ loss scales by NAV at the peak
  let maxDrawdown = 0, peak = 0, ddStart = "", ddEnd = "", peakNa = 0, ddPeakNa = 0;
  let ddCurStart = "";
  for (const p of fullPts) {
    if (p.val > peak) { peak = p.val; ddCurStart = p.date; peakNa = p.na; }
    const dd = (peak - p.val) / peak;
    if (dd > maxDrawdown) {
      maxDrawdown = dd;
      ddStart = ddCurStart;
      ddEnd = p.date;
      ddPeakNa = peakNa;
    }
  }
  const pnlLost = maxDrawdown * ddPeakNa;

  // Daily-era stats (higher-moment metrics need uniform intervals)
  const dailyReturns: number[] = [];
  for (let i = 1; i < riskPts.length; i++) {
    if (riskPts[i - 1].val > 0) dailyReturns.push(riskPts[i].val / riskPts[i - 1].val - 1);
  }
  const avgReturn = dailyReturns.length > 0 ? dailyReturns.reduce((s, r) => s + r, 0) / dailyReturns.length : 0;
  const variance = dailyReturns.length > 1 ? dailyReturns.reduce((s, r) => s + (r - avgReturn) ** 2, 0) / (dailyReturns.length - 1) : 0;
  const dailyVol = Math.sqrt(variance);
  const annualVol = dailyVol * Math.sqrt(252);
  const annualReturn = avgReturn * 252; // arithmetic — feeds Sharpe only
  const riskFreeRate = 0.015; // 1.5% CNY
  const sharpe = annualVol > 0 ? (annualReturn - riskFreeRate) / annualVol : 0;
  const calmar = maxDrawdown > 0 && longCagr != null ? (longCagr / 100) / maxDrawdown : 0;
  const winDays = dailyReturns.filter((r) => r > 0).length;
  const lossDays = dailyReturns.filter((r) => r < 0).length;
  const winRate = dailyReturns.length > 0 ? (winDays / dailyReturns.length) * 100 : 0;

  // Time ranges for labelling
  const fullStart = fullPts[0]?.date || "";
  const lastDate = fullPts[fullPts.length - 1]?.date || "";
  const dailyStart = riskPts[0]?.date || "";
  const fullYears = fullStart && lastDate
    ? (new Date(lastDate).getTime() - new Date(fullStart).getTime()) / 86400000 / 365 : 0;

  const riskNote = [
    `* 全部收益基于份额净值（TWR，已剔除出入金影响）：${fullStart} 前段来自周频 NAV/Capital 净值，${dailyStart} 起为每日快照`,
    `* 年化收益/最大回撤/卡玛用全历史（${fullYears.toFixed(1)}年）复合口径；波动率/夏普/胜率只用日频段（${dailyStart} 起），周频数据混入会失真`,
    `* 最大回撤 ${(maxDrawdown * 100).toFixed(2)}%（${ddStart} → ${ddEnd}），按峰值净资产折算亏损 ¥${formatNumber(Math.abs(pnlLost), 0)}`,
    `* Sharpe >1 = 每承担1单位波动获得>1单位超额收益（rf=1.5% CNY，日频算术年化口径）`,
    `* Calmar = 长期复合年化 ÷ 最大回撤，衡量单位最大亏损换来的收益，>1 良好 >3 优秀`,
  ].join("\n");

  return (
    <>
      {/* Performance Chart (NAV + Capital) */}
      {!hideChart && navSorted.length > 2 && <PerformanceChart navHistory={chartNav} snapshots={chartSnapshots} locale={locale} liveLast={hasLive} />}
      {!hideChart && <MonthlyHeatmap snapshots={snapshotsSorted} navHistory={navHistory} locale={locale} />}

      {/* Risk Analytics */}
      {!hideRisk && (<>
      <SectionTitle note={riskNote}>
        {locale === "zh" ? "风险指标" : "Risk Analytics"}
      </SectionTitle>
      <div className="grid grid-cols-3 md:grid-cols-7 gap-3 mb-6">
        {[
          { label: locale === "zh" ? "年化收益" : "Ann. Return (CAGR)",
            value: longCagr != null ? `${longCagr.toFixed(1)}%` : "—",
            sub: cumRet != null ? `${fullStart} 起 · ${locale === "zh" ? "累计" : "cum."} ${cumRet >= 0 ? "+" : ""}${cumRet.toFixed(0)}%` : undefined,
            color: pnlColor(longCagr || 0) },
          { label: locale === "zh" ? "年化波动率" : "Ann. Volatility", value: `${(annualVol * 100).toFixed(2)}%`,
            sub: `${locale === "zh" ? "日频段" : "daily era"} σ=${(dailyVol * 100).toFixed(2)}%/d` },
          { label: locale === "zh" ? "最大回撤" : "Max Drawdown", value: `${(maxDrawdown * 100).toFixed(2)}%`,
            sub: ddStart && ddEnd ? `¥${formatNumber(Math.abs(pnlLost), 0)} · ${ddStart.slice(2, 7)}→${ddEnd.slice(2, 7)}` : undefined,
            color: "text-red-600 dark:text-red-400" },
          { label: locale === "zh" ? "夏普比率" : "Sharpe Ratio", value: sharpe.toFixed(2),
            sub: `rf=1.5% · ${locale === "zh" ? `日频段自 ${dailyStart.slice(2)}` : `since ${dailyStart}`}` },
          { label: locale === "zh" ? "胜率" : "Win Rate", value: `${winRate.toFixed(0)}%`,
            sub: `${winDays}W / ${lossDays}L (daily)` },
          { label: locale === "zh" ? "卡玛比率" : "Calmar Ratio", value: calmar ? calmar.toFixed(2) : "—",
            sub: locale === "zh" ? `${longCagr != null ? longCagr.toFixed(1) : "—"}% ÷ ${(maxDrawdown * 100).toFixed(1)}%` : `CAGR ÷ MDD` },
          { label: locale === "zh" ? "样本" : "Sample",
            value: locale === "zh" ? `${fullYears.toFixed(1)}年` : `${fullYears.toFixed(1)}y`,
            sub: locale === "zh" ? `${riskPts.length} 个日频点` : `${riskPts.length} daily pts` },
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

/** Monthly returns heatmap — years × months grid from the TWR/ratio series.
 *  The single most professional-feeling component per tracker reviews
 *  (Sharesight/Snowball both ship it); grows richer every month. */
function MonthlyHeatmap({ snapshots, navHistory = [], locale }: {
  snapshots: Snapshot[]; navHistory?: NavHistoryPoint[]; locale: string;
}) {
  const zh = locale === "zh";
  const cells = useMemo(() => {
    const snapPts = snapshots
      .filter((s) => (s.unit_nav != null && s.unit_nav > 0) || (s.capital && s.capital > 0 && s.net_assets != null))
      .map((s) => ({
        date: s.date,
        val: s.unit_nav != null && s.unit_nav > 0 ? s.unit_nav : (s.net_assets as number) / (s.capital as number),
      }))
      .sort((a, b) => a.date.localeCompare(b.date));
    // Prepend the weekly NAV/Capital ratio history so 2024/2025 show up too
    const firstSnap = snapPts[0]?.date || "9999";
    const pts = [
      ...[...navHistory]
        .filter((n) => n.capital_invested > 0 && n.net_asset_value > 0 && n.date < firstSnap)
        .sort((a, b) => a.date.localeCompare(b.date))
        .map((n) => ({ date: n.date, val: n.net_asset_value / n.capital_invested })),
      ...snapPts,
    ];
    if (pts.length < 2) return null;
    // Last value per month, in date order
    const monthEnd = new Map<string, number>();
    for (const p of pts) monthEnd.set(p.date.slice(0, 7), p.val);
    const months = [...monthEnd.keys()].sort();
    const out: { ym: string; ret: number }[] = [];
    let prev = pts[0].val;
    for (const ym of months) {
      const v = monthEnd.get(ym)!;
      out.push({ ym, ret: (v / prev - 1) * 100 });
      prev = v;
    }
    return out;
  }, [snapshots]);

  if (!cells || cells.length === 0) return null;

  const years = [...new Set(cells.map((c) => c.ym.slice(0, 4)))].sort().reverse();
  const byYm = new Map(cells.map((c) => [c.ym, c.ret]));
  const maxAbs = Math.max(...cells.map((c) => Math.abs(c.ret)), 1);
  const cellStyle = (ret: number | undefined) => {
    if (ret == null) return {};
    const alpha = Math.min(0.85, 0.15 + (Math.abs(ret) / maxAbs) * 0.6);
    // CN convention: red = gain, green = loss (matches pnlColor)
    return { backgroundColor: ret >= 0 ? `rgba(239,68,68,${alpha})` : `rgba(34,197,94,${alpha})` };
  };

  return (
    <div className="mt-4 mb-2">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-0.5">
        {zh ? "月度收益 (%)" : "Monthly Returns (%)"}
      </div>
      <div className="text-[9px] text-gray-400 mb-2">
        {zh
          ? "口径：TWR 净值环比（与上方曲线同源，出入金免疫，各月连乘=累计）；2026-03 前为周频 NAV/Capital 近似，月末=当月最后一个数据点"
          : "Measure: month-over-month TWR unit NAV (flow-immune; months compound to the cumulative); pre-2026-03 approximated from weekly NAV/Capital"}
      </div>
      <div className="overflow-x-auto">
        <table className="text-[10px] font-mono border-collapse">
          <thead>
            <tr>
              <th className="pr-2 text-gray-400 font-normal" />
              {Array.from({ length: 12 }, (_, i) => (
                <th key={i} className="px-1 py-0.5 text-gray-400 font-normal text-center w-12">{i + 1}{zh ? "月" : ""}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y}>
                <td className="pr-2 text-gray-500">{y}</td>
                {Array.from({ length: 12 }, (_, i) => {
                  const ym = `${y}-${String(i + 1).padStart(2, "0")}`;
                  const ret = byYm.get(ym);
                  return (
                    <td key={ym} className="px-1 py-1 text-center rounded" style={cellStyle(ret)}>
                      <span className={ret != null ? "text-gray-900 dark:text-white" : "text-gray-200 dark:text-gray-800"}>
                        {ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(1)}` : "·"}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════
// Performance Chart (SVG line chart)
// ══════════════════════════════════════════

function PerformanceChart({ navHistory, snapshots = [], locale, liveLast }: {
  navHistory: NavHistoryPoint[]; snapshots?: Snapshot[]; locale: string;
  /** True when the last point is the intraday estimate, not an official snapshot. */
  liveLast?: boolean;
}) {
  const [range, setRange] = useState<string>("2Y");
  // "twr" = indexed unit-NAV view (what the hero links to); "nav" = ¥ NAV/Capital.
  // Both prefs persist — the benchmark toggle resetting on every visit is
  // exactly how the TWR curve used to "disappear"
  const [view, setViewRaw] = useState<"twr" | "nav">(() =>
    (typeof window !== "undefined" && localStorage.getItem("vs_perf_view") === "nav") ? "nav" : "twr");
  const setView = (v: "twr" | "nav") => { setViewRaw(v); try { localStorage.setItem("vs_perf_view", v); } catch { /* ignore */ } };
  const [showBenchmarks, setShowBenchmarksRaw] = useState<boolean>(() =>
    typeof window !== "undefined" && localStorage.getItem("vs_perf_bench") === "1");
  const setShowBenchmarks = (b: boolean) => { setShowBenchmarksRaw(b); try { localStorage.setItem("vs_perf_bench", b ? "1" : "0"); } catch { /* ignore */ } };
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
  const benchColors: Record<string, string> = { "CSI 300": "#ef4444", "S&P 500": "#22c55e", "Nasdaq 100": "#8b5cf6", "Hang Seng": "#f59e0b" };

  if (view === "twr") {
    // Portfolio indexed return — a stitched, seamless series:
    // before T0 the legacy NAV/Capital ratio, from T0 the TWR unit NAV.
    // The inception seed equals NAV/Capital on T0, so the segments meet
    // at the same value and the curve stays continuous.
    const rangeStart = filteredNav[0].date;
    const twrPts = snapshots.filter(
      (s) => s.unit_nav != null && s.unit_nav > 0 && s.date >= rangeStart,
    );
    const t0 = twrPts[0]?.date ?? "";
    let portIndexed: { date: string; indexed: number }[];
    if (twrPts.length > 0) {
      const pre = filteredNav
        .filter((p) => p.date < t0 && p.capital_invested > 0)
        .map((p) => ({ date: p.date, val: p.net_asset_value / p.capital_invested }));
      const post = twrPts.map((s) => ({ date: s.date, val: s.unit_nav as number }));
      const series = [...pre, ...post];
      const base = series[0].val;
      portIndexed = series.map((p) => ({ date: p.date, indexed: (p.val / base) * 100 }));
    } else {
      const startEnav = filteredNav[0].net_asset_value / filteredNav[0].capital_invested;
      portIndexed = filteredNav.map((p) => ({
        date: p.date,
        indexed: (p.net_asset_value / p.capital_invested) / startEnav * 100,
      }));
    }
    const portLabel = locale === "zh"
      ? (twrPts.length > 0 ? "组合净值 (TWR)" : "组合")
      : (twrPts.length > 0 ? "Portfolio (TWR)" : "Portfolio");
    // Two rulers, one curve: the chart rebases the WINDOW start to 100
    // (switching ranges moves the answer); the unit NAV is anchored at the
    // accounting origin (1.0 = capital just paid in). Showing both with the
    // conversion spelled out kills the "110% vs 1.70 don't match" confusion.
    const lastUnitNav = twrPts.length > 0
      ? (twrPts[twrPts.length - 1].unit_nav as number)
      : (filteredNav[filteredNav.length - 1].capital_invested > 0
        ? filteredNav[filteredNav.length - 1].net_asset_value / filteredNav[filteredNav.length - 1].capital_invested
        : null);
    const windowRet = portIndexed[portIndexed.length - 1].indexed - 100;

    // Build indexed benchmark returns (filter to date range)
    const startDate = portIndexed[0].date;
    const endDate = portIndexed[portIndexed.length - 1].date;
    const benchIndexed: Record<string, { date: string; indexed: number }[]> = {};
    for (const [name, points] of Object.entries(benchData)) {
      // base = last close on/before the portfolio's start (10-day lead-in
      // from the endpoint) — first-close-after swallowed a session
      const lead = points.filter((p) => p.date <= startDate);
      const after = points.filter((p) => p.date > startDate && p.date <= endDate);
      const base = lead.length ? lead[lead.length - 1].close : after[0]?.close;
      if (!base || base <= 0 || after.length < 1) continue;
      benchIndexed[name] = [
        { date: startDate, indexed: 100 },
        ...after.map((p) => ({ date: p.date, indexed: (p.close / base) * 100 })),
      ];
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
          note={(locale === "zh"
            ? "* 净值曲线 (起始=100)：T0(2026-07-04) 起为份额净值 (TWR)，之前为 NAV/Capital 比值无缝拼接——已剔除出入金影响\n* 勾选 Benchmarks 叠加基准：均折算人民币口径（标普×USDCNY、恒生×HKDCNY），与组合同币种可比；价格指数不含股息；沪深300 数据源滞后时自动切换 510300 ETF 代理"
            : "* Unit-NAV curve (base=100): TWR unit NAV from T0, NAV/Capital ratio before — flow-adjusted\n* Benchmarks (toggle) converted to CNY to match the portfolio's denomination; price indices, ex-dividends")
            + (liveLast
              ? (locale === "zh" ? "\n* 末端空心点为实时估算（各市场最新可得行情，随刷新变动），次日快照落定为官方净值" : "\n* Hollow end-dot is the live estimate (latest available prices per market, moves with refresh); the next daily snapshot makes it official")
              : "")}>
          {locale === "zh" ? "业绩走势" : "Performance"}
        </SectionTitle>
        <div className="flex items-center gap-2 mb-3">
          <span className={pillCls(true)}>{locale === "zh" ? "净值 (TWR)" : "Unit NAV (TWR)"}</span>
          <span className={pillCls(false)} onClick={() => setView("nav")}>{locale === "zh" ? "金额 ¥" : "NAV ¥"}</span>
          <span className="text-gray-300 dark:text-gray-700">|</span>
          {rangeOptions.map((r) => <button key={r} onClick={() => setRange(r)} className={pillCls(range === r)}>{r}</button>)}
          <span className="text-gray-300 dark:text-gray-700">|</span>
          <label className="flex items-center gap-1 text-[10px] text-gray-500 cursor-pointer select-none">
            <input type="checkbox" checked={showBenchmarks} onChange={(e) => setShowBenchmarks(e.target.checked)} className="w-3 h-3" />
            Benchmarks{benchLoading ? " ..." : ""}
          </label>
        </div>
        <div className="text-[10px] font-mono text-gray-400 mb-2"
          title={locale === "zh"
            ? "面值 1.0 = 净资产恰好等于实收资本的会计基准（非具体日期）；溢价 ≈ 累计总盈亏 ÷ 本金（方案A口径，含已消费利润）"
            : "Par 1.0 = the accounting datum where NAV equals paid-in capital (not a date); the premium ≈ lifetime P&L / capital"}>
          {locale === "zh"
            ? `本区间 ${windowRet >= 0 ? "+" : ""}${windowRet.toFixed(1)}%（${portIndexed[0].date} 起点=100）${lastUnitNav != null ? ` · 当前单位净值 ${lastUnitNav.toFixed(4)}，相对面值 1.0 溢价 ${lastUnitNav >= 1 ? "+" : ""}${((lastUnitNav - 1) * 100).toFixed(1)}% ≈ 累计盈亏/本金` : ""} —— 同一条曲线，两把量尺`
            : `Window ${windowRet >= 0 ? "+" : ""}${windowRet.toFixed(1)}% (base=100 at ${portIndexed[0].date})${lastUnitNav != null ? ` · unit NAV ${lastUnitNav.toFixed(4)}, ${lastUnitNav >= 1 ? "+" : ""}${((lastUnitNav - 1) * 100).toFixed(1)}% over par (≈ lifetime P&L / capital)` : ""}`}
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
            {/* Portfolio line; hollow end-dot = intraday estimate, solid = official snapshot */}
            <path d={portPath} fill="none" stroke="#3b82f6" strokeWidth="2.5" />
            {liveLast
              ? <circle cx={toX(portIndexed.length - 1, portIndexed.length)} cy={toY(portIndexed[portIndexed.length - 1].indexed)} r="3.5" fill="var(--background, #fff)" stroke="#3b82f6" strokeWidth="2" />
              : <circle cx={toX(portIndexed.length - 1, portIndexed.length)} cy={toY(portIndexed[portIndexed.length - 1].indexed)} r="3" fill="#3b82f6" />}
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
            <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-blue-500 inline-block" /> {portLabel} {portRet > 0 ? "+" : ""}{portRet.toFixed(1)}%</span>
            {Object.entries(benchIndexed).map(([name, pts]) => (
              <span key={name} className="flex items-center gap-1.5">
                <span className="w-4 h-0.5 inline-block" style={{ borderTop: `1.5px dashed ${benchColors[name]}`, height: 0 }} />
                {name} {((pts[pts.length - 1].indexed - 100) > 0 ? "+" : "")}{(pts[pts.length - 1].indexed - 100).toFixed(1)}%
              </span>
            ))}
          </div>
          {alphas.length > 0 && (
            <div className="text-[10px] font-mono text-gray-400 mt-1">
              {locale === "zh" ? "超额收益 (Alpha)" : "Alpha (excess return)"}: {alphas.join(" · ")}
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
          ? "* Portfolio NAV = 净资产值 (资产总值 − 杠杆)。Net P&L = NAV − Capital\n* Capital = 实收资本 = 期初冻结值 + 累计净入金流水（出金全额扣减，含已消费利润的累计盈亏保留在 Net P&L 中）\n* 阴影区域 = Net P&L (NAV 与 Capital 之间差值)"
          : "* Portfolio NAV = Net Asset Value (Total Assets − Leverage). Net P&L = NAV − Capital\n* Capital = paid-in capital: frozen opening value + net recorded flows (withdrawals deduct in full, so Net P&L keeps lifetime profit incl. consumed)\n* Shaded area = Net P&L (gap between NAV and Capital)"}>
        {locale === "zh" ? "业绩走势" : "Performance"}
      </SectionTitle>

      <div className="flex items-center gap-2 mb-3">
        <span className={pillCls(false)} onClick={() => setView("twr")}>{locale === "zh" ? "净值 (TWR)" : "Unit NAV (TWR)"}</span>
        <span className={pillCls(true)}>{locale === "zh" ? "金额 ¥" : "NAV ¥"}</span>
        <span className="text-gray-300 dark:text-gray-700">|</span>
        {rangeOptions.map((r) => <button key={r} onClick={() => setRange(r)} className={pillCls(range === r)}>{r}</button>)}
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

function ReturnAttribution({ holdings, closedTrades, dividends = {}, locale }: {
  holdings: PortfolioHolding[]; closedTrades: ClosedTrade[];
  dividends?: Record<string, { net_cny: number }>; locale: string;
}) {
  const [tab, setTab] = useState<"daily" | "ytd" | "unrealised" | "realized" | "dividends" | "total">("unrealised");

  const tabDef = useMemo(() => {
    const zh = locale === "zh";
    const tabs: { key: string; label: string; pnlKey: string }[] = [];
    const hasDaily = holdings.some((h) => h.daily_pnl_cny != null);
    const hasYtd = holdings.some((h) => h.ytd_pnl_cny != null);
    if (hasDaily) tabs.push({ key: "daily", label: zh ? "当日" : "Daily P&L", pnlKey: "daily_pnl_cny" });
    if (hasYtd) tabs.push({ key: "ytd", label: zh ? "今年以来" : "YTD P&L", pnlKey: "ytd_pnl_cny" });
    tabs.push({ key: "unrealised", label: zh ? "未实现" : "Unrealised", pnlKey: "pnl_cny" });
    if (closedTrades.length > 0) tabs.push({ key: "realized", label: zh ? "已实现" : "Realized", pnlKey: "pnl_cny" });
    if (Object.keys(dividends).length > 0) tabs.push({ key: "dividends", label: zh ? "分红" : "Dividends", pnlKey: "pnl_cny" });
    tabs.push({ key: "total", label: zh ? "累计收益 Total Return" : "Total Return", pnlKey: "pnl_cny" });
    return tabs;
  }, [holdings, closedTrades, dividends, locale]);

  const activeTabDef = tabDef.find((t) => t.key === tab) || tabDef[0];

  // Compute by market
  const byMarket = useMemo(() => {
    const map: Record<string, number> = {};
    const mktOf = new Map(holdings.map((h) => [h.ticker, h.market]));
    const addTrades = () => {
      for (const t of closedTrades) map[t.market] = (map[t.market] || 0) + (t.realized_pnl_cny || 0);
    };
    const addDivs = () => {
      for (const [tk, d] of Object.entries(dividends)) {
        const m = mktOf.get(tk) || (locale === "zh" ? "其他" : "Other");
        map[m] = (map[m] || 0) + d.net_cny;
      }
    };
    if (tab === "realized") {
      addTrades();
    } else if (tab === "dividends") {
      addDivs();
    } else {
      for (const h of holdings) {
        const val = (h as unknown as Record<string, number | null>)[activeTabDef.pnlKey] ?? 0;
        map[h.market] = (map[h.market] || 0) + (val as number);
      }
      if (tab === "total") { addTrades(); addDivs(); }
    }
    return sortMarkets(Object.keys(map)).map((m) => ({ market: m, pnl: map[m] }));
  }, [holdings, closedTrades, dividends, tab, activeTabDef, locale]);

  // Compute by stock (top contributors)
  const byStock = useMemo(() => {
    const map: Record<string, { name: string; pnl: number }> = {};
    const nameOf = new Map(holdings.map((h) => [h.ticker, h.name]));
    const addTrades = () => {
      for (const t of closedTrades) {
        const key = t.ticker || t.name;
        if (!map[key]) map[key] = { name: t.name, pnl: 0 };
        map[key].pnl += t.realized_pnl_cny || 0;
      }
    };
    const addDivs = () => {
      for (const [tk, d] of Object.entries(dividends)) {
        if (!map[tk]) map[tk] = { name: nameOf.get(tk) || tk, pnl: 0 };
        map[tk].pnl += d.net_cny;
      }
    };
    if (tab === "realized") {
      addTrades();
    } else if (tab === "dividends") {
      addDivs();
    } else {
      for (const h of holdings) {
        const val = (h as unknown as Record<string, number | null>)[activeTabDef.pnlKey] ?? 0;
        const key = h.ticker;
        if (!map[key]) map[key] = { name: h.name, pnl: 0 };
        map[key].pnl += val as number;
      }
      if (tab === "total") { addTrades(); addDivs(); }
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
          ? `* Total Return（累计收益）= 未实现 + 已实现 + 税后分红，与持仓表「累计收益」列同一公式\n* 「已实现」「分红」标签页展示各自的单独归因；分红台账自盈透 Flex 自动积累（2026-07 起），国内摊薄账户的分红已含在摊薄成本里，不重复计\n* Contribution = 单市场/个股占该口径总额的比重`
          : `* Total Return = unrealized + realized + net dividends — same formula as the holdings table\n* Realized / Dividends tabs show standalone attribution; ledger auto-fed from IBKR Flex since 2026-07\n* Contribution = share of the selected measure`}>
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
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">{locale === "zh" ? `${activeTabDef.label} · 按市场` : `${activeTabDef.label} by Market`}</div>
          <HBar items={byMarket.map((m) => ({ key: m.market, label: mktLabel(m.market, locale), pnl: m.pnl }))} />
        </div>
        {/* Top Contributors */}
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">{locale === "zh" ? `${activeTabDef.label} · 个股贡献（前10 + 拖累5）` : `${activeTabDef.label} Top Contributors`}</div>
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
    ? `* Net P&L = Net Assets − Capital。ΔNet P&L = 当日净收益变动\n* Capital = 实收资本 = 期初冻结值 + 累计净入金流水`
    : `* Net P&L = Net Assets − Capital. ΔNet P&L = daily change\n* Capital = paid-in capital: frozen opening value + net recorded flows`;

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

/** Dividend ledger journal — the fact record survives position closes, so
 *  this is where a closed position's lifetime dividends remain visible. */
function DividendJournal({ locale }: { locale: string }) {
  const zh = locale === "zh";
  const [ledger, setLedger] = useState<Partial<DividendLedger> | null>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { getDividends().then(setLedger).catch(() => {}); }, []);

  const rows = ledger?.rows || [];
  const typeLabel: Record<string, string> = zh
    ? { "Dividends": "分红", "Payment In Lieu Of Dividends": "代付分红", "Withholding Tax": "预扣税",
        "Broker Interest Paid": "利息支出", "Broker Interest Received": "利息收入" }
    : { "Dividends": "Div", "Payment In Lieu Of Dividends": "PIL", "Withholding Tax": "WHT",
        "Broker Interest Paid": "Int paid", "Broker Interest Received": "Int recv" };

  // Per-ticker cumulative (incl. tickers no longer held); interest → "(现金)"
  const byTicker = useMemo(() => {
    const m: Record<string, { native: number; ccy: string; cny: number; n: number; last: string }> = {};
    for (const r of rows) {
      const tk = r.ticker || (zh ? "（现金利息）" : "(cash interest)");
      const g = m[tk] || { native: 0, ccy: r.currency, cny: 0, n: 0, last: "" };
      g.native += r.amount;
      g.n += 1;
      if (r.date > g.last) g.last = r.date;
      m[tk] = g;
    }
    // net CNY from the server-side aggregation where available
    for (const [tk, v] of Object.entries(ledger?.by_ticker || {})) {
      if (m[tk]) m[tk].cny = v.net_cny;
    }
    return Object.entries(m).sort((a, b) => Math.abs(b[1].cny || b[1].native) - Math.abs(a[1].cny || a[1].native));
  }, [rows, ledger, zh]);

  const totalCny = Object.values(ledger?.by_ticker || {}).reduce((s, v) => s + v.net_cny, 0);

  return (
    <>
      <div className="flex items-center justify-between mt-8 mb-2">
        <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-900 dark:text-white">
          <span className="text-xs">{expanded ? "▼" : "▶"}</span>
          <span>{zh ? "分红台账" : "Dividend Ledger"}</span>
          <span className={`text-xs font-mono font-normal normal-case ${pnlColor(totalCny)}`}>
            ({rows.length} {zh ? "笔" : "entries"} · ¥{pnlSign(totalCny)})
          </span>
        </button>
      </div>

      {expanded && (rows.length === 0 ? (
        <div className="text-xs text-gray-400 mb-4 leading-relaxed">
          {zh
            ? "台账为空。开启盈透 Flex 查询的 Cash Transactions 区段后，每日对账会自动积累分红/预扣税/利息流水（含此后清仓的持仓，记录永久保留）。"
            : "Empty. Enable the Cash Transactions section on the IBKR Flex query and daily recon will accumulate dividends/tax/interest here (records survive position closes)."}
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden mb-4">
          {/* Per-ticker cumulative — includes closed positions */}
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b-2 border-gray-200 dark:border-gray-700 text-[10px] text-gray-500 uppercase">
                <th className="text-left px-3 py-1.5">{zh ? "标的（含已清仓）" : "Ticker (incl. closed)"}</th>
                <th className="text-right px-3 py-1.5">{zh ? "累计净额" : "Net"}</th>
                <th className="text-right px-3 py-1.5">¥</th>
                <th className="text-right px-3 py-1.5">{zh ? "笔数" : "#"}</th>
                <th className="text-right px-3 py-1.5">{zh ? "最近" : "Last"}</th>
              </tr>
            </thead>
            <tbody>
              {byTicker.map(([tk, g]) => (
                <tr key={tk} className="border-b border-gray-100 dark:border-gray-800/50">
                  <td className="px-3 py-1.5 font-medium">{tk}</td>
                  <td className={`text-right px-3 py-1.5 ${pnlColor(g.native)}`}>{pnlSign(g.native)} {g.ccy}</td>
                  <td className={`text-right px-3 py-1.5 ${pnlColor(g.cny)}`}>{g.cny ? pnlSign(g.cny) : "—"}</td>
                  <td className="text-right px-3 py-1.5 text-gray-500">{g.n}</td>
                  <td className="text-right px-3 py-1.5 text-gray-400">{g.last}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* Recent entries */}
          <div className="border-t border-gray-200 dark:border-gray-800 px-3 py-1.5 text-[10px] text-gray-400 uppercase">{zh ? "最近流水" : "Recent entries"}</div>
          <table className="w-full text-xs font-mono">
            <tbody>
              {rows.slice(0, 30).map((r, i) => (
                <tr key={i} className="border-b border-gray-100 dark:border-gray-800/50">
                  <td className="px-3 py-1 text-gray-400 whitespace-nowrap">{r.date}</td>
                  <td className="px-3 py-1">{r.ticker || "—"}</td>
                  <td className="px-3 py-1 text-gray-500">{typeLabel[r.type] || r.type}</td>
                  <td className={`text-right px-3 py-1 ${pnlColor(r.amount)}`}>{pnlSign(r.amount)} {r.currency}</td>
                  <td className="px-3 py-1 text-gray-400 truncate max-w-[220px]" title={r.description}>{r.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}

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

/** 3-step setup wizard — the golden five minutes. Broker presets carry the
 *  cost-method / HK-Connect configuration so new users never have to learn
 *  what 摊薄成本 means; finishing triggers a day-0 snapshot so the NAV curve
 *  starts today instead of tomorrow morning. */
const BROKER_PRESETS: { name: string; cost: "diluted" | "average"; hk: boolean }[] = [
  { name: "华泰证券", cost: "diluted", hk: true },
  { name: "中信证券", cost: "diluted", hk: true },
  { name: "招商证券", cost: "diluted", hk: true },
  { name: "东方财富", cost: "diluted", hk: true },
  { name: "富途", cost: "diluted", hk: false },
  { name: "盈透 IBKR", cost: "average", hk: false },
];

function _normalizeTicker(raw: string): { ticker: string; market: string; currency: string } | null {
  const t = raw.trim().toUpperCase();
  if (!t) return null;
  if (/^\d{6}$/.test(t)) {
    const ss = ["600", "601", "603", "605", "688"].some((p) => t.startsWith(p));
    return { ticker: t + (ss ? ".SS" : ".SZ"), market: "A股", currency: "CNY" };
  }
  if (/^\d{1,5}$/.test(t)) return { ticker: t.padStart(4, "0") + ".HK", market: "港股", currency: "HKD" };
  if (t.endsWith(".HK")) return { ticker: t, market: "港股", currency: "HKD" };
  if (t.endsWith(".T")) return { ticker: t, market: "日股", currency: "JPY" };
  if (t.endsWith(".SS") || t.endsWith(".SZ")) return { ticker: t, market: "A股", currency: "CNY" };
  if (/^[A-Z.\-]{1,6}$/.test(t)) return { ticker: t, market: "美股", currency: "USD" };
  return { ticker: t, market: "美股", currency: "USD" };
}

function SetupWizard({ locale, onRefresh }: { locale: string; onRefresh: () => void }) {
  const zh = locale === "zh";
  const [step, setStep] = useState(1);
  const [broker, setBroker] = useState<string>("");
  const [customBroker, setCustomBroker] = useState("");
  const [rows, setRows] = useState<{ code: string; qty: string; cost: string }[]>(
    [{ code: "", qty: "", cost: "" }, { code: "", qty: "", cost: "" }, { code: "", qty: "", cost: "" }]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");

  const preset = BROKER_PRESETS.find((b) => b.name === broker);
  const brokerName = broker === "__custom__" ? customBroker.trim() : broker;
  const inputCls = "w-full px-2 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:ring-1 focus:ring-blue-500 focus:outline-none";

  async function finish() {
    const valid = rows
      .map((r) => ({ norm: _normalizeTicker(r.code), qty: parseFloat(r.qty), cost: parseFloat(r.cost) }))
      .filter((r) => r.norm && r.qty > 0 && r.cost > 0) as { norm: NonNullable<ReturnType<typeof _normalizeTicker>>; qty: number; cost: number }[];
    if (valid.length === 0) { alert(zh ? "请至少填写一行有效持仓（代码/数量/成本）" : "Enter at least one valid row"); return; }
    setBusy(true);
    try {
      setProgress(zh ? "创建账户…" : "Creating account…");
      await upsertAccountSetting({
        broker: brokerName, capital_mode: "cost",
        cost_method: preset?.cost ?? "diluted", hk_connect: preset?.hk ?? false,
      });
      for (let i = 0; i < valid.length; i++) {
        const v = valid[i];
        setProgress(zh ? `添加持仓 ${i + 1}/${valid.length}…` : `Adding position ${i + 1}/${valid.length}…`);
        let name = v.norm.ticker;
        try {
          const hits = await searchStocks(v.norm.ticker.replace(/\.(SS|SZ|HK|T)$/, ""), "");
          const hit = hits.find((h) => h.symbol === v.norm.ticker) || hits[0];
          if (hit?.name) name = hit.name;
        } catch { /* name = ticker */ }
        await upsertPosition({
          ticker: v.norm.ticker, name, market: v.norm.market, broker: brokerName,
          quantity: v.qty, cost_price: v.cost, currency: v.norm.currency,
        });
      }
      setProgress(zh ? "生成你的第一张资产快照（约半分钟）…" : "Taking your first snapshot (~30s)…");
      try { await triggerSnapshot(); } catch { /* daily scheduler will cover it */ }
      trackEvent("onboarding_complete", { positions: valid.length });
      setStep(3);
      onRefresh();
    } catch {
      alert(zh ? "保存失败，请重试" : "Save failed, please retry");
    } finally { setBusy(false); setProgress(""); }
  }

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-5">
      {/* Step indicator */}
      <div className="flex items-center justify-center gap-2 mb-4">
        {[1, 2, 3].map((n) => (
          <React.Fragment key={n}>
            <span className={`w-6 h-6 rounded-full text-xs flex items-center justify-center font-medium ${step >= n ? "bg-blue-600 text-white" : "bg-gray-200 dark:bg-gray-700 text-gray-500"}`}>{n}</span>
            {n < 3 && <span className={`w-8 h-0.5 ${step > n ? "bg-blue-600" : "bg-gray-200 dark:bg-gray-700"}`} />}
          </React.Fragment>
        ))}
      </div>

      {step === 1 && (
        <>
          <div className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1 text-center">{zh ? "选择你的券商" : "Pick your broker"}</div>
          <div className="text-[11px] text-gray-400 mb-3 text-center">{zh ? "成本口径、港股通结算会自动配置好，以后可在设置中修改或添加更多账户" : "Cost method & HK-Connect are configured automatically; add more accounts later in Settings"}</div>
          <div className="grid grid-cols-3 gap-2 mb-2">
            {BROKER_PRESETS.map((b) => (
              <button key={b.name} onClick={() => setBroker(b.name)}
                className={`px-2 py-2 text-xs rounded-lg border transition-colors ${broker === b.name ? "bg-blue-600 text-white border-blue-600" : "bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-700 hover:border-blue-400"}`}>
                {b.name}
              </button>
            ))}
          </div>
          <button onClick={() => setBroker("__custom__")}
            className={`w-full px-2 py-1.5 text-xs rounded-lg border mb-2 ${broker === "__custom__" ? "border-blue-500 text-blue-600" : "border-dashed border-gray-300 dark:border-gray-700 text-gray-400 hover:border-blue-400"}`}>
            {zh ? "其他券商…" : "Other broker…"}
          </button>
          {broker === "__custom__" && (
            <input className={`${inputCls} mb-2`} placeholder={zh ? "券商名称" : "Broker name"} value={customBroker} onChange={(e) => setCustomBroker(e.target.value)} />
          )}
          <button disabled={!brokerName} onClick={() => setStep(2)}
            className="w-full px-4 py-2.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 font-medium">
            {zh ? "下一步" : "Next"}
          </button>
        </>
      )}

      {step === 2 && (
        <>
          <div className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-1 text-center">{zh ? `录入「${brokerName}」的持仓` : `Positions at ${brokerName}`}</div>
          <div className="text-[11px] text-gray-400 mb-3 text-center">{zh ? "代码直接抄券商 App：600519 / 0700 / AAPL 都行，名称自动识别" : "Codes as in your broker app: 600519 / 0700 / AAPL — names auto-resolve"}</div>
          <div className="space-y-1.5 mb-2">
            <div className="grid grid-cols-[1fr_90px_90px_24px] gap-1.5 text-[10px] text-gray-400 px-1">
              <span>{zh ? "代码" : "Code"}</span><span>{zh ? "数量" : "Qty"}</span><span>{zh ? "成本价" : "Cost"}</span><span />
            </div>
            {rows.map((r, i) => (
              <div key={i} className="grid grid-cols-[1fr_90px_90px_24px] gap-1.5">
                <input className={inputCls} placeholder="600519 / 0700 / AAPL" value={r.code}
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, code: e.target.value } : x))} />
                <input className={inputCls} inputMode="decimal" placeholder="100" value={r.qty}
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, qty: e.target.value } : x))} />
                <input className={inputCls} inputMode="decimal" placeholder="10.5" value={r.cost}
                  onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, cost: e.target.value } : x))} />
                <button className="text-gray-300 hover:text-red-400" onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
              </div>
            ))}
          </div>
          <button onClick={() => setRows([...rows, { code: "", qty: "", cost: "" }])}
            className="text-xs text-blue-500 hover:text-blue-700 mb-3">+ {zh ? "加一行" : "Add row"}</button>
          <div className="flex gap-2">
            <button onClick={() => setStep(1)} className="px-4 py-2.5 text-sm rounded-lg border border-gray-300 dark:border-gray-700 text-gray-500">{zh ? "上一步" : "Back"}</button>
            <button disabled={busy} onClick={finish}
              className="flex-1 px-4 py-2.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 font-medium">
              {busy ? (progress || "...") : (zh ? "完成设置" : "Finish")}
            </button>
          </div>
        </>
      )}

      {step === 3 && (
        <div className="text-center py-4">
          <div className="text-4xl mb-3">🎉</div>
          <div className="text-base font-semibold text-gray-900 dark:text-white mb-2">{zh ? "完成！你的第一张资产快照已生成" : "Done! Your first snapshot is in"}</div>
          <div className="text-xs text-gray-500 leading-relaxed max-w-xs mx-auto">
            {zh ? "从明天起每日自动更新净值曲线。入金出金请用「资金流」记录，日常盈亏无需任何操作。" : "The NAV curve updates daily from tomorrow. Record deposits/withdrawals in Flows; daily P&L needs nothing from you."}
          </div>
          <Link href="/portfolio/guide" className="inline-block mt-3 text-xs text-blue-500 hover:underline">
            {zh ? "📖 阅读记账指南（净值、本金、资金流的完整说明）" : "📖 Read the accounting guide"}
          </Link>
        </div>
      )}
    </div>
  );
}

function OnboardingCard({ locale, onRefresh, onOpenPanel }: { locale: string; onRefresh: () => void; onOpenPanel: (tab?: "edit" | "close" | "cash" | "flows" | "settings") => void }) {
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
      try { await triggerSnapshot(); } catch { /* daily scheduler covers it */ }
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
    <div className="max-w-2xl mx-auto mt-4 mb-8">
      {/* Hero */}
      <div className="text-center mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          Portfolio Tracker
        </h2>
        <p className="text-sm text-gray-500 whitespace-nowrap">
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
          {/* Mini NAV chart with benchmark line */}
          {(() => {
            const nav = [50,48,52,55,53,58,56,60,57,62,64,61,66,68,65,70,72,69,74,76,73,78,80,77,82,85,83,88];
            const bench = [50,49,51,53,52,54,53,55,54,56,57,56,58,59,58,60,61,60,62,63,62,64,65,64,66,67,66,68];
            const h = 64, w = 400, pad = 2;
            const toPath = (pts: number[]) => {
              const min = Math.min(...nav, ...bench), max = Math.max(...nav, ...bench);
              return pts.map((v, i) => {
                const x = pad + (i / (pts.length - 1)) * (w - pad * 2);
                const y = h - pad - ((v - min) / (max - min)) * (h - pad * 2);
                return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
              }).join(" ");
            };
            return (
              <div>
                <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 64 }}>
                  <path d={toPath(bench)} fill="none" stroke="#9ca3af" strokeWidth="1.2" strokeDasharray="3,2" opacity="0.6" />
                  <path d={toPath(nav)} fill="none" stroke="#3b82f6" strokeWidth="1.5" />
                </svg>
                <div className="flex items-center justify-center gap-3 mt-1">
                  <span className="flex items-center gap-1 text-[9px] text-gray-400">
                    <span className="inline-block w-3 h-[2px] bg-blue-500 rounded" /> {zh ? "组合净值" : "Portfolio NAV"}
                  </span>
                  <span className="flex items-center gap-1 text-[9px] text-gray-400">
                    <span className="inline-block w-3 h-[2px] bg-gray-400 rounded" style={{ borderTop: "1px dashed" }} /> {zh ? "基准指数" : "Benchmark"}
                  </span>
                </div>
              </div>
            );
          })()}
        </div>
      </div>

      {/* Feature highlights */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 mb-8 px-4">
        {(zh ? [
          { icon: "🌏", text: "跨市场、跨账户，统一追踪所有持仓与实时行情" },
          { icon: "📈", text: "未实现 & 已实现盈亏、日 / 周 / YTD 收益追踪" },
          { icon: "🎯", text: "资产配置分析（按市场 / 币种 / 行业）" },
          { icon: "📊", text: "净值曲线 + 沪深300 / 恒指 / 标普 基准对比" },
          { icon: "⚡", text: "风险分析 & 收益归因，量化投资表现" },
          { icon: "📰", text: "持仓相关新闻、财报日历、评级变动推送" },
        ] : [
          { icon: "🌏", text: "Cross-market, cross-account — track all positions with live quotes" },
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

      {/* CTA: 3-step wizard is the primary path */}
      <div className="max-w-md mx-auto space-y-3">
        <SetupWizard locale={locale} onRefresh={onRefresh} />
        <input ref={fileRef} type="file" accept=".csv" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImport(f); }} />
        <div className="flex items-center justify-center gap-4">
          <button onClick={() => fileRef.current?.click()} disabled={importing}
            className="text-xs text-gray-400 hover:text-blue-500 underline underline-offset-2">
            {importing ? (zh ? "导入中..." : "Importing...") : (zh ? "或上传 CSV 批量导入" : "or bulk-import CSV")}
          </button>
          <a href={getImportTemplateUrl("portfolio")} download
            className="text-xs text-gray-400 hover:text-blue-500 underline underline-offset-2">
            {zh ? "下载模板" : "Template"}
          </a>
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

const RECON_AUTO_KINDS = ["cash", "cost", "missing_tracker", "qty", "missing_ibkr"];

const reconBtnLabel = (kind: string, zh: boolean) =>
  kind === "missing_tracker" ? (zh ? "建仓入账" : "Add position")
    : kind === "missing_ibkr" ? (zh ? "清仓入账" : "Book close")
    : kind === "qty" ? (zh ? "同步买卖" : "Sync trade")
    : zh ? "对齐" : "Apply";

function IbkrReconBanner({ recon, locale, onApplied }: {
  recon: IbkrRecon; locale: string;
  onApplied: (next: Partial<IbkrRecon> | null) => void;
}) {
  const zh = locale === "zh";
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // "kind:ticker" or "all"
  const [applyError, setApplyError] = useState<string | null>(null);
  const ignoredCount = recon.ignored || 0;
  const costNotes = recon.cost_notes || [];
  const clearAndRefresh = async () => {
    try {
      await clearIbkrReconIgnores();
      const next = await getIbkrRecon().catch(() => null);
      onApplied(next && next.diffs && (next.diffs.length > 0 || (next.ignored || 0) > 0 || (next.cost_notes?.length || 0) > 0) ? next : null);
    } catch { /* ignore */ }
  };
  if (recon.unavailable) {
    return (
      <div className="mb-3 px-4 py-1.5 text-xs text-gray-400 flex items-center gap-2">
        <span>⚠</span>
        <span>
          {zh
            ? "盈透对账暂不可用（IBKR 网关维护中，通常北京时间上午；页面刷新会自动重试）"
            : "IBKR recon unavailable (gateway maintenance window; retries on next page load)"}
        </span>
      </div>
    );
  }
  // Recon ran against the last cached statement because the gateway is down
  // — the data is still yesterday's EOD either way, so just annotate it
  const staleNote = recon.stale && recon.fetched_at
    ? (zh ? `，缓存于 ${recon.fetched_at}` : `, cached ${recon.fetched_at}`)
    : "";
  if (!recon.diffs || (recon.diffs.length === 0 && ignoredCount === 0 && costNotes.length === 0)) return null;
  if (recon.diffs.length === 0) {
    // reconciled — quiet line; cost-basis convention gaps expandable
    return (
      <div className="mb-3 px-4 py-1.5 text-xs text-gray-400">
        <div className="flex items-center gap-2">
          <span>✓</span>
          <span>
            {zh
              ? `盈透对账一致（报表日 ${recon.report_date}${staleNote}${ignoredCount ? `，${ignoredCount} 项已忽略` : ""}${costNotes.length ? `，${costNotes.length} 项成本口径差异仅供参考` : ""}）`
              : `IBKR reconciled (${recon.report_date}${staleNote}${ignoredCount ? `, ${ignoredCount} ignored` : ""}${costNotes.length ? `, ${costNotes.length} cost-basis notes` : ""})`}
          </span>
          {costNotes.length > 0 && (
            <button onClick={() => setOpen(!open)} className="underline hover:text-gray-600">{open ? (zh ? "收起" : "hide") : (zh ? "查看" : "view")}</button>
          )}
          {ignoredCount > 0 && (
            <button onClick={clearAndRefresh} className="underline hover:text-gray-600">{zh ? "恢复已忽略项" : "unhide ignored"}</button>
          )}
        </div>
        {open && costNotes.length > 0 && (
          <div className="mt-1 pl-6 space-y-0.5 font-mono">
            {costNotes.map((d, i) => (
              <div key={i}>{d.ticker}: tracker {d.tracker} vs Flex批次 {d.ibkr}</div>
            ))}
            <div className="font-sans text-[10px] text-gray-400">
              {zh
                ? "Flex 报的是税务批次成本（FIFO），部分卖出/资本性分红后与 TWS 平均成本永久分叉——不是数据错误，无需处理。"
                : "Flex carries tax-lot (FIFO) basis, which diverges from TWS average cost after partial sells — informational, no action needed."}
            </div>
          </div>
        )}
      </div>
    );
  }
  const autoDiffs = recon.diffs.filter((d) => RECON_AUTO_KINDS.includes(d.kind));

  const refresh = async () => {
    const next = await getIbkrRecon().catch(() => null);
    onApplied(next && next.diffs && (next.diffs.length > 0 || (next.ignored || 0) > 0 || (next.cost_notes?.length || 0) > 0) ? next : null);
  };

  const apply = async (items: { kind: string; ticker: string }[], busyKey: string) => {
    setBusy(busyKey); setApplyError(null);
    try {
      const res = await applyIbkrRecon(items);
      if (res.skipped?.length) {
        setApplyError(zh
          ? `${res.skipped.length} 项未应用（${res.skipped.map((s) => s.ticker).join("、")}），请在管理面板手动处理`
          : `${res.skipped.length} item(s) skipped (${res.skipped.map((s) => s.ticker).join(", ")}) — apply manually via the Manage panel`);
      }
      await refresh();
    } catch (e: unknown) {
      setApplyError(e instanceof Error ? e.message : zh ? "应用失败" : "Apply failed");
    } finally { setBusy(null); }
  };

  const ignore = async (items: { kind: string; ticker: string }[], busyKey: string) => {
    setBusy(busyKey); setApplyError(null);
    try {
      await ignoreIbkrRecon(items);
      await refresh();
    } catch (e: unknown) {
      setApplyError(e instanceof Error ? e.message : zh ? "忽略失败" : "Ignore failed");
    } finally { setBusy(null); }
  };

  return (
    <div className="mb-3 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-4 py-2 text-sm">
      <button onClick={() => setOpen(!open)} className="w-full text-left flex items-center gap-2">
        <span>🔄</span>
        <span className="text-amber-800 dark:text-amber-300 font-medium">
          {zh
            ? `盈透对账：${recon.diffs.length} 项差异待确认（报表日 ${recon.report_date}${staleNote}）`
            : `IBKR recon: ${recon.diffs.length} difference(s), statement ${recon.report_date}${staleNote}`}
        </span>
        <span className="ml-auto text-amber-600 dark:text-amber-400 text-xs">{open ? (zh ? "收起 ▲" : "Hide ▲") : (zh ? "查看 ▼" : "View ▼")}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1 text-xs text-amber-900 dark:text-amber-200">
          {recon.diffs.map((d, i) => (
            <div key={i} className="flex flex-wrap items-center gap-x-2">
              <span className="font-mono font-medium">{d.ticker}</span>
              <span>{d.note}</span>
              {(d.kind === "qty" || d.kind === "cost" || d.kind === "cash") && (
                <span className="font-mono">tracker {d.tracker} → IBKR {d.ibkr}</span>
              )}
              {RECON_AUTO_KINDS.includes(d.kind) && (
                <button
                  onClick={() => apply([{ kind: d.kind, ticker: d.ticker }], `${d.kind}:${d.ticker}`)}
                  disabled={busy !== null}
                  className="px-1.5 py-0.5 rounded border border-amber-400 dark:border-amber-600 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-800/40 disabled:opacity-50"
                >
                  {busy === `${d.kind}:${d.ticker}` ? "…" : reconBtnLabel(d.kind, zh)}
                </button>
              )}
              <button
                onClick={() => ignore([{ kind: d.kind, ticker: d.ticker }], `ig:${d.kind}:${d.ticker}`)}
                disabled={busy !== null}
                title={zh ? "已知的口径差异（如转仓保留原始成本），钉在当前双方数值上——任一侧变动会重新出现" : "Known intentional diff — pinned to both sides' values; reappears if either moves"}
                className="px-1.5 py-0.5 rounded border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800/40 disabled:opacity-50"
              >
                {busy === `ig:${d.kind}:${d.ticker}` ? "…" : zh ? "忽略" : "Ignore"}
              </button>
            </div>
          ))}
          {costNotes.length > 0 && (
            <div className="pt-1 text-gray-400 space-y-0.5">
              <div className="text-[10px] uppercase">{zh ? "成本口径参考（不需处理）" : "Cost-basis notes (no action)"}</div>
              {costNotes.map((d, i) => (
                <div key={i} className="font-mono">{d.ticker}: tracker {d.tracker} vs Flex批次 {d.ibkr}</div>
              ))}
            </div>
          )}
          {applyError && (
            <div className="pt-1 text-red-600 dark:text-red-400">{applyError}</div>
          )}
          <div className="pt-1 flex flex-wrap items-center gap-2 text-amber-600 dark:text-amber-400">
            {autoDiffs.length > 1 && (
              <button
                onClick={() => apply(autoDiffs.map((d) => ({ kind: d.kind, ticker: d.ticker })), "all")}
                disabled={busy !== null}
                className="px-2 py-0.5 rounded border border-amber-400 dark:border-amber-600 font-medium text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-800/40 disabled:opacity-50"
              >
                {busy === "all"
                  ? (zh ? "应用中…" : "Applying…")
                  : zh ? `一键应用全部可自动项（${autoDiffs.length} 项）` : `Apply all auto-appliable diffs (${autoDiffs.length})`}
              </button>
            )}
            <span>
              {zh
                ? "全部差异均可一键入账：现金/成本照抄盈透；新持仓自动建仓；买入照抄新均价；卖出/清仓按报表成交明细自动记已实现盈亏（与「交易」页同一套归因逻辑）。刻意保留的口径差（如转仓原始成本）用「忽略」挂白名单。"
                : "Everything is one-click: cash/cost copy IBKR; new positions are created; buys copy the new average; sells/closes book realized P&L from actual fills. Use Ignore for intentional convention diffs (e.g. transfer-in costs)."}
            </span>
            {ignoredCount > 0 && (
              <button onClick={clearAndRefresh} className="underline">
                {zh ? `另有 ${ignoredCount} 项已忽略 · 恢复显示` : `${ignoredCount} ignored · show`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

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
  const showMode = false; // capital_mode retired — unified capital needs no mode choice
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

function DataPanel({ holdings, data, locale, onRefresh, open, onClose, editHolding, initialTab = "edit", tradeTarget, tradeDir, flowDir }: {
  holdings: PortfolioHolding[]; data: PortfolioData | null; locale: string;
  onRefresh: () => void; open: boolean; onClose: () => void;
  editHolding?: PortfolioHolding | null;
  initialTab?: "edit" | "close" | "cash" | "flows" | "settings";
  tradeTarget?: PortfolioHolding | null;
  tradeDir?: "buy" | "sell" | null;
  flowDir?: "in" | "out" | null;
}) {
  const [tab, setTab] = useState<"edit" | "close" | "cash" | "flows" | "settings">(initialTab);

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
  const [editOrigBroker, setEditOrigBroker] = useState("");
  const [editQty, setEditQty] = useState("");
  const [editCost, setEditCost] = useState("");
  const [editCurrency, setEditCurrency] = useState("CNY");
  const [isEditing, setIsEditing] = useState(false);

  // ── Close tab state ──
  const [closeSearch, setCloseSearch] = useState("");
  const [closeTarget, setCloseTarget] = useState<PortfolioHolding | null>(null);
  const [closeQty, setCloseQty] = useState("");
  const [closePrice, setClosePrice] = useState("");
  const [closeFee, setCloseFee] = useState("");       // diluted partial: fees fold into cost
  const [closeNewCost, setCloseNewCost] = useState(""); // diluted partial: computed, editable
  // Assisted buy (加仓): same weighted-average math for both cost methods
  const [tradeDirection, setTradeDirection] = useState<"sell" | "buy">("sell");
  const [buyQty, setBuyQty] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [buyFee, setBuyFee] = useState("");
  const [buyNewCost, setBuyNewCost] = useState(""); // computed, editable
  // Open a brand-new position from the Trade tab (buy semantics: cash is
  // deducted, YTD baseline starts at cost — unlike the raw Positions editor)
  const [openingNew, setOpeningNew] = useState(false);
  const [newTicker, setNewTicker] = useState("");
  const [newName, setNewName] = useState("");
  const [newMarket, setNewMarket] = useState("美股");
  const [newBroker, setNewBroker] = useState("");
  const [newCurrency, setNewCurrency] = useState("USD");

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
  const [acctCostMethod, setAcctCostMethod] = useState<"diluted" | "average">("diluted");
  const [acctHkConnect, setAcctHkConnect] = useState(false);
  const [acctDeposit, setAcctDeposit] = useState("");
  const [acctFx, setAcctFx] = useState("1.0");
  const [depositAction, setDepositAction] = useState<"update" | "add">("update");
  const [depositDate, setDepositDate] = useState("");
  // Cash-flow entry (TWR unit engine consumes dated flows)
  const [flowDirection, setFlowDirection] = useState<"in" | "out">("in");
  const [flowCurrency, setFlowCurrency] = useState("CNY");
  const [flowUpdateCash, setFlowUpdateCash] = useState(true);
  const [depositNotes, setDepositNotes] = useState("");
  const [depositHistory, setDepositHistory] = useState<DepositRecord[]>([]);
  const [expandedBroker, setExpandedBroker] = useState<string | null>(null);
  // Flows tab
  const [flowBroker, setFlowBroker] = useState("");
  const [flowHistory, setFlowHistory] = useState<DepositRecord[]>([]);

  useEffect(() => {
    if (open) {
      getAccountSettings().then(setAcctSettings).catch(() => {});
      getMarginBalances().then(setMarginData).catch(() => {});
    }
  }, [open]);

  useEffect(() => {
    if (open && tab === "flows") getAllFlows().then(setFlowHistory).catch(() => {});
  }, [open, tab]);

  const inputCls = "w-full px-2 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:ring-1 focus:ring-blue-500 focus:outline-none";
  const zh = locale === "zh";

  // ── Pre-fill from external edit request ──
  useEffect(() => {
    if (open && tradeTarget) {
      selectCloseTarget(tradeTarget);
      if (tradeDir) setTradeDirection(tradeDir);
    }
    if (open && flowDir) setFlowDirection(flowDir);
    if (editHolding && open) {
      setTab("edit");
      fillForm(editHolding);
    }
  }, [editHolding, open]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Edit handlers ──
  function fillForm(h: PortfolioHolding) {
    setEditTicker(h.ticker); setEditName(h.name); setEditMarket(h.market);
    setEditBroker(h.broker); setEditOrigBroker(h.broker); setEditQty(String(h.quantity)); setEditCost(String(h.cost_price)); setEditCurrency(h.currency);
    setIsEditing(true);
  }

  function clearForm() {
    setEditTicker(""); setEditName(""); setEditMarket("A股"); setEditBroker(""); setEditOrigBroker("");
    setEditQty(""); setEditCost(""); setEditCurrency("CNY"); setIsEditing(false);
  }

  async function handleSave() {
    if (!editTicker || !editName) return;
    if (!editBroker) { setMsg(zh ? "⚠️ 请先选择账户，如需新账户请到「设置」添加" : "⚠️ Select an account first. Add new accounts in Settings tab"); return; }
    setSaving(true); setMsg(null);
    try {
      if (isEditing && editOrigBroker && editOrigBroker !== editBroker) {
        await deletePosition(editTicker, editOrigBroker);
      }
      await upsertPosition({ ticker: editTicker, name: editName, market: editMarket, broker: editBroker,
        quantity: parseFloat(editQty) || 0, cost_price: parseFloat(editCost) || 0, currency: editCurrency });
      setMsg("✅ Saved"); clearForm(); onRefresh();
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  async function handleDelete(ticker: string, broker: string) {
    if (!confirm(zh
      ? `确认删除 ${ticker} (${broker})？此操作不可恢复。\n\n⚠️ 删除不会记录已实现盈亏——如果是清仓，请改用「部分卖出」标签页（卖出全部数量），否则收益会从统计中消失。`
      : `Confirm delete ${ticker} (${broker})? This cannot be undone.\n\n⚠️ Deleting books NO realized P&L — if you sold out, use the "Close" tab (sell the full quantity) instead, or the gains vanish from your stats.`)) return;
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
    setCloseFee(""); setCloseNewCost("");
    setBuyQty(""); setBuyPrice(h.price ? String(h.price) : ""); setBuyFee(""); setBuyNewCost("");
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

  // Per-broker cost convention ('diluted' default | 'average'). Used to steer
  // partial-sell / edit workflows to the right entry point per account.
  const brokerCostMethod = (broker: string): "diluted" | "average" =>
    (acctSettings.find((s) => s.broker === broker)?.cost_method as "diluted" | "average") || "diluted";

  // Diluted partial sell: assisted flow — same accounting semantics as the
  // manual Edit path (no closed_trade; realized gain absorbed into cost),
  // but the system computes the new diluted cost and books the cash.
  const dilutedPartial = !!closeTarget && closePnl != null
    && brokerCostMethod(closeTarget.broker) === "diluted"
    && closePnl.qty > 0 && closePnl.qty < closeTarget.quantity;

  // Broker formula: new cost = (old basis − net proceeds) / remaining qty.
  // Fee is deducted from proceeds, matching how brokers fold fees into the
  // diluted cost. Prefilled but editable — paste the broker's exact number
  // if it differs by a hair.
  useEffect(() => {
    if (!dilutedPartial || !closeTarget || !closePnl) return;
    const fee = parseFloat(closeFee) || 0;
    const remaining = closeTarget.quantity - closePnl.qty;
    if (remaining <= 0 || closePnl.sellPrice <= 0) return;
    const netProceeds = closePnl.qty * closePnl.sellPrice - fee;
    const newCost = (closeTarget.quantity * closeTarget.cost_price - netProceeds) / remaining;
    setCloseNewCost(newCost.toFixed(4));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dilutedPartial, closeQty, closePrice, closeFee, closeTarget]);

  // Buying math is identical for diluted & average cost methods:
  // new cost = (old basis + buy cost + fee) / new qty
  useEffect(() => {
    if (!closeTarget || tradeDirection !== "buy") return;
    const qty = parseFloat(buyQty) || 0;
    const price = parseFloat(buyPrice) || 0;
    const fee = parseFloat(buyFee) || 0;
    if (qty <= 0 || price <= 0) return;
    const newQty = closeTarget.quantity + qty;
    const newCost = (closeTarget.quantity * closeTarget.cost_price + qty * price + fee) / newQty;
    setBuyNewCost(newCost.toFixed(4));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tradeDirection, buyQty, buyPrice, buyFee, closeTarget]);

  async function handleBuy() {
    if (!closeTarget) return;
    const qty = parseFloat(buyQty) || 0;
    const price = parseFloat(buyPrice) || 0;
    const fee = parseFloat(buyFee) || 0;
    const newCost = parseFloat(buyNewCost);
    if (qty <= 0 || price <= 0 || !Number.isFinite(newCost)) return;
    const newQty = closeTarget.quantity + qty;
    let outlay = qty * price + fee;
    let cur = closeTarget.currency;
    // market values are Chinese labels ("港股"), not ISO-ish codes
    const isHkConnect = closeTarget.market === "港股"
      && !!acctSettings.find((s) => s.broker === closeTarget.broker)?.hk_connect;
    if (isHkConnect && cur !== "CNY") {
      outlay = outlay * (data?.fx?.[cur] || 1.0);
      cur = "CNY";
    }
    const msg = zh
      ? `加仓 ${closeTarget.name}\n买入: ${qty} @ ${price}${fee ? `（手续费 ${fee.toFixed(2)}）` : ""}\n新持仓: ${fmtNum(newQty, 0)} @ 新成本 ${newCost}\n将从现金扣除: ${outlay.toFixed(2)} ${cur}${isHkConnect ? "（港股通已折人民币）" : ""}\n（现金不足会记为负余额=融资）`
      : `Buy more ${closeTarget.name}\nBuy: ${qty} @ ${price}${fee ? ` (fee ${fee.toFixed(2)})` : ""}\nNew position: ${fmtNum(newQty, 0)} @ cost ${newCost}\nCash deduction: ${outlay.toFixed(2)} ${cur}${isHkConnect ? " (HK Connect → CNY)" : ""}\n(Shortfall becomes a negative balance = margin)`;
    if (!confirm(msg)) return;
    setSaving(true);
    try {
      await upsertPosition({
        ticker: closeTarget.ticker, name: closeTarget.name, market: closeTarget.market,
        broker: closeTarget.broker, quantity: newQty,
        cost_price: newCost, currency: closeTarget.currency,
      });
      const cashRow = (data?.cash || []).find((c) => c.account === closeTarget.broker && c.currency === cur);
      await updateCash({ account: closeTarget.broker, currency: cur, balance: (cashRow?.balance || 0) - outlay });
      setCloseTarget(null); setCloseSearch("");
      setMsg(`✅ ${zh ? "已加仓" : "Bought"}`); onRefresh();
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  const MARKET_DEFAULT_CCY: Record<string, string> = {
    "A股": "CNY", "基金": "CNY", "港股": "HKD", "B股": "HKD", "美股": "USD", "日股": "JPY",
  };

  async function handleOpenNew() {
    const qty = parseFloat(buyQty) || 0;
    const price = parseFloat(buyPrice) || 0;
    const fee = parseFloat(buyFee) || 0;
    const ticker = newTicker.trim();
    if (!ticker || !newName.trim() || !newBroker || qty <= 0 || price <= 0) return;
    const existing = holdings.find((h) => h.ticker === ticker && h.broker === newBroker);
    if (existing) {
      // already held on this account — upsert would clobber qty/cost, so
      // route the entered numbers into the add-to-position flow instead
      selectCloseTarget(existing);
      setTradeDirection("buy");
      setBuyQty(String(qty)); setBuyPrice(String(price)); if (fee) setBuyFee(String(fee));
      setOpeningNew(false);
      setMsg(zh ? "⚠️ 该账户已持有此标的，已切换为「加仓」" : "⚠️ Already held on this account — switched to Buy/Add");
      return;
    }
    const cost = (qty * price + fee) / qty;
    let outlay = qty * price + fee;
    let cur = newCurrency;
    const isHkConnect = newMarket === "港股"
      && !!acctSettings.find((s) => s.broker === newBroker)?.hk_connect;
    if (isHkConnect && cur !== "CNY") {
      outlay = outlay * (data?.fx?.[cur] || 1.0);
      cur = "CNY";
    }
    const confirmMsg = zh
      ? `新开仓 ${newName.trim()}（${ticker}）\n买入: ${qty} @ ${price}${fee ? `（手续费 ${fee.toFixed(2)}，摊入成本）` : ""}\n成本: ${cost.toFixed(4)} ${newCurrency}\n将从「${newBroker}」现金扣除: ${outlay.toFixed(2)} ${cur}${isHkConnect ? "（港股通已折人民币）" : ""}\n（现金不足会记为负余额=融资）`
      : `Open ${newName.trim()} (${ticker})\nBuy: ${qty} @ ${price}${fee ? ` (fee ${fee.toFixed(2)}, folds into cost)` : ""}\nCost: ${cost.toFixed(4)} ${newCurrency}\nCash deduction from "${newBroker}": ${outlay.toFixed(2)} ${cur}${isHkConnect ? " (HK Connect → CNY)" : ""}\n(Shortfall becomes a negative balance = margin)`;
    if (!confirm(confirmMsg)) return;
    setSaving(true);
    try {
      await upsertPosition({
        ticker, name: newName.trim(), market: newMarket, broker: newBroker,
        quantity: qty, cost_price: cost, currency: newCurrency,
      });
      const cashRow = (data?.cash || []).find((c) => c.account === newBroker && c.currency === cur);
      await updateCash({ account: newBroker, currency: cur, balance: (cashRow?.balance || 0) - outlay });
      setOpeningNew(false); setNewTicker(""); setNewName("");
      setBuyQty(""); setBuyPrice(""); setBuyFee("");
      setMsg(`✅ ${zh ? "已开仓" : "Opened"}`); onRefresh();
    } catch { setMsg("❌ Error"); } finally { setSaving(false); }
  }

  /** Credit sale proceeds to signed cash (negative balances net margin
   *  automatically); 港股通 HK sales convert to CNY at the day's FX. */
  async function autoBookProceeds(amount: number) {
    if (!closeTarget) return;
    let proceeds = amount;
    let cur = closeTarget.currency;
    const isHkConnect = closeTarget.market === "港股"
      && !!acctSettings.find((s) => s.broker === closeTarget.broker)?.hk_connect;
    if (isHkConnect && cur !== "CNY") {
      const rate = data?.fx?.[cur] || 1.0;
      proceeds = proceeds * rate;
      cur = "CNY";
    }
    const ok = confirm(zh
      ? `是否自动将卖出所得 ${proceeds.toFixed(2)} ${cur} 计入现金？${isHkConnect ? "\n（港股通：已按汇率折算为人民币）" : ""}\n负余额（融资）会被自动冲抵。\n（取消 = 不入账，自行手动管理）`
      : `Auto-credit sale proceeds ${proceeds.toFixed(2)} ${cur} to cash?${isHkConnect ? "\n(HK Connect: converted to CNY at FX)" : ""}\nNegative balances (margin) net automatically.\n(Cancel = manage manually)`);
    if (ok) {
      const cashRow = (data?.cash || []).find((c) => c.account === closeTarget.broker && c.currency === cur);
      await updateCash({ account: closeTarget.broker, currency: cur, balance: (cashRow?.balance || 0) + proceeds });
    }
  }

  // Warn: reducing qty via Edit on an average-cost account skips the closed_trade,
  // so realized P&L is never booked. → use the Close tab for reductions.
  const editAvgReduceWarn = (() => {
    if (!isEditing || !editBroker || brokerCostMethod(editBroker) !== "average") return false;
    const orig = holdings.find((h) => h.ticker === editTicker && h.broker === editBroker);
    const newQty = parseFloat(editQty);
    return !!orig && Number.isFinite(newQty) && newQty > 0 && newQty < orig.quantity;
  })();

  // Warn: editing qty to 0 (any account) skips the closed_trade entirely —
  // the position's realized P&L is never booked. Full close must go through
  // the Close tab.
  const editZeroWarn = (() => {
    if (!isEditing || !editBroker) return false;
    const orig = holdings.find((h) => h.ticker === editTicker && h.broker === editBroker);
    const newQty = parseFloat(editQty);
    return !!orig && orig.quantity > 0 && Number.isFinite(newQty) && newQty <= 0;
  })();

  async function handleClose() {
    if (!closeTarget || !closePnl) return;
    const qty = closePnl.qty;
    const fullClose = qty >= closeTarget.quantity;

    // ── Diluted partial sell: Edit-equivalent semantics, automated ──
    if (dilutedPartial) {
      const fee = parseFloat(closeFee) || 0;
      const newCost = parseFloat(closeNewCost);
      if (!Number.isFinite(newCost)) { alert(zh ? "请填写新成本" : "New cost required"); return; }
      const remaining = closeTarget.quantity - qty;
      const netProceeds = qty * closePnl.sellPrice - fee;
      const msg = zh
        ? `摊薄减仓 ${closeTarget.name}\n卖出: ${qty} @ ${closePnl.sellPrice}${fee ? `（手续费 ${fee.toFixed(2)}）` : ""}\n净回款: ${netProceeds.toFixed(2)} ${closePnl.currency}\n剩余: ${fmtNum(remaining, 0)} @ 新成本 ${newCost}\n（不记已实现盈亏——收益已摊入成本，与券商口径一致）`
        : `Diluted reduce ${closeTarget.name}\nSell: ${qty} @ ${closePnl.sellPrice}${fee ? ` (fee ${fee.toFixed(2)})` : ""}\nNet proceeds: ${netProceeds.toFixed(2)} ${closePnl.currency}\nRemaining: ${fmtNum(remaining, 0)} @ new cost ${newCost}\n(No realized P&L booked — absorbed into cost, matching the broker)`;
      if (!confirm(msg)) return;
      setSaving(true);
      try {
        await upsertPosition({
          ticker: closeTarget.ticker, name: closeTarget.name, market: closeTarget.market,
          broker: closeTarget.broker, quantity: remaining,
          cost_price: newCost, currency: closeTarget.currency,
        });
        await autoBookProceeds(netProceeds);
        setCloseTarget(null); setCloseSearch(""); setCloseFee(""); setCloseNewCost("");
        setMsg(`✅ ${zh ? "已减仓" : "Reduced"}`); onRefresh();
      } catch { setMsg("❌ Error"); } finally { setSaving(false); }
      return;
    }

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

      await autoBookProceeds(qty * closePnl.sellPrice);

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

  /** Record a signed, dated cash flow. The date is mandatory: the TWR unit
   *  engine converts flows into units at that day's NAV. */
  async function submitFlow(broker: string): Promise<boolean> {
    const amt = parseFloat(acctDeposit) || 0;
    if (!amt) return false;
    if (!depositDate) {
      alert(zh
        ? "请填写日期——净值(TWR)计算需要每笔资金流的准确日期"
        : "Date is required — TWR unit accounting needs the exact flow date");
      return false;
    }
    const fx = flowCurrency === "CNY" ? 1.0 : parseFloat(acctFx) || 1.0;
    const sign = flowDirection === "in" ? 1 : -1;
    await addDepositRecord({
      broker,
      amount_cny: sign * amt,
      fx_rate: fx,
      deposit_date: depositDate,
      notes: depositNotes,
      currency: flowCurrency,
      update_cash: flowUpdateCash,
    });
    return true;
  }

  async function handleAcctSave() {
    const broker = isNewAcct ? newAcctName.trim() : acctBroker;
    if (!broker) return;
    setSaving(true);
    try {
      {
        // Direct update (overwrite totals)
        await upsertAccountSetting({ broker, capital_mode: acctMode,
          deposit_cny: parseFloat(acctDeposit) || 0, deposit_fx: parseFloat(acctFx) || 1.0,
          cost_method: acctCostMethod, hk_connect: acctHkConnect });
      }
      setAcctSettings(await getAccountSettings());
      setAcctBroker(""); setNewAcctName(""); setIsNewAcct(false);
      setAcctDeposit(""); setAcctFx("1.0"); setAcctMode("cost"); setAcctCostMethod("diluted");
      setDepositAction("update"); setDepositDate(""); setDepositNotes("");
      setFlowDirection("in"); setFlowCurrency("CNY"); setFlowUpdateCash(true);
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
          <div className={tabCls("close")} onClick={() => { setTab("close"); setMsg(null); }}>{zh ? "交易" : "Trade"}</div>
          <div className={tabCls("cash")} onClick={() => { setTab("cash"); setMsg(null); }}>{zh ? "现金/杠杆" : "Cash/Margin"}</div>
          <div className={tabCls("flows")} onClick={() => { setTab("flows"); setMsg(null); }}>{zh ? "资金流" : "Flows"}</div>
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
                {!isEditing && (
                  <div className="mb-2 text-[10px] text-gray-400 leading-relaxed">
                    {zh
                      ? "此处新增不联动现金，适合转仓入库/初始导入/照抄券商。正常买入请走「交易」→ 新开仓（自动扣现金）。"
                      : "Adding here does NOT touch cash — meant for transfers-in, initial imports, or copying the broker. For a normal buy, use Trade → Open new position (cash auto-deducted)."}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <input className={inputCls} placeholder="Ticker" value={editTicker} onChange={(e) => setEditTicker(e.target.value.toUpperCase())} disabled={isEditing} />
                  <input className={inputCls} placeholder={zh ? "名称" : "Name"} value={editName} onChange={(e) => setEditName(e.target.value)} />
                  <select className={inputCls} value={editMarket} onChange={(e) => setEditMarket(e.target.value)}>
                    {["A股", "港股", "美股", "日股", "B股", "基金"].map((m) => <option key={m} value={m}>{mktLabel(m, locale)}</option>)}
                  </select>
                  <div>
                    <select className={inputCls} value={editBroker} onChange={(e) => setEditBroker(e.target.value)}>
                      <option value="">{zh ? "— 选择账户 —" : "— Select account —"}</option>
                      {acctSettings.map((s) => <option key={s.broker} value={s.broker}>{s.broker}</option>)}
                    </select>
                    {acctSettings.length === 0 && <div className="text-[9px] text-amber-500 mt-0.5">{zh ? "请先到「设置」添加账户" : "Add accounts in Settings first"}</div>}
                  </div>
                  <input className={inputCls} placeholder={zh ? "数量" : "Quantity"} inputMode="decimal" value={editQty} onChange={(e) => setEditQty(e.target.value)} />
                  <input className={inputCls} placeholder={zh ? "成本价" : "Cost price"} inputMode="decimal" value={editCost} onChange={(e) => setEditCost(e.target.value)} />
                  <select className={inputCls} value={editCurrency} onChange={(e) => setEditCurrency(e.target.value)}>
                    {["CNY", "HKD", "USD", "JPY"].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                {editAvgReduceWarn && (
                  <div className="p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-800 text-[11px] text-amber-800 dark:text-amber-200 leading-relaxed">
                    {zh
                      ? `⚠️「${editBroker}」是平均口径账户。减仓请改用「部分卖出」标签页——直接在这里改小数量不会记录已实现盈亏，Capital 和 YTD 会算错。`
                      : `⚠️ "${editBroker}" uses average cost. Reduce positions via the "Close" tab — lowering the quantity here skips the realized-P&L record, corrupting Capital and YTD.`}
                  </div>
                )}
                {editZeroWarn && (
                  <div className="p-2 rounded bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-800 text-[11px] text-red-800 dark:text-red-200 leading-relaxed">
                    {zh
                      ? "⚠️ 数量改为 0 不会记录已实现盈亏，这部分收益会从系统中消失。清仓请到「部分卖出」标签页操作（卖出全部数量）。"
                      : "⚠️ Setting quantity to 0 books no realized P&L — those gains vanish from the system. To close out, use the \"Close\" tab (sell the full quantity)."}
                  </div>
                )}
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
                {zh ? "选择持仓进行买卖（卖出自动记盈亏、买入自动算新成本，现金联动扣减/入账），或新开仓买入当前没有的标的。" : "Pick a holding to buy/sell (P&L booked on sells, cost recomputed on buys, cash auto-adjusted), or open a brand-new position."}
              </div>

              {!closeTarget && openingNew ? (
                <div className="p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[10px] text-gray-500 uppercase">{zh ? "新开仓（买入新标的）" : "Open New Position"}</div>
                    <button onClick={() => setOpeningNew(false)} className="text-xs text-blue-500 hover:text-blue-700">{zh ? "← 返回" : "← Back"}</button>
                  </div>
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <input className={inputCls} placeholder="Ticker" value={newTicker} onChange={(e) => setNewTicker(e.target.value.toUpperCase())} />
                    <input className={inputCls} placeholder={zh ? "名称" : "Name"} value={newName} onChange={(e) => setNewName(e.target.value)} />
                    <select className={inputCls} value={newMarket}
                      onChange={(e) => { setNewMarket(e.target.value); setNewCurrency(MARKET_DEFAULT_CCY[e.target.value] || "USD"); }}>
                      {["A股", "港股", "美股", "日股", "B股", "基金"].map((m) => <option key={m} value={m}>{mktLabel(m, locale)}</option>)}
                    </select>
                    <div>
                      <select className={inputCls} value={newBroker} onChange={(e) => setNewBroker(e.target.value)}>
                        <option value="">{zh ? "— 选择账户 —" : "— Select account —"}</option>
                        {acctSettings.map((s) => <option key={s.broker} value={s.broker}>{s.broker}</option>)}
                      </select>
                      {acctSettings.length === 0 && <div className="text-[9px] text-amber-500 mt-0.5">{zh ? "请先到「设置」添加账户" : "Add accounts in Settings first"}</div>}
                    </div>
                    <input className={inputCls} placeholder={zh ? "买入数量" : "Buy qty"} inputMode="decimal" value={buyQty} onChange={(e) => setBuyQty(e.target.value)} />
                    <input className={inputCls} placeholder={zh ? "买入价格" : "Buy price"} inputMode="decimal" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} />
                    <input className={inputCls} placeholder={zh ? "手续费（选填，摊入成本）" : "Fees (optional)"} inputMode="decimal" value={buyFee} onChange={(e) => setBuyFee(e.target.value)} />
                    <select className={inputCls} value={newCurrency} onChange={(e) => setNewCurrency(e.target.value)}>
                      {["CNY", "HKD", "USD", "JPY"].map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  {parseFloat(buyQty) > 0 && parseFloat(buyPrice) > 0 && (
                    <div className="mb-3 text-[10px] font-mono text-gray-500">
                      {zh ? "成本" : "Cost"} {(((parseFloat(buyQty) || 0) * (parseFloat(buyPrice) || 0) + (parseFloat(buyFee) || 0)) / (parseFloat(buyQty) || 1)).toFixed(4)} · {zh ? "扣现金" : "cash out"} {((parseFloat(buyQty) || 0) * (parseFloat(buyPrice) || 0) + (parseFloat(buyFee) || 0)).toFixed(2)} {newCurrency}
                    </div>
                  )}
                  <button onClick={handleOpenNew}
                    disabled={saving || !newTicker.trim() || !newName.trim() || !newBroker || !(parseFloat(buyQty) > 0) || !(parseFloat(buyPrice) > 0)}
                    className="w-full px-3 py-2 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 font-medium">
                    {saving ? "..." : (zh ? "确认开仓" : "Confirm Open")}
                  </button>
                </div>
              ) : !closeTarget ? (
                <>
                  <input className={`${inputCls} mb-2`} placeholder={zh ? "🔍 搜索持仓" : "🔍 Search positions"}
                    value={closeSearch} onChange={(e) => setCloseSearch(e.target.value)} />
                  <button onClick={() => { setOpeningNew(true); setBuyQty(""); setBuyPrice(""); setBuyFee(""); setMsg(null); }}
                    className="w-full mb-2 px-2 py-1.5 text-xs rounded border border-dashed border-green-400 dark:border-green-700 text-green-700 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/10 transition-colors">
                    {zh ? "＋ 新开仓（买入当前没有的标的）" : "+ Open new position (buy a new ticker)"}
                  </button>
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

                  {/* Direction toggle */}
                  <div className="flex rounded overflow-hidden border border-gray-300 dark:border-gray-700 mb-3">
                    <button type="button" onClick={() => setTradeDirection("sell")}
                      className={`flex-1 text-xs py-1.5 font-medium transition-colors ${tradeDirection === "sell" ? "bg-red-600 text-white" : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-100"}`}>
                      {zh ? "卖出 / 减仓" : "Sell / Reduce"}
                    </button>
                    <button type="button" onClick={() => setTradeDirection("buy")}
                      className={`flex-1 text-xs py-1.5 font-medium transition-colors ${tradeDirection === "buy" ? "bg-green-600 text-white" : "bg-white dark:bg-gray-900 text-gray-500 hover:bg-gray-100"}`}>
                      {zh ? "买入 / 加仓" : "Buy / Add"}
                    </button>
                  </div>

                  {tradeDirection === "buy" ? (
                    <>
                      <div className="grid grid-cols-2 gap-2 mb-3">
                        <div>
                          <div className="text-[10px] text-gray-500 mb-1">{zh ? "买入数量" : "Buy Qty"}</div>
                          <input className={inputCls} inputMode="decimal" value={buyQty} onChange={(e) => setBuyQty(e.target.value)} />
                        </div>
                        <div>
                          <div className="text-[10px] text-gray-500 mb-1">{zh ? "买入价格" : "Buy Price"}</div>
                          <input className={inputCls} inputMode="decimal" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} />
                        </div>
                        <div>
                          <div className="text-[10px] text-gray-500 mb-1">{zh ? "手续费（选填，摊入成本）" : "Fees (optional)"}</div>
                          <input className={inputCls} inputMode="decimal" placeholder="0" value={buyFee} onChange={(e) => setBuyFee(e.target.value)} />
                        </div>
                        <div>
                          <div className="text-[10px] text-gray-500 mb-1">{zh ? "新成本（可改为券商精确值）" : "New cost (editable)"}</div>
                          <input className={inputCls} inputMode="decimal" value={buyNewCost} onChange={(e) => setBuyNewCost(e.target.value)} />
                        </div>
                      </div>
                      {parseFloat(buyQty) > 0 && parseFloat(buyPrice) > 0 && (
                        <div className="mb-3 text-[10px] font-mono text-gray-500">
                          {zh ? "新持仓" : "New position"} {fmtNum(closeTarget.quantity + (parseFloat(buyQty) || 0), 0)} · {zh ? "扣现金" : "cash out"} {((parseFloat(buyQty) || 0) * (parseFloat(buyPrice) || 0) + (parseFloat(buyFee) || 0)).toFixed(2)} {closeTarget.currency}
                        </div>
                      )}
                      <button onClick={handleBuy} disabled={saving || !(parseFloat(buyQty) > 0) || !(parseFloat(buyPrice) > 0)}
                        className="w-full px-3 py-2 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 font-medium">
                        {saving ? "..." : (zh ? "确认买入" : "Confirm Buy")}
                      </button>
                    </>
                  ) : (
                  <>
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

                  {dilutedPartial && (
                    <div className="mb-3 p-2 rounded bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 space-y-2">
                      <div className="text-[11px] text-blue-800 dark:text-blue-200 leading-relaxed">
                        {zh
                          ? `「${closeTarget.broker}」是摊薄口径：本次减仓不记已实现盈亏，收益摊入剩余持仓成本（与券商一致），现金自动入账。`
                          : `"${closeTarget.broker}" uses diluted cost: no realized P&L is booked — the gain folds into the remaining cost (matching the broker) and cash is credited automatically.`}
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <div className="text-[10px] text-gray-500 mb-1">{zh ? "手续费（选填，摊入成本）" : "Fees (optional, folds into cost)"}</div>
                          <input className={inputCls} inputMode="decimal" placeholder="0"
                            value={closeFee} onChange={(e) => setCloseFee(e.target.value)} />
                        </div>
                        <div>
                          <div className="text-[10px] text-gray-500 mb-1">{zh ? "新摊薄成本（可改为券商精确值）" : "New diluted cost (editable)"}</div>
                          <input className={inputCls} inputMode="decimal"
                            value={closeNewCost} onChange={(e) => setCloseNewCost(e.target.value)} />
                        </div>
                      </div>
                      {closePnl && closePnl.qty > 0 && closePnl.sellPrice > 0 && (
                        <div className="text-[10px] font-mono text-gray-500">
                          {zh ? "剩余" : "Remaining"} {fmtNum(closeTarget.quantity - closePnl.qty, 0)} · {zh ? "净回款" : "Net proceeds"} {(closePnl.qty * closePnl.sellPrice - (parseFloat(closeFee) || 0)).toFixed(2)} {closePnl.currency}
                        </div>
                      )}
                    </div>
                  )}

                  <button onClick={handleClose} disabled={saving || !closePnl || closePnl.qty <= 0 || closePnl.sellPrice <= 0}
                    className="w-full px-3 py-2 text-sm rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 font-medium">
                    {saving ? "..." : (zh
                      ? (dilutedPartial ? "摊薄减仓" : closePnl && closePnl.qty < closeTarget.quantity ? "部分卖出" : "确认平仓")
                      : (dilutedPartial ? "Diluted Reduce" : closePnl && closePnl.qty < closeTarget.quantity ? "Partial Sell" : "Close Position"))}
                  </button>
                  </>
                  )}
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
                <div className="text-[10px] text-gray-400 leading-relaxed mb-1.5">
                  {zh
                    ? "改余额 = 修正（分红、结算、费用等，计入收益）。入金/出金请用「账户设置 → 记录资金流」，否则净值(TWR)曲线会失真。"
                    : "Edits here = corrections (dividends, settlement, fees — counted as returns). For deposits/withdrawals use Settings → Record Flow, or the TWR curve will drift."}
                </div>
                <button onClick={handleCashSaveAll} disabled={saving || Object.keys(cashEdits).length === 0} className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 mb-2">
                  {saving ? "..." : (zh ? "保存现金" : "Save Cash")}
                </button>
              </div>

              {/* Leverage — in-house margin is a negative cash balance now
                  (IBKR-style); only off-exchange leverage needs its own entry */}
              <div>
                <div className="text-[10px] text-gray-500 uppercase mb-2">{zh ? "杠杆" : "Leverage"}</div>
                <div className="text-[10px] text-gray-400 leading-relaxed mb-2">
                  {zh
                    ? "场内融资直接记为对应账户的负现金余额（如盈透融资 $10万 → USD 现金填 -100000），自动计入杠杆。"
                    : "In-house margin = a negative cash balance on the account (e.g. IBKR loan $100k → USD cash -100000); it counts as leverage automatically."}
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
          {tab === "flows" && (
            <div className="px-4 pb-4 space-y-2">
              <div className="text-[10px] text-gray-400 leading-relaxed bg-white dark:bg-gray-950 rounded px-2 py-1 border border-gray-200 dark:border-gray-800">
                {zh
                  ? "入金/出金流水：净值(TWR)按流水日期折算份额。金额填人民币真实成本（外币入金 = 购汇实际花费；出金 = 结汇实际所得）。股息、利息不记这里——直接改现金余额。"
                  : "Deposit/withdrawal ledger: TWR converts flows into units at the flow date. Enter the true CNY cost (FX deposits = actual RMB spent; withdrawals = actual RMB received). Dividends/interest don't go here — edit cash directly."}
              </div>
              <div>
                <div className="text-[10px] text-gray-400 mb-0.5">{zh ? "账户" : "Account"}</div>
                <select className={inputCls} value={flowBroker} onChange={(e) => setFlowBroker(e.target.value)}>
                  <option value="">{zh ? "选择账户…" : "Select account…"}</option>
                  {Array.from(new Set([
                    ...acctSettings.map((s) => s.broker),
                    ...(data?.cash || []).map((c) => c.account),
                  ])).map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </div>
              <div>
                <div className="text-[10px] text-gray-400 mb-0.5">{zh ? "金额 (人民币)" : "Amount (CNY)"}</div>
                <input className={inputCls} inputMode="decimal" placeholder={zh ? "例如：50000" : "e.g. 50000"}
                  value={acctDeposit} onChange={(e) => setAcctDeposit(e.target.value)} />
              </div>
              {flowCurrency !== "CNY" && (
                <div>
                  <div className="text-[10px] text-gray-400 mb-0.5">{zh ? "汇率（购汇/结汇价）" : "FX rate"}</div>
                  <input className={inputCls} inputMode="decimal" placeholder={zh ? "例如：7.10" : "e.g. 7.10"}
                    value={acctFx} onChange={(e) => setAcctFx(e.target.value)} />
                </div>
              )}
              <FlowFields zh={zh} inputCls={inputCls}
                flowDirection={flowDirection} setFlowDirection={setFlowDirection}
                flowCurrency={flowCurrency} setFlowCurrency={setFlowCurrency}
                flowUpdateCash={flowUpdateCash} setFlowUpdateCash={setFlowUpdateCash}
                depositDate={depositDate} setDepositDate={setDepositDate}
                depositNotes={depositNotes} setDepositNotes={setDepositNotes}
                amountCny={acctDeposit} fxRate={acctFx} />
              <button disabled={saving || !flowBroker || !parseFloat(acctDeposit)}
                onClick={async () => {
                  setSaving(true);
                  try {
                    if (await submitFlow(flowBroker)) {
                      setAcctDeposit(""); setDepositDate(""); setDepositNotes("");
                      setFlowHistory(await getAllFlows());
                      onRefresh(); setMsg("✅ Saved");
                    }
                  } catch { setMsg("❌ Error"); } finally { setSaving(false); }
                }}
                className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                {saving ? "..." : (zh ? "记录资金流" : "Record Flow")}
              </button>

              {/* Flow history — all accounts, newest first */}
              <div className="border-t border-gray-200 dark:border-gray-800 pt-2 mt-1">
                <div className="text-[10px] font-medium text-gray-500 mb-1">{zh ? "流水历史" : "History"}</div>
                {flowHistory.length === 0 ? (
                  <div className="text-[10px] text-gray-400">{zh ? "暂无记录" : "No records yet"}</div>
                ) : (
                  <div className="space-y-1 max-h-64 overflow-y-auto">
                    {flowHistory.map((r) => (
                      <div key={r.id} className="flex items-center gap-2 text-[11px] py-1 border-b border-gray-100 dark:border-gray-900">
                        <span className="text-gray-400 font-mono shrink-0">{r.deposit_date || r.created_at.slice(0, 10)}</span>
                        <span className="text-gray-600 dark:text-gray-300 shrink-0">{r.broker}</span>
                        <span className={`font-mono font-medium flex-1 text-right ${r.amount_cny >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                          {r.amount_cny >= 0 ? "+" : ""}¥{formatNumber(r.amount_cny)}
                          {r.currency && r.currency !== "CNY" && r.amount != null && (
                            <span className="text-gray-400 font-normal ml-1">({r.amount >= 0 ? "+" : ""}{r.amount.toFixed(0)} {r.currency})</span>
                          )}
                        </span>
                        {r.notes && <span className="text-gray-400 truncate max-w-[80px]" title={r.notes}>{r.notes}</span>}
                        <button className="text-gray-300 hover:text-red-500 shrink-0" title={zh ? "删除（不回滚已联动的现金）" : "Delete (cash not rolled back)"}
                          onClick={async () => {
                            if (!confirm(zh ? `删除这笔流水？\n注意：已联动的现金余额不会自动回滚。` : "Delete this flow?\nNote: synced cash balance is NOT rolled back.")) return;
                            try { await deleteDepositRecord(r.id); setFlowHistory(await getAllFlows()); onRefresh(); } catch { alert("Error"); }
                          }}>✕</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === "settings" && (
            <>
              <div className="text-[10px] text-gray-400 mb-3 leading-relaxed space-y-1.5">
                <p>{zh
                  ? "💰 本金（Capital）= 期初冻结值 + 累计净入金流水，全组合统一自动计算，无需按账户配置。"
                  : "💰 Capital = frozen opening value + net recorded flows — unified across the portfolio, no per-account setup."}</p>
                <p>{zh
                  ? "ℹ️ 所有账户都需要在此注册。新增持仓时，账户选项来自此列表。"
                  : "ℹ️ All accounts must be registered here. The account dropdown in Positions tab is sourced from this list."}</p>
                <p>
                  <a href="/portfolio/guide" target="_blank" rel="noopener" className="text-blue-500 hover:underline">
                    {zh ? "📖 完整规则见记账指南（净值、本金、资金流、成本口径）" : "📖 Full rules in the accounting guide"}
                  </a>
                </p>
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
                          <span className={`ml-2 px-1.5 py-0.5 rounded text-[9px] font-semibold ${s.capital_mode === "deposit" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"}`}
                            title={zh ? "本金口径：入金总额 or 持仓成本" : "Capital basis: deposit total or position cost"}>
                            {s.capital_mode === "deposit" ? (zh ? "入金" : "Deposit") : (zh ? "成本" : "Cost")}
                          </span>
                          <span className={`ml-1 px-1.5 py-0.5 rounded text-[9px] font-semibold ${s.cost_method === "average" ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400" : "bg-transparent text-gray-400 border border-gray-200 dark:border-gray-700"}`}
                            title={zh ? "个股成本口径：部分卖出后成本是否变动" : "Per-stock cost basis on partial sell"}>
                            {s.cost_method === "average" ? (zh ? "平均" : "Avg") : (zh ? "摊薄" : "Diluted")}
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
                          <button onClick={() => { setAcctBroker(s.broker); setAcctMode(s.capital_mode as "cost" | "deposit"); setAcctCostMethod((s.cost_method as "diluted" | "average") || "diluted"); setAcctHkConnect(!!s.hk_connect); setAcctDeposit(s.deposit_cny > 0 ? String(s.deposit_cny) : ""); setAcctFx(String(s.deposit_fx)); setDepositAction("update"); }} className="text-blue-500 hover:text-blue-700">✎</button>
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
                        setAcctCostMethod((existing.cost_method as "diluted" | "average") || "diluted");
                        setAcctHkConnect(!!existing.hk_connect);
                        setAcctDeposit(existing.deposit_cny > 0 ? String(existing.deposit_cny) : "");
                        setAcctFx(String(existing.deposit_fx));
                      } else {
                        setAcctMode("cost"); setAcctCostMethod("diluted"); setAcctHkConnect(false); setAcctDeposit(""); setAcctFx("1.0");
                      }
                      setDepositAction("update");
                    }}>
                      <option value="">{zh ? "— 选择账户 —" : "— Select account —"}</option>
                      {knownAccounts.map((n) => {
                        const s = acctSettings.find((st) => st.broker === n);
                        const capTag = s ? (s.capital_mode === "deposit" ? (zh ? "入金" : "Deposit") : (zh ? "成本" : "Cost")) : "";
                        const cmTag = s?.cost_method === "average" ? (zh ? "·平均" : "·Avg") : "";
                        const tag = s ? ` [${capTag}${cmTag}]` : "";
                        return <option key={n} value={n}>{n}{tag}</option>;
                      })}
                    </select>
                    <button onClick={() => { setIsNewAcct(true); setAcctBroker(""); setAcctMode("cost"); setAcctCostMethod("diluted"); setAcctHkConnect(false); setAcctDeposit(""); setAcctFx("1.0"); }}
                      className="px-2 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-700 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 whitespace-nowrap">
                      {zh ? "➕ 新增" : "➕ New"}
                    </button>
                  </div>
                ) : (
                  /* ── New account name input ── */
                  <div className="flex gap-2">
                    <input className={`${inputCls} flex-1`} placeholder={zh ? "输入账户名称" : "Enter account name"} autoFocus
                      value={newAcctName} onChange={(e) => setNewAcctName(e.target.value)} />
                    <button onClick={() => { setIsNewAcct(false); setNewAcctName(""); }}
                      className="px-2 py-1.5 text-xs text-gray-400 hover:text-gray-600">✕</button>
                  </div>
                )}

                {(!isNewAcct ? !!acctBroker : !!newAcctName.trim()) && (
                  <div className="space-y-1.5">
                    <div className="flex gap-2 items-center">
                      <span className="text-[10px] text-gray-400 whitespace-nowrap">{zh ? "成本口径" : "Cost basis"}</span>
                      <select className={inputCls} style={{ width: 130 }} value={acctCostMethod}
                        onChange={(e) => setAcctCostMethod(e.target.value as "diluted" | "average")}>
                        <option value="diluted">{zh ? "摊薄成本" : "Diluted"}</option>
                        <option value="average">{zh ? "平均成本 (盈透)" : "Average (IBKR)"}</option>
                      </select>
                    </div>
                    <div className="text-[10px] text-gray-400 leading-relaxed bg-white dark:bg-gray-950 rounded px-2 py-1 border border-gray-200 dark:border-gray-800">
                      {acctCostMethod === "average"
                        ? (zh
                          ? "平均成本：部分卖出后持仓成本不变（盈透口径）。请用「部分卖出」标签页减仓——它会记录已实现盈亏、成本保持不变。不要用「编辑」手动改成本。"
                          : "Average: cost stays unchanged on partial sell (IBKR). Reduce positions via the \"Close\" tab — it books realized P&L and keeps cost intact. Don't hand-edit the cost.")
                        : (zh
                          ? "摊薄成本：券商在部分卖出后自动下调持仓成本（国内券商、富途）。减仓推荐走「平仓」页——自动计算新摊薄成本并入账现金；也可用「编辑」照抄券商数字。"
                          : "Diluted: broker lowers the cost on partial sell (Chinese brokers, Futu). Reduce via the Close tab — it computes the new diluted cost and books the cash; or hand-copy the broker's numbers via Edit.")}
                    </div>
                    <label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer">
                      <input type="checkbox" checked={acctHkConnect} onChange={(e) => setAcctHkConnect(e.target.checked)} />
                      {zh ? "港股通账户（港股卖出回款按汇率折人民币）" : "HK Connect account (HK sale proceeds settle in CNY)"}
                    </label>
                  </div>
                )}
                {acctMode === "deposit" && (
                  <div className="text-[10px] text-gray-400 leading-relaxed bg-white dark:bg-gray-950 rounded px-2 py-1 border border-gray-200 dark:border-gray-800">
                    {zh
                      ? "本金已统一为「期初冻结值 + 资金流水」自动计算，入金总额字段仅作历史记录，不再影响本金。日常入金/出金请到「资金流」标签页记录。"
                      : "Capital is now frozen opening value + recorded flows. The deposit-total field is historical metadata only. Use the Flows tab for day-to-day flows."}
                  </div>
                )}
                <button onClick={handleAcctSave} disabled={saving || (isNewAcct ? !newAcctName.trim() : !acctBroker)}
                  className="w-full px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                  {saving ? "..." : (zh ? "保存" : "Save")}
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
  const [panelInitialTab, setPanelInitialTab] = useState<"edit" | "close" | "cash" | "flows" | "settings">("edit");
  const [ibkrRecon, setIbkrRecon] = useState<IbkrRecon | null>(null);
  useEffect(() => {
    getIbkrRecon().then((r) => {
      if (r && (r.unavailable || (r.diffs && (r.diffs.length > 0 || (r.ignored || 0) > 0 || (r.cost_notes?.length || 0) > 0)))) setIbkrRecon(r as IbkrRecon);
    }).catch(() => {});
  }, []);
  // Risk fetch waits for holdings so the price cache is already warm
  useEffect(() => {
    if (data && data.holdings.length > 0 && !riskData) {
      getRisk().then((r) => { if (r && r.nav != null) setRiskData(r); }).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const [panelEditHolding, setPanelEditHolding] = useState<PortfolioHolding | null>(null);
  const [panelTradeTarget, setPanelTradeTarget] = useState<PortfolioHolding | null>(null);
  const [panelTradeDir, setPanelTradeDir] = useState<"buy" | "sell" | null>(null);
  const [panelFlowDir, setPanelFlowDir] = useState<"in" | "out" | null>(null);
  const [fabOpen, setFabOpen] = useState(false);
  const openTrade = (h: PortfolioHolding | null, dir: "buy" | "sell") => {
    setPanelTradeTarget(h); setPanelTradeDir(dir); setPanelInitialTab("close"); setPanelOpen(true); setFabOpen(false);
  };
  const openFlow = (dir: "in" | "out") => {
    setPanelFlowDir(dir); setPanelInitialTab("flows"); setPanelOpen(true); setFabOpen(false);
  };
  const [portfolios, setPortfolios] = useState<PortfolioInfo[]>([]);
  const activePortfolio = portfolios.find((p) => p.active)?.name || "";
  const [refreshKey, setRefreshKey] = useState(0);
  const [pageTab, setPageTab] = useState<"overview" | "holdings" | "performance" | "risk" | "trades" | "events">("overview");
  const [riskData, setRiskData] = useState<Partial<RiskData> | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    try { setLoading(true); setError(null);
      const [status, pList] = await Promise.all([getPortfolioStatus(signal), listPortfolios(signal)]);
      if (signal?.aborted) return;
      setAvailable(status.available);
      setPortfolios(pList);
      if (!status.available) { setLoading(false); return; }
      setData(await getPortfolioHoldings(signal));
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return; // unmount — ignore
      setError(e instanceof Error ? e.message : "Failed to load");
    }
    finally { if (!signal?.aborted) setLoading(false); }
  }, []);

  // Silent refresh — only re-fetch holdings without full loading state (used by DataPanel after edits)
  const silentRefresh = useCallback(async () => {
    try {
      setData(await getPortfolioHoldings());
      setRefreshKey((k) => k + 1);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);

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
  const [weeklyPct, setWeeklyPct] = useState<number | null>(null);
  const [weeklyLabel, setWeeklyLabel] = useState<string>("");
  const [weeklyByMkt, setWeeklyByMkt] = useState<{ market: string; pnl: number; pct?: number }[]>([]);
  const [allClosedTrades, setAllClosedTrades] = useState<ClosedTrade[]>([]);
  const [realizedPnl, setRealizedPnl] = useState<number | null>(null);
  const [dividendsByTicker, setDividendsByTicker] = useState<Record<string, { net_cny: number }>>({});
  const closedCount = allClosedTrades.length;
  useEffect(() => {
    getDividends().then((d) => { if (d && d.by_ticker) setDividendsByTicker(d.by_ticker); }).catch(() => {});
  }, [refreshKey]);

  useEffect(() => {
    if (!data) return;
    const ac = new AbortController();
    const cancelled = () => ac.signal.aborted;

    // Single consolidated fetch: snapshots(20) covers both weekly(14) and weeklyByMkt(20)
    const fetchDerived = async () => {
      const [snaps, trades] = await Promise.all([getSnapshots(20, ac.signal), getClosedTrades(ac.signal)]);
      if (cancelled()) return;

      // ── Closed trades ──
      setAllClosedTrades(trades);
      setRealizedPnl(trades.reduce((s, t) => s + (t.realized_pnl_cny || 0), 0));

      // ── "This Week" base = last Friday's CLOSE. A snapshot dated D prices
      // D-1's close (the 06:10 run), so Friday's close lives in the
      // SATURDAY-dated snapshot — cut off at Saturday, not Friday, or the
      // week would silently start from Thursday's close. ──
      const sorted = [...snaps].sort((a, b) => a.date.localeCompare(b.date));
      const now = new Date();
      const bjNow = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
      const dow = bjNow.getDay();
      // On Sat/Sun the week just ended, so the base is the Friday BEFORE it
      // (8/9 days back) — not yesterday's Friday, which would make the window
      // zero days wide and just measure live-quote drift off Friday's close.
      const daysBack = dow === 0 ? 9 : dow === 6 ? 8 : dow + 2;
      const lastFri = new Date(bjNow.getTime() - daysBack * 86400000);
      const lastSatStr = new Date(lastFri.getTime() + 86400000)
        .toLocaleString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 10);
      const weekCandidates = sorted.filter((s) => s.date <= lastSatStr);

      // ── KPI Weekly P&L ──
      const currentNetAssets = data.summary.net_assets;
      const currentCapital = data.summary.capital;
      if (currentNetAssets != null && currentCapital != null && weekCandidates.length > 0) {
        const weekTarget = weekCandidates[weekCandidates.length - 1];
        if (weekTarget.net_assets != null && weekTarget.capital != null) {
          const currentPnl = currentNetAssets - currentCapital;
          const basePnl = weekTarget.net_assets - weekTarget.capital;
          const wPnl = currentPnl - basePnl;
          setWeeklyPnl(wPnl);
          // Weekly return % = weekly P&L / base net assets
          const baseNA = weekTarget.net_assets;
          setWeeklyPct(baseNA ? (wPnl / baseNA) * 100 : null);
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
          if (!cancelled()) setWeeklyByMkt(items);
        }
      }
    };
    fetchDerived().catch(() => {});
    return () => ac.abort();
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
    // Product preview instead of a bare lock — visitors see what the
    // tracker does (sample data) before being asked to register
    return (
      <>
        <Navbar />
        <PortfolioPreview />
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
            {data && data.holdings.length > 0 && (
              <button onClick={async () => { try { await downloadPortfolioExcel(); } catch { alert("Export failed"); } }}
                className="px-3 py-1 text-xs border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                title={locale === "zh" ? "导出Excel" : "Export Excel"}>
                📥 Excel
              </button>
            )}
            <Link href="/portfolio/guide"
              className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-gray-600 dark:text-gray-300"
              title={locale === "zh" ? "记账指南" : "Accounting guide"}>
              📖
            </Link>
            <button onClick={() => load()} disabled={loading} className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors">
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
              { key: "performance", zh: "表现", en: "Performance" },
              { key: "risk", zh: "风险", en: "Risk" },
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
          <OnboardingCard locale={locale} onRefresh={silentRefresh} onOpenPanel={(tab) => { setPanelInitialTab(tab || "edit"); setPanelOpen(true); }} />
        )}

        {data && data.holdings.length > 0 && (
          <>
            {/* Setup tips banner — shown after import until dismissed */}
            <SetupTipsBanner locale={locale} data={data} onOpenPanel={(tab) => { setPanelInitialTab(tab); setPanelOpen(true); }} />
            {ibkrRecon && (
              <IbkrReconBanner
                recon={ibkrRecon}
                locale={locale}
                onApplied={(next) => {
                  setIbkrRecon(next && next.diffs ? (next as IbkrRecon) : null);
                  silentRefresh();
                }}
              />
            )}
            <RiskAlertBanner risk={riskData} locale={locale} onGoRisk={() => setPageTab("risk")} />

            {/* ════════ OVERVIEW TAB ════════ */}
            {pageTab === "overview" && (
              <>
                <HeroSummary locale={locale} onGoPerformance={() => setPageTab("performance")}
                  unitNav={data.summary.unit_nav} unitNavEst={data.summary.unit_nav_est}
                  unitNavDate={data.summary.unit_nav_date} ytdMwr={data.summary.ytd_mwr} />
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
                    sub={pctStr((() => { const base = data.summary.net_assets - data.summary.daily_pnl_cny; return base ? (data.summary.daily_pnl_cny / base) * 100 : null; })())}
                    subColor={pnlColor(data.summary.daily_pnl_cny)} />
                  {weeklyPnl != null && (
                    <KpiCard label={weeklyLabel || (locale === "zh" ? "本周" : "This Week")}
                      value={`¥${pnlSign(weeklyPnl)}`} sub={pctStr(weeklyPct)} subColor={pnlColor(weeklyPnl)} />
                  )}
                  <KpiCard label={locale === "zh" ? "YTD 盈亏" : "YTD P&L"} value={`¥${pnlSign(data.summary.ytd_pnl_cny)}`}
                    sub={data.summary.ytd_mwr != null
                      ? `${pctStr(data.summary.ytd_mwr)} ${locale === "zh" ? "资金加权 (Dietz)" : "money-wt. (Dietz)"} · ${(data.summary.ytd_mwr_start || "").slice(5)}${locale === "zh" ? " 起" : "+"}`
                      : undefined}
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

              </>
            )}

            {/* ════════ HOLDINGS TAB ════════ */}
            {pageTab === "holdings" && (
              <>
                {/* ── Asset Allocation — the natural companion of the position list ── */}
                <div className="mt-2 mb-4 p-3 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">{locale === "zh" ? "资产配置" : "Asset Allocation"}</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-x-8 gap-y-4">
                    <AllocationBar title={locale === "zh" ? "按市场" : "By Market"} items={allocByMkt} locale={locale} />
                    <AllocationBar title={locale === "zh" ? "按币种" : "By Currency"} items={allocByCur} locale={locale} />
                    {allocBySector.length > 1 && <AllocationBar title={locale === "zh" ? "按行业" : "By Sector"} items={allocBySector} locale={locale} />}
                  </div>
                </div>
                <HoldingsTable holdings={data.holdings} summary={data.summary} locale={locale}
                  onEdit={(h) => { setPanelEditHolding(h); setPanelOpen(true); }}
                  onTrade={(h, dir) => openTrade(h, dir)} />
                <CashTable cash={data.cash} fx={data.fx} locale={locale} />
              </>
            )}

            {/* ════════ PERFORMANCE TAB ════════ */}
            {pageTab === "performance" && (
              <>
                <PerformanceSection key={`perf-${refreshKey}`} locale={locale}
                  liveUnitNav={data.summary.unit_nav_est} liveNetAssets={data.summary.net_assets} />
                <ReturnAttribution holdings={data.holdings} closedTrades={allClosedTrades} dividends={dividendsByTicker} locale={locale} />
              </>
            )}

            {/* ════════ RISK TAB ════════ */}
            {pageTab === "risk" && (
              <>
                <RiskStressSection locale={locale} risk={riskData} />
                <SustainabilitySection key={`sust-${refreshKey}`} locale={locale} />
              </>
            )}

            {/* ════════ JOURNALS TAB ════════ */}
            {pageTab === "trades" && (
              <>
                <PnlJournal key={`journal-${refreshKey}`} locale={locale} />
                <ClosedTradesSection key={`trades-${refreshKey}`} locale={locale} />
                <DividendJournal key={`divs-${refreshKey}`} locale={locale} />
              </>
            )}

            {pageTab === "events" && (
              <EventsSection key={`events-${refreshKey}`} locale={locale} fmpApiKey={fmpApiKey} />
            )}

          </>
        )}

        {/* ── Data Management Panel (sidebar) — always available when data loaded ── */}
        {/* ── "+ 记一笔" floating quick-action button ── */}
        {data && data.holdings.length > 0 && (
          <div className="fixed bottom-6 right-6 z-40 flex flex-col items-end gap-2">
            {fabOpen && (
              <div className="flex flex-col gap-1.5 mb-1">
                {([
                  { label: locale === "zh" ? "买入" : "Buy", act: () => openTrade(null, "buy"), cls: "bg-red-600 hover:bg-red-700" },
                  { label: locale === "zh" ? "卖出" : "Sell", act: () => openTrade(null, "sell"), cls: "bg-green-600 hover:bg-green-700" },
                  { label: locale === "zh" ? "入金" : "Deposit", act: () => openFlow("in"), cls: "bg-blue-600 hover:bg-blue-700" },
                  { label: locale === "zh" ? "出金" : "Withdraw", act: () => openFlow("out"), cls: "bg-gray-600 hover:bg-gray-700" },
                ]).map((b) => (
                  <button key={b.label} onClick={b.act}
                    className={`px-4 py-2 rounded-full text-white text-sm font-medium shadow-lg transition-colors ${b.cls}`}>
                    {b.label}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => setFabOpen(!fabOpen)}
              className={`w-12 h-12 rounded-full text-white text-2xl leading-none shadow-lg transition-all ${fabOpen ? "bg-gray-500 rotate-45" : "bg-blue-600 hover:bg-blue-700"}`}
              title={locale === "zh" ? "记一笔" : "Quick action"}>
              +
            </button>
          </div>
        )}

        {data && <DataPanel holdings={data.holdings} data={data} locale={locale} onRefresh={silentRefresh} open={panelOpen} onClose={() => { setPanelOpen(false); setPanelEditHolding(null); setPanelTradeTarget(null); setPanelTradeDir(null); setPanelFlowDir(null); }} editHolding={panelEditHolding} initialTab={panelInitialTab} tradeTarget={panelTradeTarget} tradeDir={panelTradeDir} flowDir={panelFlowDir} />}
      </main>
    </>
  );
}
