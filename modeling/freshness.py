# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Financial data freshness detection with akshare supplementation.

Detects when FMP API data is stale (company has reported earnings but API
hasn't updated yet).  When stale, attempts to pull the latest financial
statements from akshare (东方财富).  Once FMP catches up, the akshare
supplement is auto-invalidated and FMP data is used — keeping the data
source consistent long-term.

Covers: A-shares, HK stocks, US ADRs (all via akshare / 东方财富).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import pandas as pd

from .data import is_a_share, is_hk_stock

logger = logging.getLogger("valuescope.freshness")

_FMP_BASE = "https://financialmodelingprep.com"

# In-memory cache for freshness results (avoid repeated akshare calls within short window)
# {ticker: (timestamp, (financial_data, freshness_info))}
_freshness_mem_cache: dict[str, tuple[float, tuple]] = {}
_FRESHNESS_CACHE_TTL = 300  # 5 minutes


# ── Public entry point ─────────────────────────────────────


def check_data_freshness(ticker: str, financial_data: dict, apikey: str) -> tuple[dict, dict]:
    """Check if current data is stale; if so, try to supplement from akshare.

    Staleness detection uses two paths:
      1. FMP earnings calendar (when apikey is available) — fast, covers US/HK
      2. akshare latest report date (free, no key needed) — covers A-shares/HK/US ADR

    Returns (financial_data, freshness_info).
    financial_data may have an extra column prepended if akshare data is available.
    When the primary data source updates, the supplement is auto-invalidated.
    """
    freshness_info = {
        "is_stale": False,
        "expected_period": None,
        "data_source": "api",
    }

    # Fast path: return cached freshness result if recent (avoids repeated akshare calls)
    _cached = _freshness_mem_cache.get(ticker)
    if _cached and (time.monotonic() - _cached[0]) < _FRESHNESS_CACHE_TTL:
        cached_data, cached_info = _cached[1]
        # Re-merge cached akshare data into the fresh financial_data
        if cached_info.get("data_source", "api") != "api":
            from .freshness_cache import get_cached
            period_key = cached_info.get("_period_key", "")
            cached_entry = get_cached(ticker, period_key) if period_key else None
            if cached_entry:
                financial_data = _merge_into_summary(financial_data, cached_entry["data"], period_key)
                # Clear TTM metadata if needed
                if financial_data.get("ttm_latest_quarter"):
                    summary_df = financial_data.get("summary")
                    if summary_df is not None and "Period" in summary_df.index:
                        has_ttm = any("TTM" in str(summary_df.loc["Period"].iloc[i]) for i in range(len(summary_df.columns)))
                        if not has_ttm:
                            financial_data["ttm_latest_quarter"] = ""
                            financial_data["ttm_end_date"] = ""
                            financial_data["ttm_note"] = ""
        return financial_data, cached_info

    try:
        market = _detect_market(ticker)

        # A-shares: data source is already akshare — no staleness possible
        if market == "CN":
            return financial_data, freshness_info

        # Path 1: FMP earnings calendar (if apikey available)
        staleness = None
        if apikey:
            earnings = _fetch_earnings_dates(ticker, apikey)
            if earnings:
                staleness = _detect_staleness(earnings, financial_data)

        # Path 2: akshare direct comparison (free, no key needed)
        # If FMP didn't detect staleness (no key, or no earnings data), check akshare
        if staleness is None or not staleness["is_stale"]:
            ak_staleness = _detect_staleness_via_akshare(ticker, market, financial_data)
            if ak_staleness and ak_staleness["is_stale"]:
                staleness = ak_staleness

        if staleness is None or not staleness["is_stale"]:
            return financial_data, freshness_info

        # Data is stale
        freshness_info["is_stale"] = True
        freshness_info["expected_period"] = staleness["expected_period"]
        period_key = staleness["period_key"]
        expected_date = staleness["expected_date"]

        # Q1 → skip (existing TTM logic returns None for Q1)
        if staleness.get("is_q1"):
            return financial_data, freshness_info

        # Check SQLite cache first
        from .freshness_cache import get_cached, put_cached, invalidate

        cached = get_cached(ticker, period_key)
        if cached:
            # Primary source caught up → invalidate cache
            if _api_has_caught_up(financial_data, expected_date):
                invalidate(ticker, period_key)
                freshness_info["is_stale"] = False
                freshness_info["data_source"] = "api"
                return financial_data, freshness_info

            # Use cached akshare data
            financial_data = _merge_into_summary(financial_data, cached["data"], period_key)
            freshness_info["data_source"] = "akshare_cached"
            freshness_info["_period_key"] = period_key
            _freshness_mem_cache[ticker] = (time.monotonic(), (None, freshness_info))
            return financial_data, freshness_info

        # No cache → try akshare
        ak_data = _fetch_from_akshare(ticker, market, expected_date)
        if ak_data:
            put_cached(ticker, period_key, market, ak_data, "akshare (东方财富)")
            financial_data = _merge_into_summary(financial_data, ak_data, period_key)
            freshness_info["data_source"] = "akshare"
            freshness_info["_period_key"] = period_key
            _freshness_mem_cache[ticker] = (time.monotonic(), (None, freshness_info))
            return financial_data, freshness_info

        # akshare doesn't have it yet → just show stale warning
    except Exception as e:
        logger.debug("Freshness check failed for %s: %s", ticker, e)

    # Cache result in memory (5 min TTL) to avoid repeated akshare calls
    _freshness_mem_cache[ticker] = (time.monotonic(), (None, freshness_info))

    return financial_data, freshness_info


# ── FMP earnings calendar ──────────────────────────────────


def _fetch_earnings_dates(ticker: str, apikey: str) -> list[dict] | None:
    """Fetch earnings dates from FMP (stable API with v3 fallback).

    Uses urllib directly (not get_jsonparsed_data) to avoid noisy error prints.
    """
    if not apikey:
        return None

    import json as _json
    from urllib.request import urlopen

    for url in [
        f"{_FMP_BASE}/stable/earning-calendar-confirmed?symbol={ticker}&apikey={apikey}",
        f"{_FMP_BASE}/api/v3/historical/earning_calendar/{ticker}?apikey={apikey}",
    ]:
        try:
            resp = urlopen(url, timeout=10)
            data = _json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list):
                return data
        except Exception:
            pass
    return None


