# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Relative valuation module — PE/PB/PS percentiles and peer comparison.

Data source strategy (priority order):
  1. AKShare百度估值: daily PE(TTM)/PB, supports 近一年/近三年/近五年/近十年/全部
     - A-shares, HK stocks, US stocks
     - Most accurate (adjusted TTM, industry consensus)
  2. FMP key-metrics: quarterly PE/PB for 40 quarters (10 years), all markets
     + FMP daily prices → interpolate daily PE/PB between quarterly data points
     - Fallback for markets not covered by 百度 (e.g. Japan)
     - Uses GAAP net income (higher volatility due to one-time items)
  3. yfinance: annual EPS segmentation, constant-EPS fallback
     - Last resort when both 百度 and FMP unavailable
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from .data import is_a_share, is_hk_stock, _normalize_ticker


def _get_yf_ticker(ticker):
    """Get yfinance Ticker object."""
    import yfinance as yf
    return yf.Ticker(ticker)


def _get_ak():
    """Lazy import akshare."""
    from .data import _get_ak as data_get_ak
    return data_get_ak()


def _is_us_stock(ticker):
    """Return True if ticker looks like a US stock (no suffix)."""
    t = _normalize_ticker(ticker)
    return '.' not in t


def _is_jp_stock(ticker):
    """Return True if ticker is a Japanese stock (.T suffix)."""
    t = _normalize_ticker(ticker)
    return t.endswith('.T')


def _years_to_baidu_period(years):
    """Map years parameter to AKShare百度估值 period string."""
    if years <= 1:
        return '近一年'
    elif years <= 3:
        return '近三年'
    elif years <= 5:
        return '近五年'
    elif years <= 10:
        return '近十年'
    else:
        return '全部'


# ────────────────────────────────────────────────────────────────
# AKShare百度估值 (primary source for A-shares, HK, US)
# ────────────────────────────────────────────────────────────────

def _fetch_akshare_valuation(ticker, indicator='市盈率(TTM)', period='近一年'):
    """Fetch valuation history from AKShare百度估值.

    Args:
        ticker: Normalized ticker (e.g. '600519.SS', '0700.HK', 'AAPL')
        indicator: '市盈率(TTM)', '市盈率(静)', '市净率', '市现率', '总市值'
        period: '近一年', '近三年', '近五年', '近十年', '全部'
    """
    ak = _get_ak()

    try:
        if is_a_share(ticker):
            code = ticker.split('.')[0]
            df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period=period)
        elif is_hk_stock(ticker):
            code = ticker.split('.')[0]
            if len(code) < 5:
                code = code.zfill(5)
            df = ak.stock_hk_valuation_baidu(symbol=code, indicator=indicator, period=period)
        elif _is_us_stock(ticker):
            df = ak.stock_us_valuation_baidu(symbol=ticker, indicator=indicator, period=period)
        else:
            return None

        if df is None or df.empty:
            return None

        result = []
        for _, row in df.iterrows():
            try:
                date_str = str(row.iloc[0])
                value = float(row.iloc[1])
                if not np.isnan(value) and value > 0:
                    if len(date_str) == 8:
                        date_str = f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}'
                    result.append({'date': date_str, 'value': round(value, 2)})
            except (ValueError, IndexError):
                continue

        return result if result else None
    except Exception:
        return None


def _get_akshare_pe_pb(ticker, years=5):
    """Get PE(TTM) and PB history from AKShare百度估值.

    Uses the appropriate period based on years parameter.
    """
    period = _years_to_baidu_period(years)
    pe_history = _fetch_akshare_valuation(ticker, '市盈率(TTM)', period) or []
    pb_history = _fetch_akshare_valuation(ticker, '市净率', period) or []
    return pe_history, pb_history


# ────────────────────────────────────────────────────────────────
# FMP data source (fallback for markets not covered by 百度)
# ────────────────────────────────────────────────────────────────

