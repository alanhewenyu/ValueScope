"use client";

import { useI18n } from "@/lib/i18n";

interface FinancialTableProps {
  columns: string[];
  index: string[];
  data: string[][];
  title?: string;
}

/** Section header rows — rendered as category dividers */
const isSectionHeader = (label: string) => label.startsWith("▸");

/** Display label overrides for clarity (English fallback) */
const DISPLAY_LABELS: Record<string, string> = {
  "(+) Total Debt": "(+) Interest-Bearing Debt",
  "Debt to Assets (%)": "Int-Bearing Debt / Assets (%)",
};

/** Map English backend labels → i18n key names */
const FIN_LABEL_MAP: Record<string, string> = {
  "▸ Profitability": "fin_secProfitability",
  "▸ Reinvestment": "fin_secReinvestment",
  "▸ Capital Structure": "fin_secCapital",
  "▸ Key Ratios": "fin_secRatios",
  "Revenue": "fin_revenue",
  "EBIT": "fin_ebit",
  "Revenue Growth (%)": "fin_revGrowth",
  "EBIT Growth (%)": "fin_ebitGrowth",
  "EBIT Margin (%)": "fin_ebitMargin",
  "Tax Rate (%)": "fin_taxRate",
  "(+) Capital Expenditure": "fin_capex",
  "(-) D&A": "fin_da",
  "(+) ΔWorking Capital": "fin_wc",
  "Total Reinvestment": "fin_totalReinv",
  "(+) Total Debt": "fin_totalDebt",
  "(+) Total Equity": "fin_totalEquity",
  "(-) Cash & Equivalents": "fin_cash",
  "(-) Total Investments": "fin_investments",
  "Invested Capital": "fin_investedCapital",
  "Minority Interest": "fin_minority",
  "Revenue / IC": "fin_revIc",
  "Debt to Assets (%)": "fin_debtAssets",
  "Cost of Debt (%)": "fin_costDebt",
  "ROIC (%)": "fin_roic",
  "ROE (%)": "fin_roe",
  "Dividend Yield (%)": "fin_divYield",
  "Payout Ratio (%)": "fin_payout",
};

export default function FinancialTable({
  columns,
  index,
  data,
  title,
}: FinancialTableProps) {
  const { t } = useI18n();

  const getLabel = (label: string): string => {
    const key = FIN_LABEL_MAP[label];
    if (key) {
      const translated = (t as unknown as Record<string, unknown>)[key];
      if (typeof translated === "string") return translated;
    }
    return DISPLAY_LABELS[label] || label;
  };
  return (
    <div>
      {title && (
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          {title}
        </h3>
      )}
    <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-20">
          <tr className="border-b-2 border-gray-200 dark:border-gray-700">
            <th className="text-left py-2 px-3 font-semibold text-gray-500 dark:text-gray-400 sticky left-0 bg-white dark:bg-gray-950 z-30 min-w-[200px]">
              {t.metric}
            </th>
            {columns.map((col) => (
              <th
                key={col}
                className="text-right py-2 px-3 font-semibold text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-950 min-w-[100px]"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {index.map((rowLabel, rowIdx) => {
            if (isSectionHeader(rowLabel)) {
              // Section header row — spans full width, bold label, subtle background
              return (
                <tr
                  key={rowLabel}
                  className="border-b border-gray-200 dark:border-gray-700"
                >
                  <td
                    colSpan={columns.length + 1}
                    className="py-2 px-3 text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 bg-gray-50/80 dark:bg-gray-800/40 sticky left-0"
                  >
                    {getLabel(rowLabel).replace(/^▸\s*/, "")}
                  </td>
                </tr>
              );
            }

            return (
              <tr
                key={rowLabel}
                className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900/50 transition-colors"
              >
                <td
                  className="py-2 px-3 sticky left-0 bg-inherit text-gray-700 dark:text-gray-300"
                >
                  {getLabel(rowLabel)}
                </td>
                {data[rowIdx]?.map((cell, colIdx) => (
                  <td
                    key={colIdx}
                    className={`py-2 px-3 text-right font-mono text-gray-800 dark:text-gray-200
                      ${
                        typeof cell === "string" && cell.startsWith("-")
                          ? "text-red-600 dark:text-red-400"
                          : ""
                      }
                    `}
                  >
                    {cell ?? "—"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </div>
  );
}
