# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Real-time price and FX rate fetching with caching.

Extracted from portfolio-tracker/prices.py — no personal data,
all configuration via environment variables.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import time as _time
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .portfolio_db import DB_PATH

logger = logging.getLogger("valuescope.portfolio.prices")

# FMP fallback — only active when FMP_API_KEY env var is set.
# Public deployments (valuescope.app) leave this unset so user FMP keys
# are never required. Self-hosters with a subscription set it in .env.
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# Module-level thread pool — reused across all calls (avoids create/destroy overhead)
_pool = ThreadPoolExecutor(max_workers=8)

# ── Price cache ──────────────────────────────────────────

_price_cache = {}   # {ticker: (price, currency, prev_close, ts)}
_PRICE_TTL = 60     # 60 seconds — fast refresh during active sessions

_fx_cache = {}      # {currency: (rate_to_cny, ts)}
_FX_TTL = 600       # 10 minutes — FX rates change slowly

_FUND_CODE_RE = re.compile(r'^\d{6}$')  # 6-digit Chinese fund codes

# ── Retry config ─────────────────────────────────────────

_MAX_RETRIES = 1    # 1 retry (2 attempts total) — keep fast for 45+ positions
_RETRY_DELAY = 0.5  # seconds


def _retry(fn: Callable, retries: int = _MAX_RETRIES, delay: float = _RETRY_DELAY):
    """Call fn() with retries on exception. Returns fn() result or re-raises last exception."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < retries:
                _time.sleep(delay * (attempt + 1))  # linear backoff: 1s, 2s
    raise last_exc


# ── FMP fallback (price + FX) ─────────────────────────────

def _fetch_fmp_quote(symbol: str) -> tuple[float, float | None]:
    """Fetch (price, previousClose) from FMP /quote. Raises on failure.

    Symbol uses yfinance suffixes (.SS, .SZ, .HK, .T) — FMP accepts them as-is
    for the markets we use. US tickers have no suffix in either source.
    """
    if not FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY not set")
    import requests
    resp = requests.get(
        f"{FMP_BASE}/quote/{symbol}",
        params={"apikey": FMP_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"FMP returned empty for {symbol}")
    row = data[0]
    price = row.get("price")
    if price is None:
        raise ValueError(f"FMP no price for {symbol}")
    prev = row.get("previousClose")
    return float(price), (float(prev) if prev is not None else None)


# ── A-share domestic API fallback ─────────────────────────

def _fetch_ashare_domestic(ticker: str) -> tuple[float, str, float | None]:
    """Fetch SSE/SZSE price from eastmoney. Returns (price, currency, prev_close) or raises.

    Works for both A-shares (600xxx/000xxx → CNY) and B-shares (900xxx → USD,
    20xxxx → HKD). Eastmoney returns the price in the actual trading currency,
    so currency is inferred from the ticker via _infer_currency().
    """
    import requests
    # Map yfinance ticker to eastmoney secid: 600xxx.SS -> 1.600xxx, 000xxx.SZ -> 0.000xxx
    code = ticker.split('.')[0]
    if ticker.endswith('.SS'):
        secid = f'1.{code}'
    elif ticker.endswith('.SZ'):
        secid = f'0.{code}'
    else:
        raise ValueError(f"Not an A-share ticker: {ticker}")

    url = 'https://push2.eastmoney.com/api/qt/stock/get'
    resp = requests.get(url, params={
        'secid': secid,
        'fields': 'f43,f44,f45,f46,f47,f60,f86,f170',
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
    }, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    resp.raise_for_status()
    data = resp.json().get('data', {})
    if not data:
        raise ValueError(f"No data returned for {ticker}")

    # f43=latest price, f60=prev close, f86=last update timestamp.
    # Raw integer scale: A-shares & SZSE B-shares are ×100 (CNY/HKD, 2 decimals);
    # SSE B-shares are ×1000 (USD, 3 decimals — quoted in cents). Mismatching
    # this gives a 10× error on 900xxx.SS that silently inflates B-share MV.
    price_raw = data.get('f43')
    prev_raw = data.get('f60')
    if price_raw is None or price_raw == '-':
        raise ValueError(f"No price for {ticker}")

    divisor = 1000 if (_is_b_share(ticker) and ticker.endswith('.SS')) else 100
    price = float(price_raw) / divisor
    prev_close = float(prev_raw) / divisor if prev_raw and prev_raw != '-' else None

    # If data is not from today, market didn't trade today (weekend/holiday).
    # Set prev_close = price so daily P&L = 0.
    f86 = data.get('f86')
    if f86 and prev_close is not None:
        try:
            data_date = datetime.date.fromtimestamp(int(f86))
            if data_date < datetime.date.today():
                prev_close = price
        except (ValueError, OSError):
            pass

    return (price, _infer_currency(ticker), prev_close)


def _is_b_share(ticker: str) -> bool:
    """Check if ticker is a B-share (traded in USD on SSE or HKD on SZSE)."""
    if not ticker:
        return False
    code = ticker.split('.')[0]
    # Shanghai B: 900xxx, Shenzhen B: 20xxxx (200xxx-209xxx)
    return (ticker.endswith('.SS') and code.startswith('900')) or \
           (ticker.endswith('.SZ') and code[:2] == '20' and code[2:3].isdigit())


def _infer_currency(ticker: str) -> str | None:
    """Infer trading currency from ticker suffix (best-effort)."""
    if not ticker:
        return None
    if _is_b_share(ticker):
        code = ticker.split('.')[0]
        return 'USD' if code.startswith('900') else 'HKD'  # SSE B=USD, SZSE B=HKD
    if ticker.endswith('.SS') or ticker.endswith('.SZ'):
        return 'CNY'
    if ticker.endswith('.HK'):
        return 'HKD'
    if ticker.endswith('.T'):
        return 'JPY'
    return 'USD'


def fetch_fund_nav(code: str) -> tuple[float | None, str | None, float | None]:
    """Fetch fund NAV. Returns (nav, 'CNY', prev_nav) or (None, None, None).

    Primary: ``api.fund.eastmoney.com`` (direct, lightweight).
    Fallback: ``ak.fund_open_fund_info_em`` (used when the primary host has DNS
    or connection issues — e.g. ``api.fund.eastmoney.com`` was unreachable while
    other eastmoney subdomains still resolved).
    """
    # --- Primary: direct HTTP to eastmoney fund API ---
    try:
        import requests
        url = 'https://api.fund.eastmoney.com/f10/lsjz'
        resp = requests.get(url, params={
            'fundCode': code, 'pageIndex': 1, 'pageSize': 2,
        }, headers={
            'Referer': 'https://fund.eastmoney.com/',
            'User-Agent': 'Mozilla/5.0',
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get('Data', {}).get('LSJZList', [])
        if items:
            nav = items[0].get('DWJZ')
            prev_nav = float(items[1].get('DWJZ')) if len(items) > 1 and items[1].get('DWJZ') else None
            if nav:
                nav = float(nav)
                # Non-trading day: if latest NAV date < today, prev = nav (daily P&L = 0)
                nav_date_str = items[0].get('FSRQ', '')
                if nav_date_str and prev_nav is not None:
                    try:
                        _nav_date = datetime.date.fromisoformat(nav_date_str.strip())
                        if _nav_date < datetime.date.today():
                            prev_nav = nav
                    except Exception:
                        pass
                return nav, 'CNY', prev_nav
    except Exception as e:
        logger.warning("fund NAV (eastmoney direct) failed for %s: %s", code, e)

    # --- Fallback: akshare fund_open_fund_info_em ---
    try:
        import akshare as ak
        df = ak.fund_open_fund_info_em(symbol=code, indicator='单位净值走势')
        if df is not None and not df.empty and '单位净值' in df.columns:
            nav = float(df['单位净值'].iloc[-1])
            prev_nav = float(df['单位净值'].iloc[-2]) if len(df) > 1 else None
            # Non-trading day adjustment
            if '净值日期' in df.columns and prev_nav is not None:
                try:
                    _nav_date = datetime.date.fromisoformat(str(df['净值日期'].iloc[-1]).strip())
                    if _nav_date < datetime.date.today():
                        prev_nav = nav
                except Exception:
                    pass
            return nav, 'CNY', prev_nav
    except Exception as e:
        logger.warning("fund NAV (akshare fallback) failed for %s: %s", code, e)

    return None, None, None


def _fetch_us_extended(t, currency):
    """Fetch US stock with extended-hours pricing and correct prev_close.

    prev_close = last completed regular session close (NOT the session before that).
    price      = most recent available (regular / pre-market / after-hours).
    Uses tk.info which provides marketState, postMarketPrice, preMarketPrice.
    """
    try:
        info = t.info
    except Exception:
        # Fallback: fast_info + history (old approach)
        fi = t.fast_info
        price = float(fi.last_price) if fi.last_price and fi.last_price > 0 else None
        hist = t.history(period='5d')
        prev_close = float(hist['Close'].iloc[-2]) if hist is not None and len(hist) >= 2 else None
        if price is None and hist is not None and not hist.empty:
            price = float(hist['Close'].iloc[-1])
        return (price, currency, prev_close)

    market_state = info.get('marketState', '')
    reg_price = info.get('regularMarketPrice')
    reg_prev  = info.get('regularMarketPreviousClose')

    if market_state == 'REGULAR':
        price = reg_price
        prev_close = reg_prev
    elif market_state in ('POST', 'POSTPOST'):
        price = info.get('postMarketPrice') or reg_price
        prev_close = reg_price
    else:
        price = info.get('preMarketPrice') or info.get('postMarketPrice') or reg_price
        prev_close = reg_price
        if market_state == 'PRE' and info.get('preMarketPrice'):
            # Live pre-market on a scheduled trading day (holidays stay
            # CLOSED, never PRE): the pre-market move vs the last regular
            # close IS today's move — keep it. The stale-date zeroing below
            # would wipe it, because regularMarketTime still points at the
            # previous session until today's open.
            pass
        else:
            # No session today in the exchange's timezone (weekend/holiday):
            # zero the daily P&L instead of showing Friday's move / stale
            # after-hours drift as "today"
            try:
                from zoneinfo import ZoneInfo
                ts = info.get('regularMarketTime')
                tz = ZoneInfo(info.get('exchangeTimezoneName') or 'America/New_York')
                if ts and datetime.datetime.fromtimestamp(int(ts), tz).date() < datetime.datetime.now(tz).date():
                    prev_close = price
                elif not ts and _exchange_weekend(getattr(t, 'ticker', '')):
                    prev_close = price
            except Exception:
                if _exchange_weekend(getattr(t, 'ticker', '')):
                    prev_close = price

    if price is not None:
        price = float(price)
    if prev_close is not None:
        prev_close = float(prev_close)

    return (price, currency, prev_close)


_EXCHANGE_TZ_BY_SUFFIX = [
    ('.HK', 'Asia/Hong_Kong'),
    ('.T', 'Asia/Tokyo'),
    ('.SS', 'Asia/Shanghai'),
    ('.SZ', 'Asia/Shanghai'),
]


def _exchange_tz(ticker: str) -> str:
    """Exchange timezone name from the ticker suffix (no network calls)."""
    tu = (ticker or '').upper()
    if tu.isdigit():  # CN mutual funds (bare 6-digit codes)
        return 'Asia/Shanghai'
    for suffix, tz in _EXCHANGE_TZ_BY_SUFFIX:
        if tu.endswith(suffix):
            return tz
    return 'America/New_York'


def _exchange_weekend(ticker: str) -> bool:
    """True when it's Sat/Sun in the ticker's exchange timezone (suffix-based,
    no network calls — deterministic even when data sources are rate-limited)."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo(_exchange_tz(ticker))).weekday() >= 5


