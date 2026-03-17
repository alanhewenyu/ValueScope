"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { getScores, type ScoresData } from "@/lib/api";
import ScoreRadar from "@/components/ScoreRadar";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/lib/settings";

// ── Helper components (private) ──

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

function ScoreBar({
  label,
  score,
  weight,
}: {
  label: string;
  score: number;
  weight: number;
}) {
  const pct = score;
  let barColor: string;
  if (score >= 75) barColor = "bg-green-500";
  else if (score >= 60) barColor = "bg-blue-500";
  else if (score >= 40) barColor = "bg-yellow-500";
  else if (score >= 25) barColor = "bg-orange-500";
  else barColor = "bg-red-500";

  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-gray-700 dark:text-gray-300">
          {label}
          <span className="text-xs text-gray-400 ml-1">({weight}%)</span>
        </span>
        <span className="font-semibold text-gray-900 dark:text-white">
          {score}
        </span>
      </div>
      <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function ScoreLabel({
  range,
  label,
  color,
}: {
  range: string;
  label: string;
  color: string;
}) {
  return (
    <div className={`${color} px-3 py-2 rounded-lg text-center`}>
      <div className="font-semibold text-xs">{range}</div>
      <div className="text-xs mt-0.5">{label}</div>
    </div>
  );
}

// ── ScoringTab ──

export default function ScoringTab({ ticker, initialScores }: { ticker: string; initialScores?: ScoresData | null }) {
  const { t } = useI18n();
  const { fmpApiKey } = useSettings();
  const [scores, setScores] = useState<ScoresData | null>(initialScores ?? null);
  const [loading, setLoading] = useState(!initialScores);
  const [error, setError] = useState("");

  useEffect(() => {
    // Skip fetch if parent already provided scores
    if (initialScores) {
      setScores(initialScores);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    const apikey = fmpApiKey;
    getScores(ticker, apikey)
      .then((d) => { if (!cancelled) setScores(d); })
      .catch((e) => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ticker, fmpApiKey, initialScores]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
        <span className="ml-2 text-gray-500">{t.computingScores}</span>
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

  if (!scores) return null;

  const dims = scores.dimensions;

  // Dimension descriptions for methodology section
  const dimInfo: Record<string, { subtitle: string; factors: string }> = {
    value: {
      subtitle: t.dimValuationSub,
      factors: t.dimValuationFactors,
    },
    quality: {
      subtitle: t.dimQualitySub,
      factors: t.dimQualityFactors,
    },
    growth: {
      subtitle: t.dimGrowthSub,
      factors: t.dimGrowthFactors,
    },
    momentum: {
      subtitle: t.dimMomentumSub,
      factors: t.dimMomentumFactors,
    },
  };

  // Map backend labels to display labels
  const displayLabels: Record<string, string> = {
    Valuation: t.dimValuation,
    Quality: t.dimQuality,
    Growth: t.dimGrowth,
    Momentum: t.dimMomentum,
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Score radar chart */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 text-center">
            {t.compositeScore}
          </h3>
          <ScoreRadar scores={scores} />
        </div>

        {/* Score details */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {t.dimensionBreakdown}
          </h3>
          <div className="space-y-4">
            {Object.entries(dims).map(([key, dim]) => (
              <ScoreBar
                key={key}
                label={displayLabels[dim.label] || dim.label}
                score={dim.score}
                weight={dim.weight}
              />
            ))}
          </div>

          <div className="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
                {t.totalScore}
              </span>
              <span className="text-2xl font-bold text-gray-900 dark:text-white">
                {scores.total_score}
                <span className="text-sm text-gray-400 font-normal">
                  /100
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Scoring methodology */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          {t.scoringMethodology}
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t.scoringMethodologyDesc}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(dims).map(([key, dim]) => {
            const info = dimInfo[key];
            if (!info) return null;
            return (
              <div key={key} className="border border-gray-100 dark:border-gray-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-gray-900 dark:text-white text-sm">
                    {displayLabels[dim.label] || dim.label}
                  </span>
                  <span className="text-xs text-gray-400">{dim.weight}%</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 italic">
                  {info.subtitle}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 leading-relaxed">
                  {info.factors}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Score interpretation */}
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          {t.scoreGuide}
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
          <ScoreLabel range="0-20" label={t.veryPoor} color="bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400" />
          <ScoreLabel range="20-40" label={t.belowAverage} color="bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400" />
          <ScoreLabel range="40-60" label={t.average} color="bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-400" />
          <ScoreLabel range="60-80" label={t.aboveAverage} color="bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400" />
          <ScoreLabel range="80-100" label={t.excellent} color="bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400" />
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-4">
          {t.scoringDisclaimer}
        </p>
      </div>
    </div>
  );
}
