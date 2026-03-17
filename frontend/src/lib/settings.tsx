"use client";

import { createContext, useContext, useState, useEffect, useCallback, useMemo, type ReactNode } from "react";

// ── localStorage keys ────────────────────────────────────────────

const KEY_FMP = "fmp_apikey"; // backward compatible
const KEY_SERPER = "valuescope_serper_key";
const KEY_DEEPSEEK = "valuescope_deepseek_key";

// ── Context value type ───────────────────────────────────────────

interface SettingsContextValue {
  fmpApiKey: string;
  serperApiKey: string;
  deepseekApiKey: string;
  setFmpApiKey: (key: string) => void;
  setSerperApiKey: (key: string) => void;
  setDeepseekApiKey: (key: string) => void;
  hasAiKeys: boolean;
  ready: boolean; // true after client-side localStorage has been read
}

const SettingsContext = createContext<SettingsContextValue>({
  fmpApiKey: "",
  serperApiKey: "",
  deepseekApiKey: "",
  setFmpApiKey: () => {},
  setSerperApiKey: () => {},
  setDeepseekApiKey: () => {},
  hasAiKeys: false,
  ready: false,
});

// ── Helpers ──────────────────────────────────────────────────────

function readKey(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeKey(key: string, value: string) {
  try {
    if (value) {
      localStorage.setItem(key, value);
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    // localStorage unavailable
  }
}

// ── Provider ─────────────────────────────────────────────────────

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [fmpApiKey, setFmpState] = useState("");
  const [serperApiKey, setSerperState] = useState("");
  const [deepseekApiKey, setDeepseekState] = useState("");
  const [ready, setReady] = useState(false);

  // Read from localStorage on client mount
  useEffect(() => {
    setFmpState(readKey(KEY_FMP));
    setSerperState(readKey(KEY_SERPER));
    setDeepseekState(readKey(KEY_DEEPSEEK));
    setReady(true);
  }, []);

  const setFmpApiKey = useCallback((key: string) => {
    setFmpState(key);
    writeKey(KEY_FMP, key);
  }, []);

  const setSerperApiKey = useCallback((key: string) => {
    setSerperState(key);
    writeKey(KEY_SERPER, key);
  }, []);

  const setDeepseekApiKey = useCallback((key: string) => {
    setDeepseekState(key);
    writeKey(KEY_DEEPSEEK, key);
  }, []);

  const hasAiKeys = serperApiKey.length > 0 && deepseekApiKey.length > 0;

  const value = useMemo(() => ({
    fmpApiKey, serperApiKey, deepseekApiKey,
    setFmpApiKey, setSerperApiKey, setDeepseekApiKey,
    hasAiKeys, ready,
  }), [fmpApiKey, serperApiKey, deepseekApiKey, setFmpApiKey, setSerperApiKey, setDeepseekApiKey, hasAiKeys, ready]);

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// ── Hook ─────────────────────────────────────────────────────────

export function useSettings() {
  return useContext(SettingsContext);
}
