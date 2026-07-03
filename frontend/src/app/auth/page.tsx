"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/lib/i18n";
import { trackEvent } from "@/lib/gtag";
import { Loader2 } from "lucide-react";

// Use relative path so requests go through Next.js rewrites (no CORS issues)
const API_BASE = "";

export default function AuthPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>}>
      <AuthPageInner />
    </Suspense>
  );
}

function AuthPageInner() {
  const { t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, login, register } = useAuth();

  const resetToken = searchParams.get("reset");
  const [mode, setMode] = useState<"login" | "register" | "forgot" | "reset">(
    resetToken ? "reset" : "login"
  );
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  // Redirect if already logged in
  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      if (mode === "login") {
        await login(email, password);
        router.replace("/");
      } else if (mode === "register") {
        if (password !== confirmPassword) {
          setError(t.authPasswordMismatch);
          setLoading(false);
          return;
        }
        await register(email, password);
        trackEvent("sign_up");
        router.replace("/");
      } else if (mode === "forgot") {
        const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Failed" }));
          throw new Error(err.detail);
        }
        setSuccess(t.authResetSent);
      } else if (mode === "reset") {
        if (password !== confirmPassword) {
          setError(t.authPasswordMismatch);
          setLoading(false);
          return;
        }
        const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: resetToken, password }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Failed" }));
          throw new Error(err.detail);
        }
        setSuccess(t.authResetSuccess);
        setTimeout(() => setMode("login"), 2000);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">
            ValueScope
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {mode === "login" && t.authLoginSubtitle}
            {mode === "register" && t.authRegisterSubtitle}
            {mode === "forgot" && t.authForgotSubtitle}
            {mode === "reset" && t.authResetSubtitle}
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6 space-y-4"
        >
          {error && (
            <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}
          {success && (
            <div className="p-3 rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 text-sm text-green-600 dark:text-green-400">
              {success}
            </div>
          )}

          {(mode === "login" || mode === "register" || mode === "forgot") && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t.authEmail}
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="you@example.com"
              />
            </div>
          )}

          {mode !== "forgot" && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t.authPassword}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder={t.authPasswordPlaceholder}
              />
            </div>
          )}

          {(mode === "register" || mode === "reset") && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t.authConfirmPassword}
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
                className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {mode === "login" && t.authLogin}
            {mode === "register" && t.authRegister}
            {mode === "forgot" && t.authSendReset}
            {mode === "reset" && t.authResetPassword}
          </button>

          <div className="text-center text-sm text-gray-500 dark:text-gray-400 space-y-1">
            {mode === "login" && (
              <>
                <button
                  type="button"
                  onClick={() => { setMode("forgot"); setError(""); setSuccess(""); }}
                  className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                >
                  {t.authForgotPassword}
                </button>
                <div>
                  {t.authNoAccount}{" "}
                  <button
                    type="button"
                    onClick={() => { setMode("register"); setError(""); setSuccess(""); }}
                    className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                  >
                    {t.authRegister}
                  </button>
                </div>
              </>
            )}
            {mode === "register" && (
              <div>
                {t.authHasAccount}{" "}
                <button
                  type="button"
                  onClick={() => { setMode("login"); setError(""); setSuccess(""); }}
                  className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                >
                  {t.authLogin}
                </button>
              </div>
            )}
            {mode === "forgot" && (
              <button
                type="button"
                onClick={() => { setMode("login"); setError(""); setSuccess(""); }}
                className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                {t.authBackToLogin}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
