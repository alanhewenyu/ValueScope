# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Stock search & profile API endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import Optional
import json
import logging
import re
import urllib.request

logger = logging.getLogger("valuescope.stock")

from modeling.data import (
    validate_ticker,
    _normalize_ticker,
    fetch_company_profile,
    get_company_share_float,
    get_historical_financials,
    format_summary_df,
    is_a_share,
    is_hk_stock,
    _fill_profile_from_financial_data,
    _calculate_beta_akshare,
    get_index_membership,
)
from modeling.constants import HISTORICAL_DATA_PERIODS_ANNUAL
from backend.cache import get as cache_get, put as cache_put, make_key

router = APIRouter()

# ── Cached stock lists for fast prefix search ──
_a_share_cache: list[tuple[str, str]] | None = None  # [(code, name), ...]
_ticker_cache: list[dict] | None = None  # [{"s": symbol, "n": name, "x": exchange}, ...]


def _get_a_share_list() -> list[tuple[str, str]]:
    """Lazily load and cache A-share code/name list from akshare."""
    global _a_share_cache
    if _a_share_cache is not None:
        return _a_share_cache
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        _a_share_cache = list(zip(df["code"].tolist(), df["name"].tolist()))
    except Exception as e:
        logger.warning("Failed to load A-share list: %s", e)
        _a_share_cache = []
    return _a_share_cache


def _get_ticker_list() -> list[dict]:
    """Load pre-built ticker list (US/HK/JP stocks) from tickers.json."""
    global _ticker_cache
    if _ticker_cache is not None:
        return _ticker_cache
    try:
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            ".streamlit", "static", "tickers.json")
        with open(path, "r", encoding="utf-8") as f:
            _ticker_cache = json.loads(f.read())
    except Exception as e:
        logger.warning("Failed to load tickers.json: %s", e)
        _ticker_cache = []
    return _ticker_cache


# ── Response models ──

class SearchResult(BaseModel):
    symbol: str
    name: str
    exchange: str = ""


@router.get("/server-config")
def get_server_config(request: Request):
    """Return server-side API keys for auto-fill (localhost only).

    Only returns keys when the request comes from localhost.
    Production (Railway/cloud) never exposes keys.
    """
    import os

    # Only serve keys on localhost
    host = request.headers.get("host", "")
    if not any(h in host for h in ("localhost", "127.0.0.1")):
        return {"fmpApiKey": ""}

    return {
        "fmpApiKey": os.environ.get("FMP_API_KEY", ""),
    }


class CompanyProfile(BaseModel):
    symbol: str
    company_name: str
    industry: str = ""
    sector: str = ""
    country: str = ""
    currency: str = "USD"
    price: float = 0
    market_cap: float = 0
    beta: float = 0
    description: str = ""
    exchange: str = ""
    image: str = ""


# ── Endpoints ──

