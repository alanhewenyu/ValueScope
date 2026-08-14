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

// GA4 treats these event params as traffic-source attribution input, not as
// custom dimensions — passing one overwrites the session's real source and
// dumps it into the Unassigned channel. Use link_location / click_source etc.
const RESERVED_ATTRIBUTION_PARAMS = [
  "source",
  "medium",
  "campaign",
  "campaign_id",
  "term",
  "content",
  "source_platform",
];

export function trackEvent(
  name: string,
  params?: Record<string, string | number | boolean>,
) {
  if (typeof window === "undefined") return;
  const safeParams = { ...(params ?? {}) };
  for (const key of RESERVED_ATTRIBUTION_PARAMS) {
    if (key in safeParams) {
      delete safeParams[key];
      if (process.env.NODE_ENV !== "production") {
        console.warn(
          `trackEvent("${name}"): dropped reserved GA4 param "${key}" — it would overwrite traffic attribution.`,
        );
      }
    }
  }
  try {
    window.gtag?.("event", name, safeParams);
  } catch {
    // analytics must never break the app
  }
}
