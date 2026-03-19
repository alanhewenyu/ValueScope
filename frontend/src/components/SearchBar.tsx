"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2 } from "lucide-react";
import { searchStocks, type SearchResult } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { useSettings } from "@/lib/settings";

interface SearchBarProps {
  size?: "lg" | "md";
  className?: string;
}

export default function SearchBar({ size = "md", className = "" }: SearchBarProps) {
  const router = useRouter();
  const { t } = useI18n();
  const { fmpApiKey } = useSettings();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const searchIdRef = useRef(0); // Tracks latest search to discard stale results

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 1) {
      setResults([]);
      setShowDropdown(false);
      return;
    }
    const thisSearchId = ++searchIdRef.current;
    setLoading(true);
    try {
      const data = await searchStocks(q, fmpApiKey);
      // Only apply results if this is still the latest search
      if (thisSearchId !== searchIdRef.current) return;
      setResults(data);
      setShowDropdown(data.length > 0);
      setSelectedIdx(-1);
    } catch {
      if (thisSearchId !== searchIdRef.current) return;
      setResults([]);
    } finally {
      if (thisSearchId === searchIdRef.current) setLoading(false);
    }
  }, [fmpApiKey]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(val), 300);
  };

  const navigate = (symbol: string) => {
    setShowDropdown(false);
    setQuery(symbol);
    router.push(`/stock/${encodeURIComponent(symbol)}`);
  };

  // Check if input contains Chinese characters (needs search-first, not direct navigate)
  const isChinese = (s: string) => /[\u4e00-\u9fff]/.test(s);

  const navigateOrSearch = async (raw: string) => {
    // If there are already search results, navigate to the first one
    if (results.length > 0) {
      navigate(results[0].symbol);
      return;
    }
    // If input is Chinese or digits (potential A-share), search first then navigate
    if (isChinese(raw) || /^\d{1,6}$/.test(raw)) {
      try {
        const data = await searchStocks(raw, fmpApiKey);
        if (data.length > 0) {
          navigate(data[0].symbol);
          return;
        }
      } catch { /* fall through */ }
    }
    // Fallback: navigate directly (works for AAPL, 0700.HK, etc.)
    navigate(raw.toUpperCase());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showDropdown) {
      if (e.key === "Enter" && query.trim()) {
        navigateOrSearch(query.trim());
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIdx((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIdx((prev) => Math.max(prev - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIdx >= 0 && results[selectedIdx]) {
        navigate(results[selectedIdx].symbol);
      } else if (query.trim()) {
        navigateOrSearch(query.trim());
      }
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const isLg = size === "lg";

  return (
    <div className={`relative ${className}`}>
      <div className="relative">
        <Search
          className={`absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 ${
            isLg ? "w-5 h-5" : "w-4 h-4"
          }`}
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => results.length > 0 && setShowDropdown(true)}
          placeholder={t.searchPlaceholder}
          className={`w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl
            focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
            placeholder:text-gray-400 text-gray-900 dark:text-white
            ${isLg ? "pl-11 pr-10 py-4 text-lg" : "pl-10 pr-9 py-2.5 text-sm"}`}
        />
        {loading && (
          <Loader2
            className={`absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-gray-400 ${
              isLg ? "w-5 h-5" : "w-4 h-4"
            }`}
          />
        )}
      </div>

      {showDropdown && (
        <div
          ref={dropdownRef}
          className="absolute z-50 w-full mt-1 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg overflow-hidden"
        >
          {results.map((item, idx) => (
            <button
              key={item.symbol}
              onClick={() => navigate(item.symbol)}
              className={`w-full px-4 py-3 flex items-center gap-3 text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors
                ${idx === selectedIdx ? "bg-blue-50 dark:bg-blue-900/30" : ""}
                ${idx < results.length - 1 ? "border-b border-gray-100 dark:border-gray-800" : ""}
              `}
            >
              <span className="font-mono font-semibold text-blue-600 dark:text-blue-400 min-w-[80px]">
                {item.symbol}
              </span>
              <span className="text-gray-700 dark:text-gray-300 truncate flex-1">
                {item.name}
              </span>
              {item.exchange && (
                <span className="text-xs text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                  {item.exchange}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
