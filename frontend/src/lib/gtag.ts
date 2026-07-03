/**
 * Google Analytics event helpers.
 *
 * Conversion events for measuring what the site is actually for — running
 * valuations — instead of raw pageviews. After deploying, mark these as
 * Key events in GA Admin → Events: run_valuation, ai_analyze, gap_analyze,
 * export_excel, sign_up.
 */

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

export function trackEvent(
  name: string,
  params?: Record<string, string | number | boolean>,
) {
  if (typeof window === "undefined") return;
  try {
    window.gtag?.("event", name, params ?? {});
  } catch {
    // analytics must never break the app
  }
}
