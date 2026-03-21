# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Stock search & profile API endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
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
from backend.data_cache import get_company_profile as cached_get_profile

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

    profile = cached_get_profile(normalized, apikey)

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
    from concurrent.futures import ThreadPoolExecutor, as_completed
    executor = ThreadPoolExecutor(max_workers=5)
    fut_fin = executor.submit(
        get_historical_financials, normalized, "annual", apikey, HISTORICAL_DATA_PERIODS_ANNUAL
    )
    fut_prof = executor.submit(cached_get_profile, normalized, apikey)
    fut_beta = executor.submit(_calculate_beta_akshare, normalized) if is_a_share(normalized) else None

    # Wait for financials first (critical path)
    financial_data = fut_fin.result()
    if financial_data is None:
        executor.shutdown(wait=False)
        raise HTTPException(status_code=404, detail=f"Financial data not found: {ticker}")

    # Start freshness check immediately (depends only on financial_data)
    def _freshness():
        try:
            from modeling.freshness import check_data_freshness
            return check_data_freshness(normalized, financial_data, apikey)
        except Exception as e:
            logger.debug("Freshness check skipped: %s", e)
            return financial_data, {"is_stale": False, "data_source": "api"}
    fut_fresh = executor.submit(_freshness)

    # Wait for profile + beta
    profile = fut_prof.result()
    profile = _fill_profile_from_financial_data(profile, financial_data)
    if fut_beta is not None:
        profile["beta"] = fut_beta.result()

    # Collect freshness result (share_float moved to DCF endpoint — not needed for overview)
    financial_data, freshness_info = fut_fresh.result()
    executor.shutdown(wait=False)

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

    # Replace NaN/Inf with None for JSON serialization
    import math
    def _clean_val(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    _summary_data = [[_clean_val(v) for v in row] for row in summary_df.values.tolist()]
    result = {
        "ticker": normalized,
        "company_name": profile.get("companyName", ""),
        "profile": profile,
        "summary": {
            "columns": list(summary_df.columns),
            "index": list(summary_df.index),
            "data": _summary_data,
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


@router.get("/estimates/{ticker}")
def get_estimates(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get analyst earnings estimates and surprises for a given ticker."""
    if not apikey:
        return {"available": False, "reason": "FMP API key required"}

    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        return {"available": False, "reason": err}

    normalized = _normalize_ticker(ticker)

    # Check cache (TTL 1 hour)
    ck = make_key("estimates", normalized)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    from modeling.data import get_jsonparsed_data
    from concurrent.futures import ThreadPoolExecutor

    base = "https://financialmodelingprep.com/api/v3"
    url_surprises = f"{base}/earnings-surprises/{normalized}?apikey={apikey}"
    url_estimates = f"{base}/analyst-estimates/{normalized}?apikey={apikey}&period=quarter"
    url_annual = f"{base}/analyst-estimates/{normalized}?apikey={apikey}&period=annual&limit=5"
    url_profile = f"{base}/profile/{normalized}?apikey={apikey}"
    url_income = f"{base}/income-statement/{normalized}?apikey={apikey}&period=annual&limit=2"
    url_grades = f"{base}/grade/{normalized}?apikey={apikey}&limit=50"

    try:
        with ThreadPoolExecutor(max_workers=6) as executor:
            fut_surprises = executor.submit(get_jsonparsed_data, url_surprises)
            fut_estimates = executor.submit(get_jsonparsed_data, url_estimates)
            fut_annual = executor.submit(get_jsonparsed_data, url_annual)
            fut_profile = executor.submit(get_jsonparsed_data, url_profile)
            fut_income = executor.submit(get_jsonparsed_data, url_income)
            fut_grades = executor.submit(get_jsonparsed_data, url_grades)
            surprises = fut_surprises.result() or []
            estimates = fut_estimates.result() or []
            annual_estimates = fut_annual.result() or []
            profile_data = fut_profile.result() or []
            income_data = fut_income.result() or []
            grades_data = fut_grades.result() or []
    except Exception as e:
        logger.debug("Estimates fetch failed for %s: %s", ticker, e)
        return {"available": False, "reason": "Failed to fetch estimates data"}

    if not isinstance(surprises, list):
        surprises = []
    if not isinstance(estimates, list):
        estimates = []

    if not surprises and not estimates:
        return {"available": False, "reason": "No estimates data available"}

    # Detect currency mismatch for Chinese ADRs
    # FMP analyst-estimates uses reporting currency (CNY) but
    # earnings-surprises uses trading currency (USD) for ADRs
    fx_rate = 1.0
    currency_note = None
    if isinstance(profile_data, list) and profile_data:
        prof = profile_data[0]
        country = prof.get("country", "")
        trading_currency = prof.get("currency", "")
        # Chinese ADRs: estimates in CNY, actuals in USD
        if country == "CN" and trading_currency == "USD":
            try:
                from modeling.yfinance_data import fetch_forex_yfinance
                cny_usd = fetch_forex_yfinance("CNY", "USD")
                fx_rate = (1.0 / cny_usd) if cny_usd and cny_usd > 0 else 7.0
            except Exception:
                fx_rate = 7.0
            currency_note = f"Estimates converted from CNY (÷{fx_rate:.2f})"
            logger.debug("Currency mismatch detected for %s, fx_rate=%.2f", ticker, fx_rate)

    # Build lookup of surprises by date
    from datetime import datetime, timedelta

    surprise_by_date = {}
    for s in surprises:
        d = s.get("date", "")
        if d:
            surprise_by_date[d] = s

    # Classify estimates as past or future
    today_str = datetime.now().strftime("%Y-%m-%d")
    past_quarters = []
    forward_quarters = []

    for est in estimates:
        est_date = est.get("date", "")
        if not est_date:
            continue

        # Try to find matching surprise (actual earnings) within 45 days
        matched_surprise = None
        try:
            est_dt = datetime.strptime(est_date, "%Y-%m-%d")
            for s_date, s_data in surprise_by_date.items():
                try:
                    s_dt = datetime.strptime(s_date, "%Y-%m-%d")
                    if abs((est_dt - s_dt).days) <= 45:
                        matched_surprise = s_data
                        break
                except ValueError:
                    continue
        except ValueError:
            pass

        estimated_eps_raw = est.get("estimatedEpsAvg", 0) or 0
        estimated_revenue = est.get("estimatedRevenueAvg", 0) or 0
        estimated_ebit = est.get("estimatedEbitAvg", 0) or 0
        num_analysts = est.get("numberAnalystsEstimatedEps", 0) or 0

        # Only convert EPS for ADR comparison; keep revenue/EBIT in original currency
        estimated_eps = estimated_eps_raw / fx_rate if fx_rate != 1.0 else estimated_eps_raw

        # EBIT Margin (%)
        ebit_margin = round((estimated_ebit / estimated_revenue) * 100, 1) if estimated_revenue else None

        # Derive period label from date
        try:
            dt = datetime.strptime(est_date, "%Y-%m-%d")
            quarter_num = (dt.month - 1) // 3 + 1
            period_label = f"Q{quarter_num} FY{dt.year}"
        except ValueError:
            period_label = est_date

        entry = {
            "period": period_label,
            "estimated_eps": round(estimated_eps, 4) if estimated_eps else 0,
            "estimated_revenue": estimated_revenue,
            "estimated_ebit": estimated_ebit,
            "ebit_margin": ebit_margin,
            "number_of_analysts": num_analysts,
        }

        if matched_surprise and est_date <= today_str:
            actual_eps = matched_surprise.get("actualEarningResult")
            if actual_eps is not None and estimated_eps:
                surprise_pct = round(((actual_eps - estimated_eps) / abs(estimated_eps)) * 100, 2) if estimated_eps != 0 else 0
            else:
                surprise_pct = None

            entry.update({
                "date": matched_surprise.get("date", est_date),
                "actual_eps": round(actual_eps, 4) if actual_eps is not None else None,
                "eps_surprise_pct": surprise_pct,
            })
            past_quarters.append(entry)
        elif est_date > today_str:
            entry.update({
                "date": est_date,
                "actual_eps": None,
                "eps_surprise_pct": None,
            })
            forward_quarters.append(entry)

    # Sort: past newest first
    past_quarters.sort(key=lambda x: x["date"], reverse=True)
    past_quarters = past_quarters[:8]

    # Build annual forward estimates from FMP annual data
    if not isinstance(annual_estimates, list):
        annual_estimates = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    # Collect all annual estimates (past + future) sorted by date for YoY calc
    all_annual = []
    for est in sorted(annual_estimates, key=lambda x: x.get("date", "")):
        est_date = est.get("date", "")
        if not est_date:
            continue
        rev = est.get("estimatedRevenueAvg", 0) or 0
        eps = est.get("estimatedEpsAvg", 0) or 0
        ni = est.get("estimatedNetIncomeAvg", 0) or 0
        n_analysts = est.get("numberAnalystsEstimatedEps", 0) or 0
        eps_converted = eps / fx_rate if fx_rate != 1.0 else eps
        ni_margin = round((ni / rev) * 100, 1) if rev else None
        try:
            dt = datetime.strptime(est_date, "%Y-%m-%d")
            period_label = f"FY{dt.year}"
        except ValueError:
            period_label = est_date
        all_annual.append({
            "date": est_date,
            "period": period_label,
            "estimated_eps": round(eps_converted, 4),
            "estimated_revenue": rev,
            "estimated_net_income": ni,
            "net_income_margin": ni_margin,
            "number_of_analysts": n_analysts,
            "rev_raw": rev,
        })

    # Calculate YoY revenue growth and filter to future only
    forward_annual = []
    for i, entry in enumerate(all_annual):
        if entry["date"] <= today_str:
            continue
        # Skip entries with zero/missing EPS (bad data from FMP)
        if not entry["estimated_eps"] or entry["estimated_eps"] == 0:
            continue
        rev_growth = None
        if i > 0 and all_annual[i - 1]["rev_raw"] and all_annual[i - 1]["rev_raw"] > 0:
            rev_growth = round((entry["rev_raw"] / all_annual[i - 1]["rev_raw"] - 1) * 100, 1)
        forward_annual.append({
            "period": entry["period"],
            "estimated_eps": entry["estimated_eps"],
            "estimated_revenue": entry["estimated_revenue"],
            "revenue_growth": rev_growth,
            "estimated_net_income": entry["estimated_net_income"],
            "net_income_margin": entry["net_income_margin"],
            "number_of_analysts": entry["number_of_analysts"],
        })

    # Count beats
    beat_count = sum(
        1 for q in past_quarters
        if q.get("actual_eps") is not None and q.get("estimated_eps")
        and q["actual_eps"] > q["estimated_eps"]
    )

    # Determine currencies for display
    eps_currency = "USD"
    financials_currency = "CNY" if fx_rate != 1.0 else "USD"
    if isinstance(profile_data, list) and profile_data:
        trading_cur = profile_data[0].get("currency", "USD")
        eps_currency = trading_cur
        if fx_rate == 1.0:
            financials_currency = trading_cur

    # Build actual base years from income statement for comparison
    if not isinstance(income_data, list):
        income_data = []
    actual_years = []
    for inc in income_data:
        inc_date = inc.get("date", "")
        rev = inc.get("revenue", 0) or 0
        ni = inc.get("netIncome", 0) or 0
        eps_val = inc.get("eps", 0) or 0
        eps_adj = eps_val / fx_rate if fx_rate != 1.0 else eps_val
        ni_margin = round((ni / rev) * 100, 1) if rev else None
        try:
            dt = datetime.strptime(inc_date, "%Y-%m-%d")
            period_label = f"FY{dt.year}"
        except ValueError:
            period_label = inc_date
        actual_years.append({
            "period": period_label,
            "estimated_eps": round(eps_adj, 4),
            "estimated_revenue": rev,
            "revenue_growth": None,
            "estimated_net_income": ni,
            "net_income_margin": ni_margin,
            "number_of_analysts": None,
            "is_actual": True,
        })
    actual_years.sort(key=lambda x: x["period"])

    # Calc revenue growth for actual years & between actual→forecast
    if len(actual_years) == 2:
        prev_rev = actual_years[0]["estimated_revenue"]
        cur_rev = actual_years[1]["estimated_revenue"]
        if prev_rev and prev_rev > 0:
            actual_years[1]["revenue_growth"] = round((cur_rev / prev_rev - 1) * 100, 1)
    if actual_years and forward_annual:
        last_actual_rev = actual_years[-1]["estimated_revenue"]
        if last_actual_rev and last_actual_rev > 0 and forward_annual[0].get("revenue_growth") is None:
            first_fwd_rev = forward_annual[0]["estimated_revenue"]
            forward_annual[0]["revenue_growth"] = round((first_fwd_rev / last_actual_rev - 1) * 100, 1)

    # Process analyst rating changes
    if not isinstance(grades_data, list):
        grades_data = []
    rating_changes = []
    upgrades = 0
    downgrades = 0
    maintains = 0
    for g in grades_data:
        prev = g.get("previousGrade", "")
        new = g.get("newGrade", "")
        company = g.get("gradingCompany", "")
        date = g.get("date", "")
        changed = prev != new and prev and new
        if changed:
            # Simple heuristic: check if it's upgrade or downgrade
            buy_terms = {"Buy", "Overweight", "Outperform", "Strong Buy", "Positive", "Strong-Buy"}
            hold_terms = {"Hold", "Neutral", "Equal-Weight", "Market Perform", "Peer Perform", "Equal Weight", "Sector Perform"}
            sell_terms = {"Sell", "Underweight", "Underperform", "Reduce", "Strong Sell"}
            def _score(grade):
                if grade in buy_terms: return 3
                if grade in hold_terms: return 2
                if grade in sell_terms: return 1
                return 2  # unknown → neutral
            if _score(new) > _score(prev):
                upgrades += 1
                direction = "upgrade"
            else:
                downgrades += 1
                direction = "downgrade"
        else:
            maintains += 1
            direction = "maintain"
        rating_changes.append({
            "date": date,
            "company": company,
            "previous": prev,
            "new": new,
            "direction": direction,
        })

    result = {
        "available": True,
        "ticker": normalized,
        "estimates": past_quarters,
        "forward_estimates": forward_annual,
        "actual_years": actual_years,
        "rating_changes": rating_changes,
        "rating_summary": {"upgrades": upgrades, "downgrades": downgrades, "maintains": maintains},
        "beat_count": beat_count,
        "total_count": len(past_quarters),
        "eps_currency": eps_currency,
        "financials_currency": financials_currency,
    }
    if currency_note:
        result["currency_note"] = currency_note
    cache_put(ck, result, ttl=3600)
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


# ── Earnings Call Transcript Endpoints ──


@router.get("/transcript-dates/{ticker}")
def get_transcript_dates(
    ticker: str,
    apikey: str = Query("", description="FMP API key"),
):
    """Get available earnings call transcript dates for a ticker."""
    if not apikey:
        return {"available": False, "reason": "FMP API key required", "dates": []}

    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        return {"available": False, "reason": err, "dates": []}

    normalized = _normalize_ticker(ticker)

    # Check cache (TTL 24 hours)
    ck = make_key("transcript_dates", normalized)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    try:
        url = f"https://financialmodelingprep.com/api/v4/earning_call_transcript?symbol={normalized}&apikey={apikey}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("Transcript dates fetch failed for %s: %s", ticker, e)
        return {"available": False, "reason": "Failed to fetch transcript dates", "dates": []}

    if not isinstance(data, list) or len(data) == 0:
        return {"available": False, "reason": "No transcripts available", "dates": []}

    dates = []
    for item in data:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            dates.append({"quarter": item[0], "year": item[1], "date": item[2]})
        elif isinstance(item, dict):
            dates.append({
                "quarter": item.get("quarter", 0),
                "year": item.get("year", 0),
                "date": item.get("date", ""),
            })

    result = {"available": True, "dates": dates}
    cache_put(ck, result, ttl=86400)  # 24 hours
    return result


class TranscriptAnalysisParams(BaseModel):
    ticker: str
    apikey: str = ""
    quarters: int = 4
    deepseek_key: str = ""


@router.post("/transcript-analysis")
def transcript_analysis(params: TranscriptAnalysisParams, request: Request):
    """Streaming SSE analysis of earnings call transcripts using AI."""
    import requests as http_requests
    from collections import Counter

    is_valid, err = validate_ticker(params.ticker)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err)

    normalized = _normalize_ticker(params.ticker)

    # Check cache first — if cached, return JSON directly (not SSE)
    ck = make_key("transcript_analysis", normalized)
    cached = cache_get(ck)
    if cached is not None:
        return cached

    if not params.apikey:
        raise HTTPException(status_code=400, detail="FMP API key required")

    import os
    deepseek_key = params.deepseek_key or os.environ.get("DEEPSEEK_API_KEY", "")
    if not deepseek_key:
        raise HTTPException(status_code=400, detail="DeepSeek API key required for transcript analysis")

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def generate():
        yield _sse("progress", {"message": "Fetching transcript dates..."})

        # Fetch transcript dates
        try:
            url = f"https://financialmodelingprep.com/api/v4/earning_call_transcript?symbol={normalized}&apikey={params.apikey}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                dates_data = json.loads(resp.read().decode())
        except Exception as e:
            yield _sse("error", {"message": f"Failed to fetch transcript dates: {e}"})
            return

        if not isinstance(dates_data, list) or len(dates_data) == 0:
            yield _sse("error", {"message": "No earnings call transcripts available for this stock"})
            return

        # Parse dates - could be list of tuples [quarter, year, date] or list of dicts
        transcript_dates = []
        for item in dates_data:
            if isinstance(item, (list, tuple)) and len(item) >= 3:
                transcript_dates.append({"quarter": item[0], "year": item[1], "date": item[2]})
            elif isinstance(item, dict):
                transcript_dates.append({
                    "quarter": item.get("quarter", 0),
                    "year": item.get("year", 0),
                    "date": item.get("date", ""),
                })

        # Take only the last N quarters
        transcript_dates = transcript_dates[:params.quarters]

        if not transcript_dates:
            yield _sse("error", {"message": "No transcript dates found"})
            return

        yield _sse("progress", {"message": f"Found {len(transcript_dates)} transcripts. Fetching content..."})

        # Fetch each transcript and analyze
        results = []
        for i, td in enumerate(transcript_dates):
            q = td["quarter"]
            y = td["year"]
            yield _sse("progress", {"message": f"Analyzing Q{q} {y} transcript ({i+1}/{len(transcript_dates)})..."})

            # Fetch transcript content
            try:
                t_url = f"https://financialmodelingprep.com/api/v3/earning_call_transcript/{normalized}?year={y}&quarter={q}&apikey={params.apikey}"
                with urllib.request.urlopen(t_url, timeout=15) as resp:
                    t_data = json.loads(resp.read().decode())
            except Exception as e:
                logger.debug("Transcript fetch failed for %s Q%s %s: %s", normalized, q, y, e)
                continue

            if not isinstance(t_data, list) or len(t_data) == 0:
                continue

            transcript = t_data[0]
            content = transcript.get("content", "")
            if not content:
                continue

            # Truncate very long transcripts to ~12000 chars to fit API limits
            if len(content) > 12000:
                content = content[:12000] + "\n\n[...transcript truncated...]"

            # Call DeepSeek to analyze
            prompt = f"""Analyze this earnings call transcript for {normalized} (Q{q} {y}) and return ONLY a JSON object with no other text:
{{
    "sentiment_score": <float from -1.0 to 1.0, where -1=very bearish, 0=neutral, 1=very bullish>,
    "tone": "bullish" | "neutral" | "cautious" | "bearish",
    "key_themes": ["theme1", "theme2", "theme3"],
    "guidance_direction": "raised" | "maintained" | "lowered" | "not_given",
    "management_confidence": <int 1-5, where 1=very low, 5=very high>,
    "summary": "<2-3 sentence summary of the key takeaways>"
}}

Transcript:
{content}"""

            try:
                ai_resp = http_requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={
                        "Authorization": f"Bearer {deepseek_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                    },
                    timeout=60,
                )
                ai_resp.raise_for_status()
                ai_data = ai_resp.json()
                ai_text = ai_data["choices"][0]["message"]["content"].strip()

                # Parse JSON from response (handle markdown code blocks)
                if ai_text.startswith("```"):
                    ai_text = re.sub(r'^```(?:json)?\s*', '', ai_text)
                    ai_text = re.sub(r'\s*```$', '', ai_text)

                analysis = json.loads(ai_text)

                results.append({
                    "year": y,
                    "quarter": q,
                    "date": td.get("date", ""),
                    "sentiment_score": float(analysis.get("sentiment_score", 0)),
                    "tone": analysis.get("tone", "neutral"),
                    "key_themes": analysis.get("key_themes", [])[:5],
                    "guidance_direction": analysis.get("guidance_direction", "not_given"),
                    "management_confidence": int(analysis.get("management_confidence", 3)),
                    "summary": analysis.get("summary", ""),
                })
            except Exception as e:
                logger.warning("AI analysis failed for %s Q%s %s: %s", normalized, q, y, e)
                continue

        if not results:
            yield _sse("error", {"message": "Failed to analyze any transcripts"})
            return

        yield _sse("progress", {"message": "Computing trends..."})

        # Compute trend
        # Sort results by date (oldest first) for trend calculation
        results_sorted = sorted(results, key=lambda r: (r["year"], r["quarter"]))

        # Sentiment direction
        if len(results_sorted) >= 2:
            oldest_score = results_sorted[0]["sentiment_score"]
            newest_score = results_sorted[-1]["sentiment_score"]
            diff = newest_score - oldest_score
            if diff > 0.15:
                sentiment_direction = "improving"
            elif diff < -0.15:
                sentiment_direction = "declining"
            else:
                sentiment_direction = "stable"
        else:
            sentiment_direction = "stable"

        # Recurring themes (appear in 2+ quarters)
        theme_counter: Counter = Counter()
        for r in results:
            for theme in r["key_themes"]:
                theme_counter[theme] += 1
        recurring_themes = [t for t, c in theme_counter.most_common() if c >= 2][:5]

        # Average confidence
        confidences = [r["management_confidence"] for r in results]
        avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else 3.0

        # Results in reverse chronological order for display
        results_display = sorted(results, key=lambda r: (r["year"], r["quarter"]), reverse=True)

        final_result = {
            "ticker": normalized,
            "quarters_analyzed": len(results),
            "results": results_display,
            "trend": {
                "sentiment_direction": sentiment_direction,
                "recurring_themes": recurring_themes,
                "avg_confidence": avg_confidence,
            },
            "engine": "deepseek",
        }

        # Cache the result
        cache_put(ck, final_result, ttl=86400)

        yield _sse("result", final_result)

    return StreamingResponse(generate(), media_type="text/event-stream")