# ── Staleness detection ────────────────────────────────────


def _detect_staleness(earnings: list[dict], financial_data: dict) -> dict | None:
    """Compare latest earnings date vs latest period in summary DataFrame."""
    summary_df = financial_data.get("summary")
    if summary_df is None or summary_df.empty:
        return None

    latest_api_date = _get_latest_summary_date(summary_df)
    if latest_api_date is None:
        return None

    # Find most recent past earnings announcement
    now = datetime.now()
    recent = []
    for e in earnings:
        try:
            edate_str = e.get("date") or e.get("publicationDate") or ""
            if not edate_str:
                continue
            edate = datetime.strptime(edate_str[:10], "%Y-%m-%d")
            if edate <= now:
                recent.append({"date": edate, "fiscal_date_ending": e.get("fiscalDateEnding", "")})
        except (ValueError, TypeError):
            continue

    if not recent:
        return None

    recent.sort(key=lambda x: x["date"], reverse=True)
    latest = recent[0]

    expected_str = latest["fiscal_date_ending"]
    if not expected_str:
        return None
    try:
        expected_date = datetime.strptime(expected_str[:10], "%Y-%m-%d")
    except ValueError:
        return None

    if expected_date <= latest_api_date:
        return None  # API is up to date

    fy_end_month = financial_data.get("fy_end_month", 12)
    period_key = _make_period_key(expected_date, fy_end_month)
    quarter = _quarter_from_date(expected_date, fy_end_month)

    return {
        "is_stale": True,
        "expected_period": period_key,
        "expected_date": expected_date,
        "period_key": period_key,
        "is_q1": quarter == "Q1",
    }


def _detect_staleness_via_akshare(ticker: str, market: str, financial_data: dict) -> dict | None:
    """Detect staleness by comparing akshare's latest report date vs summary DataFrame.

    No API key needed — uses free akshare data.
    """
    summary_df = financial_data.get("summary")
    if summary_df is None or summary_df.empty:
        return None

    # Find latest date in current summary
    latest_api_date = _get_latest_summary_date(summary_df)
    if latest_api_date is None:
        return None

    # Get akshare's latest available report date
    try:
        ak_latest = _get_akshare_latest_date(ticker, market)
        if ak_latest is None:
            return None

        if ak_latest <= latest_api_date:
            return None  # no newer data in akshare

        fy_end_month = financial_data.get("fy_end_month", 12)
        period_key = _make_period_key(ak_latest, fy_end_month)
        quarter = _quarter_from_date(ak_latest, fy_end_month)

        return {
            "is_stale": True,
            "expected_period": period_key,
            "expected_date": ak_latest,
            "period_key": period_key,
            "is_q1": quarter == "Q1",
        }
    except Exception as e:
        logger.debug("akshare staleness check failed for %s: %s", ticker, e)
        return None


