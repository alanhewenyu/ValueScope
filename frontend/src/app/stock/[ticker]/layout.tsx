import type { Metadata } from "next";
import { Suspense } from "react";

const BACKEND_URL =
  process.env.BACKEND_URL || "https://valuescope-production.up.railway.app";

// Cold tickers can take >10s upstream (akshare); allow the streamed
// SEO section to finish instead of being killed at the default limit.
export const maxDuration = 30;

interface StockLayoutProps {
  children: React.ReactNode;
  params: Promise<{ ticker: string }>;
}

interface SeoProfile {
  symbol: string;
  company_name: string;
  name_zh?: string;
  industry?: string;
  sector?: string;
  currency?: string;
  price?: number;
  description?: string;
  exchange?: string;
}

interface SeoFinancials {
  formatted_summary?: {
    columns: string[];
    index: string[];
    data: string[][];
  };
}

const CURRENCY_SYMBOL: Record<string, string> = {
  CNY: "¥",
  HKD: "HK$",
  JPY: "¥",
  USD: "$",
  EUR: "€",
  GBP: "£",
};

function formatPrice(profile: SeoProfile): string {
  if (!profile.price) return "";
  const sym = CURRENCY_SYMBOL[profile.currency || "USD"] ?? `${profile.currency} `;
  return `${sym}${profile.price}`;
}

/** Display name: Chinese short name first for A-shares, else English name. */
function displayName(profile: SeoProfile, fallback: string): string {
  return profile.name_zh || profile.company_name || fallback;
}

async function fetchSeoProfile(ticker: string): Promise<SeoProfile | null> {
  try {
    const res = await fetch(`${BACKEND_URL}/api/stock/profile/${ticker}`, {
      next: { revalidate: 3600 }, // cache for 1 hour
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return (await res.json()) as SeoProfile;
  } catch {
    return null;
  }
}

async function fetchSeoFinancials(ticker: string): Promise<SeoFinancials | null> {
  // A-share / HK financials need no API key. US/JP require the user's FMP
  // key (402 without one), so the fetch simply returns null for those.
  try {
    const res = await fetch(`${BACKEND_URL}/api/stock/financials/${ticker}`, {
      next: { revalidate: 21600 }, // cache for 6 hours
      signal: AbortSignal.timeout(9000),
    });
    if (!res.ok) return null;
    return (await res.json()) as SeoFinancials;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: StockLayoutProps): Promise<Metadata> {
  const { ticker } = await params;
  const decoded = decodeURIComponent(ticker);

  const profile = await fetchSeoProfile(decoded);

  let title: string;
  let description: string;

  if (profile) {
    const name = displayName(profile, decoded);
    const nameEn = profile.company_name || "";
    const price = formatPrice(profile);
    const sector = profile.sector || "";
    title = `${name}（${decoded}）DCF估值与内在价值分析 | ValueScope`;
    description =
      `${name}${nameEn && nameEn !== name ? ` ${nameEn}` : ""}（${decoded}）` +
      `${price ? `当前股价 ${price}，` : ""}DCF 内在价值估算、相对估值、财务评分与 AI 分析。` +
      `${sector ? `行业：${sector}。` : ""}免费在线估值工具，支持 A股、港股、美股。`;
  } else {
    title = `${decoded} DCF估值与内在价值分析 | ValueScope`;
    description = `${decoded} 股票 DCF 估值与 AI 分析 — 免费在线内在价值估算工具，支持 A股、港股、美股 | ValueScope`;
  }

  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `https://valuescope.app/stock/${decoded}`,
      type: "article",
    },
    twitter: {
      card: "summary",
      title,
      description,
    },
    alternates: {
      canonical: `https://valuescope.app/stock/${decoded}`,
    },
  };
}

/** Server-rendered, crawlable company summary below the interactive app.
 *  Real user-visible content (not cloaking) so Google/Baidu get substance
 *  without executing JS or waiting for client-side API calls. */
async function SeoContent({ ticker }: { ticker: string }) {
  const [profile, financials] = await Promise.all([
    fetchSeoProfile(ticker),
    fetchSeoFinancials(ticker),
  ]);

  if (!profile) return null;

  const name = displayName(profile, ticker);
  const nameEn = profile.company_name || "";
  const summary = financials?.formatted_summary;

  return (
    <section className="max-w-7xl mx-auto px-4 py-8 text-sm text-gray-600 dark:text-gray-400">
      <div className="border-t border-gray-200 dark:border-gray-800 pt-6 space-y-4">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">
          {name}
          {nameEn && nameEn !== name ? ` ${nameEn}` : ""}（{ticker}）公司简介
        </h2>
        {profile.description && (
          <p className="leading-relaxed max-w-4xl">{profile.description}</p>
        )}
        <p>
          {profile.exchange ? `交易所：${profile.exchange}。` : ""}
          {profile.sector ? `行业板块：${profile.sector}。` : ""}
          {profile.industry ? `细分行业：${profile.industry}。` : ""}
          {profile.price ? `最新股价：${formatPrice(profile)}。` : ""}
          本页提供 {name} 的 DCF 现金流折现估值、相对估值历史分位、多维财务评分与 AI 辅助分析。
        </p>
        {summary && summary.index.length > 0 && (
          <div className="overflow-x-auto">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-2">
              {name} 历史财务数据
            </h3>
            <table className="min-w-full border-collapse text-xs">
              <thead>
                <tr>
                  <th className="text-left py-1.5 pr-4 border-b border-gray-200 dark:border-gray-800 font-medium">
                    指标
                  </th>
                  {summary.columns.map((col) => (
                    <th
                      key={col}
                      className="text-right py-1.5 pl-4 border-b border-gray-200 dark:border-gray-800 font-medium"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.index.map((rowName, i) => (
                  <tr key={rowName}>
                    <td className="text-left py-1.5 pr-4 border-b border-gray-100 dark:border-gray-900">
                      {rowName}
                    </td>
                    {(summary.data[i] || []).map((val, j) => (
                      <td
                        key={j}
                        className="text-right py-1.5 pl-4 border-b border-gray-100 dark:border-gray-900 tabular-nums"
                      >
                        {val ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default async function StockLayout({
  children,
  params,
}: StockLayoutProps) {
  const { ticker } = await params;
  const decoded = decodeURIComponent(ticker);
  return (
    <>
      {children}
      {/* Suspense: the interactive app streams immediately; the crawlable
          summary arrives later in the same response without blocking TTFB */}
      <Suspense fallback={null}>
        <SeoContent ticker={decoded} />
      </Suspense>
    </>
  );
}
