# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Cached wrappers for expensive data fetches (financials, company profile).

Uses per-ticker locks so concurrent requests for the same ticker wait for
the first fetch to complete, then all share the cached result.
"""

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend import persistent_cache

_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()
_TTL = 300  # 5 minutes
_PROFILE_TTL = 600  # 10 minutes
_BETA_TTL = 86400  # 24 hours — beta barely changes day-to-day
# Small hot layer only — the SQLite disk cache (persistent_cache) serves
# misses in ~10-20ms, so a big in-memory cache just burns Railway GB-minutes.
# Financial dicts hold multiple DataFrames (MBs each); 100 entries ≈ hundreds
# of MB once crawlers sweep the 10k-page sitemap.
_MAX_CACHE_ENTRIES = 24

# Persistent (SQLite) TTLs — the warm layer that survives restarts.
# Financial statements change quarterly; a day-old copy beats a 5-20s cold fetch.
_DISK_FIN_TTL = 86400        # 24 hours
_DISK_PROFILE_TTL = 3600     # 1 hour (price drifts, but router already caches 30 min)
_DISK_BETA_TTL = 7 * 86400   # 7 days


def _evict_if_needed():
    """Evict expired entries, then oldest entries if cache exceeds max size."""
    if len(_cache) <= _MAX_CACHE_ENTRIES:
        return
    now = time.monotonic()
    # Phase 1: remove expired entries
    expired = [k for k, (ts, _) in _cache.items()
               if (now - ts) > max(_TTL, _PROFILE_TTL, _BETA_TTL)]
    for k in expired:
        _cache.pop(k, None)
        _locks.pop(k, None)
    # Phase 2: if still over limit, remove oldest 25%
    if len(_cache) > _MAX_CACHE_ENTRIES:
        sorted_keys = sorted(_cache, key=lambda k: _cache[k][0])
        to_remove = sorted_keys[:len(sorted_keys) // 4 or 1]
        for k in to_remove:
            _cache.pop(k, None)
            _locks.pop(k, None)


def _get_lock(key: str) -> threading.Lock:
    with _global_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def get_historical_financials(ticker, period, apikey, historical_periods):
    """Fetch financials with per-ticker locking + caching + freshness check.

    If multiple threads request the same ticker concurrently, only the first
    one fetches; the rest wait and get the cached result.
    """
    cache_key = f"{ticker}:{period}"

    # Fast path: cache hit (no lock needed)
    cached = _cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _TTL:
        return copy.deepcopy(cached[1])

    # Slow path: acquire per-ticker lock so only one thread fetches
    lock = _get_lock(cache_key)
    with lock:
        # Double-check after acquiring lock (another thread may have populated cache)
        cached = _cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _TTL:
            return copy.deepcopy(cached[1])

        # Warm layer: disk cache survives restarts and covers cold tickers
        disk = persistent_cache.get(f"fin:{cache_key}")
        if disk is not None:
            _cache[cache_key] = (time.monotonic(), copy.deepcopy(disk))
            _evict_if_needed()
            return disk

        from modeling.data import get_historical_financials as _raw

        data = _raw(ticker, period, apikey, historical_periods)
        if data is not None and period == "annual":
            try:
                from modeling.freshness import check_data_freshness
                data, freshness_info = check_data_freshness(ticker, data, apikey)
                data["_freshness_info"] = freshness_info
            except Exception:
                data["_freshness_info"] = {"is_stale": False, "data_source": "api"}

        if data is not None:
            _cache[cache_key] = (time.monotonic(), copy.deepcopy(data))
            _evict_if_needed()
            persistent_cache.put(f"fin:{cache_key}", data, _DISK_FIN_TTL)

        return data


def get_beta(ticker):
    """Cached beta calculation with 24h TTL.

    Beta uses 3 years of daily data and barely changes day-to-day.
    Separate cache avoids recomputing on every profile refresh.
    """
    cache_key = f"beta:{ticker}"

    cached = _cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _BETA_TTL:
        return cached[1]

    lock = _get_lock(cache_key)
    with lock:
        cached = _cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _BETA_TTL:
            return cached[1]

        disk = persistent_cache.get(cache_key)
        if disk is not None:
            _cache[cache_key] = (time.monotonic(), disk)
            _evict_if_needed()
            return disk

        from modeling.data import _calculate_beta_akshare
        beta = _calculate_beta_akshare(ticker)
        _cache[cache_key] = (time.monotonic(), beta)
        _evict_if_needed()
        persistent_cache.put(cache_key, beta, _DISK_BETA_TTL)
        return beta


def get_company_profile(ticker, apikey=''):
    """Cached wrapper for fetch_company_profile + beta + enrichment.

    Multiple endpoints (wacc, buffett, scores, dcf) all need the same profile.
    This ensures only one network request per ticker.

    For A-shares, profile fetch and beta calculation run in parallel
    (~3s each → ~3s total instead of ~6s serial).
    """
    cache_key = f"profile:{ticker}"

    cached = _cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _PROFILE_TTL:
        return copy.deepcopy(cached[1])

    lock = _get_lock(cache_key)
    with lock:
        cached = _cache.get(cache_key)
        if cached and (time.monotonic() - cached[0]) < _PROFILE_TTL:
            return copy.deepcopy(cached[1])

        disk = persistent_cache.get(cache_key)
        if disk is not None:
            _cache[cache_key] = (time.monotonic(), copy.deepcopy(disk))
            _evict_if_needed()
            return disk

        from modeling.data import (
            fetch_company_profile as _raw_profile,
            _fill_profile_from_financial_data,
            is_a_share,
        )

        _is_a = is_a_share(ticker)

        if _is_a:
            # Parallelize profile API call + beta calculation
            # (profile uses Eastmoney, beta uses Sina — no rate-limit conflict)
            with ThreadPoolExecutor(max_workers=2) as ex:
                fut_prof = ex.submit(_raw_profile, ticker, apikey)
                fut_beta = ex.submit(get_beta, ticker)
                profile = fut_prof.result()
                profile["beta"] = fut_beta.result()
        else:
            profile = _raw_profile(ticker, apikey)

        # Enrich profile with financial data if available
        fin_key = f"{ticker}:annual"
        fin_cached = _cache.get(fin_key)
        if fin_cached and (time.monotonic() - fin_cached[0]) < _TTL:
            profile = _fill_profile_from_financial_data(profile, fin_cached[1])

        # Don't cache an obviously incomplete profile for A/HK shares — happens when
        # push2.eastmoney.com is unreachable but datacenter-web (financials) still works.
        # Skipping cache lets the next request retry; meanwhile callers should call
        # update_profile_cache() after enriching with financial_data to seed the cache.
        from modeling.data import is_a_share, is_hk_stock
        _needs_shares = is_a_share(ticker) or is_hk_stock(ticker)
        if not (_needs_shares and not profile.get('outstandingShares')):
            _cache[cache_key] = (time.monotonic(), copy.deepcopy(profile))
            _evict_if_needed()
            persistent_cache.put(cache_key, profile, _DISK_PROFILE_TTL)
        return profile


def update_profile_cache(ticker, profile):
    """Push an enriched profile back into the cache.

    Used when callers fetch profile + financials in parallel and then enrich
    profile with financial_data after both complete. Without this, the cache
    would hold the un-enriched (e.g. outstandingShares=0) version.
    """
    cache_key = f"profile:{ticker}"
    _cache[cache_key] = (time.monotonic(), copy.deepcopy(profile))
    persistent_cache.put(cache_key, profile, _DISK_PROFILE_TTL)
