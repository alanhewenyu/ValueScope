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

_price_cache = {}   # {ticker: (price, currency, prev_close, ts, source)}
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


# ── Eastmoney real-time quotes (A/B-shares + HKEX) ────────

_EM_QUOTE_URL = 'https://push2.eastmoney.com/api/qt/stock/get'
# f43=latest price, f59=decimal places, f60=prev close, f86=last update ts
_EM_FIELDS = 'f43,f44,f45,f46,f47,f59,f60,f86,f170'


_em_session = None


def _eastmoney_session():
    """Session for eastmoney, with retries and keep-alive disabled.

    push2.eastmoney.com closes pooled connections without responding
    (RemoteDisconnected), and urllib3 only finds out when it tries to reuse
    one — which failed far more often than opening a fresh connection each
    time. Batching means one request per refresh anyway, so there is no
    pooling benefit to trade away.
    """
    global _em_session
    if _em_session is None:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        sess = requests.Session()
        sess.headers.update({'User-Agent': 'Mozilla/5.0', 'Connection': 'close'})
        adapter = HTTPAdapter(max_retries=Retry(
            total=4,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(['GET']),
        ))
        sess.mount('https://', adapter)
        _em_session = sess
    return _em_session


def _fetch_eastmoney_raw(secid: str, ticker: str) -> dict:
    """GET one quote from eastmoney push2. Returns the ``data`` dict or raises."""
    resp = _eastmoney_session().get(_EM_QUOTE_URL, params={
        'secid': secid,
        'fields': _EM_FIELDS,
        'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
    }, timeout=10)
    resp.raise_for_status()
    data = resp.json().get('data', {})
    if not data:
        raise ValueError(f"No data returned for {ticker}")
    return data


def _zero_if_stale(ticker: str, f86, price: float, prev_close: float | None) -> float | None:
    """Return prev_close, or ``price`` when the quote predates today.

    A quote whose last-update date is before today in the exchange's timezone
    means there was no session today (weekend/holiday), and pairing it with
    f60 would replay the previous session's move as "today". The comparison
    must happen in the exchange's timezone, not the server's — a UTC host
    rolls the date over mid-session in Asia.
    """
    if not f86 or prev_close is None:
        return prev_close
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(_exchange_tz(ticker))
        if datetime.datetime.fromtimestamp(int(f86), tz).date() < datetime.datetime.now(tz).date():
            return price
    except (ValueError, OSError, TypeError):
        pass
    return prev_close


def _eastmoney_secid(ticker: str) -> str | None:
    """Eastmoney secid for a ticker, or None if eastmoney doesn't cover it.

    600xxx.SS -> 1.600xxx, 000xxx.SZ -> 0.000xxx, 0700.HK -> 116.00700
    """
    if not ticker or '.' not in ticker:
        return None
    code = ticker.split('.')[0]
    if not code.isdigit():
        return None
    if ticker.endswith('.SS'):
        return f'1.{code}'
    if ticker.endswith('.SZ'):
        return f'0.{code}'
    if ticker.endswith('.HK'):
        return f'116.{code.zfill(5)}'
    return None


_EM_BATCH_URL = 'https://push2.eastmoney.com/api/qt/ulist.np/get'
# f1=decimal places, f2=latest price, f12=code, f13=market,
# f18=prev close, f297=trading date (YYYYMMDD)
_EM_BATCH_FIELDS = 'f1,f2,f12,f13,f18,f297'
_EM_BATCH_SIZE = 50


def _fetch_eastmoney_batch(tickers: list[str]) -> dict[str, tuple[float, str, float | None]]:
    """Batch-fetch eastmoney quotes, 50 tickers per request.

    Secondary to _fetch_tencent_batch: this host drops connections often
    enough that it cannot be relied on alone (4 of 5 full-book requests
    failed while Tencent served 12 of 12), but it is a useful second opinion
    for anything Tencent does not return.

    Returns {ticker: (price, currency, prev_close)} for whatever resolved;
    tickers missing from the result are left for the per-ticker path.
    """
    by_secid = {}
    for t in tickers:
        secid = _eastmoney_secid(t)
        if secid:
            by_secid[secid] = t

    out: dict[str, tuple[float, str, float | None]] = {}
    secids = list(by_secid)
    for i in range(0, len(secids), _EM_BATCH_SIZE):
        chunk = secids[i:i + _EM_BATCH_SIZE]
        try:
            resp = _eastmoney_session().get(_EM_BATCH_URL, params={
                'secids': ','.join(chunk),
                'fields': _EM_BATCH_FIELDS,
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
            }, timeout=15)
            resp.raise_for_status()
            diff = (resp.json().get('data') or {}).get('diff') or []
            rows = diff.values() if isinstance(diff, dict) else diff
        except Exception as e:
            logger.warning("eastmoney batch failed for %d tickers: %s", len(chunk), e)
            continue

        for row in rows:
            try:
                ticker = by_secid.get(f"{row.get('f13')}.{row.get('f12')}")
                price_raw = row.get('f2')
                if not ticker or price_raw is None or price_raw == '-':
                    continue
                # f1 carries the decimal places, so this covers HK's mixed
                # 2/3-decimal quoting and the SSE B-share x1000 scale alike.
                divisor = 10 ** int(row.get('f1') or 2)
                price = float(price_raw) / divisor
                prev_raw = row.get('f18')
                prev_close = float(prev_raw) / divisor if prev_raw not in (None, '-') else None
                prev_close = _zero_if_stale_date(ticker, row.get('f297'), price, prev_close)
                currency = 'HKD' if ticker.endswith('.HK') else _infer_currency(ticker)
                out[ticker] = (price, currency, prev_close)
            except (TypeError, ValueError) as e:
                logger.warning("eastmoney batch row parse failed: %s", e)

    return out