def _get_latest_summary_date(summary_df) -> datetime | None:
    """Get the latest date across all columns in the summary DataFrame."""
    try:
        date_row = summary_df.loc["Date"] if "Date" in summary_df.index else None
        if date_row is None:
            return None
        latest = None
        for i in range(len(summary_df.columns)):
            ds = str(date_row.iloc[i])
            if ds in ("N/A", "", "nan"):
                continue
            try:
                d = datetime.strptime(ds[:10], "%Y-%m-%d")
                if latest is None or d > latest:
                    latest = d
            except ValueError:
                continue
        return latest
    except (IndexError, KeyError):
        return None


def _get_akshare_latest_date(ticker: str, market: str) -> datetime | None:
    """Get the latest report date available in akshare for this ticker."""
    from .data import _get_ak
    ak = _get_ak()

    try:
        if market == "CN":
            ak_code = "SH" + ticker.split(".")[0] if ticker.endswith(".SS") else "SZ" + ticker.split(".")[0]
            df = ak.stock_profit_sheet_by_report_em(symbol=ak_code)
            if df.empty:
                return None
            latest = str(df["REPORT_DATE"].iloc[0])[:10]
        elif market == "HK":
            code = ticker.split(".")[0].zfill(5)
            df = ak.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="年度")
            if df.empty:
                return None
            latest = str(df["REPORT_DATE"].iloc[0])[:10]
        else:  # US ADR
            symbol = ticker.split(".")[0]
            df = ak.stock_financial_us_report_em(stock=symbol, symbol="综合损益表", indicator="年报")
            if df.empty:
                return None
            latest = str(df["REPORT_DATE"].iloc[0])[:10]

        return datetime.strptime(latest, "%Y-%m-%d")
    except Exception as e:
        logger.debug("akshare latest date lookup failed for %s: %s", ticker, e)
        return None


def _make_period_key(date: datetime, fy_end_month: int) -> str:
    from .data import _fiscal_year_quarter
    fy, fq = _fiscal_year_quarter(date.strftime("%Y-%m-%d"), fy_end_month)
    return f"{fy}-{fq}"


def _quarter_from_date(date: datetime, fy_end_month: int) -> str:
    from .data import _fiscal_year_quarter
    _, fq = _fiscal_year_quarter(date.strftime("%Y-%m-%d"), fy_end_month)
    return fq


def _detect_market(ticker: str) -> str:
    if is_a_share(ticker):
        return "CN"
    if is_hk_stock(ticker):
        return "HK"
    return "US"


# ── akshare extraction ─────────────────────────────────────


def _fetch_from_akshare(ticker: str, market: str, expected_date: datetime) -> dict | None:
    """Pull latest financial statements from akshare if available.

    Returns a dict with standardized field names (raw currency units), or None.
    """
    # FMP fiscalDateEnding may differ by ±1 day from akshare REPORT_DATE
    # (e.g. 2025-12-30 vs 2025-12-31).  Try exact match first, then ±3 days.
    from datetime import timedelta
    candidates = [expected_date + timedelta(days=d) for d in (0, 1, -1, 2, -2, 3)]
    for dt in candidates:
        target = dt.strftime("%Y-%m-%d")
        try:
            if market == "CN":
                result = _akshare_cn(ticker, target)
            elif market == "HK":
                result = _akshare_hk(ticker, target)
            else:
                result = _akshare_us(ticker, target)
            if result:
                return result
        except Exception as e:
            logger.debug("akshare fetch failed for %s (date=%s): %s", ticker, target, e)
    return None