def _fmp_get(endpoint, apikey, params=None):
    """Call FMP API and return parsed JSON, or None on error."""
    base = 'https://financialmodelingprep.com/api/v3'
    url = f'{base}/{endpoint}?apikey={apikey}'
    if params:
        for k, v in params.items():
            url += f'&{k}={v}'
    try:
        req = Request(url, headers={'User-Agent': 'ValueScope/2.0'})
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if isinstance(data, dict) and 'Error Message' in data:
            return None
        return data
    except (URLError, HTTPError, json.JSONDecodeError):
        return None


def _get_fmp_ticker(ticker):
    """Convert normalized ticker to FMP format."""
    return _normalize_ticker(ticker)


def _get_fmp_pe_pb(ticker, apikey, years=5):
    """Get PE/PB history from FMP key-metrics + daily prices.

    Strategy: Use FMP quarterly PE/PB ratios as anchor points, then
    interpolate daily values using price changes between quarters:
      daily_PE(date) = quarterly_PE * (daily_price / quarterly_price)
    This works regardless of currency because PE ratios from FMP are
    already currency-consistent.

    Returns:
        (pe_history, pb_history) — each is list of {'date': str, 'value': float}
        or (None, None) if FMP data unavailable
    """
    fmp_ticker = _get_fmp_ticker(ticker)

    # Get quarterly key metrics (up to 40 quarters = 10 years)
    quarters_needed = min(years * 4 + 4, 40)
    metrics = _fmp_get(f'key-metrics/{fmp_ticker}', apikey,
                       {'period': 'quarter', 'limit': str(quarters_needed)})

    if not metrics or len(metrics) < 4:
        return None, None

    # Get daily prices for the period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365 + 30)
    price_data = _fmp_get(f'historical-price-full/{fmp_ticker}', apikey,
                          {'from': start_date.strftime('%Y-%m-%d'),
                           'to': end_date.strftime('%Y-%m-%d')})

    prices = []
    if isinstance(price_data, dict) and 'historical' in price_data:
        prices = price_data['historical']
    elif isinstance(price_data, list):
        prices = price_data

    if not prices or len(prices) < 10:
        return None, None

    # Build quarterly anchor points: (date, pe, pb, price)
    # FMP metrics are newest first; we need oldest first
    anchors = []
    for m in reversed(metrics):
        date_str = m.get('date', '')
        pe = m.get('peRatio')
        pb = m.get('pbRatio') or m.get('ptbRatio')

        if not date_str:
            continue

        quarter_price = _find_price_on_date(prices, date_str)
        if quarter_price and quarter_price > 0:
            anchors.append({
                'date': date_str,
                'pe': pe if pe and pe > 0 else None,
                'pb': pb if pb and pb > 0 else None,
                'price': quarter_price,
            })

    if len(anchors) < 2:
        return None, None

    # Interpolate daily PE/PB
    cutoff = (datetime.now() - timedelta(days=years * 365)).strftime('%Y-%m-%d')

    pe_history = []
    pb_history = []

    for p in prices:
        p_date = p.get('date', '')
        close = p.get('close')

        if not p_date or not close or close <= 0:
            continue
        if p_date < cutoff:
            continue

        # Find the most recent quarterly anchor <= this date
        anchor = None
        for a in anchors:
            if a['date'] <= p_date:
                anchor = a
            else:
                break

        if anchor is None:
            continue

        # Interpolate: daily_ratio = quarterly_ratio * (daily_price / quarterly_price)
        price_ratio = close / anchor['price']

        if anchor['pe'] is not None:
            daily_pe = anchor['pe'] * price_ratio
            if 0 < daily_pe < 500:
                pe_history.append({'date': p_date, 'value': round(daily_pe, 2)})

        if anchor['pb'] is not None:
            daily_pb = anchor['pb'] * price_ratio
            if 0 < daily_pb < 100:
                pb_history.append({'date': p_date, 'value': round(daily_pb, 2)})

    # Sort by date (FMP prices are newest first)
    pe_history.sort(key=lambda x: x['date'])
    pb_history.sort(key=lambda x: x['date'])

    return pe_history, pb_history