def _zero_if_stale_date(ticker: str, f297, price: float, prev_close: float | None) -> float | None:
    """prev_close guard driven by eastmoney's f297 trading date (YYYYMMDD int)."""
    if not f297 or prev_close is None:
        return prev_close
    try:
        from zoneinfo import ZoneInfo
        quote_date = datetime.datetime.strptime(str(int(f297)), '%Y%m%d').date()
        if quote_date < datetime.datetime.now(ZoneInfo(_exchange_tz(ticker))).date():
            return price
    except (ValueError, OSError, TypeError):
        pass
    return prev_close


# ── Tencent real-time quotes (HKEX + SSE/SZSE, batched) ───

_TX_BATCH_URL = 'https://qt.gtimg.cn/q='
_TX_BATCH_SIZE = 60


def _tencent_symbol(ticker: str) -> str | None:
    """Tencent quote symbol for a ticker, or None if not covered.

    600415.SS -> sh600415, 002966.SZ -> sz002966, 0700.HK -> r_hk00700
    (the ``r_`` prefix is the real-time HK feed).
    """
    if not ticker or '.' not in ticker:
        return None
    code = ticker.split('.')[0]
    if not code.isdigit():
        return None
    if ticker.endswith('.SS'):
        return f'sh{code}'
    if ticker.endswith('.SZ'):
        return f'sz{code}'
    if ticker.endswith('.HK'):
        return f'r_hk{code.zfill(5)}'
    return None


def _fetch_tencent_batch(tickers: list[str]) -> dict[str, tuple[float, str, float | None]]:
    """Batch-fetch HKEX/SSE/SZSE quotes from Tencent. Never raises.

    Preferred over eastmoney: it answers the whole book in one request in
    ~0.5s where eastmoney dropped 4 of 5 connections at the same pace, and it
    returns prices as plain decimals — no per-market integer scale to get
    wrong, which is what made B-shares fragile on the eastmoney path.

    Returns {ticker: (price, currency, prev_close)} for whatever resolved.
    """
    by_symbol = {}
    for t in tickers:
        sym = _tencent_symbol(t)
        if sym:
            by_symbol[sym] = t

    out: dict[str, tuple[float, str, float | None]] = {}
    symbols = list(by_symbol)
    for i in range(0, len(symbols), _TX_BATCH_SIZE):
        chunk = symbols[i:i + _TX_BATCH_SIZE]
        try:
            resp = _fetch_tencent_raw(','.join(chunk))
        except Exception as e:
            logger.warning("tencent batch failed for %d tickers: %s", len(chunk), e)
            continue

        for line in resp.split('\n'):
            if '~' not in line:
                continue
            try:
                fields = line.split('~')
                # head looks like: v_r_hk00700="100
                symbol = fields[0].split('=', 1)[0].strip()[2:]
                ticker = by_symbol.get(symbol)
                if not ticker or len(fields) < 5:
                    continue
                price = float(fields[3]) if fields[3] else 0.0
                if price <= 0:
                    continue  # suspended / no quote
                prev_close = float(fields[4]) if fields[4] else None
                if prev_close is not None and prev_close <= 0:
                    prev_close = None
                # f[30] is the quote time: "2026/07/31 10:10:51" for HK,
                # "20260731101051" for the mainland boards. Reduce both to
                # YYYYMMDD for the no-session-today guard.
                digits = ''.join(c for c in (fields[30] if len(fields) > 30 else '') if c.isdigit())
                prev_close = _zero_if_stale_date(
                    ticker, digits[:8] if len(digits) >= 8 else None, price, prev_close)
                currency = 'HKD' if ticker.endswith('.HK') else _infer_currency(ticker)
                out[ticker] = (price, currency, prev_close)
            except (TypeError, ValueError, IndexError) as e:
                logger.warning("tencent batch row parse failed: %s", e)

    return out