def _fetch_yfinance(ticker, currency, regular_only=False):
    """Fetch price via yfinance. Returns (price, currency, prev_close). Raises on failure."""
    import yfinance as yf
    t = yf.Ticker(ticker)

    if currency == 'USD' and not regular_only:
        return _fetch_us_extended(t, currency)
    elif currency == 'USD' and regular_only:
        try:
            info = t.info
            price = info.get('regularMarketPrice')
            prev_close = info.get('regularMarketPreviousClose')
            if price is not None:
                price = float(price)
            if prev_close is not None:
                prev_close = float(prev_close)
            return (price, currency, prev_close)
        except Exception:
            fi = t.fast_info
            price = float(fi.last_price) if fi.last_price and fi.last_price > 0 else None
            return (price, currency, None)
    else:
        fi = t.fast_info
        price = float(fi.last_price) if fi.last_price and fi.last_price > 0 else None
        # fast_info.previous_close is lightweight (no extra API call) and directly
        # gives the previous session's close — more reliable than parsing history
        prev_close = None
        try:
            pc = fi.previous_close
            if pc and pc > 0:
                prev_close = float(pc)
        except Exception:
            pass
        # Weekend in the exchange's timezone: no session today, so last_price
        # is Friday's close and previous_close is THURSDAY's — the pair would
        # show Friday's whole move as "today". Zero it instead. Timezone is
        # inferred from the ticker suffix — fi.timezone is a lazy web request
        # that gets rate-limited and would silently disable this guard.
        if prev_close is not None and _exchange_weekend(ticker):
            prev_close = price
        # Holiday guard (e.g. Japan's 海の日 falls on a Monday): the weekday
        # check can't see exchange holidays, and fast_info then pairs the last
        # session's close with the one before — showing that whole session as
        # "today". If the newest daily bar is older than today in the
        # exchange's timezone there is no session today (holiday, or simply
        # pre-open after midnight): zero the move.
        #
        # BUT a missing today-bar can also mean "session open, bar not
        # published yet" — Yahoo's daily history lags a while after the open
        # (seen on HK at 09:40). Disambiguate with live-trading evidence: on
        # a closed day the live price sits exactly on the last completed
        # bar's close; if it has moved off it, a session is running — keep
        # the move.
        elif prev_close is not None and prev_close != price:
            try:
                from zoneinfo import ZoneInfo
                hist = t.history(period='5d')
                if hist is not None and not hist.empty:
                    _bar = hist.index[-1]
                    _bar_date = _bar.date() if hasattr(_bar, 'date') else None
                    _today = datetime.datetime.now(ZoneInfo(_exchange_tz(ticker))).date()
                    _last_close = float(hist['Close'].iloc[-1])
                    _off_last_bar = (price is not None and _last_close > 0
                                     and abs(price - _last_close) / _last_close > 1e-6)
                    if _bar_date and _bar_date < _today and not _off_last_bar:
                        prev_close = price
            except Exception:
                pass  # guard is best-effort; a failed check keeps fast_info's pair
        # Fall back to history if fast_info.previous_close unavailable
        if prev_close is None:
            hist = t.history(period='5d')
            if hist is not None and not hist.empty:
                if price is None:
                    price = float(hist['Close'].iloc[-1])
                if len(hist) >= 2:
                    _bar_date = hist.index[-1].date() if hasattr(hist.index[-1], 'date') else None
                    if _bar_date and _bar_date < datetime.date.today():
                        prev_close = float(hist['Close'].iloc[-1])
                    else:
                        prev_close = float(hist['Close'].iloc[-2])
        return (price, currency, prev_close)


