"use client";

import SearchBar from "@/components/SearchBar";
import LanguageToggle from "@/components/LanguageToggle";
import { useI18n } from "@/lib/i18n";

export default function Home() {
  const { t } = useI18n();

  return (
    <div className="min-h-screen flex flex-col">
      {/* Floating language toggle for home page */}
      <div className="absolute top-4 right-4 z-40">
        <LanguageToggle />
      </div>
      {/* Hero section */}
      <main className="flex-1 flex flex-col items-center justify-center px-4">
        <div className="text-center w-full max-w-2xl mx-auto">
          <h1 className="text-5xl font-bold text-gray-900 dark:text-white mb-3 tracking-tight">
            <span className="text-4xl mr-2">🎯</span> ValueScope
          </h1>
          <p className="text-lg text-gray-500 dark:text-gray-400 mb-8">
            {t.heroSubtitle}
          </p>

          <SearchBar size="lg" className="w-full mb-6" />

          <p className="text-xs text-gray-400 dark:text-gray-500">
            {t.heroSupports}
          </p>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto mt-16">
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
