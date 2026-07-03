import type { MetadataRoute } from "next";
import tickers from "@/data/sitemap-tickers.json";

// Full indexable surface: all A-shares + HK main board (the differentiated
// niche — no direct competitor covers A-share DCF), plus major US/JP names.
// Snapshot generated from public/tickers.json; regenerate when that updates.

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();

  const pages: MetadataRoute.Sitemap = [
    {
      url: "https://valuescope.app",
      lastModified: now,
      changeFrequency: "weekly",
      priority: 1.0,
    },
  ];

  const groups: { symbols: string[]; priority: number }[] = [
    { symbols: tickers.a_shares, priority: 0.7 },
    { symbols: tickers.hk, priority: 0.6 },
    { symbols: tickers.us, priority: 0.8 },
    { symbols: tickers.jp, priority: 0.6 },
  ];

  for (const { symbols, priority } of groups) {
    for (const symbol of symbols) {
      pages.push({
        url: `https://valuescope.app/stock/${symbol}`,
        lastModified: now,
        changeFrequency: "weekly",
        priority,
      });
    }
  }

  return pages;
}