def _akshare_cn(ticker: str, target_date: str) -> dict | None:
    """A-shares: wide-format APIs with English column names."""
    from .data import _get_ak
    ak = _get_ak()

    ak_code = "SH" + ticker.split(".")[0] if ticker.endswith(".SS") else "SZ" + ticker.split(".")[0]

    inc = ak.stock_profit_sheet_by_report_em(symbol=ak_code)
    inc = inc[inc["REPORT_DATE"].astype(str).str[:10] == target_date]
    if inc.empty:
        return None

    row = inc.iloc[0]
    revenue = _safe_float(row.get("TOTAL_OPERATE_INCOME"))
    if not revenue:
        return None

    # Balance sheet
    bs_data = {}
    try:
        bs = ak.stock_balance_sheet_by_report_em(symbol=ak_code)
        bs = bs[bs["REPORT_DATE"].astype(str).str[:10] == target_date]
        if not bs.empty:
            b = bs.iloc[0]
            bs_data = {
                "totalDebt": _safe_float(b.get("SHORT_LOAN")) + _safe_float(b.get("LONG_LOAN")) + _safe_float(b.get("BOND_PAYABLE")),
                "totalEquity": _safe_float(b.get("TOTAL_EQUITY")),
                "cashAndEquivalents": _safe_float(b.get("MONETARYFUNDS")),
                "minorityInterest": _safe_float(b.get("MINORITY_EQUITY")),
                "totalInvestments": _safe_float(b.get("TRADE_FINASSET_NOTFVTPL")) + _safe_float(b.get("OTHER_EQUITY_INVEST")),
            }
    except Exception:
        pass

    # Cash flow (D&A only in annual/semi-annual; capex usually available)
    cf_data = {}
    try:
        cf = ak.stock_cash_flow_sheet_by_report_em(symbol=ak_code)
        cf = cf[cf["REPORT_DATE"].astype(str).str[:10] == target_date]
        if not cf.empty:
            c = cf.iloc[0]
            cf_data = {
                "capitalExpenditure": abs(_safe_float(c.get("CONSTRUCT_LONG_ASSET"))),
                "depreciationAndAmortization": (
                    _safe_float(c.get("FA_IR_DEPR")) +
                    _safe_float(c.get("IA_AMORTIZE")) +
                    _safe_float(c.get("LPE_AMORTIZE"))
                ),
            }
    except Exception:
        pass

    return {
        "revenue": revenue,
        "operatingIncome": _safe_float(row.get("OPERATE_PROFIT")),
        "incomeTaxExpense": _safe_float(row.get("INCOME_TAX")),
        "periodEndDate": target_date,
        **cf_data,
        **bs_data,
    }


def _akshare_hk(ticker: str, target_date: str) -> dict | None:
    """HK stocks: long-format (row-per-item) with Chinese field names."""
    from .data import _get_ak
    ak = _get_ak()

    # 0700.HK → 00700
    code = ticker.split(".")[0].zfill(5)

    # Income statement
    try:
        inc = ak.stock_financial_hk_report_em(stock=code, symbol="利润表", indicator="年度")
    except Exception:
        return None

    inc_row = inc[inc["REPORT_DATE"].astype(str).str[:10] == target_date]
    if inc_row.empty:
        return None

    revenue = _lookup_item(inc_row, "营业额") or _lookup_item(inc_row, "营业收入")
    if not revenue:
        return None

    # Balance sheet
    bs_data = {}
    try:
        bs = ak.stock_financial_hk_report_em(stock=code, symbol="资产负债表", indicator="年度")
        bs_row = bs[bs["REPORT_DATE"].astype(str).str[:10] == target_date]
        if not bs_row.empty:
            _l = lambda name: _lookup_item(bs_row, name)
            total_debt = _l("短期贷款") + _l("长期贷款") + _l("应付票据(非流动)")
            total_assets = _l("总资产")
            cash = _l("现金及等价物")
            short_deposits = _l("短期存款")
            # Total Investments: all non-operating financial/investment assets.
            # Use keyword matching for generality across different companies.
            total_investments = _sum_investment_items_hk(bs_row)

            bs_data = {
                "totalDebt": total_debt,
                "totalEquity": _l("总权益"),
                "shareholderEquity": _l("股东权益"),
                "cashAndEquivalents": cash,
                "totalInvestments": total_investments,
                "minorityInterest": _l("少数股东权益"),
                "totalAssets": total_assets,
                # For ratio calculation
                "financeCost": _lookup_item(inc_row, "融资成本"),
                "netIncome": _lookup_item(inc_row, "股东应占溢利"),
            }
    except Exception:
        pass

    # Cash flow — only net totals available for HK, no capex/D&A detail
    cf_data = {}
    try:
        cf = ak.stock_financial_hk_report_em(stock=code, symbol="现金流量表", indicator="年度")
        cf_row = cf[cf["REPORT_DATE"].astype(str).str[:10] == target_date]
        if not cf_row.empty:
            cf_data = {
                "operatingCashFlow": _lookup_item(cf_row, "经营业务现金净额"),
                "investingCashFlow": _lookup_item(cf_row, "投资业务现金净额"),
            }
    except Exception:
        pass

    return {
        "revenue": revenue,
        "operatingIncome": _lookup_item(inc_row, "经营溢利"),
        "incomeTaxExpense": _lookup_item(inc_row, "税项"),
        "periodEndDate": target_date,
        **bs_data,
        **cf_data,
    }


