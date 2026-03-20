"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
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
  compareValuation,
  type ValuationRecord,
  type ValuationDetail,
  type HistoryFilters,
  type CompareResult,
} from "@/lib/api";

// ────────────────────────────────────────
// Helpers
// ────────────────────────────────────────

function _v(val: unknown): boolean {
  if (val == null) return false;
  if (typeof val === "number" && isNaN(val)) return false;
  return true;
}

function fmtPrice(val: number | null | undefined): string {
  if (!_v(val)) return "\u2014";
  return val!.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtAmount(val: number | null | undefined): string {
  if (!_v(val)) return "\u2014";
  return val!.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function fmtPct(val: number | null | undefined): string {
  if (!_v(val)) return "\u2014";
  return `${(val! * 100).toFixed(1)}%`;
}

function fmtPctRaw(val: number | null | undefined): string {
  if (!_v(val)) return "\u2014";
  return `${val!.toFixed(1)}%`;
}

function fmtRatio(val: number | null | undefined): string {
  if (!_v(val)) return "\u2014";
  return val!.toFixed(2);
}

function gapColor(pct: number | null | undefined): string {
  if (!_v(pct)) return "text-gray-400";
  return pct! >= 0
    ? "text-green-600 dark:text-green-400"
    : "text-red-600 dark:text-red-400";
}

function gapStr(pct: number | null | undefined): string {
  if (!_v(pct)) return "\u2014";
  const prefix = pct! > 0 ? "+" : "";
  return `${prefix}${pct!.toFixed(1)}%`;
}

function modeLabel(mode: string): string {
  const m: Record<string, string> = { manual: "Manual", copilot: "Copilot", auto: "Auto" };
  return m[mode] || mode;
}

// ────────────────────────────────────────
// Dropdown Multi-Select Component
// ────────────────────────────────────────

function MultiSelect({
  label,
  options,
  selected,
  onChange,
  renderOption,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
  renderOption?: (v: string) => string;
}) {
  const [open, setOpen] = useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const toggle = (v: string) => {
    onChange(
      selected.includes(v) ? selected.filter((s) => s !== v) : [...selected, v],
    );
  };

  const display = renderOption || ((v: string) => v);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none min-w-[120px] hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
      >
        <span className="flex-1 text-left truncate">
          {selected.length === 0
            ? label
            : selected.length === options.length
              ? `${label} (All)`
              : `${label} (${selected.length})`}
        </span>
        <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full min-w-[160px] rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg py-1">
          {options.map((opt) => (
            <label
              key={opt}
              className="flex items-center gap-2 px-3 py-1.5 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 text-sm"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt)}
                onChange={() => toggle(opt)}
                className="rounded border-gray-300 dark:border-gray-600 text-blue-500 focus:ring-blue-500"
              />
              <span>{display(opt)}</span>
            </label>
          ))}
          {selected.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="w-full text-left px-3 py-1.5 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 border-t border-gray-100 dark:border-gray-800 mt-1"
            >
              Clear all
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function modeBadgeColor(mode: string): string {
  if (mode === "auto") return "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300";
  if (mode === "copilot") return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300";
  return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
}

// ────────────────────────────────────────
// Summary Panel (single company)
// ────────────────────────────────────────

function SummaryPanel({ records }: { records: ValuationRecord[] }) {
  const { locale } = useI18n();
  const [compare, setCompare] = useState<CompareResult | null>(null);

  const latest = records[0];
  const isDual = latest.reported_currency && latest.currency && latest.reported_currency !== latest.currency;

  // Reporting-currency IV
  const adjRep = latest.gap_adjusted_price_reporting;
  const pps = latest.price_per_share;
  const ivRep = _v(adjRep) ? adjRep : (_v(pps) ? pps : null);
  const hasAdj = _v(adjRep) && adjRep;
  const panelLabel = hasAdj
    ? (locale === "zh" ? "AI修正估值" : "Adjusted DCF Estimate")
    : (locale === "zh" ? "DCF估值" : "DCF Estimate");

  useEffect(() => {
    compareValuation(latest.id).then(setCompare).catch(() => {});
  }, [latest.id]);

  const repCur = latest.reported_currency || latest.currency || "";
  const tradeCur = latest.currency || repCur;

  // Trading-currency value
  let ivTrade: number | null = null;
  if (isDual) {
    const adjT = latest.gap_adjusted_price;
    if (_v(adjT)) {
      ivTrade = adjT;
    } else if (_v(ivRep) && ivRep! > 0 && _v(latest.forex_rate) && latest.forex_rate! > 0) {
      ivTrade = ivRep! * latest.forex_rate!;
    }
  }

  const currentPrice = compare?.current_price ?? null;
  const cmpVal = isDual ? ivTrade : ivRep;
  let gapPct: number | null = null;
  if (_v(cmpVal) && cmpVal! > 0 && _v(currentPrice) && currentPrice! > 0) {
    gapPct = ((cmpVal! - currentPrice!) / currentPrice!) * 100;
  }

  const borderClass = gapPct != null
    ? (gapPct > 0 ? "border-l-green-500" : "border-l-red-500")
    : "border-l-gray-300 dark:border-l-gray-700";

  return (
    <div className={`bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 border-l-4 ${borderClass} rounded-lg p-4 mb-5 font-mono text-sm`}>
      <div className="flex flex-wrap items-start gap-x-8 gap-y-3">
        <div>
          <div className="text-[11px] text-gray-500 uppercase tracking-wider">
            {locale === "zh" ? "公司" : "Company"}
          </div>
          <div className="text-lg font-bold text-gray-900 dark:text-white">
            {latest.company_name} ({latest.ticker})
          </div>
        </div>
        <div>
          <div className="text-[11px] text-gray-500 uppercase tracking-wider">
            {locale === "zh" ? "最新估值" : "Latest Valuation"}
          </div>
          <div className="text-lg font-bold">{latest.valuation_date}</div>
        </div>
        {_v(ivRep) && (
          <div>
            <div className="text-[11px] text-gray-500 uppercase tracking-wider">
              {panelLabel} ({repCur})
            </div>
            <div className="text-lg font-bold">{fmtPrice(ivRep)}</div>
          </div>
        )}
        {isDual && _v(ivTrade) && (
          <div>
            <div className="text-[11px] text-gray-500 uppercase tracking-wider">
              {panelLabel} ({tradeCur})
            </div>
            <div className="text-lg font-bold">{fmtPrice(ivTrade)}</div>
          </div>
        )}
        <div>
          <div className="text-[11px] text-gray-500 uppercase tracking-wider">
            {locale === "zh" ? "当前股价" : "Current Price"} ({tradeCur})
          </div>
          <div className="text-lg font-bold">
            {_v(currentPrice) ? fmtPrice(currentPrice) : "\u2014"}
          </div>
        </div>
        {gapPct != null && (
          <div>
            <div className="text-[11px] text-gray-500 uppercase tracking-wider">
              DCF vs {locale === "zh" ? "市价" : "Market"}
            </div>
            <div className={`text-lg font-bold ${gapColor(gapPct)}`}>
              {gapPct > 0 ? "+" : ""}{gapPct.toFixed(1)}% {gapPct > 0 ? (locale === "zh" ? "低估" : "Undervalued") : (locale === "zh" ? "高估" : "Overvalued")}
            </div>
          </div>
        )}
      </div>
      {/* Forex rate annotation for dual-currency */}
      {isDual && _v(latest.forex_rate) && latest.forex_rate! > 0 && (
        <div className="text-[11px] text-gray-400 mt-1.5">
          * {repCur}/{tradeCur} {locale === "zh" ? "汇率" : "exchange rate"}: {latest.forex_rate!.toFixed(4)}
          {compare?.current_price ? " (real-time via yfinance)" : ""}
        </div>
      )}
    </div>
  );
}


// ────────────────────────────────────────
// Historical Tab
// ────────────────────────────────────────

const SECTION_HEADERS = new Set(["Profitability", "Capital Structure", "Returns", "Dividends"]);
const AMOUNT_ROWS = new Set([
  "Revenue", "EBIT", "Net Income", "(+) Capital Expenditure", "(-) D&A",
  "(+) \u0394Working Capital", "Total Reinvestment",
  "(+) Total Debt", "(+) Total Equity", "Minority Interest",
  "(-) Cash & Equivalents", "(-) Total Investments", "Invested Capital",
]);
const RATIO_ROWS = new Set([
  "Revenue Growth (%)", "EBIT Growth (%)", "EBIT Margin (%)", "Incremental Margin (%)", "Tax Rate (%)",
  "Revenue / IC", "Debt to Assets (%)", "Cost of Debt (%)",
  "ROIC (%)", "ROE (%)", "Dividend Yield (%)", "Payout Ratio (%)",
]);

function HistoricalTab({ detail }: { detail: ValuationDetail }) {
  const { locale } = useI18n();
  const sj = detail.summary_json;
  if (!sj) {
    return (
      <div className="text-gray-500 py-6 text-center">
        {locale === "zh" ? "暂无历史财务数据" : "Historical financial data not available for this valuation."}
      </div>
    );
  }

  // summary_json is a pandas DataFrame JSON: { "col1": { "row1": val, ... }, ... }
  // or it could be orient="columns" — keys are column names, values are {index: value}
  const data = sj as Record<string, Record<string, unknown>>;
  // Sort columns so newest year is first (consistent with web overview)
  const columns = Object.keys(data).sort((a, b) => {
    // Extract year number, TTM columns should come first
    const aYear = parseInt(a.replace(/\D/g, '').slice(0, 4)) || 0;
    const bYear = parseInt(b.replace(/\D/g, '').slice(0, 4)) || 0;
    if (aYear !== bYear) return bYear - aYear;
    // TTM columns sort before FY for same year
    const aTTM = a.includes('TTM') ? 1 : 0;
    const bTTM = b.includes('TTM') ? 1 : 0;
    return bTTM - aTTM;
  });
  // Gather all row indices from the first column
  const firstColData = data[columns[0]] || {};
  const allRows = Object.keys(firstColData);

  // Extract reported currency if present
  let reportedCurrency = "";
  if (allRows.includes("Reported Currency")) {
    for (const col of columns) {
      const v = data[col]?.["Reported Currency"];
      if (v && String(v).trim()) {
        reportedCurrency = String(v);
        break;
      }
    }
  }

  return (
    <div>
      <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
        {locale === "zh" ? "历史财务数据（百万）" : "Historical Financial Data (in millions)"}
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr className="border-b-2 border-gray-300 dark:border-gray-600">
              <th className="text-left px-2 py-1.5 text-blue-700 dark:text-blue-300 font-semibold whitespace-nowrap" />
              {columns.map((col) => (
                <th key={col} className="text-right px-2 py-1.5 text-blue-700 dark:text-blue-300 font-semibold whitespace-nowrap">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {reportedCurrency && (
              <tr className="text-gray-400 italic text-[11px]">
                <td className="px-2 py-0.5">Reported Currency</td>
                {columns.map((col) => (
                  <td key={col} className="text-right px-2 py-0.5">{reportedCurrency}</td>
                ))}
              </tr>
            )}
            {allRows.filter((r) => r !== "Reported Currency").map((rowName) => {
              if (SECTION_HEADERS.has(rowName)) {
                return (
                  <tr key={rowName}>
                    <td colSpan={columns.length + 1} className="px-2 pt-3 pb-1 text-blue-700 dark:text-blue-300 font-bold text-[11px]">
                      ► {rowName}
                    </td>
                  </tr>
                );
              }
              const isAmount = AMOUNT_ROWS.has(rowName);
              const isRatio = RATIO_ROWS.has(rowName);
              return (
                <tr key={rowName} className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-blue-50/30 dark:hover:bg-blue-900/10">
                  <td className="px-2 py-0.5 font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    {rowName}
                  </td>
                  {columns.map((col) => {
                    const raw = data[col]?.[rowName];
                    let display = "\u2014";
                    if (raw != null && raw !== "" && !(typeof raw === "number" && isNaN(raw))) {
                      if (isAmount) {
                        try { display = parseInt(String(raw)).toLocaleString("en-US"); } catch { display = String(raw); }
                      } else if (isRatio) {
                        try { display = parseFloat(String(raw)).toFixed(1); } catch { display = String(raw); }
                      } else {
                        display = String(raw);
                      }
                    }
                    return (
                      <td key={col} className={`text-right px-2 py-0.5 whitespace-nowrap ${isRatio ? "text-gray-500 dark:text-gray-400" : "text-gray-800 dark:text-gray-200"}`}>
                        {display}
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
}

// ────────────────────────────────────────
// DCF Breakdown Tab
// ────────────────────────────────────────

function DCFBreakdownTab({ detail }: { detail: ValuationDetail }) {
  const { locale } = useI18n();
  const repCur = detail.reported_currency || detail.currency || "";
  const stkCur = detail.currency || repCur;
  const isDual = repCur && stkCur && repCur !== stkCur;

  // ── Cash Flow Forecast Table ──
  const dcfData = detail.dcf_table_json;
  let dcfRows: Record<string, unknown>[] | null = null;
  if (dcfData) {
    if (Array.isArray(dcfData)) {
      dcfRows = dcfData as Record<string, unknown>[];
    } else {
      // pandas orient="columns" format: convert to array of rows
      const cols = Object.keys(dcfData);
      if (cols.length > 0) {
        const firstCol = dcfData[cols[0]] as Record<string, unknown>;
        const indices = Object.keys(firstCol);
        dcfRows = indices.map((idx) => {
          const row: Record<string, unknown> = {};
          for (const col of cols) {
            row[col] = (dcfData[col] as Record<string, unknown>)?.[idx];
          }
          return row;
        });
      }
    }
  }

  // Year labels
  const ttmLabel = detail.ttm_label || "";
  const baseYear = detail.base_year;
  let baseLabel = "Base Year";
  if (ttmLabel) baseLabel = `Base (${ttmLabel})`;
  else if (baseYear) baseLabel = `Base (${String(baseYear).replace("FY", "")})`;
  const yearLabels = [baseLabel, ...Array.from({ length: 10 }, (_, i) => String(i + 1)), "Terminal"];

  const fields: [string, string, string][] = [
    ["Revenue Growth Rate", "Revenue Growth Rate", "pct"],
    ["Revenue", "Revenue", "amount"],
    ["EBIT Margin", "EBIT Margin", "pct"],
    ["EBIT", "EBIT", "amount"],
    ["Tax Rate", "Tax to EBIT", "pct"],
    ["EBIT(1-t)", "EBIT(1-t)", "amount"],
    ["Reinvestments", "Reinvestments", "amount"],
    ["FCFF", "FCFF", "amount"],
    ["WACC", "WACC", "pct"],
    ["Discount Factor", "Discount Factor", "factor"],
    ["PV (FCFF)", "PV (FCFF)", "amount"],
  ];

  // ── Valuation Breakdown ──
  const sharesM = _v(detail.outstanding_shares) ? detail.outstanding_shares! / 1e6 : null;
  const ivReporting = _v(detail.price_per_share) ? detail.price_per_share : null;
  const pvSum = (_v(detail.pv_cf_10yr) && _v(detail.pv_terminal))
    ? (detail.pv_cf_10yr! + detail.pv_terminal!)
    : null;

  const breakdownRows: [string, string, "normal" | "subtotal" | "highlight"][] = [
    ["PV of FCFF (10 years)", fmtAmount(detail.pv_cf_10yr), "normal"],
    ["PV of Terminal Value", fmtAmount(detail.pv_terminal), "normal"],
    ["Sum of Present Values", fmtAmount(pvSum), "subtotal"],
    ["+ Cash & Equivalents", fmtAmount(detail.cash), "normal"],
    ["+ Total Investments", fmtAmount(detail.total_investments), "normal"],
    ["Enterprise Value", fmtAmount(detail.enterprise_value), "subtotal"],
    ["- Total Debt", fmtAmount(detail.total_debt), "normal"],
    ["- Minority Interest", fmtAmount(detail.minority_interest), "normal"],
    ["Equity Value", fmtAmount(detail.equity_value), "subtotal"],
    ["Outstanding Shares (M)", fmtAmount(sharesM), "normal"],
    [`DCF Estimate Per Share${repCur ? ` (${repCur})` : ""}`, fmtPrice(ivReporting), "highlight"],
  ];

  // Dual currency line
  if (isDual) {
    const gapDcf = detail.gap_dcf_price;
    if (_v(gapDcf) && gapDcf) {
      let fxNote = "";
      if (_v(ivReporting) && ivReporting! > 0) {
        const impliedFx = gapDcf! / ivReporting!;
        fxNote = `  (\u00d7 ${impliedFx.toFixed(4)})`;
      }
      breakdownRows.push([`DCF Estimate Per Share (${stkCur})`, `${fmtPrice(gapDcf)}${fxNote}`, "highlight"]);
    } else if (_v(ivReporting) && ivReporting! > 0 && _v(detail.forex_rate) && detail.forex_rate! > 0) {
      const converted = ivReporting! * detail.forex_rate!;
      breakdownRows.push([`DCF Estimate Per Share (${stkCur})`, `${fmtPrice(converted)}  (\u00d7 ${detail.forex_rate!.toFixed(4)})`, "highlight"]);
    }
  }

  // ── Parameters ──
  const paramRows: [string, string][] = [
    ["Rev Growth Y1", fmtPctRaw(detail.revenue_growth_1)],
    ["Rev Growth Y2-5", fmtPctRaw(detail.revenue_growth_2)],
    ["Target EBIT Margin", fmtPctRaw(detail.ebit_margin)],
    ["Convergence", _v(detail.convergence) ? `${detail.convergence!.toFixed(0)} yrs` : "\u2014"],
    ["Rev/IC Y1-2", fmtRatio(detail.rev_ic_ratio_1)],
    ["Rev/IC Y3-5", fmtRatio(detail.rev_ic_ratio_2)],
    ["Rev/IC Y5-10", fmtRatio(detail.rev_ic_ratio_3)],
    ["Tax Rate", fmtPctRaw(detail.tax_rate)],
    ["WACC", fmtPctRaw(detail.wacc)],
    ["Terminal WACC", fmtPct(detail.terminal_wacc)],
    ["RONIC", fmtPct(detail.ronic)],
    ["Risk-free Rate", fmtPct(detail.risk_free_rate)],
    ["Beta", fmtRatio(detail.beta)],
  ];

  return (
    <div className="space-y-6">
      {/* Cash Flow Forecast */}
      {dcfRows && dcfRows.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
            {locale === "zh" ? "现金流预测（百万）" : "Cash Flow Forecast (in millions)"}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b-2 border-gray-300 dark:border-gray-600">
                  <th className="text-left px-2 py-1.5 text-blue-700 dark:text-blue-300 font-semibold" />
                  {yearLabels.slice(0, dcfRows.length).map((lbl, i) => (
                    <th key={i} className={`text-right px-2 py-1.5 whitespace-nowrap font-semibold ${
                      i === 0 ? "bg-blue-50/50 dark:bg-blue-900/10 text-blue-700 dark:text-blue-300" :
                      i === dcfRows!.length - 1 ? "bg-blue-50/30 dark:bg-blue-900/5 text-blue-700 dark:text-blue-300" :
                      "text-blue-700 dark:text-blue-300"
                    }`}>
                      {lbl}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fields.map(([displayName, colName, fmt]) => {
                  if (!dcfRows!.some((r) => colName in r)) return null;
                  return (
                    <tr key={displayName} className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-blue-50/30 dark:hover:bg-blue-900/10">
                      <td className="px-2 py-0.5 text-gray-500 dark:text-gray-400 whitespace-nowrap">{displayName}</td>
                      {dcfRows!.map((row, i) => {
                        const val = row[colName];
                        let display = "\u2014";
                        if (val != null && !(typeof val === "number" && isNaN(val))) {
                          const num = Number(val);
                          if (fmt === "pct") display = `${(num * 100).toFixed(1)}%`;
                          else if (fmt === "amount") display = num.toLocaleString("en-US", { maximumFractionDigits: 0 });
                          else if (fmt === "factor") display = num.toFixed(3);
                          else display = String(val);
                        }
                        return (
                          <td key={i} className={`text-right px-2 py-0.5 whitespace-nowrap ${
                            i === 0 ? "bg-blue-50/50 dark:bg-blue-900/10" :
                            i === dcfRows!.length - 1 ? "bg-blue-50/30 dark:bg-blue-900/5" : ""
                          }`}>
                            {display}
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
      )}

      {/* Valuation Breakdown */}
      <div>
        <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
          {locale === "zh" ? "估值分解（百万）" : "Valuation Breakdown (in millions)"}
        </h3>
        <div className="font-mono text-sm space-y-0">
          {breakdownRows.map(([label, value, style], i) => (
            <div key={i} className={`flex justify-between py-1 px-2 border-b border-gray-100 dark:border-gray-800/50 hover:bg-blue-50/30 dark:hover:bg-blue-900/10 ${
              style === "highlight" ? "font-bold text-green-700 dark:text-green-400 border-t-2 border-t-gray-300 dark:border-t-gray-600 pt-2 text-[15px]" :
              style === "subtotal" ? "font-semibold text-blue-600 dark:text-blue-400" : ""
            }`}>
              <span>{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Parameters */}
      <div>
        <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
          {locale === "zh" ? "估值参数" : "Valuation Parameters"}
        </h3>
        <div className="font-mono text-sm space-y-0">
          {paramRows.map(([label, value], i) => (
            <div key={i} className="flex justify-between py-1 px-2 border-b border-gray-100 dark:border-gray-800/50 hover:bg-blue-50/30 dark:hover:bg-blue-900/10">
              <span className="text-gray-600 dark:text-gray-400">{label}</span>
              <span>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────
// AI Reasoning Tab
// ────────────────────────────────────────

const AI_PARAM_LABELS: Record<string, string> = {
  revenue_growth_1: "Year 1 Revenue Growth",
  revenue_growth_2: "Years 2-5 Revenue CAGR",
  ebit_margin: "Target EBIT Margin",
  convergence: "Margin Convergence Period",
  revenue_invested_capital_ratio_1: "Revenue/IC Ratio (Y1-2)",
  revenue_invested_capital_ratio_2: "Revenue/IC Ratio (Y3-5)",
  revenue_invested_capital_ratio_3: "Revenue/IC Ratio (Y5-10)",
  tax_rate: "Effective Tax Rate",
  wacc: "WACC",
  ronic_match_wacc: "RONIC = WACC?",
};

function AIReasoningTab({ detail }: { detail: ValuationDetail }) {
  const { locale } = useI18n();
  const params = detail.ai_parameters_json as Record<string, { value: unknown; reasoning: string }> | null;
  const rawText = detail.ai_raw_text;
  const hasParams = params && Object.keys(params).length > 0;
  const hasRaw = rawText && rawText.trim().length > 0;

  if (!hasParams && !hasRaw) {
    return (
      <div className="text-gray-500 py-6 text-center">
        {locale === "zh" ? "无AI分析数据（手动模式或数据未保存）" : "No AI reasoning available (manual mode or data not captured)."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {hasParams && (
        <div>
          <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
            {locale === "zh" ? "AI参数分析" : "AI Parameter Analysis"}
          </h3>
          <div className="space-y-4">
            {Object.entries(AI_PARAM_LABELS).map(([key, label]) => {
              const p = params![key];
              if (!p || typeof p !== "object" || !p.reasoning) return null;
              const val = p.value;
              const valStr = typeof val === "boolean" ? (val ? "Yes" : "No") : String(val);
              return (
                <div key={key} className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-sm text-gray-900 dark:text-white">{label}</span>
                    <span className="font-mono text-sm bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded">
                      {valStr}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap leading-relaxed">
                    {p.reasoning}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {hasRaw && (
        <div>
          <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
            {hasParams ? (locale === "zh" ? "完整AI分析" : "Full AI Analysis") : (locale === "zh" ? "AI分析" : "AI Analysis")}
          </h3>
          <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed max-h-[500px] overflow-y-auto">
            {rawText}
          </div>
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────
// Sensitivity Tab
// ────────────────────────────────────────

function SensitivityTab({ detail }: { detail: ValuationDetail }) {
  const { locale } = useI18n();
  const sensData = detail.sensitivity_json as Record<string, Record<string, number>> | null;
  const waccData = detail.wacc_sensitivity_json as Record<string, number> | null;
  const baseGrowth = detail.revenue_growth_2 ?? 0;  // already percentage (e.g. 12.9)
  const baseMargin = detail.ebit_margin ?? 0;
  const waccBase = detail.wacc ?? null;

  const hasSens = sensData && Object.keys(sensData).length > 0;
  const hasWacc = waccData && Object.keys(waccData).length > 0;

  if (!hasSens && !hasWacc) {
    return (
      <div className="text-gray-500 py-6 text-center">
        {locale === "zh" ? "暂无敏感性分析数据" : "No sensitivity data available."}
      </div>
    );
  }

  const growthKeys = hasSens ? Object.keys(sensData!).sort((a, b) => parseFloat(b) - parseFloat(a)) : [];
  const marginKeys = hasSens ? Object.keys(sensData![growthKeys[0]]).sort((a, b) => parseFloat(a) - parseFloat(b)) : [];
  const waccKeys = hasWacc ? Object.keys(waccData!).sort((a, b) => parseFloat(a) - parseFloat(b)) : [];

  return (
    <div className="space-y-6">
      {hasSens && (
        <div>
          <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
            {locale === "zh" ? "营收增长 \u00d7 EBIT利润率 敏感性" : "Revenue Growth \u00d7 EBIT Margin Sensitivity"}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse">
              <thead>
                <tr>
                  <th className="text-right px-2 py-1.5 text-gray-400 text-[10px] italic border-b-2 border-gray-300 dark:border-gray-600">
                    EBIT Margin →<br /><span className="not-italic">Rev Growth ↓</span>
                  </th>
                  {marginKeys.map((m) => {
                    const mf = parseFloat(m);
                    const isBaseCol = Math.abs(mf - baseMargin) < 0.5;
                    return (
                      <th key={m} className={`text-right px-2 py-1.5 border-b-2 border-gray-300 dark:border-gray-600 whitespace-nowrap ${
                        isBaseCol ? "text-blue-700 dark:text-blue-300 font-bold" : "text-gray-500 font-semibold"
                      }`}>
                        {Math.round(mf)}%
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {growthKeys.map((g) => {
                  const gf = parseFloat(g);
                  const isBaseRow = Math.abs(gf - baseGrowth) < 0.5;
                  return (
                    <tr key={g} className="border-b border-gray-100 dark:border-gray-800/50">
                      <td className={`text-right px-2 py-0.5 whitespace-nowrap ${
                        isBaseRow ? "text-blue-700 dark:text-blue-300 font-bold" : "text-gray-500 font-medium"
                      }`}>
                        {Math.round(gf)}%
                      </td>
                      {marginKeys.map((m) => {
                        const mf = parseFloat(m);
                        const isBaseCol = Math.abs(mf - baseMargin) < 0.5;
                        const val = sensData![g]?.[m] ?? 0;
                        const isCenter = isBaseRow && isBaseCol;
                        const isCross = isBaseRow || isBaseCol;
                        return (
                          <td key={m} className={`text-right px-2 py-0.5 whitespace-nowrap ${
                            isCenter
                              ? "text-green-700 dark:text-green-400 font-extrabold text-sm bg-green-50 dark:bg-green-900/20"
                              : isCross
                                ? "text-blue-700 dark:text-blue-300 bg-blue-50/50 dark:bg-blue-900/10"
                                : "text-gray-500 dark:text-gray-400"
                          }`}>
                            {Number(val).toLocaleString("en-US", { maximumFractionDigits: 0 })}
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
      )}

      {hasWacc && (
        <div>
          <h3 className="text-sm font-bold text-blue-700 dark:text-blue-300 uppercase tracking-wide mb-3 pl-3 border-l-[3px] border-blue-500">
            {locale === "zh" ? "WACC 敏感性" : "WACC Sensitivity"}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse text-center">
              <thead>
                <tr className="border-b-2 border-gray-300 dark:border-gray-600">
                  <td className="text-left px-2 py-1.5 text-gray-400 text-[10px] italic whitespace-nowrap">WACC</td>
                  {waccKeys.map((w) => {
                    const wf = parseFloat(w);
                    const isBase = waccBase != null && Math.abs(wf - waccBase) < 0.05;
                    return (
                      <th key={w} className={`px-2 py-1.5 whitespace-nowrap ${
                        isBase ? "text-blue-700 dark:text-blue-300 font-bold" : "text-gray-500 font-semibold"
                      }`}>
                        {wf.toFixed(1)}%
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-gray-100 dark:border-gray-800/50">
                  <td className="text-left px-2 py-1 text-gray-400 text-[10px] italic whitespace-nowrap">Price / Share</td>
                  {waccKeys.map((w) => {
                    const wf = parseFloat(w);
                    const isBase = waccBase != null && Math.abs(wf - waccBase) < 0.05;
                    return (
                      <td key={w} className={`px-2 py-1 whitespace-nowrap ${
                        isBase
                          ? "text-green-700 dark:text-green-400 font-extrabold text-sm bg-green-50 dark:bg-green-900/20"
                          : "text-gray-500 dark:text-gray-400"
                      }`}>
                        {Number(waccData![w]).toLocaleString("en-US", { maximumFractionDigits: 0 })}
                      </td>
                    );
                  })}
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────
// Gap Analysis Tab
// ────────────────────────────────────────

function GapAnalysisTab({ detail }: { detail: ValuationDetail }) {
  const { locale } = useI18n();
  const gapText = detail.gap_analysis_text;

  if (!gapText || gapText.trim().length === 0) {
    return (
      <div className="text-gray-500 py-6 text-center">
        {locale === "zh" ? "暂无差距分析数据" : "No gap analysis available for this valuation."}
      </div>
    );
  }

  // Strip ADJUSTED_PRICE line from display
  const cleanText = gapText.replace(/\n?\s*ADJUSTED_PRICE:.*$/m, "").trim();

  return (
    <div className="space-y-4">
      {/* Gap Bar */}
      <div className="flex flex-wrap items-center gap-4 p-3 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg font-mono text-sm">
        {_v(detail.gap_dcf_price) && (
          <div>
            <div className="text-[10px] text-gray-400 uppercase">DCF Estimate</div>
            <div className="font-bold">{fmtPrice(detail.gap_dcf_price)}</div>
          </div>
        )}
        {_v(detail.gap_market_price) && (
          <div>
            <div className="text-[10px] text-gray-400 uppercase">Market Price</div>
            <div className="font-bold">{fmtPrice(detail.gap_market_price)}</div>
          </div>
        )}
        {_v(detail.gap_pct) && (
          <div>
            <div className="text-[10px] text-gray-400 uppercase">Gap</div>
            <div className={`font-bold ${gapColor(detail.gap_pct)}`}>{gapStr(detail.gap_pct)}</div>
          </div>
        )}
        {_v(detail.gap_adjusted_price) && (
          <div>
            <div className="text-[10px] text-gray-400 uppercase">Adjusted Price</div>
            <div className="font-bold">{fmtPrice(detail.gap_adjusted_price)}</div>
          </div>
        )}
      </div>

      {/* Gap Text */}
      <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg p-4 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed max-h-[500px] overflow-y-auto">
        {cleanText}
      </div>
    </div>
  );
}

// ────────────────────────────────────────
// Detail Card (expandable)
// ────────────────────────────────────────

function DetailCard({
  record,
  isExpanded,
  onToggle,
}: {
  record: ValuationRecord;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const { locale } = useI18n();
  const [detail, setDetail] = useState<ValuationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);

  // Lazy-load detail
  useEffect(() => {
    if (isExpanded && !detail && !loading) {
      setLoading(true);
      getValuationDetail(record.id)
        .then(setDetail)
        .catch(() => setDetail(null))
        .finally(() => setLoading(false));
    }
  }, [isExpanded, record.id, detail, loading]);

  const isDual = record.reported_currency && record.currency && record.reported_currency !== record.currency;
  const repCur = record.reported_currency || record.currency || "";
  const stkCur = record.currency || repCur;

  // DCF display: reporting-currency IV
  const pps = record.price_per_share;
  const gapDcf = record.gap_dcf_price;
  const intrinsicRep = _v(pps) ? pps : (!isDual && _v(gapDcf) ? gapDcf : null);

  // Trading-currency IV (for dual)
  let ivTrade: number | null = null;
  if (isDual) {
    if (_v(gapDcf)) ivTrade = gapDcf;
    else if (_v(pps) && pps! > 0 && _v(record.forex_rate) && record.forex_rate! > 0) {
      ivTrade = pps! * record.forex_rate!;
    }
  }

  const mkt = _v(record.gap_market_price) ? record.gap_market_price : (_v(record.market_price) ? record.market_price : null);
  const adj = record.gap_adjusted_price;

  if (deleted) return null;

  async function handleDelete() {
    try {
      await deleteValuation(record.id);
      setDeleted(true);
    } catch { /* ignore */ }
  }

  const tabNames = [
    locale === "zh" ? "历史数据" : "Historical",
    locale === "zh" ? "DCF分解" : "DCF Breakdown",
    locale === "zh" ? "AI分析" : "AI Reasoning",
    locale === "zh" ? "敏感性" : "Sensitivity",
    locale === "zh" ? "差距分析" : "Gap Analysis",
  ];

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg mb-2 transition-shadow hover:shadow-md hover:border-blue-400 dark:hover:border-blue-500">
      {/* Row header (always visible, clickable) */}
      <button
        onClick={onToggle}
        className="w-full text-left px-4 py-2.5 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-800/30 transition-colors rounded-t-lg"
      >
        <svg className={`w-4 h-4 text-gray-400 transition-transform flex-shrink-0 ${isExpanded ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>

        <span className="text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap w-24 font-mono">{record.valuation_date}</span>

        <span className="font-semibold text-sm text-gray-900 dark:text-white truncate max-w-[180px]">{record.company_name}</span>

        <Link
          href={`/stock/${record.ticker}`}
          onClick={(e) => e.stopPropagation()}
          className="text-sm text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
        >
          {record.ticker}
        </Link>

        <span className={`inline-block px-2 py-0.5 text-[10px] rounded-full font-medium whitespace-nowrap ${modeBadgeColor(record.mode)}`}>
          {modeLabel(record.mode)}
        </span>

        {record.ai_engine && (
          <span className="text-[11px] text-gray-500 whitespace-nowrap">{record.ai_engine}</span>
        )}

        <span className="text-[11px] text-gray-400 whitespace-nowrap">{repCur}</span>

        <span className="ml-auto font-mono text-sm whitespace-nowrap">
          {fmtPrice(intrinsicRep)}
        </span>

        {_v(adj) && (
          <span className="font-mono text-sm text-gray-500 whitespace-nowrap">
            {fmtPrice(_v(record.gap_adjusted_price_reporting) ? record.gap_adjusted_price_reporting : adj)}
          </span>
        )}
      </button>

      {/* Expanded Detail */}
      {isExpanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-4">
          {/* Key metrics bar */}
          <div className="flex flex-wrap gap-6 mb-4 font-mono text-sm">
            {isDual ? (
              <>
                <div>
                  <div className="text-[10px] text-gray-400 uppercase">DCF ({repCur})</div>
                  <div className="text-lg font-bold">{fmtPrice(intrinsicRep)}</div>
                </div>
                <div>
                  <div className="text-[10px] text-gray-400 uppercase">DCF ({stkCur})</div>
                  <div className="text-lg font-bold">{fmtPrice(ivTrade)}</div>
                </div>
              </>
            ) : (
              <div>
                <div className="text-[10px] text-gray-400 uppercase">DCF{repCur ? ` (${repCur})` : ""}</div>
                <div className="text-lg font-bold">{fmtPrice(intrinsicRep)}</div>
              </div>
            )}
            <div>
              <div className="text-[10px] text-gray-400 uppercase">{locale === "zh" ? "市场价" : "Market"}{isDual ? ` (${stkCur})` : (repCur ? ` (${repCur})` : "")}</div>
              <div className="text-lg font-bold">{fmtPrice(mkt)}</div>
            </div>
            <div>
              <div className="text-[10px] text-gray-400 uppercase">Gap</div>
              <div className={`text-lg font-bold ${gapColor(record.gap_pct)}`}>{gapStr(record.gap_pct)}</div>
            </div>
            {_v(adj) && (
              <div>
                <div className="text-[10px] text-gray-400 uppercase">{locale === "zh" ? "AI修正" : "Adjusted"}{isDual ? ` (${stkCur})` : ""}</div>
                <div className="text-lg font-bold">{fmtPrice(adj)}</div>
              </div>
            )}
          </div>

          {loading && (
            <div className="flex items-center justify-center h-24 text-gray-500">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600 mr-2" />
              {locale === "zh" ? "加载中..." : "Loading..."}
            </div>
          )}

          {detail && !loading && (
            <>
              {/* Tabs */}
              <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700 mb-4 overflow-x-auto">
                {tabNames.map((name, i) => (
                  <button
                    key={i}
                    onClick={() => setActiveTab(i)}
                    className={`px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-colors ${
                      activeTab === i
                        ? "text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400 -mb-px"
                        : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    }`}
                  >
                    {name}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              <div className="min-h-[100px]">
                {activeTab === 0 && <HistoricalTab detail={detail} />}
                {activeTab === 1 && <DCFBreakdownTab detail={detail} />}
                {activeTab === 2 && <AIReasoningTab detail={detail} />}
                {activeTab === 3 && <SensitivityTab detail={detail} />}
                {activeTab === 4 && <GapAnalysisTab detail={detail} />}
              </div>

              {/* Delete button */}
              <div className="flex justify-end mt-4 pt-3 border-t border-gray-100 dark:border-gray-800">
                {confirmDelete ? (
                  <div className="flex gap-2">
                    <button
                      onClick={handleDelete}
                      className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
                    >
                      {locale === "zh" ? "确认删除" : "Confirm Delete"}
                    </button>
                    <button
                      onClick={() => setConfirmDelete(false)}
                      className="px-3 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      {locale === "zh" ? "取消" : "Cancel"}
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setConfirmDelete(true)}
                    className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                    title={locale === "zh" ? "删除" : "Delete"}
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                    </svg>
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────
// Main Page
// ────────────────────────────────────────

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
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");

  // Accordion: which card is expanded
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const search = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await searchValuations({
        q: query || undefined,
        modes: selectedModes.length ? selectedModes.join(",") : undefined,
        engines: selectedEngines.length ? selectedEngines.join(",") : undefined,
        date_start: dateStart || undefined,
        date_end: dateEnd || undefined,
        limit: 200,
      });
      setRecords(res.results);
      setTotalCount(res.count);
      setExpandedId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [query, selectedModes, selectedEngines, dateStart, dateEnd]);

  const [searched, setSearched] = useState(false);

  // Wrap search to track searched state
  const doSearch = useCallback(async () => {
    await search();
    setSearched(true);
  }, [search]);

  // Initial load — only check availability and fetch filters, don't auto-search
  useEffect(() => {
    (async () => {
      try {
        const status = await getHistoryStatus();
        setAvailable(status.available);
        if (!status.available) {
          setLoading(false);
          return;
        }
        const f = await getHistoryFilters();
        setFilters(f);
        setLoading(false);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load");
        setLoading(false);
      }
    })();
  }, []);

  // Check if all results are same company
  const isSingleCompany = useMemo(() => {
    if (records.length === 0) return false;
    const first = records[0].company_name;
    return records.every((r) => r.company_name === first);
  }, [records]);

  return (
    <>
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          {locale === "zh" ? "估值记录" : "Valuation History"}
        </h1>

        {available === false && !loading && (
          <div className="text-center py-20">
            <div className="text-5xl mb-4">&#128202;</div>
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
            {/* Search Bar */}
            <div className="max-w-2xl mb-6">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
                placeholder={locale === "zh" ? "输入代码或公司名，回车搜索 ..." : "Enter ticker or company, press Enter to search ..."}
                className="w-full px-4 py-2.5 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                autoFocus
              />
            </div>

            {/* Advanced Filters — only show when there are results */}
            {searched && records.length > 0 && (
              <div className="flex flex-wrap gap-3 mb-5 items-end">
                {filters && filters.modes.length > 0 && (
                  <MultiSelect
                    label={locale === "zh" ? "估值模式" : "Mode"}
                    options={filters.modes}
                    selected={selectedModes}
                    onChange={setSelectedModes}
                    renderOption={modeLabel}
                  />
                )}
                {filters && filters.engines.length > 0 && (
                  <MultiSelect
                    label={locale === "zh" ? "AI引擎" : "AI Engine"}
                    options={filters.engines}
                    selected={selectedEngines}
                    onChange={setSelectedEngines}
                  />
                )}
                <input type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)}
                  className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                <input type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)}
                  className="px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none" />
                <button onClick={doSearch} className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                  {locale === "zh" ? "筛选" : "Filter"}
                </button>
              </div>
            )}

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

            {!loading && searched && records.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                {locale === "zh" ? "没有找到匹配的估值记录" : "No matching valuations found"}
              </div>
            )}

            {!loading && !searched && (
              <div className="py-16" />
            )}

            {!loading && searched && records.length > 0 && (
              <>
                {/* Single-Company Summary Panel */}
                {isSingleCompany && <SummaryPanel records={records} />}

                {/* Overview Table */}
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden mb-4">
                  <div className="overflow-auto max-h-[70vh]">
                    <table className="w-full text-xs font-mono">
                      <thead className="sticky top-0 z-10 bg-white dark:bg-gray-900">
                        <tr className="border-b-2 border-gray-200 dark:border-gray-700 text-[11px] text-blue-700 dark:text-blue-300 uppercase">
                          <th className="text-left px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "日期" : "Date"}</th>
                          <th className="text-left px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "公司" : "Company"}</th>
                          <th className="text-left px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "代码" : "Ticker"}</th>
                          <th className="text-left px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "模式" : "Mode"}</th>
                          <th className="text-left px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "AI引擎" : "AI Engine"}</th>
                          <th className="text-left px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "币种" : "Currency"}</th>
                          <th className="text-right px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "DCF估值" : "DCF Estimate"}</th>
                          <th className="text-right px-3 py-2 bg-white dark:bg-gray-900">{locale === "zh" ? "AI修正估值" : "Adj. DCF"}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((r) => {
                          const rIsDual = r.reported_currency && r.currency && r.reported_currency !== r.currency;
                          // DCF Estimate — in trading currency
                          const rPps = r.price_per_share; // reporting currency
                          const rGdcf = r.gap_dcf_price;  // trading currency
                          let dcfDisplay: number | null = null;
                          if (_v(rGdcf)) dcfDisplay = rGdcf;
                          else if (_v(rPps) && !rIsDual) dcfDisplay = rPps; // single-currency
                          else if (_v(rPps) && rIsDual && _v(r.forex_rate) && r.forex_rate! > 0) dcfDisplay = rPps! * r.forex_rate!; // convert to trading

                          // Adjusted DCF — in trading currency
                          const rAdjTrade = r.gap_adjusted_price;         // trading currency
                          const rAdjRep = r.gap_adjusted_price_reporting; // reporting currency
                          let adjDisplay: number | null = null;
                          if (_v(rAdjTrade)) adjDisplay = rAdjTrade;
                          else if (_v(rAdjRep) && !rIsDual) adjDisplay = rAdjRep; // single-currency
                          else if (_v(rAdjRep) && rIsDual && _v(r.forex_rate) && r.forex_rate! > 0) adjDisplay = rAdjRep! * r.forex_rate!; // convert

                          return (
                            <tr
                              key={r.id}
                              onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                              className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-blue-50/40 dark:hover:bg-blue-900/10 cursor-pointer transition-colors"
                            >
                              <td className="px-3 py-1.5 whitespace-nowrap text-gray-600 dark:text-gray-400">{r.valuation_date}</td>
                              <td className="px-3 py-1.5 text-gray-900 dark:text-white font-medium truncate max-w-[160px]">{r.company_name}</td>
                              <td className="px-3 py-1.5 whitespace-nowrap">{r.ticker || "\u2014"}</td>
                              <td className="px-3 py-1.5 whitespace-nowrap uppercase">{r.mode}</td>
                              <td className="px-3 py-1.5 whitespace-nowrap text-gray-500">{r.ai_engine || "\u2014"}</td>
                              <td className="px-3 py-1.5 whitespace-nowrap text-gray-500">{r.currency || r.reported_currency || "\u2014"}</td>
                              <td className="text-right px-3 py-1.5 whitespace-nowrap">{fmtPrice(dcfDisplay)}</td>
                              <td className="text-right px-3 py-1.5 whitespace-nowrap">{fmtPrice(adjDisplay)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="px-4 py-2 text-[11px] text-gray-500 border-t border-gray-200 dark:border-gray-800">
                    {locale === "zh" ? `共 ${records.length} 条记录` : `${records.length} records`}
                  </div>
                </div>

                {/* Expandable Detail Cards */}
                <div className="space-y-0">
                  {records.map((r) => (
                    <DetailCard
                      key={r.id}
                      record={r}
                      isExpanded={expandedId === r.id}
                      onToggle={() => setExpandedId(expandedId === r.id ? null : r.id)}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </main>
    </>
  );
}