def fetch_price(ticker: str, regular_only: bool = False) -> tuple[float | None, str | None]:
    """Fetch latest price for a ticker via yfinance (or eastmoney for funds).
    Returns (price, currency) or (None, None).
    Also caches previous_close -- access via get_previous_close(ticker).

    regular_only: if True, US stocks return regularMarketPrice (ignoring
                  pre/post-market). Used by snapshot for stable EOD values.
    """
    if not ticker:
        return None, None

    # Skip cache when regular_only (snapshot needs fresh regular price)
    if not regular_only:
        cached = _price_cache.get(ticker)
        if cached and (_time.time() - cached[3]) < _PRICE_TTL:
            return cached[0], cached[1]

    # Chinese fund codes (6 digits, no suffix) -> use eastmoney fund API
    if _FUND_CODE_RE.match(ticker):
        nav, cur, prev_nav = fetch_fund_nav(ticker)
        result = (nav, cur, prev_nav)
    else:
        currency = _infer_currency(ticker)

        # SSE/SZSE tickers (A-share + B-share): eastmoney returns the price in the
        # actual trading currency, so it's safe for B-shares too. yfinance is a
        # fallback when eastmoney is unreachable.
        if ticker.endswith('.SS') or ticker.endswith('.SZ'):
            try:
                result = _retry(lambda: _fetch_ashare_domestic(ticker))
            except Exception as e_dom:
                logger.warning("domestic API failed for %s: %s, trying yfinance...", ticker, e_dom)
                try:
                    result = _retry(lambda: _fetch_yfinance(ticker, currency, regular_only))
                except Exception as e_yf:
                    logger.warning("yfinance also failed for %s: %s", ticker, e_yf)
                    result = (None, None, None)
        else:
            # All other markets: yfinance with retry
            try:
                result = _retry(lambda: _fetch_yfinance(ticker, currency, regular_only))
            except Exception as e:
                logger.warning("price fetch failed for %s: %s", ticker, e)
                result = (None, None, None)

        # FMP fallback — last resort when yfinance/eastmoney both failed.
        # Skip B-shares: FMP returns the SS/SZ listing price in CNY, but B-shares
        # are denominated in USD/HKD, so the number would be in the wrong currency.
        if result[0] is None and FMP_API_KEY and not _is_b_share(ticker):
            try:
                price, prev = _retry(lambda: _fetch_fmp_quote(ticker))
                result = (price, currency, prev)
                logger.warning("FMP fallback succeeded for %s", ticker)
            except Exception as e_fmp:
                logger.warning("FMP fallback failed for %s: %s", ticker, e_fmp)

    # Central weekend guard — covers EVERY source (yfinance, FMP fallback,
    # eastmoney): when the exchange has no session today, price is the last
    # close and any "previous close" pairs it with the session before —
    # which would show the last trading day's move as "today". Zero it here
    # at the chokepoint so no fallback path can leak it back in.
    if result[0] is not None and result[2] is not None and _exchange_weekend(ticker):
        result = (result[0], result[1], result[0])

    # Only cache successful fetches; failed ones (None) should be retried immediately
    if result[0] is not None:
        _price_cache[ticker] = (result[0], result[1], result[2], _time.time())
    return result[0], result[1]


