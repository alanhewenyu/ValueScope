import type { Metadata } from "next";

const BACKEND_URL =
  process.env.BACKEND_URL || "https://valuescope-production.up.railway.app";

interface StockLayoutProps {
  children: React.ReactNode;
  params: Promise<{ ticker: string }>;
}

export async function generateMetadata({
  params,
}: StockLayoutProps): Promise<Metadata> {
  const { ticker } = await params;
  const decoded = decodeURIComponent(ticker);

  // Fetch company profile from backend for dynamic meta tags
  let companyName = decoded;
  let description = "";
  try {
    const res = await fetch(`${BACKEND_URL}/api/stock/profile/${decoded}`, {
      next: { revalidate: 3600 }, // cache for 1 hour
    });
    if (res.ok) {
      const profile = await res.json();
      companyName = profile.companyName || profile.name || decoded;
      const price = profile.price ? `$${profile.price}` : "";
      const sector = profile.sector || "";
      description = `${companyName} (${decoded}) ${price ? price + " — " : ""}DCF 内在价值估算、AI 分析、财务评分。${sector ? "行业：" + sector + "。" : ""}免费在线估值工具。`;
    }
  } catch {
    // Fallback to ticker-only metadata
  }

  if (!description) {
    description = `${decoded} 股票 DCF 估值与 AI 分析 — 免费在线内在价值估算工具 | ValueScope`;
  }

  const title = `${companyName} (${decoded}) DCF 估值与分析 | ValueScope`;

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

export default function StockLayout({ children }: StockLayoutProps) {
  return children;
}
