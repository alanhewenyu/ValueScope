"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SearchBar from "@/components/SearchBar";
import LanguageToggle from "@/components/LanguageToggle";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth-context";
import { trackEvent } from "@/lib/gtag";

export default function Home() {
  const { t, locale } = useI18n();
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Floating top-right nav — links hidden on mobile to avoid overlap */}
      <div className="absolute top-4 right-4 z-40 flex items-center gap-3 sm:gap-4 text-sm text-gray-500 dark:text-gray-400">
        <Link href="/history" className="hidden sm:inline hover:text-gray-900 dark:hover:text-white transition-colors">
          {locale === "zh" ? "估值记录" : "History"}
        </Link>
        <Link href="/portfolio" className="hidden sm:inline hover:text-gray-900 dark:hover:text-white transition-colors">
          {locale === "zh" ? "投资组合" : "Portfolio Tracker"}
        </Link>
        {/* MCP sits last in the link group site-wide (matches shared Navbar) */}
        <Link
          href="/mcp"
          onClick={() => trackEvent("mcp_docs_click", { link_location: "home_nav" })}
          className="font-medium text-violet-600 dark:text-violet-400 hover:text-violet-800 dark:hover:text-violet-300 transition-colors"
        >
          🔌 MCP
        </Link>
        <LanguageToggle />
        {!authLoading && !user && (
          <Link
            href="/auth"
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg transition-colors"
          >
            {t.authLogin}
          </Link>
        )}
        {!authLoading && user && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="w-7 h-7 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-medium hover:bg-blue-700 transition-colors"
            >
              {user.email[0].toUpperCase()}
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-2 w-48 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 shadow-lg py-2 z-50">
                <div className="px-4 py-2 text-xs text-gray-500 dark:text-gray-400 truncate border-b border-gray-100 dark:border-gray-800">
                  {user.email}
                </div>
                <button
                  onClick={() => { logout(); setMenuOpen(false); router.push("/"); }}
                  className="w-full text-left px-4 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  {t.authLogout}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      {/* Hero section */}
      <main className="flex-1 flex flex-col items-center justify-center px-4">
        <div className="text-center w-full max-w-2xl mx-auto">
          <h1 className="text-3xl sm:text-5xl font-bold text-gray-900 dark:text-white mb-3 tracking-tight">
            <span className="text-3xl sm:text-4xl mr-2">🎯</span> ValueScope
          </h1>
          <p className="text-base sm:text-lg text-gray-500 dark:text-gray-400 mb-2">
            {t.heroSubtitle}
          </p>
          <p className="text-xs sm:text-sm text-gray-400 dark:text-gray-500 mb-8">
            {t.heroTagline}
          </p>

          <SearchBar size="lg" className="w-full mb-6" />

          <p className="text-xs text-gray-400 dark:text-gray-500">
            {t.heroSupports}
          </p>

          {/* The hero promises "the DCF engine your AI can call", but MCP used
              to live only as a small link in the corner nav — 247 homepage
              visitors reached /mcp 31 times last quarter. Give the pitch its
              own first-screen entry point. */}
          <Link
            href="/mcp"
            onClick={() => trackEvent("mcp_docs_click", { link_location: "home_hero" })}
            className="group inline-flex flex-col items-center gap-0.5 mt-6 px-4 py-2.5 rounded-xl border border-violet-200 dark:border-violet-900 bg-violet-50/60 dark:bg-violet-950/30 hover:border-violet-400 dark:hover:border-violet-700 hover:bg-violet-50 dark:hover:bg-violet-950/50 transition-colors"
          >
            <span className="text-sm font-semibold text-violet-700 dark:text-violet-300">
              {t.heroMcpCta}
              <span className="inline-block ml-1 transition-transform group-hover:translate-x-0.5">→</span>
            </span>
            <span className="text-xs text-violet-600/80 dark:text-violet-400/80">
              {t.heroMcpCtaSub}
            </span>
          </Link>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 max-w-4xl mx-auto mt-8 sm:mt-16">
          <FeatureCard
            icon="📊"
            title={t.featureDCFTitle}
            description={t.featureDCFDesc}
          />
          <FeatureCard
            icon="📈"
            title={t.featureRelTitle}
            description={t.featureRelDesc}
          />
          <FeatureCard
            icon="📐"
            title={t.featureScoringTitle}
            description={t.featureScoringDesc}
          />
          <FeatureCard
            icon="💼"
            title={t.featurePortfolioTitle}
            description={t.featurePortfolioDesc}
          />
        </div>
      </main>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
  badge,
  href,
  actionLabel,
}: {
  icon: string;
  title: string;
  description: string;
  badge?: string;
  href?: string;
  actionLabel?: string;
}) {
  const card = (
    <div className={`bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 hover:shadow-md transition-shadow ${href ? "cursor-pointer" : ""}`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-2xl">{icon}</span>
        <h3 className="font-semibold text-gray-900 dark:text-white">{title}</h3>
        {badge && (
          <span className="text-[10px] font-medium text-blue-600 bg-blue-50 dark:bg-blue-950 dark:text-blue-400 px-2 py-0.5 rounded-full">
            {badge}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
        {description}
      </p>
      {actionLabel && (
        <p className="mt-3 text-xs font-medium text-blue-600 dark:text-blue-400">{actionLabel}</p>
      )}
    </div>
  );
  return href ? <Link href={href}>{card}</Link> : card;
}