def _akshare_us(ticker: str, target_date: str) -> dict | None:
    """US ADRs: long-format (row-per-item) with Chinese field names."""
    from .data import _get_ak
    ak = _get_ak()

    symbol = ticker.split(".")[0]

    # Income statement
    try:
        inc = ak.stock_financial_us_report_em(stock=symbol, symbol="综合损益表", indicator="年报")
    except Exception:
        return None

    inc_row = inc[inc["REPORT_DATE"].astype(str).str[:10] == target_date]
    if inc_row.empty:
        return None

    revenue = _lookup_item_us(inc_row, "主营收入") or _lookup_item_us(inc_row, "营业收入")
    if not revenue:
        return None

    # Balance sheet
    bs_data = {}
    try:
        bs = ak.stock_financial_us_report_em(stock=symbol, symbol="资产负债表", indicator="年报")
        bs_row = bs[bs["REPORT_DATE"].astype(str).str[:10] == target_date]
        if not bs_row.empty:
            _l = lambda name: _lookup_item_us(bs_row, name)
            total_debt = _l("应付票据(非流动)") + _l("长期负债") + _l("可转换票据及债券")
            total_assets = _l("总资产")
            cash = _l("现金及现金等价物")
            total_investments = _sum_investment_items_us(bs_row)

            bs_data = {
                "totalDebt": total_debt,
                "totalEquity": _l("股东权益合计"),
                "shareholderEquity": _l("归属于母公司股东权益"),
                "cashAndEquivalents": cash,
                "totalInvestments": total_investments,
                "minorityInterest": _l("少数股东权益"),
                "totalAssets": total_assets,
                "netIncome": _lookup_item_us(inc_row, "归属于母公司股东净利润"),
                "financeCost": _lookup_item_us(inc_row, "利息费用"),
            }
    except Exception:
        pass

    return {
        "revenue": revenue,
        "operatingIncome": _lookup_item_us(inc_row, "营业利润"),
        "incomeTaxExpense": _lookup_item_us(inc_row, "所得税"),
        "periodEndDate": target_date,
        **bs_data,
    }


# ── akshare helpers ────────────────────────────────────────


def _sum_investment_items_hk(bs_row: pd.DataFrame) -> float:
    """Sum all non-operating investment assets from HK balance sheet.

    Includes: equity investments (associates/JV), financial assets at fair value,
    investment properties, term deposits, securities investments.
    Excludes: 受限制存款及现金 (restricted cash → cash side), 客户存款 (bank liability).
    """
    # Include: equity investments, financial assets, securities, investment properties, deposits
    # yfinance bundles 中长期存款 into "Investmentin Financial Assets", so we include it too.
    # Exclude: restricted cash (→ cash side), bank liabilities (客户存款/同业存款)
    _INCLUDE_KEYWORDS = ["投资", "联营", "合营", "公允价值", "金融资产", "存款", "证券投资"]
    _EXCLUDE_KEYWORDS = ["受限制", "客户存款", "负债", "同业"]

    total = 0.0
    if "STD_ITEM_NAME" not in bs_row.columns:
        return 0.0
    for _, row in bs_row.iterrows():
        name = str(row.get("STD_ITEM_NAME", ""))
        val = row.get("AMOUNT", 0)
        if not val or pd.isna(val):
            continue
        if any(k in name for k in _EXCLUDE_KEYWORDS):
            continue
        if any(k in name for k in _INCLUDE_KEYWORDS):
            total += float(val)
    return total


