# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Cached wrapper for get_historical_financials with freshness check.

Caches raw financial data in memory (5 min TTL) so multiple endpoints
querying the same ticker within a short window don't re-fetch from
yfinance/akshare.
"""

import time
import copy

_cache: dict[str, tuple[float, dict]] = {}
_TTL = 300  # 5 minutes


def get_historical_financials(ticker, period, apikey, historical_periods):
    """Fetch financials with caching + freshness check."""
    from modeling.data import get_historical_financials as _raw
    from modeling.constants import HISTORICAL_DATA_PERIODS_ANNUAL

    cache_key = f"{ticker}:{period}"
    cached = _cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _TTL:
        return copy.deepcopy(cached[1])

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
