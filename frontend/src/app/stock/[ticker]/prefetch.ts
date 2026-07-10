import type { CompanyProfile, FinancialData } from "@/lib/api";

const BACKEND_URL =
  process.env.BACKEND_URL || "https://valuescope-production.up.railway.app";

async function prefetch<T>(path: string, revalidate: number): Promise<T | null> {
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      next: { revalidate },
      // Warm-path only: backend disk cache answers in <1s; a cold ticker
      // would block TTFB, so give up fast and let the client fetch as before
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Server-side prefetch runs Vercel↔Railway (same-continent, fast) instead
 *  of the visitor's browser↔Railway (China→US, ~1s per round-trip). */
export async function prefetchStockData(ticker: string): Promise<{
  profile: CompanyProfile | null;
  financials: FinancialData | null;
}> {
  const [profile, financials] = await Promise.all([
    prefetch<CompanyProfile>(`/api/stock/profile/${ticker}`, 300),
    prefetch<FinancialData>(`/api/stock/financials/${ticker}`, 600),
  ]);
  return { profile, financials };
}
