"use client";

import { useI18n } from "@/lib/i18n";

interface PercentileBarProps {
  label: string;
  percentile: number | null;
  current: number | null;
  min: number | null;
  max: number | null;
  mean: number | null;
}

export default function PercentileBar({
  label,
  percentile,
  current,
  min,
  max,
  mean,
}: PercentileBarProps) {
  const { t } = useI18n();

  if (percentile === null || current === null) {
    return (
      <div className="py-3">
        <div className="flex justify-between text-sm mb-1">
          <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
          <span className="text-gray-400">{t.na}</span>
        </div>
        <div className="h-3 bg-gray-100 dark:bg-gray-800 rounded-full" />
      </div>
    );
  }

  // Color based on percentile: low = green (undervalued), high = red (overvalued)
  let barColor: string;
  let textColor: string;
  if (percentile <= 20) {
    barColor = "bg-green-500";
    textColor = "text-green-600 dark:text-green-400";
  } else if (percentile <= 40) {
    barColor = "bg-green-400";
    textColor = "text-green-600 dark:text-green-400";
  } else if (percentile <= 60) {
    barColor = "bg-yellow-400";
    textColor = "text-yellow-600 dark:text-yellow-400";
  } else if (percentile <= 80) {
    barColor = "bg-orange-400";
    textColor = "text-orange-600 dark:text-orange-400";
  } else {
    barColor = "bg-red-500";
    textColor = "text-red-600 dark:text-red-400";
  }

  return (
    <div className="py-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
        <div className="flex items-center gap-3">
          <span className="text-gray-400 text-xs">
            {min?.toFixed(1)} — {mean?.toFixed(1)} — {max?.toFixed(1)}
          </span>
          <span className={`font-semibold ${textColor}`}>
            {current.toFixed(1)}x
          </span>
        </div>
      </div>

      {/* Bar */}
      <div className="relative h-3 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`absolute h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(100, percentile)}%` }}
        />
        {/* Mean marker */}
        {mean !== null && min !== null && max !== null && max > min && (
          <div
            className="absolute top-0 h-full w-0.5 bg-gray-400 dark:bg-gray-500"
            style={{
              left: `${((mean - min) / (max - min)) * 100}%`,
            }}
          />
        )}
      </div>

      <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
        <span>{t.low}</span>
        <span className={textColor}>
          {t.thPercentile(percentile.toFixed(0))}
        </span>
        <span>{t.high}</span>
      </div>
    </div>
  );
}
