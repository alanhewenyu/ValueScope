"use client";

import { formatCurrency, formatPercent } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

interface VerdictCardProps {
  dcfPrice: number;
  marketPrice: number;
  diffPct: number;
  currency: string;
  companyName: string;
  ttmLabel?: string;
}

export default function VerdictCard({
  dcfPrice,
  marketPrice,
  diffPct,
  currency,
  companyName,
  ttmLabel,
}: VerdictCardProps) {
  const { t } = useI18n();

  // Determine verdict
  const absDiff = Math.abs(diffPct);
  let verdict: string;
  let verdictColor: string;
  let bgColor: string;

  if (diffPct > 0.15) {
    verdict = t.verdictAbove;
    verdictColor = "text-green-700 dark:text-green-400";
    bgColor = "bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800";
  } else if (diffPct < -0.15) {
    verdict = t.verdictBelow;
    verdictColor = "text-red-700 dark:text-red-400";
    bgColor = "bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800";
  } else {
    verdict = t.verdictFair;
    verdictColor = "text-yellow-700 dark:text-yellow-400";
    bgColor = "bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800";
  }

  return (
    <div className={`rounded-xl border p-6 ${bgColor}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          {t.dcfResult}
        </h3>
        {ttmLabel && (
          <span className="text-xs text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
            {ttmLabel}
          </span>
        )}
      </div>

      <div className="flex items-baseline gap-3 mb-2">
        <span className={`text-2xl font-bold ${verdictColor}`}>
          {verdict}
        </span>
        <span className={`text-lg font-semibold ${verdictColor}`}>
          {diffPct > 0 ? "+" : ""}{formatPercent(diffPct, 1)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 mt-4">
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
            {t.dcfEstimate}
          </div>
          <div className="text-xl font-semibold text-gray-900 dark:text-white">
            {formatCurrency(dcfPrice, currency)}
          </div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400 mb-1">
            {t.marketPrice}
          </div>
          <div className="text-xl font-semibold text-gray-900 dark:text-white">
            {formatCurrency(marketPrice, currency)}
          </div>
        </div>
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500 mt-4 text-left">
        ⚙️ {t.dcfDisclaimer}
      </p>
    </div>
  );
}