def _fetch_tencent_raw(symbols: str) -> str:
    """GET a Tencent quote batch, decoded as GBK. Raises on failure."""
    import requests
    resp = requests.get(f'{_TX_BATCH_URL}{symbols}',
                        headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
    resp.raise_for_status()
    resp.encoding = 'gbk'
    return resp.text


def prime_price_cache(tickers: list[str]) -> int:
    """Seed the price cache for every real-time-covered ticker in one shot.

    Call before fanning out per-ticker fetches; those then hit the cache
    instead of opening a connection each. Tencent answers the whole book in
    one request; eastmoney backfills anything it missed. Returns how many
    tickers were seeded.
    """
    if not tickers:
        return 0

    seeded: dict[str, tuple[float, str, float | None]] = {}
    try:
        seeded = _fetch_tencent_batch(tickers)
    except Exception as e:
        logger.warning("tencent prime failed: %s", e)

    missing = [t for t in tickers if t not in seeded and _eastmoney_secid(t)]
    if missing:
        try:
            seeded.update(_fetch_eastmoney_batch(missing))
        except Exception as e:
            logger.warning("eastmoney prime failed: %s", e)

    now = _time.time()
    for ticker, (price, currency, prev_close) in seeded.items():
        if price is not None:
            _price_cache[ticker] = (price, currency, prev_close, now, 'domestic')
    return len(seeded)


def _fetch_ashare_domestic(ticker: str) -> tuple[float, str, float | None]:
    """Fetch SSE/SZSE price from eastmoney. Returns (price, currency, prev_close) or raises.

    Works for both A-shares (600xxx/000xxx → CNY) and B-shares (900xxx → USD,
    20xxxx → HKD). Eastmoney returns the price in the actual trading currency,
    so currency is inferred from the ticker via _infer_currency().
    """
    # Map yfinance ticker to eastmoney secid: 600xxx.SS -> 1.600xxx, 000xxx.SZ -> 0.000xxx
    code = ticker.split('.')[0]
    if ticker.endswith('.SS'):
        secid = f'1.{code}'
    elif ticker.endswith('.SZ'):
        secid = f'0.{code}'
    else:
        raise ValueError(f"Not an A-share ticker: {ticker}")

    data = _fetch_eastmoney_raw(secid, ticker)

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
    prev_close = _zero_if_stale(ticker, data.get('f86'), price, prev_close)

    return (price, _infer_currency(ticker), prev_close)


def _fetch_domestic(ticker: str) -> tuple[float, str, float | None]:
    """Real-time quote from whichever domestic feed answers.

    Tencent first — it is the reliable one — then eastmoney. Raises when
    neither has the ticker, which drops fetch_price through to yfinance.
    """
    got = _fetch_tencent_batch([ticker])
    if ticker in got:
        return got[ticker]
    if ticker.endswith('.HK'):
        return _fetch_hk_domestic(ticker)
    return _fetch_ashare_domestic(ticker)


def _fetch_hk_domestic(ticker: str) -> tuple[float, str, float | None]:
    """Fetch HKEX price from eastmoney. Returns (price, 'HKD', prev_close) or raises.

    yfinance is NOT an equivalent source here: Yahoo's HKEX feed is
    exchange-delayed by 15 minutes (it says so itself in
    ``info['exchangeDataDelayedBy']``), which showed up as 1-3% price errors
    on active names while the session was running. Eastmoney quotes HKEX in
    real time, so it is primary and yfinance is the degraded fallback.
    """
    secid = _eastmoney_secid(ticker) if ticker.endswith('.HK') else None
    if not secid:
        raise ValueError(f"Not an HK ticker: {ticker}")

    data = _fetch_eastmoney_raw(secid, ticker)

    price_raw = data.get('f43')
    if price_raw is None or price_raw == '-':
        raise ValueError(f"No price for {ticker}")

    # Unlike the mainland boards, HKEX names are quoted at 2 or 3 decimals
    # depending on price level, so the scale must be read from f59 rather
    # than assumed — penny stocks like 1060.HK come back ×1000.
    divisor = 10 ** int(data.get('f59') or 2)
    price = float(price_raw) / divisor
    prev_raw = data.get('f60')
    prev_close = float(prev_raw) / divisor if prev_raw and prev_raw != '-' else None
    prev_close = _zero_if_stale(ticker, data.get('f86'), price, prev_close)

    return (price, 'HKD', prev_close)


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
        # After-hours is a continuation of TODAY's session, so the reference
        # point stays the previous regular close. Pairing the after-hours
        # price with today's regular close instead would drop the regular
        # session's move from the daily P&L the moment the bell rings — e.g.
        # AAPL closing -1.4% then falling 6% on earnings showed as -6.3%
        # for the day rather than -7.6%.
        price = info.get('postMarketPrice') or reg_price
        prev_close = reg_prev
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

    # Skip cache when regular_only (snapshot needs the regular-session price,
    # and a cached entry may hold an extended-hours one). Only US tickers have
    # an extended session, so elsewhere the cached value IS the regular price
    # and honouring the cache lets the batch prefetch serve the snapshot too.
    if not (regular_only and _eastmoney_secid(ticker) is None):
        cached = _price_cache.get(ticker)
        if cached and (_time.time() - cached[3]) < _PRICE_TTL:
            return cached[0], cached[1]

    source = None
    # Chinese fund codes (6 digits, no suffix) -> use eastmoney fund API
    if _FUND_CODE_RE.match(ticker):
        nav, cur, prev_nav = fetch_fund_nav(ticker)
        result = (nav, cur, prev_nav)
        source = 'fund_nav'
    else:
        currency = _infer_currency(ticker)

        # Exchanges with a real-time domestic feed, preferred over yfinance:
        #   SSE/SZSE — quoted in the actual trading currency, so B-shares work.
        #   HKEX     — yfinance is 15min delayed here (see _fetch_hk_domestic).
        # yfinance stays as the last resort when both domestic feeds are down.
        if _tencent_symbol(ticker) or _eastmoney_secid(ticker):
            try:
                result = _retry(lambda: _fetch_domestic(ticker))
                source = 'domestic'
            except Exception as e_dom:
                logger.warning("domestic API failed for %s: %s, trying yfinance...", ticker, e_dom)
                try:
                    result = _retry(lambda: _fetch_yfinance(ticker, currency, regular_only))
                    source = 'yfinance'
                except Exception as e_yf:
                    logger.warning("yfinance also failed for %s: %s", ticker, e_yf)
                    result = (None, None, None)
        else:
            # All other markets: yfinance with retry
            try:
                result = _retry(lambda: _fetch_yfinance(ticker, currency, regular_only))
                source = 'yfinance'
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
                source = 'fmp'
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
        _price_cache[ticker] = (result[0], result[1], result[2], _time.time(), source)
    return result[0], result[1]


def get_previous_close(ticker: str) -> float | None:
    """Get cached previous close price for a ticker. Call fetch_price first."""
    cached = _price_cache.get(ticker)
    if cached:
        return cached[2]  # previous_close
    return None


def get_price_source(ticker: str) -> str | None:
    """Which feed served the cached price ('domestic'/'yfinance'/'fmp'/'fund_nav')."""
    cached = _price_cache.get(ticker)
    return cached[4] if cached and len(cached) > 4 else None


# How stale a feed's quotes are, in minutes, by market. The domestic feeds
# (Tencent/eastmoney) are real time; Yahoo and FMP resell exchange-delayed
# data everywhere outside the US. Yahoo's own ``exchangeDataDelayedBy`` says
# 15 for HKEX, 15 for the mainland boards and 20 for Tokyo; measured lag was
# ~15min on all three. Mainland and HK normally come off the domestic feed
# at 0 — these numbers apply when that feed is down and we fell back, so a
# silent degradation shows up in the UI as a delay marker instead.
_DELAY_BY_SOURCE_MARKET = {
    'yfinance': {'HK': 15, 'JP': 20, 'CN': 15},
    'fmp': {'HK': 15, 'JP': 15, 'CN': 15},
}


def _market_of(ticker: str) -> str:
    tu = (ticker or '').upper()
    if tu.endswith('.HK'):
        return 'HK'
    if tu.endswith('.T'):
        return 'JP'
    if tu.endswith('.SS') or tu.endswith('.SZ'):
        return 'CN'
    return 'US'


def get_price_delay_minutes(ticker: str) -> int:
    """Quote delay in minutes for the cached price — 0 when it is real time.

    Lets the UI mark prices that cannot be trusted as "now". Japan is the
    case that actually bites: no free real-time feed covers Tokyo, so those
    quotes sit ~15-20min behind, which on an earnings day is a double-digit
    percentage move that has not shown up yet.
    """
    source = get_price_source(ticker)
    if not source:
        return 0
    return _DELAY_BY_SOURCE_MARKET.get(source, {}).get(_market_of(ticker), 0)


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

    # One batched call covers every mainland/HK name up front; the fan-out
    # below then serves those from cache and only hits the network for US,
    # JP and fund codes.
    prime_price_cache(tickers)

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
