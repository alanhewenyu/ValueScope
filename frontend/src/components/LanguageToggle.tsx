"use client";

import { useI18n, type Locale } from "@/lib/i18n";

export default function LanguageToggle() {
  const { locale, setLocale } = useI18n();

  const toggleLocale = () => {
    setLocale(locale === "en" ? "zh" : "en" as Locale);
  };

  return (
    <button
      onClick={toggleLocale}
      className="px-2.5 py-1 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-xs font-medium text-gray-600 dark:text-gray-400"
      title={locale === "en" ? "切换到中文" : "Switch to English"}
    >
      {locale === "en" ? "中文" : "EN"}
    </button>
  );
}
