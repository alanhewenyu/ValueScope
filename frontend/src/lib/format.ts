/**
 * Number formatting utilities for financial data display.
 */

export function formatNumber(value: number, decimals = 0): string {
  if (value === null || value === undefined || isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPercent(value: number, decimals = 1): string {
  if (value === null || value === undefined || isNaN(value)) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatCurrency(
  value: number,
  currency = "USD",
  decimals = 2
): string {
  if (value === null || value === undefined || isNaN(value)) return "—";
  const symbols: Record<string, string> = {
    USD: "$",
    CNY: "¥",
    HKD: "HK$",
    JPY: "¥",
    GBP: "£",
    EUR: "€",
  };
  const symbol = symbols[currency] || currency + " ";
  return `${symbol}${formatNumber(value, decimals)}`;
}

export function formatLargeNumber(value: number): string {
  if (value === null || value === undefined || isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}
