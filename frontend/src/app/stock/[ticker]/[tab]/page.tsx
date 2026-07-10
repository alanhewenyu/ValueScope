import type { Metadata } from "next";
import { notFound } from "next/navigation";
import StockPageClient from "../StockPageClient";
import { prefetchStockData } from "../prefetch";

// Deep-linkable tab views of the stock page. "overview" is the base URL
// (/stock/TICKER), so it is deliberately not a valid segment here.
const TAB_META: Record<string, { zh: string; desc: string }> = {
  dcf: {
    zh: "DCF估值模型",
    desc: "现金流折现（DCF）估值：自动填充历史参数，支持 AI 参数建议、敏感性分析与反向 DCF。",
  },
  relative: {
    zh: "相对估值",
    desc: "PE / PB 历史分位与同业对比，判断当前估值处于历史什么水平。",
  },
  scoring: {
    zh: "财务评分",
    desc: "盈利能力、成长性、财务健康度多维评分与雷达图。",
  },
  insights: {
    zh: "AI洞察",
    desc: "分析师预期、业绩会纪要 AI 解读与关键趋势提炼。",
  },
};

type Params = Promise<{ ticker: string; tab: string }>;

export async function generateMetadata({
  params,
}: {
  params: Params;
}): Promise<Metadata> {
  const { ticker, tab } = await params;
  const decoded = decodeURIComponent(ticker);
  const meta = TAB_META[tab];
  if (!meta) return {};

  const title = `${decoded} ${meta.zh} | ValueScope`;
  const description = `${decoded} ${meta.desc}免费在线估值工具，支持 A股、港股、美股。`;
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      url: `https://valuescope.app/stock/${decoded}/${tab}`,
      type: "article",
    },
    twitter: { card: "summary", title, description },
    alternates: {
      // Tab views are shallow variants of the same app — canonicalize to the
      // main stock page so crawl signals consolidate instead of spreading
      // across four thin duplicates.
      canonical: `https://valuescope.app/stock/${decoded}`,
    },
  };
}

export default async function StockTabPage({ params }: { params: Params }) {
  const { ticker, tab } = await params;
  if (!(tab in TAB_META)) notFound();
  const decoded = decodeURIComponent(ticker);

  const { profile, financials } = await prefetchStockData(decoded);

  return (
    <StockPageClient
      ticker={decoded}
      initialProfile={profile}
      initialFinancials={financials}
      initialTab={tab as "dcf" | "relative" | "scoring" | "insights"}
    />
  );
}
