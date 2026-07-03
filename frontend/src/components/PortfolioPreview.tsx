"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { trackEvent } from "@/lib/gtag";

/** Logged-out /portfolio: a read-only sample portfolio rendered in the real
 *  UI style, so visitors see the product's value before being asked to
 *  register (previously this route was just a lock icon). */

const SAMPLE_NAV = [100, 101.2, 100.5, 102.8, 104.1, 103.2, 105.6, 107.9, 106.8, 109.4, 111.2, 113.8];
const SAMPLE_BENCH = [100, 100.8, 99.6, 101.1, 102.0, 101.2, 102.5, 103.8, 103.1, 104.6, 105.2, 106.4];

const SAMPLE_HOLDINGS = [
  { name: "贵州茅台", ticker: "600519.SS", market: "A股", broker: "华泰", qty: "200", cost: "¥1,420.00", price: "¥1,189.00", pnl: -16.3 },
  { name: "腾讯控股", ticker: "0700.HK", market: "港股", broker: "富途", qty: "500", cost: "HK$385.20", price: "HK$492.60", pnl: 27.9 },
  { name: "Apple", ticker: "AAPL", market: "美股", broker: "IBKR", qty: "120", cost: "$186.40", price: "$308.63", pnl: 65.6 },
  { name: "长江电力", ticker: "600900.SS", market: "A股", broker: "华泰", qty: "3,000", cost: "¥22.15", price: "¥29.84", pnl: 34.7 },
];

function NavChart() {
  const w = 560, h = 150, pad = 8;
  const all = [...SAMPLE_NAV, ...SAMPLE_BENCH];
  const min = Math.min(...all), max = Math.max(...all);
  const x = (i: number) => pad + (i / (SAMPLE_NAV.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - min) / (max - min)) * (h - 2 * pad);
  const line = (data: number[]) => data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-36" preserveAspectRatio="none" aria-hidden>
      <polyline points={line(SAMPLE_BENCH)} fill="none" stroke="#9ca3af" strokeWidth="1.5" strokeDasharray="4 3" />
      <polyline points={line(SAMPLE_NAV)} fill="none" stroke="#3b82f6" strokeWidth="2" />
    </svg>
  );
}

export default function PortfolioPreview() {
  const { locale } = useI18n();
  const zh = locale === "zh";

  const kpis = [
    { label: zh ? "净资产" : "Net Assets", value: "¥1,286,400", sub: zh ? "示例" : "sample" },
    { label: zh ? "今年以来收益" : "YTD Return", value: "+13.8%", sub: zh ? "vs 沪深300 +6.4%" : "vs CSI300 +6.4%", green: true },
    { label: zh ? "累计浮动盈亏" : "Unrealized P&L", value: "+¥168,900", green: true },
    { label: zh ? "杠杆" : "Leverage", value: "0%" },
  ];

  const features = zh
    ? ["A股 · 港股 · 美股 · 日股多市场持仓，统一人民币计价", "摊薄成本（国内券商）与平均成本（IBKR）两种口径并存", "每日自动快照：净值曲线、YTD 收益、与基准指数对比", "券商 CSV 一键导入，多账户合并视图"]
    : ["Multi-market holdings (A-shares, HK, US, JP) unified in CNY", "Diluted & average cost methods side by side (CN brokers / IBKR)", "Automatic daily snapshots: NAV curve, YTD return, benchmark compare", "One-click broker CSV import, multi-account view"];

  return (
    <main className="max-w-[1100px] mx-auto px-4 py-8">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white m-0">Portfolio Tracker</h2>
        <span className="text-[11px] px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
          {zh ? "示例数据 · 注册后管理你自己的持仓" : "Sample data · sign up to track your own"}
        </span>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {kpis.map((k) => (
          <div key={k.label} className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4">
            <div className="text-xs text-gray-400 mb-1">{k.label}</div>
            <div className={`text-lg font-bold ${k.green ? "text-green-600 dark:text-green-400" : "text-gray-900 dark:text-white"}`}>{k.value}</div>
            {k.sub && <div className="text-[10px] text-gray-400 mt-0.5">{k.sub}</div>}
          </div>
        ))}
      </div>

      {/* NAV chart */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 m-0">
            {zh ? "组合净值 vs 基准" : "Portfolio NAV vs Benchmark"}
          </h3>
          <div className="flex gap-4 text-[11px] text-gray-400">
            <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-blue-500 inline-block" /> Portfolio +13.8%</span>
            <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-gray-400 inline-block" style={{ borderTop: "1.5px dashed #9ca3af", height: 0 }} /> {zh ? "沪深300" : "CSI 300"} +6.4%</span>
          </div>
        </div>
        <NavChart />
      </div>

      {/* Holdings table */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-x-auto mb-6">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-400 border-b border-gray-100 dark:border-gray-800">
              <th className="text-left px-4 py-2.5 font-medium">{zh ? "名称" : "Name"}</th>
              <th className="text-left px-4 py-2.5 font-medium">{zh ? "市场" : "Market"}</th>
              <th className="text-left px-4 py-2.5 font-medium">{zh ? "券商" : "Broker"}</th>
              <th className="text-right px-4 py-2.5 font-medium">{zh ? "持仓量" : "Qty"}</th>
              <th className="text-right px-4 py-2.5 font-medium">{zh ? "成本" : "Cost"}</th>
              <th className="text-right px-4 py-2.5 font-medium">{zh ? "现价" : "Price"}</th>
              <th className="text-right px-4 py-2.5 font-medium">{zh ? "盈亏" : "P&L"}</th>
            </tr>
          </thead>
          <tbody>
            {SAMPLE_HOLDINGS.map((h) => (
              <tr key={h.ticker} className="border-b border-gray-50 dark:border-gray-800/50">
                <td className="px-4 py-2.5">
                  <span className="text-gray-900 dark:text-white">{h.name}</span>
                  <span className="text-xs text-gray-400 ml-2">{h.ticker}</span>
                </td>
                <td className="px-4 py-2.5 text-gray-500">{h.market}</td>
                <td className="px-4 py-2.5 text-gray-500">{h.broker}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{h.qty}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{h.cost}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{h.price}</td>
                <td className={`px-4 py-2.5 text-right tabular-nums font-medium ${h.pnl >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                  {h.pnl >= 0 ? "+" : ""}{h.pnl.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Features + CTA */}
      <div className="grid sm:grid-cols-2 gap-6 items-center bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400 m-0">
          {features.map((f) => (
            <li key={f} className="flex gap-2">
              <span className="text-green-500 shrink-0">✓</span>
              {f}
            </li>
          ))}
        </ul>
        <div className="text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
            {zh ? "免费注册，导入你的持仓，第二天起自动记录净值曲线" : "Sign up free, import your holdings — NAV history starts tomorrow"}
          </p>
          <Link
            href="/auth"
            onClick={() => trackEvent("portfolio_preview_signup_click")}
            className="inline-block px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            {zh ? "免费注册 / 登录" : "Sign Up Free / Log In"}
          </Link>
        </div>
      </div>
    </main>
  );
}
