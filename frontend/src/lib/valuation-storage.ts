/**
 * Unified valuation storage interface.
 *
 * Logged-in users → server API (persistent across devices)
 * Anonymous users → IndexedDB (local browser only)
 */

import type { SavedValuation } from "./indexeddb";

const TOKEN_KEY = "valuescope_token";

function isLoggedIn(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem(TOKEN_KEY);
}

// ── Server-backed storage (for logged-in users) ──

async function serverGetHistory(limit = 50): Promise<SavedValuation[]> {
  const { searchValuations } = await import("./api");
  const { results } = await searchValuations({ limit });
  // Map server format → SavedValuation format
  return results.map((r): SavedValuation => ({
    id: r.id,
    ticker: r.ticker,
    company_name: r.company_name,
    date: r.valuation_date,
    updated_at: r.valuation_date,
    mode: r.mode,
    ai_engine: r.ai_engine ?? undefined,
    dcf_price: r.price_per_share ?? r.gap_dcf_price ?? 0,
    market_price: r.market_price ?? r.gap_market_price ?? 0,
    diff_pct: r.gap_pct != null ? r.gap_pct / 100 : 0,
    currency: r.currency ?? "",
    reported_currency: r.reported_currency ?? undefined,
    revenue_growth_1: r.revenue_growth_1 ?? 0,
    revenue_growth_2: r.revenue_growth_2 ?? 0,
    ebit_margin: r.ebit_margin ?? 0,
    convergence: 0,
    rev_ic_1: 0,
    rev_ic_2: 0,
    rev_ic_3: 0,
    tax_rate: 0,
    wacc: r.wacc ?? 0,
    ronic_match_wacc: false,
    bridge: {},
    gap_analysis: r.gap_adjusted_price != null
      ? { analysis_text: "", adjusted_price: r.gap_adjusted_price, gap_pct: r.gap_pct ?? undefined }
      : undefined,
  }));
}

async function serverDeleteValuation(id: number): Promise<void> {
  const { deleteValuation } = await import("./api");
  await deleteValuation(id);
}

// ── Public API ──

/**
 * Get all valuation history (for the history dropdown on the stock page).
 * Routes to server for logged-in users, IndexedDB for anonymous.
 */
export async function getAllHistory(limit = 50): Promise<SavedValuation[]> {
  if (isLoggedIn()) {
    try {
      return await serverGetHistory(limit);
    } catch {
      // Fallback to IndexedDB if server fails
    }
  }
  const { getAllValuationHistory } = await import("./indexeddb");
  return getAllValuationHistory(limit);
}

/**
 * Delete a valuation record.
 * Routes to server for logged-in users, IndexedDB for anonymous.
 */
export async function deleteHistory(id: number): Promise<void> {
  if (isLoggedIn()) {
    try {
      await serverDeleteValuation(id);
      return;
    } catch {
      // Fallback
    }
  }
  const { deleteValuation } = await import("./indexeddb");
  await deleteValuation(id);
}

/**
 * Save a valuation. Always saves to IndexedDB for immediate access.
 * Server save is handled separately by handleSave in the stock page
 * (it already does dual save to both IndexedDB + server).
 */
export async function saveToLocal(
  data: Omit<SavedValuation, "id">,
  existingId?: number
): Promise<number> {
  const { saveValuation } = await import("./indexeddb");
  return saveValuation(data, existingId);
}
