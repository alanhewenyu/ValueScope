import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import Providers from "@/components/Providers";
import Footer from "@/components/Footer";

const GA_MEASUREMENT_ID = "G-V43CZJ8B32";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://valuescope.app"),
  title: "ValueScope — 让你的 AI 学会 DCF 估值 | Teach Your AI to Run DCF Valuations",
  description:
    "把标准化 DCF 估值引擎接进你的 Claude / ChatGPT：AI 负责前瞻判断，ValueScope 负责数据和计算，同样的输入永远得到同样的结果。A股港股完全免费，支持美股、日股。AI brings the intelligence, ValueScope brings the framework and discipline.",
  keywords: [
    "DCF估值", "股票估值", "内在价值", "现金流折现", "AI估值", "MCP",
    "估值MCP", "A股估值", "港股估值", "美股估值", "WACC", "免费估值工具",
    "stock valuation", "intrinsic value", "DCF calculator", "valuation MCP server",
  ],
  verification: {
    google: "4mcNP75rC_oaDhSwvwS-vVV9mSylXl1CGLl45Y_CSoM",
  },
  openGraph: {
    title: "ValueScope — AI 驱动的股票估值与分析",
    description:
      "免费 AI 驱动的 DCF 股票估值工具。支持 A 股、港股、美股，一键 AI 估值，实时参数调节，敏感性分析。",
    type: "website",
    siteName: "ValueScope",
    url: "https://valuescope.app",
    locale: "zh_CN",
    alternateLocale: "en_US",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "ValueScope — AI-Powered DCF Stock Valuation",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ValueScope — AI 驱动的股票估值与分析",
    description:
      "免费 AI 驱动的 DCF 估值工具。支持 A 股、港股、美股，一键估值 + 敏感性分析。",
    images: ["/og-image.png"],
  },
  icons: {
    icon: "/favicon.ico",
    apple: "/icons/icon-192.png",
  },
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "ValueScope",
  },
  alternates: {
    canonical: "https://valuescope.app",
    languages: {
      "zh": "https://valuescope.app",
      "en": "https://valuescope.app",
    },
  },
  other: {
    "baidu-site-verification": "codeva-8CrbIdgNjp",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <head>
        <meta name="theme-color" content="#2563eb" />
        <meta name="mobile-web-app-capable" content="yes" />
        <Script id="sw-register" strategy="afterInteractive">
          {`if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(() => {}); }`}
        </Script>
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
          strategy="afterInteractive"
        />
        <Script id="gtag-init" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${GA_MEASUREMENT_ID}');
          `}
        </Script>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "WebApplication",
              name: "ValueScope",
              alternateName: "ValueScope AI 估值工具",
              description:
                "免费 AI 驱动的 DCF 股票估值工具，支持 A 股、港股、美股。提供一键 AI 估值、实时参数调节、敏感性分析。",
              url: "https://valuescope.app",
              applicationCategory: "FinanceApplication",
              operatingSystem: "Web",
              inLanguage: ["zh-CN", "en"],
              offers: {
                "@type": "Offer",
                price: "0",
                priceCurrency: "USD",
              },
              featureList: [
                "AI 一键 DCF 估值",
                "A 股 / 港股 / 美股 / 日股支持",
                "实时参数调节",
                "敏感性分析",
                "中英文双语界面",
              ],
            }),
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-gray-50 dark:bg-gray-950 min-h-screen`}
      >
        <Providers>
          {children}
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
