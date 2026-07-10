"use client";

import { useState, useEffect, useCallback } from "react";
import { useSettings } from "@/lib/settings";
import { useI18n } from "@/lib/i18n";
import { getAIQuota } from "@/lib/api";
import { AI_VALUATION_ENABLED } from "@/lib/flags";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

// ── Password input with show/hide toggle ─────────────────────────

function KeyInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        {label}
      </label>
      <div className="relative">
        <input
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder ?? "sk-..."}
          className="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 pr-16 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
        />
        <button
          type="button"
          onClick={() => setVisible(!visible)}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 px-2 py-1 rounded transition-colors"
        >
          {visible ? (
            /* Eye-off icon */
            <span className="flex items-center gap-1">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
              </svg>
              {t.settingsHideKey}
            </span>
          ) : (
            /* Eye icon */
            <span className="flex items-center gap-1">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {t.settingsShowKey}
            </span>
          )}
        </button>
      </div>
    </div>
  );
}

// ── Main drawer ──────────────────────────────────────────────────

export default function SettingsDrawer({ open, onClose }: SettingsDrawerProps) {
  const { t } = useI18n();
  const {
    fmpApiKey, serperApiKey, deepseekApiKey,
    setFmpApiKey, setSerperApiKey, setDeepseekApiKey,
    hasAiKeys,
  } = useSettings();

  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "fail">("idle");
  const [testSerperStatus, setTestSerperStatus] = useState<"idle" | "testing" | "success" | "fail">("idle");
  const [testDeepseekStatus, setTestDeepseekStatus] = useState<"idle" | "testing" | "success" | "fail">("idle");
  const [aiDailyLimit, setAiDailyLimit] = useState<number | null>(null);

  // Fetch AI daily limit
  useEffect(() => {
    if (!AI_VALUATION_ENABLED) return;
    getAIQuota().then((q) => setAiDailyLimit(q.limit)).catch(() => {});
  }, []);

  // Reset test status when key changes
  useEffect(() => {
    setTestStatus("idle");
  }, [fmpApiKey]);
  useEffect(() => {
    setTestSerperStatus("idle");
  }, [serperApiKey]);
  useEffect(() => {
    setTestDeepseekStatus("idle");
  }, [deepseekApiKey]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const testFmpKey = useCallback(async () => {
    if (!fmpApiKey.trim()) return;
    setTestStatus("testing");
    try {
      const res = await fetch(`/api/stock/search?q=AAPL&apikey=${encodeURIComponent(fmpApiKey.trim())}`);
      if (res.ok) {
        const data = await res.json();
        setTestStatus(Array.isArray(data) && data.length > 0 ? "success" : "fail");
      } else {
        setTestStatus("fail");
      }
    } catch {
      setTestStatus("fail");
    }
  }, [fmpApiKey]);

  const testSerperKey = useCallback(async () => {
    if (!serperApiKey.trim()) return;
    setTestSerperStatus("testing");
    try {
      const res = await fetch("https://google.serper.dev/search", {
        method: "POST",
        headers: { "X-API-KEY": serperApiKey.trim(), "Content-Type": "application/json" },
        body: JSON.stringify({ q: "test", num: 1 }),
      });
      setTestSerperStatus(res.ok ? "success" : "fail");
    } catch {
      setTestSerperStatus("fail");
    }
  }, [serperApiKey]);

  const testDeepseekKey = useCallback(async () => {
    if (!deepseekApiKey.trim()) return;
    setTestDeepseekStatus("testing");
    try {
      const res = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${deepseekApiKey.trim()}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: "deepseek-chat", messages: [{ role: "user", content: "hi" }], max_tokens: 1 }),
      });
      setTestDeepseekStatus(res.ok ? "success" : "fail");
    } catch {
      setTestDeepseekStatus("fail");
    }
  }, [deepseekApiKey]);

  const hasSerper = serperApiKey.trim().length > 0;
  const hasDeepseek = deepseekApiKey.trim().length > 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-50 bg-black/30 backdrop-blur-sm transition-opacity duration-300 ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`fixed inset-y-0 right-0 z-50 w-full max-w-md bg-white dark:bg-gray-900 shadow-2xl transform transition-transform duration-300 ease-in-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="h-full flex flex-col overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              {t.settings}
            </h2>
            <button
              onClick={onClose}
              className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 px-6 py-6 space-y-8">
            {/* ── Section 1: FMP API Key ──────────────────────────── */}
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                {/* Database icon */}
                <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
                </svg>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                  {t.settingsFmpTitle}
                </h3>
              </div>

              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t.settingsFmpDesc}
              </p>

              <KeyInput
                label="FMP API Key"
                value={fmpApiKey}
                onChange={setFmpApiKey}
                placeholder="your-fmp-api-key"
              />

              {/* Test button + status */}
              <div className="flex items-center gap-3">
                <button
                  onClick={testFmpKey}
                  disabled={!fmpApiKey.trim() || testStatus === "testing"}
                  className="px-4 py-1.5 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {testStatus === "testing" ? t.settingsTesting : t.settingsTestKey}
                </button>
                {testStatus === "success" && (
                  <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {t.settingsTestSuccess}
                  </span>
                )}
                {testStatus === "fail" && (
                  <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                    {t.settingsTestFail}
                  </span>
                )}
              </div>

              {/* Affiliate card */}
              <a
                href="https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope"
                target="_blank"
                rel="noopener noreferrer"
                className="block rounded-xl border border-purple-200 dark:border-purple-800 bg-gradient-to-br from-purple-50 via-blue-50 to-indigo-50 dark:from-purple-950/40 dark:via-blue-950/40 dark:to-indigo-950/40 p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex items-center gap-2">
                  {/* Gift icon */}
                  <svg className="w-4 h-4 text-purple-600 dark:text-purple-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 11.25v8.25a1.5 1.5 0 01-1.5 1.5H5.25a1.5 1.5 0 01-1.5-1.5v-8.25M12 4.875A2.625 2.625 0 109.375 7.5H12m0-2.625V7.5m0-2.625A2.625 2.625 0 1114.625 7.5H12m0 0V21m-8.625-9.75h18c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125h-18c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z" />
                  </svg>
                  <span className="text-sm font-medium text-purple-700 dark:text-purple-300">
                    {t.settingsFmpAffiliate}
                  </span>
                  <svg className="w-3.5 h-3.5 text-purple-400 ml-auto shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                  </svg>
                </div>
              </a>
            </section>

            {/* ── Section 2: AI Engine — hidden with the AI valuation UI ── */}
            {AI_VALUATION_ENABLED && (
            <>
            {/* Divider */}
            <hr className="border-gray-200 dark:border-gray-700" />

            <section className="space-y-4">
              <div className="flex items-center gap-2">
                {/* Sparkle icon */}
                <svg className="w-5 h-5 text-amber-500 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
                </svg>
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                  {t.settingsAiTitle}
                </h3>
              </div>

              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t.settingsAiDesc}
              </p>

              <KeyInput
                label={t.settingsSerperKey}
                value={serperApiKey}
                onChange={setSerperApiKey}
              />
              <div className="flex items-center gap-3">
                <button
                  onClick={testSerperKey}
                  disabled={!serperApiKey.trim() || testSerperStatus === "testing"}
                  className="px-4 py-1.5 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {testSerperStatus === "testing" ? t.settingsTestAiTesting : t.settingsTestAi}
                </button>
                {testSerperStatus === "success" && (
                  <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {t.settingsTestAiSuccess}
                  </span>
                )}
                {testSerperStatus === "fail" && (
                  <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                    {t.settingsTestAiFail}
                  </span>
                )}
                <a
                  href="https://serper.dev"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline ml-auto"
                >
                  {t.settingsGetSerperKey}
                </a>
              </div>

              <KeyInput
                label={t.settingsDeepseekKey}
                value={deepseekApiKey}
                onChange={setDeepseekApiKey}
              />
              <div className="flex items-center gap-3">
                <button
                  onClick={testDeepseekKey}
                  disabled={!deepseekApiKey.trim() || testDeepseekStatus === "testing"}
                  className="px-4 py-1.5 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {testDeepseekStatus === "testing" ? t.settingsTestAiTesting : t.settingsTestAi}
                </button>
                {testDeepseekStatus === "success" && (
                  <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {t.settingsTestAiSuccess}
                  </span>
                )}
                {testDeepseekStatus === "fail" && (
                  <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                    {t.settingsTestAiFail}
                  </span>
                )}
                <a
                  href="https://platform.deepseek.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline ml-auto"
                >
                  {t.settingsGetDeepseekKey}
                </a>
              </div>

              {/* Status indicator */}
              <div className="flex items-center gap-2 mt-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    hasAiKeys
                      ? "bg-green-500"
                      : hasSerper || hasDeepseek
                        ? "bg-yellow-500"
                        : "bg-gray-300 dark:bg-gray-600"
                  }`}
                />
                <span className="text-xs text-gray-600 dark:text-gray-400">
                  {hasAiKeys ? t.settingsAiReady : (hasSerper || hasDeepseek) ? t.settingsAiPartial : t.settingsAiPartial}
                </span>
              </div>

              {/* Free quota note — only show when user has no AI keys */}
              {!hasAiKeys && aiDailyLimit != null && (
                <div className="rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 px-3 py-2">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t.settingsAiFreeNote(aiDailyLimit)}
                  </p>
                </div>
              )}
            </section>
            </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
