"use client";

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { ScoresData } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

interface ScoreRadarProps {
  scores: ScoresData;
}

export default function ScoreRadar({ scores }: ScoreRadarProps) {
  const { t } = useI18n();
  const dims = scores.dimensions;

  const data = [
    { dimension: t.dimValuation, score: dims.value.score, fullMark: 100 },
    { dimension: t.dimQuality, score: dims.quality.score, fullMark: 100 },
    { dimension: t.dimGrowth, score: dims.growth.score, fullMark: 100 },
    { dimension: t.dimMomentum, score: dims.momentum.score, fullMark: 100 },
  ];

  // Custom tick: dimension name + score on two lines
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const renderTick = (props: any) => {
    const { x, y, payload } = props;
    const item = data.find((d) => d.dimension === payload.value);
    const score = item?.score ?? "";
    // Nudge labels outward slightly so they don't overlap the polygon
    const cx = 175; // half of max-w-[350px]
    const cy = 150; // half of h-[300px]
    const dx = x - cx;
    const dy = y - cy;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const nudge = 12;
    const nx = x + (dx / dist) * nudge;
    const ny = y + (dy / dist) * nudge;
    return (
      <g>
        <text x={nx} y={ny - 6} textAnchor="middle" fontSize={11} fill="#6b7280">
          {payload.value}
        </text>
        <text x={nx} y={ny + 8} textAnchor="middle" fontSize={11} fontWeight="600" fill="#374151">
          {score}
        </text>
      </g>
    );
  };

  // Determine color based on total score
  let fillColor: string;
  let strokeColor: string;
  if (scores.total_score >= 75) {
    fillColor = "rgba(34, 197, 94, 0.25)";
    strokeColor = "#22c55e";
  } else if (scores.total_score >= 50) {
    fillColor = "rgba(59, 130, 246, 0.25)";
    strokeColor = "#3b82f6";
  } else if (scores.total_score >= 25) {
    fillColor = "rgba(234, 179, 8, 0.25)";
    strokeColor = "#eab308";
  } else {
    fillColor = "rgba(239, 68, 68, 0.25)";
    strokeColor = "#ef4444";
  }

  return (
    <div className="flex flex-col items-center">
      <div className="w-full max-w-[350px] h-[250px] sm:h-[300px]">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
            <PolarGrid
              stroke="#e5e7eb"
              gridType="polygon"
            />
            <PolarAngleAxis
              dataKey="dimension"
              tick={renderTick}
            />
            <PolarRadiusAxis
              angle={90}
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickCount={5}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255,255,255,0.95)",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Radar
              name={t.score}
              dataKey="score"
              stroke={strokeColor}
              fill={fillColor}
              strokeWidth={2}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Total score badge */}
      <div className="flex items-center gap-2 -mt-2">
        <span
          className="text-3xl font-bold"
          style={{ color: strokeColor }}
        >
          {scores.total_score}
        </span>
        <span className="text-sm text-gray-400">/100</span>
      </div>
    </div>
  );
}
