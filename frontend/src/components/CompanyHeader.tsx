"use client";

import Link from "next/link";
import { formatCurrency, formatLargeNumber } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { trackEvent } from "@/lib/gtag";

interface CompanyHeaderProps {
  companyName: string;
  ticker: string;
  price: number;
  currency: string;
  marketCap: number;
  industry: string;
  sector: string;
  exchange: string;
  country: string;
  image?: string;
  indexes?: string[];
}

export default function CompanyHeader({
  companyName,
  ticker,
  price,
  currency,
  marketCap,
  industry,
  sector,
  exchange,
  country,
  image,
  indexes,
}: CompanyHeaderProps) {
  const { t } = useI18n();
  return (
    <div className="flex items-start gap-4 mb-6">
      {image && (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          src={image}
          alt={companyName}
          width={48}
          height={48}
          loading="lazy"
          className="w-12 h-12 rounded-lg object-contain bg-white border border-gray-200 dark:border-gray-700 p-1"
        />
      )}
      <div className="flex-1">
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
            {companyName}
          </h1>
          <span className="font-mono text-base sm:text-lg text-blue-600 dark:text-blue-400">
            {ticker}
          </span>
          {exchange && (
            <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
              {exchange}
            </span>
          )}
          <Link
            href="/mcp"
            onClick={() => trackEvent("mcp_docs_click", { source: "stock_header", ticker })}
            className="text-xs font-medium text-violet-600 dark:text-violet-400 bg-violet-50 dark:bg-violet-950/50 px-2 py-0.5 rounded hover:bg-violet-100 dark:hover:bg-violet-900/50 transition-colors"
          >
            {t.mcpStockChip}
          </Link>
        </div>
        <div className="flex items-center gap-4 mt-2 text-sm text-gray-500 dark:text-gray-400 flex-wrap">
          {price > 0 && (
            <span className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white">
              {formatCurrency(price, currency)}
              <span className="text-xs font-normal text-gray-400 ml-1">{t.currentPrice}</span>
            </span>
          )}
          {marketCap > 0 && (
            <span>{t.marketCap}: {formatLargeNumber(marketCap)}</span>
          )}
        </div>
        {/* Industry / Sector / Country / Index tags */}
        {(industry || sector || country || (indexes && indexes.length > 0)) && (
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            {indexes && indexes.map((idx) => (
              <span
                key={idx}
                className="text-xs bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 px-2.5 py-0.5 rounded-full border border-amber-200 dark:border-amber-800 font-medium"
              >
                {idx}
              </span>
            ))}
            {sector && (
              <span className="text-xs bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 px-2.5 py-0.5 rounded-full border border-blue-200 dark:border-blue-800">
                {sector}
              </span>
            )}
            {industry && (
              <span className="text-xs bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 px-2.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
                {industry}
              </span>
            )}
            {country && (
              <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2.5 py-0.5 rounded-full border border-gray-200 dark:border-gray-700">
                {country}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
