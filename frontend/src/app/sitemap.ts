import type { MetadataRoute } from "next";

// Popular tickers that should be indexed by search engines.
// These cover A-shares (blue chips + popular), HK stocks, and US mega-caps.
const SEED_TICKERS = [
  // A-shares — blue chips
  "600519.SS", "000858.SZ", "601318.SS", "600036.SS", "000333.SZ",
  "600900.SS", "601012.SS", "000568.SZ", "600276.SS", "300750.SZ",
  "601899.SS", "600031.SS", "000001.SZ", "600809.SS", "002594.SZ",
  "601888.SS", "600030.SS", "000651.SZ", "601166.SS", "600690.SS",
  // HK stocks
  "00700.HK", "09988.HK", "03690.HK", "09999.HK", "01810.HK",
  "02020.HK", "09618.HK", "01024.HK", "00941.HK", "02318.HK",
  // US stocks
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
  "TSLA", "META", "BRK-B", "JPM", "V",
];

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

  for (const ticker of SEED_TICKERS) {
    pages.push({
      url: `https://valuescope.app/stock/${ticker}`,
      lastModified: now,
      changeFrequency: "daily",
      priority: 0.8,
    });
  }

  return pages;
}