def _sum_investment_items_us(bs_row: pd.DataFrame) -> float:
    """Sum all non-operating investment assets from US ADR balance sheet."""
    _INCLUDE_KEYWORDS = ["投资", "投資", "证券"]
    _EXCLUDE_KEYWORDS = ["受限制"]

    total = 0.0
    if "ITEM_NAME" not in bs_row.columns:
        return 0.0
    for _, row in bs_row.iterrows():
        name = str(row.get("ITEM_NAME", ""))
        val = row.get("AMOUNT", 0)
        if not val or pd.isna(val):
            continue
        if any(k in name for k in _EXCLUDE_KEYWORDS):
            continue
        if any(k in name for k in _INCLUDE_KEYWORDS):
            total += float(val)
    return total


def _safe_float(val) -> float:
    """Convert to float, treating NaN/None as 0."""
    if val is None:
        return 0.0
    try:
        f = float(val)
        return 0.0 if pd.isna(f) else f
    except (ValueError, TypeError):
        return 0.0


def _lookup_item(df: pd.DataFrame, item_name: str) -> float:
    """Look up a value by STD_ITEM_NAME in HK long-format data."""
    col = "STD_ITEM_NAME"
    if col not in df.columns:
        return 0.0
    match = df[df[col] == item_name]
    if match.empty:
        return 0.0
    return _safe_float(match.iloc[0].get("AMOUNT", 0))


def _lookup_item_us(df: pd.DataFrame, item_name: str) -> float:
    """Look up a value by ITEM_NAME in US ADR long-format data."""
    col = "ITEM_NAME"
    if col not in df.columns:
        return 0.0
    match = df[df[col] == item_name]
    if match.empty:
        return 0.0
    return _safe_float(match.iloc[0].get("AMOUNT", 0))


# ── Merge into summary ─────────────────────────────────────


