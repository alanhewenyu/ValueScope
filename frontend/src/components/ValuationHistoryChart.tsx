"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { useI18n } from "@/lib/i18n";

interface ValuationHistoryChartProps {
  data: { date: string; value: number }[];
  label: string;
  stats: {
    min: number;
    max: number;
    mean: number;
    median: number;
    current: number;
  } | null;
  color?: string;
}

export default function ValuationHistoryChart({
  data,
  label,
  stats,
  color = "#3b82f6",
}: ValuationHistoryChartProps) {
  const { t } = useI18n();

  if (!data || data.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
        {t.noHistoricalData(label)}
      </div>
    );
  }

  return (
    <div>
      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {t.historyTitle(label)}
      </h4>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
            <defs>
              <linearGradient id={`grad-${label}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.2} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              tickFormatter={(d) => d.slice(0, 7)}
              minTickGap={60}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#9ca3af" }}
              domain={["auto", "auto"]}
              width={40}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255,255,255,0.95)",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelFormatter={(d) => d}
              formatter={(v) => [Number(v).toFixed(2), label]}
            />
            {stats?.mean && (
              <ReferenceLine
                y={stats.mean}
                stroke="#9ca3af"
                strokeDasharray="4 4"
                label={{ value: t.mean(stats.mean.toFixed(1)), fontSize: 10, fill: "#9ca3af" }}
              />
            )}
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              fill={`url(#grad-${label})`}
              strokeWidth={1.5}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
