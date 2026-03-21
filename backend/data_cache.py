# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Cached wrappers for expensive data fetches (financials, company profile).

Uses per-ticker locks so concurrent requests for the same ticker wait for
the first fetch to complete, then all share the cached result.
"""

import copy
import threading
import time

_cache: dict[str, tuple[float, dict]] = {}
_locks: dict[str, threading.Lock] = {}
_global_lock = threading.Lock()
_TTL = 300  # 5 minutes
_PROFILE_TTL = 600  # 10 minutes


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

        from modeling.data import get_historical_financials as _raw

        data = _raw(ticker, period, apikey, historical_periods)
        if data is not None and period == "annual":
            try:
                from modeling.freshness import check_data_freshness
                data, _ = check_data_freshness(ticker, data, apikey)
            except Exception:
                pass

        if data is not None:
            _cache[cache_key] = (time.monotonic(), copy.deepcopy(data))

        return data


def get_company_profile(ticker, apikey=''):
    """Cached wrapper for fetch_company_profile + _fill_profile_from_financial_data.

    Multiple endpoints (wacc, buffett, scores, dcf) all need the same profile.
    This ensures only one network request per ticker.
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

        from modeling.data import (
            fetch_company_profile as _raw_profile,
            _fill_profile_from_financial_data,
            is_a_share,
            _calculate_beta_akshare,
        )

        profile = _raw_profile(ticker, apikey)

        # Enrich profile with financial data if available
        fin_key = f"{ticker}:annual"
        fin_cached = _cache.get(fin_key)
        if fin_cached and (time.monotonic() - fin_cached[0]) < _TTL:
            profile = _fill_profile_from_financial_data(profile, fin_cached[1])

        if is_a_share(ticker):
            profile["beta"] = _calculate_beta_akshare(ticker)

        _cache[cache_key] = (time.monotonic(), copy.deepcopy(profile))
        return profile