def _merge_into_summary(financial_data: dict, ak_data: dict, period_key: str) -> dict:
    """Prepend akshare data as the newest column in the summary DataFrame."""
    summary_df = financial_data.get("summary")
    if summary_df is None or summary_df.empty:
        return financial_data

    period_end_date = ak_data.get("periodEndDate", "")
    revenue = _safe_float(ak_data.get("revenue"))
    ebit = _safe_float(ak_data.get("operatingIncome"))
    tax = _safe_float(ak_data.get("incomeTaxExpense"))
    da = _safe_float(ak_data.get("depreciationAndAmortization"))
    capex = _safe_float(ak_data.get("capitalExpenditure"))
    debt = _safe_float(ak_data.get("totalDebt"))
    equity = _safe_float(ak_data.get("totalEquity"))
    cash = _safe_float(ak_data.get("cashAndEquivalents"))
    invest = _safe_float(ak_data.get("totalInvestments"))
    minority = _safe_float(ak_data.get("minorityInterest"))

    # Additional fields from enriched extraction
    wc = _safe_float(ak_data.get("workingCapital"))
    total_assets = _safe_float(ak_data.get("totalAssets"))
    shareholder_equity = _safe_float(ak_data.get("shareholderEquity"))
    net_income = _safe_float(ak_data.get("netIncome"))
    finance_cost = _safe_float(ak_data.get("financeCost"))

    M = 1_000_000
    revenue_m = revenue / M
    ebit_m = ebit / M
    debt_m = debt / M
    equity_m = equity / M
    cash_m = abs(cash) / M
    invest_m = abs(invest) / M
    minority_m = abs(minority) / M
    ic_m = debt_m + equity_m - cash_m - invest_m

    # Fallback: if capex/D&A/WC not available from akshare, use prior year values
    _fallback_items = []
    # The first column in summary_df is the prior period (before we prepend akshare)
    # Look for a FY column to label the fallback source
    prev_fy_label = "prior year"
    if "Period" in summary_df.index:
        for i in range(len(summary_df.columns)):
            if "FY" in str(summary_df.loc["Period"].iloc[i]):
                prev_fy_label = f"FY{summary_df.columns[i]}"
                break

    capex_m = abs(capex) / M
    da_m = abs(da) / M
    wc_m = wc / M if wc else 0

    # Find the first FY column index (skip TTM if present)
    _fy_col = 0
    if "Period" in summary_df.index:
        for i in range(len(summary_df.columns)):
            p = str(summary_df.loc["Period"].iloc[i])
            if "TTM" not in p:
                _fy_col = i
                break

    # WC change is not directly available from akshare single-period pull.
    # Always use prior FY's value as fallback (same as TTM logic).
    wc_m = _get_float(summary_df, "(+) ΔWorking Capital", _fy_col)

    _fallback_rows = ["(+) ΔWorking Capital"]  # WC always uses fallback
    if capex == 0 and da == 0:
        # No cash flow detail — use prior FY data
        capex_m = _get_float(summary_df, "(+) Capital Expenditure", _fy_col)
        da_m = _get_float(summary_df, "(-) D&A", _fy_col)
        _fallback_rows.extend(["(+) Capital Expenditure", "(-) D&A"])
        _fallback_items.append("Capex/D&A/WC")
    else:
        _fallback_items.append("WC")

    _fallback_rows.append("Total Reinvestment")

    freshness_note = ""
    if _fallback_items:
        freshness_note = f"* {'/'.join(_fallback_items)} use {prev_fy_label} data (CF detail unavailable from akshare)"

    reinvest_m = capex_m - da_m + wc_m

    tax_rate = (tax / ebit * 100) if ebit != 0 else 0
    ebit_margin = (ebit / revenue * 100) if revenue != 0 else 0
    rev_to_ic = (revenue_m / ic_m) if ic_m > 0 else 0

    # Derived ratios
    debt_to_assets = (debt / total_assets * 100) if total_assets > 0 else 0
    cost_of_debt = (finance_cost / debt * 100) if debt > 0 else 0
    # ROE = Net Income / Shareholder Equity (use current period; ideally avg with prior)
    prev_sh_equity = _get_float(summary_df, "(+) Total Equity", _fy_col) * M - _get_float(summary_df, "Minority Interest", _fy_col) * M
    avg_sh_equity = (shareholder_equity + prev_sh_equity) / 2 if prev_sh_equity > 0 else shareholder_equity
    roe = (net_income / avg_sh_equity * 100) if avg_sh_equity > 0 else 0
    roic = (ebit * (1 - tax / ebit if ebit else 0) / (ic_m * M) * 100) if ic_m > 0 else 0

    # Growth vs prior FY column (reuse _fy_col computed above)
    prev_rev = _get_float(summary_df, "Revenue", _fy_col)
    prev_ebit = _get_float(summary_df, "EBIT", _fy_col)
    rev_growth = ((revenue_m / prev_rev - 1) * 100) if prev_rev else 0
    ebit_growth = ((ebit_m / prev_ebit - 1) * 100) if prev_ebit else 0

    col_label = period_key.split("-")[0]  # e.g. "2025"

    # Build column matching existing index
    new_col = {}
    for idx in summary_df.index:
        if idx == "Date":
            new_col[idx] = period_end_date
        elif idx == "Period":
            new_col[idx] = "FY"
        elif idx == "Reported Currency":
            new_col[idx] = summary_df.loc["Reported Currency"].iloc[0] if "Reported Currency" in summary_df.index else "N/A"
        elif idx == "Revenue":
            new_col[idx] = revenue_m
        elif idx == "EBIT":
            new_col[idx] = ebit_m
        elif idx == "Revenue Growth (%)":
            new_col[idx] = rev_growth
        elif idx == "EBIT Growth (%)":
            new_col[idx] = ebit_growth
        elif idx == "EBIT Margin (%)":
            new_col[idx] = ebit_margin
        elif idx == "Tax Rate (%)":
            new_col[idx] = tax_rate
        elif idx == "(+) Capital Expenditure":
            new_col[idx] = capex_m
        elif idx == "(-) D&A":
            new_col[idx] = da_m
        elif idx == "(+) ΔWorking Capital":
            new_col[idx] = wc_m
        elif idx == "Total Reinvestment":
            new_col[idx] = reinvest_m
        elif idx == "(+) Total Debt":
            new_col[idx] = debt_m
        elif idx == "(+) Total Equity":
            new_col[idx] = equity_m
        elif idx == "(-) Cash & Equivalents":
            new_col[idx] = cash_m
        elif idx == "(-) Total Investments":
            new_col[idx] = invest_m
        elif idx == "Invested Capital":
            new_col[idx] = ic_m
        elif idx == "Minority Interest":
            new_col[idx] = minority_m
        elif idx == "Revenue / IC":
            new_col[idx] = rev_to_ic
        elif idx == "ROIC (%)":
            new_col[idx] = roic
        elif idx == "ROE (%)":
            new_col[idx] = roe
        elif idx == "Debt to Assets (%)":
            new_col[idx] = debt_to_assets
        elif idx == "Cost of Debt (%)":
            new_col[idx] = cost_of_debt
        elif idx.startswith("▸") or idx in ("Calendar Year",):
            new_col[idx] = ""
        else:
            new_col[idx] = 0

    series = pd.Series(new_col, name=col_label)

    # Drop any existing TTM column that is older than the new akshare FY data.
    # e.g. "2025Q2(TTM)" with date 2025-06-30 is superseded by akshare FY2025 (2025-12-31).
    if "Period" in summary_df.index and "Date" in summary_df.index:
        cols_to_drop = []
        for i, c in enumerate(summary_df.columns):
            p = str(summary_df.loc["Period"].iloc[i])
            d = str(summary_df.loc["Date"].iloc[i])
            if "TTM" in p and d < period_end_date:
                cols_to_drop.append(c)
                # Can only drop by position since column names may duplicate
                break
        if cols_to_drop:
            summary_df = summary_df.drop(columns=summary_df.columns[[
                i for i, c in enumerate(summary_df.columns)
                if str(summary_df.loc["Period"].iloc[i]).find("TTM") >= 0
                and str(summary_df.loc["Date"].iloc[i]) < period_end_date
            ]])
            # Clear TTM metadata — akshare FY data supersedes the TTM
            financial_data["ttm_latest_quarter"] = ""
            financial_data["ttm_end_date"] = ""
            financial_data["ttm_note"] = ""

    summary_df = pd.concat([series.to_frame(), summary_df], axis=1)

    # Recalculate Incremental Margin (%) after merge
    if 'Incremental Margin (%)' in summary_df.index and 'EBIT' in summary_df.index and 'Revenue' in summary_df.index:
        _rev = pd.to_numeric(summary_df.loc['Revenue'], errors='coerce')
        _ebit = pd.to_numeric(summary_df.loc['EBIT'], errors='coerce')
        for ci in range(len(summary_df.columns)):
            if ci + 1 < len(summary_df.columns):
                d_rev = _rev.iloc[ci] - _rev.iloc[ci + 1]
                d_ebit = _ebit.iloc[ci] - _ebit.iloc[ci + 1]
                prev_rev = _rev.iloc[ci + 1]
                if prev_rev != 0 and abs(d_rev / prev_rev) < 0.03:
                    summary_df.loc['Incremental Margin (%)', summary_df.columns[ci]] = float('nan')
                elif d_rev != 0:
                    summary_df.loc['Incremental Margin (%)', summary_df.columns[ci]] = d_ebit / d_rev * 100
                else:
                    summary_df.loc['Incremental Margin (%)', summary_df.columns[ci]] = float('nan')
            else:
                summary_df.loc['Incremental Margin (%)', summary_df.columns[ci]] = float('nan')

    financial_data["summary"] = summary_df

    # Append freshness note about fallback data
    if freshness_note:
        existing_note = financial_data.get("ttm_note", "")
        financial_data["ttm_note"] = freshness_note if not existing_note else f"{existing_note}; {freshness_note}"

    # Store fallback row info so formatted_summary can add * markers
    if _fallback_rows:
        financial_data["_freshness_fallback_rows"] = _fallback_rows

    return financial_data