def get_previous_close(ticker: str) -> float | None:
    """Get cached previous close price for a ticker. Call fetch_price first."""
    cached = _price_cache.get(ticker)
    if cached:
        return cached[2]  # previous_close
    return None


def fetch_fx_rate(currency: str) -> float | None:
    """Fetch FX rate to CNY. Returns rate or None."""
    if not currency or currency == 'CNY':
        return 1.0

    cached = _fx_cache.get(currency)
    if cached and (_time.time() - cached[1]) < _FX_TTL:
        return cached[0]

    def _try_yf_fx():
        import yfinance as yf
        pair = f"{currency}CNY=X"
        rate = yf.Ticker(pair).fast_info.last_price
        if rate and rate > 0:
            return float(rate)
        raise ValueError(f"Invalid FX rate for {currency}")

    try:
        result = _retry(_try_yf_fx)
    except Exception:
        result = None

    # FMP fallback (only when key set) — preferred over exchangerate.host
    if result is None and FMP_API_KEY:
        try:
            price, _ = _fetch_fmp_quote(f"{currency}CNY")
            result = price
            logger.warning("FMP FX fallback succeeded for %s", currency)
        except Exception as e_fmp:
            logger.warning("FMP FX fallback failed for %s: %s", currency, e_fmp)

    # Last resort: exchangerate.host (free, no key needed)
    if result is None:
        try:
            import requests
            resp = requests.get(
                'https://api.exchangerate.host/latest',
                params={'base': currency, 'symbols': 'CNY'},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            rate = data.get('rates', {}).get('CNY')
            result = float(rate) if rate else None
        except Exception:
            result = None

    # Only cache successful fetches; failed ones (None) should be retried immediately
    if result is not None:
        _fx_cache[currency] = (result, _time.time())
    return result


def get_fx_rates(db_path: str | None = None) -> dict[str, float]:
    """Get all FX rates (from DB as fallback, then try live).

    When live rates are fetched successfully they are persisted to the
    ``fx_rates`` table so the DB fallback stays up-to-date even when
    snapshot cron cannot fetch (e.g. missing yfinance in cron env).
    """
    path = db_path or DB_PATH
    rates = {'CNY': 1.0}

    # Load DB defaults
    try:
        with sqlite3.connect(path) as conn:
            for row in conn.execute("SELECT currency, rate_to_cny FROM fx_rates"):
                rates[row[0]] = row[1]
    except Exception:
        pass

    # Try live rates in parallel (3 requests at once instead of sequential)
    _fx_currencies = ('USD', 'HKD', 'JPY')
    try:
        _fx_results = list(_pool.map(fetch_fx_rate, _fx_currencies, timeout=15))
    except Exception:
        _fx_results = [None, None, None]

    _updated = []
    for cur, live in zip(_fx_currencies, _fx_results):
        if live:
            # Sanity check: reject live rate if >15% away from DB fallback
            db_rate = rates.get(cur)
            if db_rate and db_rate > 0:
                deviation = abs(live - db_rate) / db_rate
                if deviation > 0.15:
                    logger.warning("FX sanity check REJECTED %s: live=%.6f vs db=%.6f (deviation=%.0f%%)",
                                   cur, live, db_rate, deviation * 100)
                    continue  # keep DB fallback
            rates[cur] = live
            _updated.append((cur, live))

    # Persist successful live rates to DB so fallback stays fresh
    if _updated:
        try:
            with sqlite3.connect(path) as conn:
                for cur, rate in _updated:
                    conn.execute("""
                        INSERT INTO fx_rates (currency, rate_to_cny, updated_at)
                        VALUES (?, ?, datetime('now','localtime'))
                        ON CONFLICT(currency) DO UPDATE SET
                            rate_to_cny = excluded.rate_to_cny,
                            updated_at  = excluded.updated_at
                    """, (cur, rate))
                conn.commit()
        except Exception:
            pass  # best-effort; don't break the dashboard

    return rates


def refresh_all_prices(db_path: str | None = None, timeout: float = 25.0) -> dict[str, tuple[float, str]]:
    """Fetch prices for all open positions with overall timeout.
    Returns {ticker: (price, currency)}. Partial results if timeout hit."""
    from concurrent.futures import as_completed, TimeoutError as FuturesTimeoutError
    path = db_path or DB_PATH
    with sqlite3.connect(path) as conn:
        tickers = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM positions WHERE status='open' AND ticker != ''"
        ).fetchall()]

    results = {}
    if not tickers:
        return results

    futures = {_pool.submit(fetch_price, t): t for t in tickers}
    try:
        for f in as_completed(futures, timeout=timeout):
            t = futures[f]
            try:
                p, c = f.result()
                if p:
                    results[t] = (p, c)
            except Exception:
                pass
    except (FuturesTimeoutError, TimeoutError):
        logger.warning("refresh_all_prices timed out after %.0fs, got %d/%d prices",
                       timeout, len(results), len(tickers))

    return results


def prefetch_all(db_path: str | None = None) -> None:
    """Prefetch FX rates and all position prices in parallel."""
    fx_future = _pool.submit(get_fx_rates, db_path)
    prices_future = _pool.submit(refresh_all_prices, db_path)
    fx_future.result(timeout=30)
    prices_future.result(timeout=60)
