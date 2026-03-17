import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";
import Footer from "@/components/Footer";

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
  title: "ValueScope — AI-Powered Stock Valuation & Analysis",
  description:
    "DCF valuation, relative valuation, multi-dimensional scoring, and financial analysis for A-shares, HK stocks, and US stocks.",
  openGraph: {
    title: "ValueScope — AI-Powered Stock Valuation & Analysis",
    description:
      "DCF valuation, relative valuation, multi-dimensional scoring, and financial analysis for A-shares, HK stocks, and US stocks.",
    type: "website",
    siteName: "ValueScope",
    url: "https://valuescope.app",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "ValueScope — AI-Powered Stock Valuation & Analysis",
    description:
      "DCF valuation, relative valuation, multi-dimensional scoring, and financial analysis for A-shares, HK stocks, and US stocks.",
  },
  icons: {
    icon: "/favicon.ico",
  },
  alternates: {
    canonical: "https://valuescope.app",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
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
