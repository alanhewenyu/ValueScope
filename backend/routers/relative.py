# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Relative valuation & scoring API endpoints."""

import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, Query
import numpy as np

logger = logging.getLogger("valuescope.analysis")

from modeling.data import (
    validate_ticker,
    _normalize_ticker,
    _fill_profile_from_financial_data,
)
from backend.data_cache import get_historical_financials, get_company_profile as cached_get_profile
from modeling.relative_valuation import (
    get_current_valuation,
    get_historical_valuations,
    get_peer_comparison,
)
from modeling.scoring import compute_scores
from modeling.constants import HISTORICAL_DATA_PERIODS_ANNUAL
from backend.cache import get as cache_get, put as cache_put, make_key


router = APIRouter()


def _safe_json(obj):
    """Convert numpy/pandas types to JSON-safe Python types."""
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_json(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64)):
        val = float(obj)
        if np.isnan(val) or np.isinf(val):
            return None
        return val
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


@router.get("/valuation/{ticker}")
def get_relative_valuation(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
    years: int = Query(5, ge=1, le=10, description="Years of history for percentile calc"),
):
    """Get relative valuation data: current ratios + historical percentiles."""
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(ticker)

    # Check cache (TTL 1 hour)
    ck = make_key("relval", normalized, str(years))
    cached = cache_get(ck)
    if cached is not None:
        return cached

    # Get current valuation ratios
    current = get_current_valuation(normalized, apikey)
    if 'error' in current:
        raise HTTPException(status_code=404, detail=current['error'])

    # Get historical PE/PB percentiles
    historical = get_historical_valuations(normalized, years=years, apikey=apikey)

    result = _safe_json({
        'current': current,
        'historical': historical,
    })
    cache_put(ck, result, ttl=3600)  # 1 hour
    return result


@router.get("/peers/{ticker}")
def get_peers(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get peer comparison data for a stock."""
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(ticker)
    result = get_peer_comparison(normalized, apikey)
    return _safe_json(result)


@router.get("/scores/{ticker}")
def get_scores(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get 4-dimension scores for a stock.

    Returns Value, Quality, Growth, Momentum scores (each 0-100, 25% weight)
    and a total weighted score (0-100).

    Performance: All data fetches run in parallel (~4-5s total vs ~17s serial).
    """
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(ticker)

    # Check cache (TTL 1 hour — scoring is expensive: ~4-5s)
    ck = make_key("scores", normalized)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    # ── Parallel data fetching ────────────────────────────────────────
    # All independent API calls run concurrently to minimize latency.
    # financials is the critical path; others run alongside it.

    def _fetch_financial():
        return get_historical_financials(
            normalized, "annual", apikey, HISTORICAL_DATA_PERIODS_ANNUAL
        )

    def _fetch_profile():
        return cached_get_profile(normalized, apikey)

    def _fetch_valuation():
        v = get_current_valuation(normalized, apikey)
        return None if 'error' in v else v

    def _fetch_historical():
        try:
            return get_historical_valuations(normalized, years=5, apikey=apikey)
        except Exception as e:
            logger.debug("Peer data fetch failed: %s", e)
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        fut_fin = executor.submit(_fetch_financial)
        fut_prof = executor.submit(_fetch_profile)
        fut_val = executor.submit(_fetch_valuation)
        fut_hist = executor.submit(_fetch_historical)

        financial_data = fut_fin.result()
        profile = fut_prof.result()
        valuation_data = fut_val.result()
        historical = fut_hist.result()

    if financial_data is None:
        raise HTTPException(status_code=404, detail=f"Financial data not found: {ticker}")

    # Post-processing (profile already enriched by cached_get_profile,
    # including beta for A-shares via get_beta cache)
    profile = _fill_profile_from_financial_data(profile, financial_data)

    # ── Scoring computation (~0.5s) ──────────────────────────────────
    scores = compute_scores(financial_data, profile, valuation_data, historical)

    result = _safe_json(scores)
    cache_put(ck, result, ttl=3600)  # 1 hour
    return result