def _get_float(df: pd.DataFrame, row_name: str, col_idx: int) -> float:
    try:
        return float(df.loc[row_name].iloc[col_idx])
    except (KeyError, IndexError, ValueError, TypeError):
        return 0.0


def _get_float_nonzero(df: pd.DataFrame, row_name: str) -> float:
    """Get the nearest non-zero value from prior year columns.

    Scans columns left-to-right (most recent first) and returns the first
    non-zero value. Falls back to 0.0 if all columns are zero.
    """
    if row_name not in df.index:
        return 0.0
    row = df.loc[row_name]
    for i in range(len(row)):
        try:
            v = float(row.iloc[i])
            if v != 0 and not pd.isna(v):
                return v
        except (ValueError, TypeError):
            continue
    return 0.0


# ── API catch-up check ─────────────────────────────────────


def _api_has_caught_up(financial_data: dict, expected_date: datetime) -> bool:
    """Check if API's latest period is at or past the expected date."""
    summary_df = financial_data.get("summary")
    if summary_df is None or summary_df.empty:
        return False
    try:
        if "Date" not in summary_df.index:
            return False
        ds = str(summary_df.loc["Date"].iloc[0])
        if ds in ("N/A", "", "nan"):
            return False
        return datetime.strptime(ds[:10], "%Y-%m-%d") >= expected_date
    except (ValueError, IndexError):
        return False
