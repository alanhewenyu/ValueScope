"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SearchBar from "@/components/SearchBar";
import LanguageToggle from "@/components/LanguageToggle";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { t, locale } = useI18n();
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const [isLocal, setIsLocal] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = window.location.hostname;
    setIsLocal(h === "localhost" || h === "127.0.0.1");
  }, []);
  const showPrivate = isLocal || !!user;

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
      {/* Floating top-right nav */}
      <div className="absolute top-4 right-4 z-40 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
        {showPrivate && (
          <>
            <Link href="/history" className="hover:text-gray-900 dark:hover:text-white transition-colors">
              {locale === "zh" ? "估值记录" : "History"}
            </Link>
            <Link href="/portfolio" className="hover:text-gray-900 dark:hover:text-white transition-colors">
              {locale === "zh" ? "投资组合" : "Portfolio"}
            </Link>
          </>
        )}
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
          <p className="text-base sm:text-lg text-gray-500 dark:text-gray-400 mb-8">
            {t.heroSubtitle}
          </p>

          <SearchBar size="lg" className="w-full mb-6" />

          <p className="text-xs text-gray-400 dark:text-gray-500">
            {t.heroSupports}
          </p>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto mt-8 sm:mt-16">
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
}: {
  icon: string;
  title: string;
  description: string;
  badge?: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 hover:shadow-md transition-shadow">
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
    </div>
  );
}
