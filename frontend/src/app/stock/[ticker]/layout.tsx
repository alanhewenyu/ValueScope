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
  const profile = await fetchSeoProfile(ticker);

  if (!profile) return null;

  const name = displayName(profile, ticker);
  const nameEn = profile.company_name || "";

  return (
    <section className="max-w-7xl mx-auto px-4 py-8 text-sm text-gray-600 dark:text-gray-400">
      {/* Collapsed by default: crawlers index <details> content at full weight
          (mobile-first), while users just see one quiet row at the page end.
          The expanded description users read lives in the client page above
          the tabs; this server-rendered copy exists for no-JS crawlers. */}
      <details className="border-t border-gray-200 dark:border-gray-800 pt-4 space-y-4">
        <summary className="cursor-pointer text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 select-none">
          {name}（{ticker}）公司简介
        </summary>
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mt-4">
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
      </details>
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
      {/* min-h-screen: while the app is loading (skeleton/tab spinner) the
          content area collapses; without a floor the SEO section below gets
          pulled into the viewport and then pushed back down — a visible flash */}
      <div className="min-h-screen">{children}</div>
      {/* Suspense: the interactive app streams immediately; the crawlable
          summary arrives later in the same response without blocking TTFB */}
      <Suspense fallback={null}>
        <SeoContent ticker={decoded} />
      </Suspense>
    </>
  );
}
