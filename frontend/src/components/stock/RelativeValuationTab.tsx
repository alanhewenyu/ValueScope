"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getRelativeValuation, type RelativeValuationData } from "@/lib/api";
import PercentileBar from "@/components/PercentileBar";
import ValuationHistoryChart from "@/components/ValuationHistoryChart";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/lib/settings";

function MetricItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">
        {label}
      </div>
      <div className="text-lg font-semibold text-gray-900 dark:text-white">
        {value}
      </div>
    </div>
  );
}

export default function RelativeValuationTab({ ticker, initialData }: { ticker: string; initialData?: RelativeValuationData | null }) {
  const { t } = useI18n();
  const { fmpApiKey } = useSettings();
  const [data, setData] = useState<RelativeValuationData | null>(initialData ?? null);
  const [loading, setLoading] = useState(!initialData);
  const [error, setError] = useState("");
  const [years, setYears] = useState(5);

  useEffect(() => {
    // Skip fetch if we have initial data for default 5Y view
    if (years === 5 && initialData) {
      setData(initialData);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    const apikey = fmpApiKey;
    getRelativeValuation(ticker, apikey, years)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticker, years, fmpApiKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        <span className="ml-2 text-gray-500">{t.loadingValuation}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-950/30 rounded-xl p-6 text-red-600 dark:text-red-400">
        {error}
      </div>
    );
  }

  if (!data) return null;

  const { current, historical } = data;

  return (
    <div className="space-y-6">
      {/* Current valuation metrics */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t.currentValuationMetrics}
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <MetricItem
            label={t.trailingPE}
            value={current.trailing_pe?.toFixed(1) ?? "\u2014"}
          />
          <MetricItem
            label={t.forwardPE}
            value={current.forward_pe?.toFixed(1) ?? "\u2014"}
          />
          <MetricItem
            label={t.pb}
            value={current.price_to_book?.toFixed(1) ?? "\u2014"}
          />
          <MetricItem
            label={t.ps}
            value={current.price_to_sales?.toFixed(1) ?? "\u2014"}
          />
          <MetricItem
            label={t.evEbitda}
            value={current.ev_to_ebitda?.toFixed(1) ?? "\u2014"}
          />
        </div>
        <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-3">{t.dataSource("yfinance")}</p>
      </div>

      {/* Historical percentiles with time range selector */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {t.historicalPercentile}
          </h3>
          {/* Time range selector */}
          <div className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
            {[3, 5, 10].map((y) => (
              <button
                key={y}
                onClick={() => setYears(y)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors
                  ${
                    years === y
                      ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm"
                      : "text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                  }
                `}
              >
                {y}Y
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <PercentileBar
            label={t.peRatio}
            percentile={historical.pe_percentile}
            current={historical.pe_stats?.current ?? null}
            min={historical.pe_stats?.min ?? null}
            max={historical.pe_stats?.max ?? null}
            mean={historical.pe_stats?.mean ?? null}
          />
          <PercentileBar
            label={t.pbRatio}
            percentile={historical.pb_percentile}
            current={historical.pb_stats?.current ?? null}
            min={historical.pb_stats?.min ?? null}
            max={historical.pb_stats?.max ?? null}
            mean={historical.pb_stats?.mean ?? null}
          />
        </div>
        {historical.data_source && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">
            {t.dataSource(historical.data_source)}
          </p>
        )}
      </div>

      {/* Historical charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <ValuationHistoryChart
            data={historical.pe_history || []}
            label="P/E"
            stats={historical.pe_stats}
            color="#3b82f6"
          />
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <ValuationHistoryChart
            data={historical.pb_history || []}
            label="P/B"
            stats={historical.pb_stats}
            color="#8b5cf6"
          />
        </div>
      </div>

      {/* Data source footnote */}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        ⚙️ {t.relativeDataNote}
      </p>
    </div>
  );
}