@router.get("/search", response_model=list[SearchResult])
def search_stocks(
    q: str = Query(..., min_length=1, description="Search query (ticker or company name)"),
    apikey: str = Query("", description="FMP API key (needed for US stock search)"),
    limit: int = Query(8, ge=1, le=20),
):
    """Search stocks by ticker symbol or company name.

    Uses local cached lists (A-shares from akshare, US/HK/JP from tickers.json)
    for instant results. FMP API is supplementary (broader but requires key).
    """
    results = []
    q_stripped = q.strip()
    q_upper = q_stripped.upper()

    # A-share prefix search: digits (partial or full) → instant local match
    # Skip for 4-5 digit codes starting with 0 (likely HK stocks, not A-shares)
    _is_likely_hk = re.match(r'^0\d{3,4}$', q_stripped)
    if re.match(r'^\d{1,6}$', q_stripped) and not _is_likely_hk:
        a_shares = _get_a_share_list()
        for code, name in a_shares:
            if code.startswith(q_stripped):
                suffix = '.SS' if code[:3] in ('600', '601', '603', '605', '688') else '.SZ'
                results.append(SearchResult(
                    symbol=code + suffix,
                    name=name,
                    exchange="SSE" if suffix == '.SS' else "SZSE",
                ))
                if len(results) >= limit:
                    break

    # A-share name search: Chinese characters → match by name
    if not results and re.search(r'[\u4e00-\u9fff]', q_stripped):
        a_shares = _get_a_share_list()
        for code, name in a_shares:
            if q_stripped in name:
                suffix = '.SS' if code[:3] in ('600', '601', '603', '605', '688') else '.SZ'
                results.append(SearchResult(
                    symbol=code + suffix,
                    name=name,
                    exchange="SSE" if suffix == '.SS' else "SZSE",
                ))
                if len(results) >= limit:
                    break

    # Local ticker list search (US/HK/JP — instant, no API needed)
    if len(results) < limit:
        tickers = _get_ticker_list()
        seen = {r.symbol for r in results}
        # For numeric input like "0700", also try zero-padded HK format "00700.HK"
        _q_variants = [q_upper]
        if re.match(r'^\d{1,5}$', q_stripped):
            _q_variants.append(q_stripped.zfill(5) + ".HK")  # 0700 → 00700.HK
        # Tier 1: exact symbol match
        for t in tickers:
            if any(t["s"] == qv for qv in _q_variants) and t["s"] not in seen:
                results.append(SearchResult(symbol=t["s"], name=t["n"], exchange=t.get("x", "")))
                seen.add(t["s"])
                break
        # Tier 2: symbol prefix match
        if len(results) < limit:
            for t in tickers:
                if any(t["s"].startswith(qv) for qv in _q_variants) and t["s"] not in seen:
                    results.append(SearchResult(symbol=t["s"], name=t["n"], exchange=t.get("x", "")))
                    seen.add(t["s"])
                    if len(results) >= limit:
                        break
        # Tier 3: name contains (case-insensitive)
        if len(results) < limit:
            q_lower = q_stripped.lower()
            for t in tickers:
                if q_lower in t["n"].lower() and t["s"] not in seen:
                    results.append(SearchResult(symbol=t["s"], name=t["n"], exchange=t.get("x", "")))
                    seen.add(t["s"])
                    if len(results) >= limit:
                        break

    # FMP search for supplementary results (requires API key)
    if apikey and len(results) < limit:
        try:
            url = f"https://financialmodelingprep.com/api/v3/search?query={q}&limit={limit}&apikey={apikey}"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            if isinstance(data, list):
                seen = {r.symbol for r in results}
                for item in data:
                    sym = item.get("symbol", "")
                    if sym and sym not in seen:
                        results.append(SearchResult(
                            symbol=sym,
                            name=item.get("name", ""),
                            exchange=item.get("exchangeShortName", ""),
                        ))
                        seen.add(sym)
        except Exception as e:
            logger.debug("FMP search failed: %s", e)

    return results[:limit]