def _find_price_on_date(prices, date_str):
    """Find the closing price on or near a date from FMP price data."""
    best_price = None
    best_diff = 999

    for p in prices:
        p_date = p.get('date', '')
        if not p_date:
            continue
        try:
            diff = abs((datetime.strptime(p_date, '%Y-%m-%d') -
                       datetime.strptime(date_str, '%Y-%m-%d')).days)
            if diff < best_diff:
                best_diff = diff
                best_price = p.get('close')
                if diff == 0:
                    break
        except ValueError:
            continue

    return best_price if best_diff <= 10 else None


# ────────────────────────────────────────────────────────────────
# yfinance data source (final fallback)
# ────────────────────────────────────────────────────────────────

def _get_yfinance_pe_pb(t, normalized, years, trailing_eps, book_value, current_price):
    """Get PE/PB history from yfinance (annual EPS segmentation or constant-EPS)."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)

    hist = t.history(start=start_date.strftime('%Y-%m-%d'),
                     end=end_date.strftime('%Y-%m-%d'))
    if hist.empty:
        return [], []

    pe_history = []
    pb_history = []

    # Try annual EPS/BPS segmentation (availability-date-aware)
    annual_eps, annual_bps = _build_annual_eps_bps(t, trailing_eps, book_value)

    if annual_eps:
        pe_history = _compute_segmented_ratio_history(hist['Close'], annual_eps, 'pe')
    if annual_bps:
        pb_history = _compute_segmented_ratio_history(hist['Close'], annual_bps, 'pb')

    # Constant-EPS/BPS fallback
    if not pe_history and trailing_eps and trailing_eps > 0:
        pe_values = hist['Close'] / trailing_eps
        pe_history = [
            {'date': d.strftime('%Y-%m-%d'), 'value': round(float(v), 2)}
            for d, v in pe_values.items()
            if not np.isnan(v) and 0 < v < 500
        ]

    if not pb_history and book_value and book_value > 0:
        pb_values = hist['Close'] / book_value
        pb_history = [
            {'date': d.strftime('%Y-%m-%d'), 'value': round(float(v), 2)}
            for d, v in pb_values.items()
            if not np.isnan(v) and 0 < v < 100
        ]

    return pe_history, pb_history


def _build_annual_eps_bps(t, current_trailing_eps, current_book_value):
    """Build annual EPS/BPS timeline with availability-date awareness."""
    eps_timeline = []
    bps_timeline = []
    REPORT_DELAY_DAYS = 90

    try:
        income = t.income_stmt
        if income is not None and not income.empty:
            eps_label = None
            if 'Diluted EPS' in income.index:
                eps_label = 'Diluted EPS'
            elif 'Basic EPS' in income.index:
                eps_label = 'Basic EPS'

            if eps_label:
                for date, val in income.loc[eps_label].items():
                    if not pd.isna(val) and val > 0:
                        available_date = date + timedelta(days=REPORT_DELAY_DAYS)
                        eps_timeline.append((available_date, float(val)))
    except Exception:
        pass

    try:
        bs = t.balance_sheet
        shares = t.info.get('sharesOutstanding', 0)
        if bs is not None and not bs.empty and shares > 0:
            for label in ['Total Stockholders Equity', 'Stockholders Equity',
                          'Common Stock Equity']:
                if label in bs.index:
                    for date, val in bs.loc[label].items():
                        if not pd.isna(val) and val > 0:
                            available_date = date + timedelta(days=REPORT_DELAY_DAYS)
                            bps_timeline.append((available_date, float(val) / shares))
                    break
    except Exception:
        pass

    eps_timeline.sort(key=lambda x: x[0])
    bps_timeline.sort(key=lambda x: x[0])

    now = datetime.now()
    if current_trailing_eps and current_trailing_eps > 0:
        if not eps_timeline or now > eps_timeline[-1][0]:
            eps_timeline.append((now, current_trailing_eps))
    if current_book_value and current_book_value > 0:
        if not bps_timeline or now > bps_timeline[-1][0]:
            bps_timeline.append((now, current_book_value))

    return (eps_timeline if len(eps_timeline) >= 2 else None,
            bps_timeline if len(bps_timeline) >= 2 else None)


def _compute_segmented_ratio_history(prices, timeline, ratio_type):
    """Compute PE/PB using availability-date-aware EPS/BPS timeline."""
    if not timeline:
        return []

    result = []
    for price_date, price in prices.items():
        if pd.isna(price) or price <= 0:
            continue

        pd_naive = price_date
        if hasattr(price_date, 'tz_localize'):
            pd_naive = price_date.tz_localize(None) if price_date.tzinfo else price_date

        per_share = None
        for avail_date, value in timeline:
            avail_naive = avail_date
            if hasattr(avail_date, 'tz_localize'):
                avail_naive = avail_date.tz_localize(None) if avail_date.tzinfo else avail_date
            if avail_naive <= pd_naive:
                per_share = value
            else:
                break

        if per_share is None or per_share <= 0:
            continue

        ratio = float(price) / per_share

        if ratio_type == 'pe' and (ratio <= 0 or ratio > 500):
            continue
        if ratio_type == 'pb' and (ratio <= 0 or ratio > 100):
            continue

        result.append({
            'date': price_date.strftime('%Y-%m-%d'),
            'value': round(ratio, 2),
        })

    return result


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _merge_histories(primary, secondary):
    """Merge two history lists, primary takes priority for overlapping dates."""
    if not secondary:
        return primary
    if not primary:
        return secondary

    primary_dates = {p['date'] for p in primary}
    earliest_primary = min(primary_dates)
    merged = [p for p in secondary if p['date'] < earliest_primary]
    merged.extend(primary)
    merged.sort(key=lambda p: p['date'])
    return merged


def _downsample(points, max_points=250):
    """Downsample a list of data points to max_points for frontend rendering."""
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    return [points[int(i * step)] for i in range(max_points)]


# ────────────────────────────────────────────────────────────────
# Current valuation ratios
# ────────────────────────────────────────────────────────────────

def get_current_valuation(ticker, apikey=''):
    """Get current valuation ratios for a stock.

    Returns dict with PE, PB, PS, EV/EBITDA, forward PE, and related data.
    Works for A-shares, HK stocks, and US stocks via yfinance.
    """
    normalized = _normalize_ticker(ticker)
    try:
        t = _get_yf_ticker(normalized)
        info = t.info

        result = {
            'ticker': normalized,
            'company_name': info.get('longName') or info.get('shortName', normalized),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'currency': info.get('currency', 'USD'),
            'price': info.get('currentPrice') or info.get('regularMarketPrice', 0),
            'market_cap': info.get('marketCap', 0),
            'trailing_pe': info.get('trailingPE'),
            'forward_pe': info.get('forwardPE'),
            'price_to_book': info.get('priceToBook'),
            'price_to_sales': info.get('priceToSalesTrailing12Months'),
            'ev_to_ebitda': info.get('enterpriseToEbitda'),
            'ev_to_revenue': info.get('enterpriseToRevenue'),
            'enterprise_value': info.get('enterpriseValue', 0),
            'trailing_eps': info.get('trailingEps'),
            'forward_eps': info.get('forwardEps'),
            'book_value': info.get('bookValue'),
            'revenue_per_share': info.get('revenuePerShare'),
            'profit_margins': info.get('profitMargins'),
            'return_on_equity': info.get('returnOnEquity'),
            'return_on_assets': info.get('returnOnAssets'),
            'dividend_yield': info.get('dividendYield'),
        }

        return result
    except Exception as e:
        return {'ticker': normalized, 'error': str(e)}


# ────────────────────────────────────────────────────────────────
# Historical PE/PB percentile calculation
# ────────────────────────────────────────────────────────────────

def get_historical_valuations(ticker, years=5, apikey=''):
    """Calculate historical PE and PB percentiles.

    Data source priority:
      1. AKShare百度估值 (daily PE(TTM)/PB, up to 10 years, most accurate)
         - A-shares, HK stocks, US stocks
      2. FMP key-metrics (quarterly PE/PB, 10 years) + daily price interpolation
         - Japan stocks, or fallback when 百度 unavailable
      3. yfinance (annual EPS segmentation / constant-EPS)
         - Last resort

    Returns dict with pe/pb history, percentiles, stats, and data source info.
    """
    normalized = _normalize_ticker(ticker)

    pe_history = []
    pb_history = []
    data_source = ''

    # ── Layer 1: AKShare百度估值 (primary for A-shares, HK, US) ──
    has_akshare = is_a_share(normalized) or is_hk_stock(normalized) or _is_us_stock(normalized)
    ak_pe, ak_pb = [], []
    if has_akshare:
        try:
            ak_pe, ak_pb = _get_akshare_pe_pb(normalized, years)
        except Exception:
            pass

    # ── Layer 2: FMP (fallback for markets not covered by 百度, e.g. Japan) ──
    fmp_pe, fmp_pb = [], []
    if not ak_pe and apikey:
        try:
            _fmp_pe, _fmp_pb = _get_fmp_pe_pb(normalized, apikey, years)
            fmp_pe = _fmp_pe or []
            fmp_pb = _fmp_pb or []
        except Exception:
            pass

    # ── Layer 3: yfinance (final fallback) ──
    yf_pe, yf_pb = [], []
    if not ak_pe and not fmp_pe:
        try:
            t = _get_yf_ticker(normalized)
            info = t.info
            trailing_eps = info.get('trailingEps')
            book_value = info.get('bookValue')
            current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
            yf_pe, yf_pb = _get_yfinance_pe_pb(t, normalized, years, trailing_eps, book_value, current_price)
        except Exception:
            pass

    # ── Select best data source ──
    if ak_pe:
        pe_history = ak_pe
        data_source = 'AKShare百度估值'
    elif fmp_pe:
        pe_history = fmp_pe
        data_source = 'FMP'
    elif yf_pe:
        pe_history = yf_pe
        data_source = 'yfinance'

    if ak_pb:
        pb_history = ak_pb
    elif fmp_pb:
        pb_history = fmp_pb
    elif yf_pb:
        pb_history = yf_pb

    if not data_source:
        data_source = 'N/A'

    # ── Calculate percentiles ──
    result = {
        'ticker': normalized,
        'years': years,
        'data_source': data_source,
    }

    # Determine current PE/PB
    current_pe = None
    current_pb = None

    if pe_history:
        current_pe = pe_history[-1]['value']  # latest data point
    if pb_history:
        current_pb = pb_history[-1]['value']

    for name, history, current_ratio in [
        ('pe', pe_history, current_pe),
        ('pb', pb_history, current_pb),
    ]:
        values = [p['value'] for p in history]

        if values and current_ratio and current_ratio > 0:
            percentile = float(np.sum(np.array(values) <= current_ratio) / len(values) * 100)
            result[f'{name}_history'] = _downsample(history, max_points=250)
            result[f'{name}_percentile'] = round(percentile, 1)
            result[f'{name}_stats'] = {
                'min': round(float(np.min(values)), 2),
                'max': round(float(np.max(values)), 2),
                'mean': round(float(np.mean(values)), 2),
                'median': round(float(np.median(values)), 2),
                'current': round(float(current_ratio), 2),
            }
        else:
            result[f'{name}_history'] = _downsample(history, max_points=250)
            result[f'{name}_percentile'] = None
            result[f'{name}_stats'] = None

    return result


# ────────────────────────────────────────────────────────────────
# Peer comparison
# ────────────────────────────────────────────────────────────────

def get_peer_comparison(ticker, apikey=''):
    """Get valuation comparison with industry peers."""
    normalized = _normalize_ticker(ticker)
    t = _get_yf_ticker(normalized)
    info = t.info

    current = {
        'ticker': normalized,
        'company_name': info.get('longName') or info.get('shortName', normalized),
        'trailing_pe': info.get('trailingPE'),
        'forward_pe': info.get('forwardPE'),
        'price_to_book': info.get('priceToBook'),
        'ev_to_ebitda': info.get('enterpriseToEbitda'),
        'market_cap': info.get('marketCap', 0),
        'profit_margins': info.get('profitMargins'),
        'return_on_equity': info.get('returnOnEquity'),
    }

    industry = info.get('industry', '')
    sector = info.get('sector', '')
    peers = []

    return {
        'ticker': normalized,
        'current': current,
        'industry': industry,
        'sector': sector,
        'peers': peers,
    }