@router.get("/profile/{ticker}", response_model=CompanyProfile)
def get_profile(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get company profile for a given ticker."""
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(ticker)

    # Check cache (TTL 30 min for profile — price may change)
    ck = make_key("profile", normalized)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    profile = fetch_company_profile(normalized, apikey)

    # For A-shares and HK stocks, enrich with yfinance data if akshare returned minimal info
    company_name = profile.get("companyName", "")
    if is_a_share(normalized) or is_hk_stock(normalized):
        # akshare may return ticker as companyName if its API failed
        if not company_name or company_name == normalized:
            try:
                import yfinance as yf
                yf_info = yf.Ticker(normalized).info
                company_name = yf_info.get("longName") or yf_info.get("shortName") or company_name
                if not profile.get("industry"):
                    profile["industry"] = yf_info.get("industry", "")
                if not profile.get("sector"):
                    profile["sector"] = yf_info.get("sector", "")
                if not profile.get("price") or profile.get("price", 0) == 0:
                    profile["price"] = yf_info.get("currentPrice") or yf_info.get("regularMarketPrice", 0)
                if not profile.get("marketCap") or profile.get("marketCap", 0) == 0:
                    profile["marketCap"] = yf_info.get("marketCap", 0)
                if not profile.get("description"):
                    profile["description"] = yf_info.get("longBusinessSummary", "")
            except Exception as e:
                logger.warning("yfinance enrichment failed for %s: %s", normalized, e)

    if not company_name or company_name == normalized:
        raise HTTPException(status_code=404, detail=f"Company not found: {ticker}")

    result = CompanyProfile(
        symbol=normalized,
        company_name=company_name,
        industry=profile.get("industry", ""),
        sector=profile.get("sector", ""),
        country=profile.get("country", ""),
        currency=profile.get("currency", "USD"),
        price=profile.get("price", 0),
        market_cap=profile.get("marketCap") or profile.get("mktCap", 0),
        beta=profile.get("beta", 0),
        description=profile.get("description", ""),
        exchange=profile.get("exchangeShortName") or profile.get("exchange", ""),
        image=profile.get("image", ""),
    )
    cache_put(ck, result, ttl=1800)  # 30 min
    return result


@router.get("/financials/{ticker}")
def get_financials(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get historical financial data (annual) for a given ticker.

    Returns summary financial table, company profile, and share data.
    """
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(ticker)

    # Check cache (TTL 1 hour — financial data changes infrequently)
    ck = make_key("financials", normalized)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    # Fetch financial data + profile + beta in parallel
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_fin = executor.submit(
            get_historical_financials, normalized, "annual", apikey, HISTORICAL_DATA_PERIODS_ANNUAL
        )
        fut_prof = executor.submit(fetch_company_profile, normalized, apikey)
        if is_a_share(normalized):
            fut_beta = executor.submit(_calculate_beta_akshare, normalized)
        else:
            fut_beta = None

    financial_data = fut_fin.result()
    if financial_data is None:
        raise HTTPException(status_code=404, detail=f"Financial data not found: {ticker}")

    # Freshness check — detects when FMP data lags behind actual earnings releases
    freshness_info = {"is_stale": False, "data_source": "api"}
    try:
        from modeling.freshness import check_data_freshness
        financial_data, freshness_info = check_data_freshness(normalized, financial_data, apikey)
    except Exception as e:
        logger.debug("Freshness check skipped: %s", e)

    profile = fut_prof.result()
    profile = _fill_profile_from_financial_data(profile, financial_data)

    if fut_beta is not None:
        profile["beta"] = fut_beta.result()

    share_info = get_company_share_float(normalized, apikey, company_profile=profile)

    # Convert summary DataFrame to JSON-serializable format
    summary_df = financial_data["summary"]
    formatted = format_summary_df(summary_df)

    # Mark fallback cells with * in formatted_summary (akshare supplemented data)
    _fallback_rows = financial_data.get("_freshness_fallback_rows", [])
    if _fallback_rows and len(formatted.columns) > 0:
        col0 = formatted.columns[0]  # akshare column (leftmost)
        for row_name in _fallback_rows:
            if row_name in formatted.index:
                val = str(formatted.at[row_name, col0])
                if val and val != "N/A":
                    formatted.at[row_name, col0] = val + " *"

    # Build response
    result = {
        "ticker": normalized,
        "company_name": profile.get("companyName", ""),
        "profile": profile,
        "share_info": share_info,
        "summary": {
            "columns": list(summary_df.columns),
            "index": list(summary_df.index),
            "data": summary_df.values.tolist(),
        },
        "formatted_summary": {
            "columns": list(formatted.columns),
            "index": list(formatted.index),
            "data": formatted.values.tolist(),
        },
        "ttm_note": financial_data.get("ttm_note", ""),
        "ttm_latest_quarter": financial_data.get("ttm_latest_quarter", ""),
        "ttm_end_date": financial_data.get("ttm_end_date", ""),
        "average_tax_rate": financial_data.get("average_tax_rate", 0),
        "fy_end_month": financial_data.get("fy_end_month", 12),
        "freshness": freshness_info,
    }
    # Shorter cache when using akshare supplement (check for API catch-up more often)
    ttl = 3600 if freshness_info.get("data_source", "api") == "api" else 600
    cache_put(ck, result, ttl=ttl)
    return result


@router.get("/indexes/{ticker}")
def get_indexes(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get major index membership for a ticker (e.g. S&P 500, CSI 300)."""
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(ticker)
    try:
        indexes = get_index_membership(normalized, apikey)
    except Exception as e:
        logger.debug("Index lookup failed for %s: %s", ticker, e)
        indexes = []

    return {"ticker": normalized, "indexes": indexes}
