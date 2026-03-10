#!/usr/bin/env python3
# Copyright (c) 2025 Alan He. Licensed under MIT.
"""ValueScope Valuation History Viewer.

Usage:
    streamlit run viewer.py
    # or via alias: valuescope-view
"""

import json
import os
import re
import sqlite3
import threading
import time as _time_mod
from io import StringIO

import pandas as pd
import streamlit as st
import streamlit.components.v1 as _components

try:
    import markdown as _md
    _HAS_MD = True
except ImportError:
    _HAS_MD = False

st.set_page_config(page_title="ValueScope History", page_icon="📊", layout="wide")
DB_PATH = os.environ.get('VS_DB_PATH', os.path.join(os.path.dirname(__file__), 'valuations.db'))

def _delete_record(row_id):
    """Delete a valuation record by ID."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM valuations WHERE id = ?", (int(row_id),))
            conn.commit()
        st.cache_data.clear()
        _rt_cache.clear()
        _fx_cache.clear()
    except Exception as e:
        st.error(f"Failed to delete record: {e}")


# ────────────────────────────────────────
# Database
# ────────────────────────────────────────

def _query(sql, params=()):
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn, params=params)

@st.cache_data(ttl=5, show_spinner=False)
def _get_filter_options():
    with sqlite3.connect(DB_PATH) as conn:
        modes = [r[0] for r in conn.execute("SELECT DISTINCT mode FROM valuations").fetchall()]
        engines = [r[0] for r in conn.execute(
            "SELECT DISTINCT ai_engine FROM valuations WHERE ai_engine IS NOT NULL").fetchall()]
    return modes, engines

@st.cache_data(ttl=5, show_spinner=False)
def search_valuations(search='', modes=None, engines=None, date_start=None, date_end=None):
    sql = """SELECT id, ticker, company_name, valuation_date, mode, ai_engine, source,
               currency, reported_currency,
               price_per_share, gap_dcf_price, market_price, gap_market_price, gap_pct,
               gap_adjusted_price, gap_adjusted_price_reporting, forex_rate,
               revenue_growth_1, revenue_growth_2, ebit_margin, wacc, base_year, ttm_label
        FROM valuations WHERE 1=1"""
    params = []
    if search:
        sql += " AND (company_name LIKE ? OR ticker LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    if modes:
        sql += f" AND mode IN ({','.join('?' * len(modes))})"
        params += list(modes)
    if engines:
        # Don't exclude manual-mode records (ai_engine IS NULL)
        sql += f" AND (ai_engine IN ({','.join('?' * len(engines))}) OR ai_engine IS NULL)"
        params += list(engines)
    if date_start:
        sql += " AND valuation_date >= ?"; params.append(str(date_start))
    if date_end:
        sql += " AND valuation_date <= ?"; params.append(str(date_end))
    sql += " ORDER BY valuation_date DESC, company_name"
    return _query(sql, params)

def get_valuation_detail(row_id):
    return _query("SELECT * FROM valuations WHERE id = ?", (row_id,))

@st.cache_data(ttl=5, show_spinner=False)
def _get_all_details(ids):
    """Batch-fetch all detail rows in a single query."""
    if not ids:
        return {}
    placeholders = ','.join('?' * len(ids))
    df = _query(f"SELECT * FROM valuations WHERE id IN ({placeholders})", ids)
    return {r['id']: r for _, r in df.iterrows()}


# ────────────────────────────────────────
# Formatting
# ────────────────────────────────────────

def _v(val):
    return val is not None and not (isinstance(val, float) and pd.isna(val))

def _fmt_amount(val):
    return f"{val:,.0f}" if _v(val) else "—"

def _fmt_price(val):
    return f"{val:,.2f}" if _v(val) else "—"

def _fmt_pct(val):
    return f"{val:.1f}%" if _v(val) else "—"

def _fmt_ratio(val):
    return f"{val:.2f}" if _v(val) else "—"

def _display_price(row):
    pps = row.get('price_per_share')
    if _v(pps) and pps: return pps
    dcf = row.get('gap_dcf_price')
    if _v(dcf) and dcf: return dcf
    return None

_rt_cache = {}   # {ticker: (price, currency, timestamp)}
_RT_TTL = 300    # 5 minutes

def _fetch_current_price(ticker):
    """Fetch real-time market price via yfinance. Module-level cache, 5 min TTL."""
    if not ticker:
        return None, None
    cached = _rt_cache.get(ticker)
    if cached and (_time_mod.time() - cached[2]) < _RT_TTL:
        return cached[0], cached[1]
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        price = fi.last_price
        currency = fi.currency
        result = (float(price), currency) if price and price > 0 else (None, None)
    except Exception:
        result = (None, None)
    _rt_cache[ticker] = (result[0], result[1], _time_mod.time())
    return result

def _effective_market_price(row):
    """Best available market price: prefer market_price, fall back to gap_market_price."""
    mp = row.get('market_price')
    if _v(mp) and mp: return mp
    gmp = row.get('gap_market_price')
    if _v(gmp) and gmp: return gmp
    return None


_fx_cache = {}   # {(from, to): (rate, timestamp)}
_FX_TTL = 3600   # 1 hour

def _fetch_forex_rate(from_cur, to_cur):
    """Fetch forex rate via yfinance. Module-level cache, 1 hour TTL."""
    if not from_cur or not to_cur or from_cur == to_cur:
        return None
    key = (from_cur, to_cur)
    cached = _fx_cache.get(key)
    if cached and (_time_mod.time() - cached[1]) < _FX_TTL:
        return cached[0]
    try:
        import yfinance as yf
        pair = f"{from_cur}{to_cur}=X"
        rate = yf.Ticker(pair).fast_info.last_price
        result = float(rate) if rate and rate > 0 else None
    except Exception:
        result = None
    _fx_cache[key] = (result, _time_mod.time())
    return result

# Background prefetch: forex rates + current prices for all tickers in DB.
# Runs once at startup so searches hit warm cache.
def _prefetch_market_data():
    _fetch_forex_rate('CNY', 'HKD')
    _fetch_forex_rate('CNY', 'USD')
    try:
        with sqlite3.connect(DB_PATH) as conn:
            tickers = [r[0] for r in conn.execute(
                "SELECT DISTINCT ticker FROM valuations WHERE ticker IS NOT NULL AND ticker != ''"
            ).fetchall()]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(len(tickers), 4) or 1) as pool:
            pool.map(_fetch_current_price, tickers)
    except Exception:
        pass

if 'market_data_prefetched' not in st.session_state:
    st.session_state.market_data_prefetched = True
    threading.Thread(target=_prefetch_market_data, daemon=True).start()


# ────────────────────────────────────────
# Rendering: Historical Financials (web_app.py style)
# ────────────────────────────────────────

SECTION_HEADERS = {'Profitability', 'Capital Structure', 'Returns', 'Dividends'}
AMOUNT_ROWS = {'Revenue', 'EBIT', '(+) Capital Expenditure', '(-) D&A',
               '(+) ΔWorking Capital', 'Total Reinvestment',
               '(+) Total Debt', '(+) Total Equity', 'Minority Interest',
               '(-) Cash & Equivalents', '(-) Total Investments', 'Invested Capital'}
RATIO_ROWS = {'Revenue Growth (%)', 'EBIT Growth (%)', 'EBIT Margin (%)', 'Tax Rate (%)',
              'Revenue / IC', 'Debt to Assets (%)', 'Cost of Debt (%)',
              'ROIC (%)', 'ROE (%)', 'Dividend Yield (%)', 'Payout Ratio (%)'}

def _render_financial_table(summary_json):
    if not summary_json: return None
    try:
        df = pd.read_json(StringIO(summary_json))
    except Exception:
        return None
    cols = list(df.columns)
    reported_currency = ''
    if 'Reported Currency' in df.index:
        rc = df.loc['Reported Currency'].dropna().unique()
        rc = [v for v in rc if v and str(v).strip()]
        if rc: reported_currency = str(rc[0])

    html = '<div style="overflow-x:auto;"><table class="fin-table"><thead><tr><th></th>'
    for c in cols: html += f'<th>{c}</th>'
    html += '</tr></thead><tbody>'
    if reported_currency:
        html += f'<tr class="currency-row"><td>Reported Currency</td>'
        for _ in cols: html += f'<td>{reported_currency}</td>'
        html += '</tr>'
    for idx in df.index:
        if idx == 'Reported Currency': continue
        row_vals = df.loc[idx]
        if idx in SECTION_HEADERS:
            html += f'<tr class="section-row"><td colspan="{len(cols)+1}">► {idx}</td></tr>'
            continue
        is_amount = idx in AMOUNT_ROWS
        is_ratio = idx in RATIO_ROWS
        row_class = 'amount-row' if is_amount else ('ratio-row' if is_ratio else '')
        html += f'<tr class="{row_class}"><td>{idx}</td>'
        for c in cols:
            raw = row_vals[c]
            if pd.isna(raw) or raw == '' or raw is None:
                html += '<td>—</td>'
            elif is_amount:
                try: html += f'<td>{int(float(raw)):,}</td>'
                except Exception: html += f'<td>{raw}</td>'
            elif is_ratio:
                try: html += f'<td>{float(raw):.1f}</td>'
                except Exception: html += f'<td>{raw}</td>'
            else:
                html += f'<td>{raw}</td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    return html


# ────────────────────────────────────────
# Rendering: DCF Forecast Table (web_app.py style)
# ────────────────────────────────────────

def _render_dcf_table(dcf_table_json, ttm_label='', base_year=None):
    if not dcf_table_json: return None
    try:
        dcf = pd.read_json(StringIO(dcf_table_json))
    except Exception:
        return None

    if ttm_label:
        base_label = f'Base ({ttm_label})'
    elif base_year:
        base_label = f'Base ({int(base_year)})'
    else:
        base_label = 'Base Year'
    year_labels = [base_label] + [str(i) for i in range(1, 11)] + ['Terminal']
    if len(dcf) < len(year_labels):
        year_labels = year_labels[:len(dcf)]

    fields = [
        ('Revenue Growth Rate', 'Revenue Growth Rate', 'pct'),
        ('Revenue', 'Revenue', 'amount'),
        ('EBIT Margin', 'EBIT Margin', 'pct'),
        ('EBIT', 'EBIT', 'amount'),
        ('Tax Rate', 'Tax to EBIT', 'pct'),
        ('EBIT(1-t)', 'EBIT(1-t)', 'amount'),
        ('Reinvestments', 'Reinvestments', 'amount'),
        ('FCFF', 'FCFF', 'amount'),
        ('WACC', 'WACC', 'pct'),
        ('Discount Factor', 'Discount Factor', 'factor'),
        ('PV (FCFF)', 'PV (FCFF)', 'amount'),
    ]

    html = '<div style="overflow-x:auto;"><table class="dcf-table"><thead><tr><th></th>'
    for i, lbl in enumerate(year_labels):
        cls = ' class="base-col"' if i == 0 else (' class="terminal-col"' if i == len(year_labels)-1 else '')
        html += f'<th{cls}>{lbl}</th>'
    html += '</tr></thead><tbody>'

    for display_name, col_name, fmt in fields:
        if col_name not in dcf.columns: continue
        html += f'<tr><td>{display_name}</td>'
        for i in range(len(year_labels)):
            val = dcf.iloc[i][col_name] if i < len(dcf) else None
            cls = ' class="base-col"' if i == 0 else (' class="terminal-col"' if i == len(year_labels)-1 else '')
            if val is None or (isinstance(val, float) and pd.isna(val)):
                html += f'<td{cls}>—</td>'
            elif fmt == 'pct':
                html += f'<td{cls}>{val:.1%}</td>'
            elif fmt == 'amount':
                html += f'<td{cls}>{val:,.0f}</td>'
            elif fmt == 'factor':
                html += f'<td{cls}>{val:.3f}</td>'
            else:
                html += f'<td{cls}>{val}</td>'
        html += '</tr>'
    html += '</tbody></table></div>'
    return html


# ────────────────────────────────────────
# Rendering: Valuation Breakdown (web_app.py style)
# ────────────────────────────────────────

def _render_valuation_breakdown(d, forex_rate=None):
    pps = d.get('price_per_share')          # always in reported_currency
    gap_dcf = d.get('gap_dcf_price')        # in trading currency (if gap analysis done)
    reported_cur = d.get('reported_currency') or ''
    stock_cur = d.get('currency') or ''
    _dual = (stock_cur and reported_cur and stock_cur != reported_cur)

    # Outstanding shares: stored as actual count, display in millions
    shares_raw = d.get('outstanding_shares')
    shares_m = shares_raw / 1e6 if _v(shares_raw) and shares_raw else None

    # The breakdown amounts (pv, ev, etc.) are all in reported_currency
    # price_per_share is the raw DCF result in reported_currency
    iv_reporting = pps if _v(pps) else None
    cur_label = f" ({reported_cur})" if reported_cur else ""

    rows = [
        ("PV of FCFF (10 years)", _fmt_amount(d.get('pv_cf_10yr')), False, False),
        ("PV of Terminal Value", _fmt_amount(d.get('pv_terminal')), False, False),
        ("Sum of Present Values", _fmt_amount(
            (d['pv_cf_10yr'] or 0) + (d['pv_terminal'] or 0)
            if _v(d.get('pv_cf_10yr')) and _v(d.get('pv_terminal')) else None
        ), True, False),
        ("+ Cash & Equivalents", _fmt_amount(d.get('cash')), False, False),
        ("+ Total Investments", _fmt_amount(d.get('total_investments')), False, False),
        ("Enterprise Value", _fmt_amount(d.get('enterprise_value')), True, False),
        ("- Total Debt", _fmt_amount(d.get('total_debt')), False, False),
        ("- Minority Interest", _fmt_amount(d.get('minority_interest')), False, False),
        ("Equity Value", _fmt_amount(d.get('equity_value')), True, False),
        ("Outstanding Shares (M)", _fmt_amount(shares_m), False, False),
        (f"Intrinsic Value Per Share{cur_label}",
         _fmt_price(iv_reporting), False, True),
    ]

    # Dual currency: add trading-currency IV line
    if _dual:
        if _v(gap_dcf) and gap_dcf:
            # Historical gap_dcf_price is the authoritative trading-currency IV
            fx_str = ''
            if _v(iv_reporting) and iv_reporting and iv_reporting > 0:
                implied_fx = gap_dcf / iv_reporting
                fx_str = f'  (× {implied_fx:.4f})'
            rows.append((
                f"Intrinsic Value Per Share ({stock_cur})",
                f"{gap_dcf:,.2f}{fx_str}", False, True))
        elif _v(iv_reporting) and iv_reporting and forex_rate and forex_rate > 0:
            # No gap analysis — convert using provided forex rate
            converted = iv_reporting * forex_rate
            rows.append((
                f"Intrinsic Value Per Share ({stock_cur})",
                f"{converted:,.2f}  (× {forex_rate:.4f})", False, True))

    html = '<div class="val-breakdown">'
    for label, value, is_sub, is_hl in rows:
        cls = 'highlight' if is_hl else ('subtotal' if is_sub else '')
        html += f'<div class="row {cls}"><span>{label}</span><span>{value}</span></div>'
    html += '</div>'
    return html


# ────────────────────────────────────────
# Rendering: Sensitivity Tables (web_app.py style)
# ────────────────────────────────────────

def _render_sensitivity_table(sens_json, base_growth, base_margin):
    if not sens_json: return None
    try: data = json.loads(sens_json)
    except Exception: return None
    growth_keys = sorted(data.keys(), key=lambda x: float(x), reverse=True)
    if not growth_keys: return None
    margin_keys = sorted(data[growth_keys[0]].keys(), key=lambda x: float(x))

    html = '<div style="overflow-x:auto;"><table class="sens-table">'
    # Header: axis label + EBIT Margin column headers
    html += f'<tr><th class="sens-axis-label" style="border-bottom:2px solid var(--vx-border);">EBIT Margin →<br><span style="font-style:normal;">Rev Growth ↓</span></th>'
    for m in margin_keys:
        mf = float(m)
        hl = ' sens-hl-col' if abs(mf - base_margin) < 0.01 else ''
        html += f'<th class="{hl}">{int(mf)}%</th>'
    html += '</tr>'
    for g in growth_keys:
        gf = float(g)
        is_base_row = abs(gf - base_growth) < 0.01
        html += '<tr>'
        html += f'<td class="{"sens-hl-row-label" if is_base_row else ""}">{int(gf)}%</td>'
        for m in margin_keys:
            mf = float(m)
            val = data[g].get(m, 0)
            is_base_col = abs(mf - base_margin) < 0.01
            if is_base_row and is_base_col: cls = 'sens-hl-center'
            elif is_base_row or is_base_col: cls = 'sens-hl-cross'
            else: cls = ''
            html += f'<td class="{cls}">{float(val):,.0f}</td>'
        html += '</tr>'
    html += '</table></div>'
    return html

def _render_wacc_sensitivity(wacc_json, wacc_base):
    if not wacc_json: return None
    try: data = json.loads(wacc_json)
    except Exception: return None
    wacc_keys = sorted(data.keys(), key=lambda x: float(x))
    html = '<div style="overflow-x:auto;"><table class="wacc-sens-table">'
    # Header: WACC values
    html += f'<tr><td class="wacc-label">WACC</td>'
    for w in wacc_keys:
        wf = float(w)
        hl = ' sens-hl-col' if _v(wacc_base) and abs(wf - wacc_base) < 0.01 else ''
        html += f'<th class="{hl}">{wf:.1f}%</th>'
    html += '</tr>'
    # Values row
    html += f'<tr><td class="wacc-label">Price / Share</td>'
    for w in wacc_keys:
        wf = float(w)
        is_base = _v(wacc_base) and abs(wf - wacc_base) < 0.01
        cls = ' class="sens-hl-center"' if is_base else ''
        html += f'<td{cls}>{float(data[w]):,.0f}</td>'
    html += '</tr></table></div>'
    return html


# ────────────────────────────────────────
# Rendering: AI Reasoning (web_app.py style)
# ────────────────────────────────────────

def _render_ai_reasoning(ai_params_json):
    if not ai_params_json: return None
    try: params = json.loads(ai_params_json)
    except Exception: return None
    LABELS = {
        'revenue_growth_1': 'Year 1 Revenue Growth',
        'revenue_growth_2': 'Years 2-5 Revenue CAGR',
        'ebit_margin': 'Target EBIT Margin',
        'convergence': 'Margin Convergence Period',
        'revenue_invested_capital_ratio_1': 'Revenue/IC Ratio (Y1-2)',
        'revenue_invested_capital_ratio_2': 'Revenue/IC Ratio (Y3-5)',
        'revenue_invested_capital_ratio_3': 'Revenue/IC Ratio (Y5-10)',
        'tax_rate': 'Effective Tax Rate',
        'wacc': 'WACC',
        'ronic_match_wacc': 'RONIC = WACC?',
    }
    sections = []
    for key, label in LABELS.items():
        p = params.get(key)
        if not isinstance(p, dict): continue
        reasoning = p.get('reasoning', '')
        if not reasoning: continue
        val = p.get('value', '')
        val_str = ('Yes' if val else 'No') if isinstance(val, bool) else str(val)
        sections.append(f"**{label}** → `{val_str}`\n\n{reasoning}")
    return '\n\n---\n\n'.join(sections) if sections else None


def _render_gap_analysis(gap_text):
    if not gap_text: return None
    text = re.sub(r'\n?\s*ADJUSTED_PRICE:.*$', '', gap_text).strip()
    if _HAS_MD:
        return _md.markdown(text, extensions=['tables'])
    return text


# ────────────────────────────────────────
# CSS — copied from web_app.py for consistency
# ────────────────────────────────────────

st.markdown("""
<style>
    /* ── Theme variables (matching web_app.py) ── */
    :root {
        --vx-bg:            #ffffff;
        --vx-bg-secondary:  #f6f8fa;
        --vx-text:          #1f2328;
        --vx-text-secondary:#656d76;
        --vx-text-muted:    #8b949e;
        --vx-border:        #d0d7de;
        --vx-border-light:  #e8ebef;
        --vx-accent:        #0969da;
        --vx-accent-light:  rgba(9,105,218,0.08);
        --vx-table-header:  #0550ae;
        --vx-table-border:  #e8ebef;
        --vx-ai-card-bg:    #f6f8fa;
        --vx-wacc-item-bg:  #f6f8fa;
        --vx-green:         #1a7f37;
        --vx-red:           #cf222e;
        --vx-intrinsic:     #0550ae;
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --vx-bg:            #1a1b26;
            --vx-bg-secondary:  #161b22;
            --vx-text:          #e0e0e0;
            --vx-text-secondary:#c9d1d9;
            --vx-text-muted:    #8b949e;
            --vx-border:        #30363d;
            --vx-border-light:  #21262d;
            --vx-accent:        #58a6ff;
            --vx-accent-light:  rgba(88,166,255,0.08);
            --vx-table-header:  #7ec8e3;
            --vx-table-border:  #1a1a2e;
            --vx-ai-card-bg:    #14151f;
            --vx-wacc-item-bg:  #161b22;
            --vx-green:         #2ecc71;
            --vx-red:           #e74c3c;
            --vx-intrinsic:     #58a6ff;
        }
    }

    /* ── Page header ── */
    .main-title { font-size: 1.6rem; font-weight: 700; margin-bottom: 0.3rem; }

    /* ── Reduce Streamlit default top padding ── */
    .stMainBlockContainer { padding-top: 1.5rem !important; }
    header[data-testid="stHeader"] { display: none !important; }

    /* ── Sticky header: title + filters + count ── */
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(.main-title) {
        position: sticky; top: 0; z-index: 999;
        background: var(--vx-bg);
    }
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:nth-child(3) {
        position: sticky; top: 38px; z-index: 998;
        background: var(--vx-bg); padding-bottom: 2px;
    }
    /* scroll offset so expanded cards land below sticky header */
    div[data-testid="stExpander"] { border: 1px solid var(--vx-border); border-radius: 8px; margin-bottom: 8px; transition: box-shadow 0.2s ease, border-color 0.2s ease; scroll-margin-top: 160px; }
    div[data-testid="stExpander"]:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-color: var(--vx-accent); }

    /* ── Section headers (web_app.py) ── */
    .section-hdr {
        font-size: 1.2rem; font-weight: 700; color: var(--vx-text);
        border-bottom: 1px solid var(--vx-border-light); padding-bottom: 6px;
        margin: 1.8rem 0 0.8rem 0; letter-spacing: 0.2px;
        position: relative; padding-left: 12px;
    }
    .section-hdr::before {
        content: ''; position: absolute; left: 0; top: 4px; bottom: 4px; width: 3px;
        background: linear-gradient(180deg, var(--vx-accent) 0%, color-mix(in srgb, var(--vx-accent) 40%, transparent) 100%);
        border-radius: 2px;
    }

    /* ── Financial table (web_app.py) ── */
    .fin-table {
        width: 100%; border-collapse: collapse; font-size: 13px;
        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    }
    .fin-table th {
        text-align: right; padding: 3px 10px; color: var(--vx-table-header);
        font-weight: 600; border-bottom: 1px solid var(--vx-border); white-space: nowrap;
    }
    .fin-table th:first-child { text-align: left; }
    .fin-table td {
        text-align: right; padding: 3px 10px; border-bottom: 1px solid var(--vx-table-border);
        white-space: nowrap; color: var(--vx-text);
    }
    .fin-table td:first-child { text-align: left; font-weight: 500; }
    .fin-table .section-row td {
        font-weight: 700; color: var(--vx-table-header); padding-top: 10px;
        border-bottom: none; font-size: 12px;
    }
    .fin-table .amount-row td:not(:first-child) { color: var(--vx-text); }
    .fin-table .ratio-row td:not(:first-child) { color: var(--vx-text-secondary); }
    .fin-table .currency-row td {
        color: var(--vx-text-muted); font-size: 12px; font-style: italic;
    }

    /* ── DCF table (web_app.py) ── */
    .dcf-table {
        width: 100%; border-collapse: collapse; font-size: 12.5px;
        font-family: 'SF Mono', monospace; overflow-x: auto;
    }
    .dcf-table th {
        padding: 4px 8px; color: var(--vx-table-header); border-bottom: 2px solid var(--vx-border);
        white-space: nowrap; font-weight: 600; text-align: right;
    }
    .dcf-table th:first-child { text-align: left; }
    .dcf-table td {
        padding: 3px 8px; border-bottom: 1px solid var(--vx-table-border); text-align: right;
        white-space: nowrap; color: var(--vx-text);
    }
    .dcf-table td:first-child { text-align: left; color: var(--vx-text-secondary); }
    .dcf-table .base-col { background: color-mix(in srgb, var(--vx-accent) 6%, transparent); }
    .dcf-table .terminal-col { background: color-mix(in srgb, var(--vx-accent) 4%, transparent); }

    /* ── Valuation breakdown (web_app.py) ── */
    .val-breakdown {
        font-size: 14px; font-family: 'SF Mono', monospace; color: var(--vx-text);
    }
    .val-breakdown .row {
        display: flex; justify-content: space-between; padding: 5px 0;
        border-bottom: 1px solid var(--vx-table-border);
    }
    .val-breakdown .row.highlight {
        font-weight: 700; color: var(--vx-green); border-top: 2px solid var(--vx-border);
        padding-top: 10px; font-size: 15px;
    }
    .val-breakdown .row.subtotal { font-weight: 600; color: var(--vx-accent); }

    /* ── Sensitivity tables (web_app.py) ── */
    .sens-table {
        width: 100%; border-collapse: collapse; font-size: 13px;
        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    }
    .sens-table th {
        padding: 4px 8px; color: var(--vx-text-muted); font-weight: 600;
        border-bottom: 2px solid var(--vx-border); text-align: right; white-space: nowrap;
    }
    .sens-table th:first-child { text-align: right; color: var(--vx-text-muted); font-weight: 400; }
    .sens-table td {
        padding: 4px 8px; text-align: right; border-bottom: 1px solid var(--vx-table-border);
        white-space: nowrap; color: var(--vx-text-secondary);
    }
    .sens-table td:first-child { text-align: right; color: var(--vx-text-muted); font-weight: 500; }
    .sens-table th.sens-hl-col { color: var(--vx-table-header); font-weight: 700; }
    .sens-table td.sens-hl-row-label { color: var(--vx-table-header); font-weight: 700; }
    .sens-table td.sens-hl-cross {
        color: var(--vx-table-header);
        background: color-mix(in srgb, var(--vx-accent) 6%, transparent);
    }
    .sens-table td.sens-hl-center {
        color: var(--vx-green); font-weight: 800;
        background: color-mix(in srgb, var(--vx-green) 10%, transparent); font-size: 14px;
    }
    .sens-table .sens-axis-label { color: var(--vx-text-muted); font-size: 11px; font-style: italic; }

    .wacc-sens-table {
        width: 100%; border-collapse: collapse; font-size: 13px;
        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; text-align: center;
    }
    .wacc-sens-table th {
        padding: 5px 6px; color: var(--vx-text-muted); font-weight: 600;
        border-bottom: 2px solid var(--vx-border);
    }
    .wacc-sens-table td {
        padding: 5px 6px; color: var(--vx-text-secondary);
        border-bottom: 1px solid var(--vx-table-border);
    }
    .wacc-sens-table th.sens-hl-col { color: var(--vx-table-header); font-weight: 700; }
    .wacc-sens-table td.sens-hl-center {
        color: var(--vx-green); font-weight: 800;
        background: color-mix(in srgb, var(--vx-green) 10%, transparent); font-size: 14px;
    }
    .wacc-sens-table td.wacc-label {
        color: var(--vx-text-muted); font-size: 11px; font-style: italic;
        text-align: left; white-space: nowrap;
    }

    /* ── AI card (web_app.py) ── */
    .ai-card {
        background: var(--vx-ai-card-bg); border: 1px solid var(--vx-border);
        border-radius: 8px; padding: 20px 24px; margin: 8px 0; line-height: 1.7;
        transition: box-shadow 0.2s ease;
    }
    .ai-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
    .ai-card h1 { font-size: 1.1rem !important; font-weight: 700; margin: 0 0 12px 0; }
    .ai-card h2 { font-size: 1.0rem !important; font-weight: 700; margin: 16px 0 8px 0; }
    .ai-card h3 { font-size: 0.95rem !important; font-weight: 600; margin: 12px 0 6px 0; }
    .ai-card h4 { font-size: 0.9rem !important; font-weight: 600; margin: 10px 0 4px 0; }
    .ai-card p, .ai-card li { font-size: 0.88rem; }
    .ai-card a { color: var(--vx-accent); text-decoration: none; }
    .ai-card a:hover { text-decoration: underline; }
    .ai-card ul, .ai-card ol { margin: 6px 0; padding-left: 1.5em; }
    .ai-card table {
        border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.85rem;
    }
    .ai-card th, .ai-card td {
        border: 1px solid var(--vx-border); padding: 6px 10px; text-align: left;
    }
    .ai-card th { background: var(--vx-bg-secondary); font-weight: 600; }

    /* ── Gap summary bar ── */
    .gap-bar { display: flex; align-items: center; gap: 16px;
        padding: 10px 16px; border-radius: 8px; margin-bottom: 12px;
        background: var(--vx-bg-secondary); border: 1px solid var(--vx-border);
        font-family: 'SF Mono', monospace; font-size: 14px; }
    .gap-bar .label { color: var(--vx-text-muted); font-size: 12px; }
    .gap-bar .val { font-weight: 700; }
    .gap-bar .positive { color: var(--vx-green); }
    .gap-bar .negative { color: var(--vx-red); }

    /* ── Hover effects (web_app.py) ── */
    .fin-table tbody tr:hover td { background: color-mix(in srgb, var(--vx-accent) 4%, transparent); }
    .dcf-table tbody tr:hover td { background: color-mix(in srgb, var(--vx-accent) 4%, transparent); }
    .sens-table tbody tr:hover td { background: color-mix(in srgb, var(--vx-accent) 3%, transparent); }
    .val-breakdown .row:hover {
        background: color-mix(in srgb, var(--vx-accent) 3%, transparent); border-radius: 4px;
    }

    /* ── Animations (web_app.py) ── */
    @keyframes fadeSlideIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .section-hdr { animation: fadeSlideIn 0.3s ease-out; }
    .sens-table, .wacc-sens-table { animation: fadeSlideIn 0.3s ease-out; }
    .val-breakdown { animation: fadeSlideIn 0.3s ease-out; }

    /* ── Latest Assessment ── */
    .latest-box {
        display: flex; align-items: flex-start; gap: 28px; flex-wrap: wrap;
        padding: 14px 20px; border-radius: 8px; margin: 8px 0 12px 0;
        background: var(--vx-bg-secondary); border: 1px solid var(--vx-border);
        border-left: 4px solid var(--vx-border);
        font-family: 'SF Mono', monospace; animation: fadeSlideIn 0.3s ease-out;
    }
    .latest-box.undervalued { border-left: 4px solid var(--vx-green); }
    .latest-box.overvalued  { border-left: 4px solid var(--vx-red); }
    .latest-box .lbl { color: var(--vx-text-muted); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }
    .latest-box .val { font-weight: 700; font-size: 18px; margin-top: 2px; }
    .latest-box .positive { color: var(--vx-green); }
    .latest-box .negative { color: var(--vx-red); }
</style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────
# Header
# ────────────────────────────────────────

st.markdown('<div class="main-title">📊 ValueScope Valuation History</div>', unsafe_allow_html=True)

if not os.path.exists(DB_PATH):
    st.error(f"Database not found: {DB_PATH}")
    st.stop()


# ────────────────────────────────────────
# Search & Filters
# ────────────────────────────────────────

all_modes, all_engines = _get_filter_options()
col_search, col_mode, col_engine, col_d1, col_d2 = st.columns([4, 2, 2, 2, 2])
with col_search:
    _default_search = st.query_params.get("search", "")
    search_query = st.text_input("🔍 Search", value=_default_search,
                                  placeholder="e.g. Tencent, NYT",
                                  key="search_box")
with col_mode:
    selected_modes = st.multiselect("Mode", all_modes, default=[])
with col_engine:
    selected_engines = st.multiselect("AI Engine", all_engines, default=[])
with col_d1:
    date_start = st.date_input("From", value=None)
with col_d2:
    date_end = st.date_input("To", value=None)

# Auto-submit search when input is cleared (Streamlit only commits on Enter/blur).
# Inject a persistent script into the parent document (survives Streamlit reruns).
# MutationObserver re-attaches listeners and refocuses after each rerun.
_components.html("""<script>
(function(){
    var p = window.parent;
    if (p._vxSetup) return;
    p._vxSetup = true;
    var s = p.document.createElement('script');
    s.textContent = '(' + function(){
        var SEL = 'input[aria-label="\\ud83d\\udd0d Search"]';
        function attach() {
            var inp = document.querySelector(SEL);
            if (!inp || inp._vxBound) return;
            inp._vxBound = true;
            inp.addEventListener('input', function() {
                if (this.value === '') {
                    window._vxRefocus = true;
                    var el = this;
                    setTimeout(function(){ el.blur(); }, 150);
                }
            });
        }
        attach();
        new MutationObserver(function() {
            attach();
            if (window._vxRefocus) {
                var inp = document.querySelector(SEL);
                if (inp) { window._vxRefocus = false; inp.focus(); }
            }
        }).observe(document.body, { childList: true, subtree: true });
    }.toString() + ')();';
    p.document.head.appendChild(s);
})();
</script>""", height=0)

df = search_valuations(search_query, tuple(selected_modes) if selected_modes else None,
                       tuple(selected_engines) if selected_engines else None,
                       date_start, date_end)
if df.empty:
    st.info("No valuations found. Try a different search or adjust filters.")
    st.stop()


# ────────────────────────────────────────
# Valuation Overview
# ────────────────────────────────────────

# If all results are for a single company, show latest assessment summary
unique_companies = df['company_name'].unique()
if len(unique_companies) == 1:
    latest = df.iloc[0]  # already sorted DESC
    cname = latest['company_name']
    _ticker = latest.get('ticker') or ''
    ticker_str = f" ({_ticker})" if _ticker else ""
    dcf_raw = _display_price(latest)
    rep_cur = latest.get('reported_currency') or ''
    stk_cur = latest.get('currency') or ''

    # Reporting-currency IV: prefer gap_adjusted_price_reporting, fall back to price_per_share
    # Both are always in reporting currency. Do NOT use gap_adjusted_price (may be trading currency).
    adj_rep = latest.get('gap_adjusted_price_reporting')
    if _v(adj_rep) and adj_rep:
        iv_rep = adj_rep; _has_adj = True
    else:
        _pps = latest.get('price_per_share')
        iv_rep = _pps if _v(_pps) and _pps else None
        _has_adj = False
    _panel_label = "Adjusted Intrinsic Value" if _has_adj else "Intrinsic Value"

    # Fetch real-time market price (in trading currency)
    rt_price, rt_cur = _fetch_current_price(_ticker) if _ticker else (None, None)
    mkt_cur = rt_cur or stk_cur or rep_cur or ''

    # Trading-currency value: prefer adjusted, otherwise convert
    _needs_fx = (rep_cur and mkt_cur and rep_cur != mkt_cur)
    _panel_fx = None
    if _needs_fx:
        _panel_fx = _fetch_forex_rate(rep_cur, mkt_cur)
    adj_trade = latest.get('gap_adjusted_price')  # in trading currency
    if _v(adj_trade) and adj_trade:
        iv_trade = adj_trade
    elif _v(iv_rep) and iv_rep and iv_rep > 0 and _panel_fx and _panel_fx > 0:
        iv_trade = iv_rep * _panel_fx
    else:
        iv_trade = None

    # Determine box class based on valuation gap
    box_cls = ''
    _gap_pct = None
    _cmp_val = iv_trade if _needs_fx else iv_rep  # compare in trading currency
    if _v(_cmp_val) and _cmp_val > 0 and rt_price:
        _gap_pct = (_cmp_val - rt_price) / rt_price * 100
        box_cls = ' undervalued' if _gap_pct > 0 else ' overvalued'

    html = f'<div class="latest-box{box_cls}">'
    html += f'<div><span class="lbl">Company</span><div class="val">{cname}{ticker_str}</div></div>'
    html += f'<div><span class="lbl">Latest Valuation</span><div class="val">{latest["valuation_date"]}</div></div>'
    if _v(iv_rep):
        html += f'<div><span class="lbl">{_panel_label} ({rep_cur or mkt_cur})</span><div class="val">{iv_rep:,.2f}</div></div>'
    if _needs_fx and _v(iv_trade):
        html += f'<div><span class="lbl">{_panel_label} ({mkt_cur})</span><div class="val">{iv_trade:,.2f}</div></div>'
    if rt_price:
        html += f'<div><span class="lbl">Current Price ({mkt_cur})</span><div class="val">{rt_price:,.2f}</div></div>'
        if _gap_pct is not None:
            cls = 'positive' if _gap_pct > 0 else 'negative'
            label = 'Undervalued' if _gap_pct > 0 else 'Overvalued'
            html += f'<div><span class="lbl">DCF vs Market</span><div class="val {cls}">{_gap_pct:+.1f}% {label}</div></div>'
    elif not rt_price and _ticker:
        html += f'<div><span class="lbl">Current Price</span><div class="val">—</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)
    # Forex rate annotation below the panel
    if _needs_fx and _panel_fx:
        st.markdown(
            f'<div style="color:var(--vx-text-muted);font-size:0.78rem;margin:-6px 0 8px 0;">'
            f'* {rep_cur}/{mkt_cur} exchange rate: {_panel_fx:.4f} (real-time via yfinance)</div>',
            unsafe_allow_html=True)

# Overview table — rendered via components.html for clickable rows with JS
_ovr_css = """
<style>
    body { margin: 0; padding: 0; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
    .overview-table {
        width: 100%; border-collapse: collapse; font-size: 13px;
    }
    .overview-table th {
        text-align: right; padding: 6px 10px; color: #0550ae;
        font-weight: 600; border-bottom: 2px solid #d0d7de; white-space: nowrap;
    }
    .overview-table th:nth-child(-n+6) { text-align: left; }
    .overview-table td {
        text-align: right; padding: 5px 10px; border-bottom: 1px solid #e8ebef;
        white-space: nowrap; color: #1f2328;
    }
    .overview-table td:nth-child(-n+6) { text-align: left; }
    .ovr-row { cursor: pointer; }
    .ovr-row:hover td { background: rgba(9,105,218,0.06); }
    @media (prefers-color-scheme: dark) {
        body { background: transparent; }
        .overview-table th { color: #7ec8e3; border-bottom-color: #30363d; }
        .overview-table td { color: #e0e0e0; border-bottom-color: #1a1a2e; }
        .ovr-row:hover td { background: rgba(88,166,255,0.06); }
    }
</style>
"""

ovr = '<table class="overview-table"><thead><tr>'
ovr += '<th>Date</th><th>Company</th><th>Ticker</th><th>Mode</th><th>AI Engine</th>'
ovr += '<th>Reporting Currency</th><th>Intrinsic Value</th><th>Adjusted Intrinsic Value</th>'
ovr += '</tr></thead><tbody>'
for idx, (_, r) in enumerate(df.iterrows()):
    stk_cur = r.get('currency') or ''
    rep_cur_r = r.get('reported_currency') or ''
    _is_dual = (stk_cur and rep_cur_r and stk_cur != rep_cur_r)

    # Intrinsic Value — must be in reporting currency
    pps = r.get('price_per_share')
    gdcf = r.get('gap_dcf_price')
    if _v(pps) and pps:
        dcf_p = pps  # always in reporting currency
    elif _v(gdcf) and gdcf and not _is_dual:
        dcf_p = gdcf  # single-currency: gap_dcf_price == reporting currency
    else:
        dcf_p = None  # dual-currency but no price_per_share → can't show in reporting cur

    # Adjusted DCF Price — must be in reporting currency
    adj_rep = r.get('gap_adjusted_price_reporting')
    adj_trade = r.get('gap_adjusted_price')
    if _v(adj_rep) and adj_rep:
        adj_display = adj_rep
    elif _v(adj_trade) and adj_trade and not _is_dual:
        adj_display = adj_trade  # single-currency: already in reporting currency
    else:
        adj_display = None  # no gap analysis or can't convert
    tk = r.get('ticker') or '—'
    md = (r.get('mode') or '').upper()
    eng = r.get('ai_engine') or '—'
    rep_cur = rep_cur_r or '—'
    ovr += f'<tr class="ovr-row" data-idx="{idx}" onclick="ovrClick({idx})">'
    ovr += f'<td>{r["valuation_date"]}</td><td>{r["company_name"]}</td><td>{tk}</td><td>{md}</td><td>{eng}</td>'
    ovr += f'<td>{rep_cur}</td><td>{_fmt_price(dcf_p)}</td>'
    ovr += f'<td>{_fmt_price(adj_display)}</td></tr>'
ovr += '</tbody></table>'
ovr += f'<div style="color:#888;font-size:12px;margin-top:6px;">{len(df)} valuations found</div>'

_ovr_js = '''<script>
function ovrClick(idx) {
    const parentDoc = window.parent.document;
    const expanders = parentDoc.querySelectorAll('[data-testid="stExpander"]');
    if (!expanders[idx]) return;

    const target = expanders[idx].querySelector('details');
    const isOpen = target && target.open;

    // Collapse ALL open expanders first
    expanders.forEach(exp => {
        const d = exp.querySelector('details');
        if (d && d.open) {
            const s = d.querySelector('summary');
            if (s) s.click();
        }
    });

    if (!isOpen) {
        setTimeout(() => {
            expanders[idx].scrollIntoView({behavior:'smooth', block:'start'});
            setTimeout(() => {
                const d2 = expanders[idx].querySelector('details');
                if (d2 && !d2.open) {
                    const s2 = d2.querySelector('summary');
                    if (s2) s2.click();
                }
            }, 300);
        }, 100);
    }
}
</script>'''

_ovr_height = 38 + len(df) * 31 + 10  # header + rows + padding
_ovr_height = _ovr_height + 22  # account for the count line
_components.html(_ovr_css + ovr + _ovr_js, height=_ovr_height, scrolling=False)


# ────────────────────────────────────────
# Valuation Cards
# ────────────────────────────────────────

# Batch-fetch all detail data in one query (avoid N+1)
_detail_map = _get_all_details(tuple(df['id'].tolist()))

for _, row in df.iterrows():
    intrinsic_raw = row.get('price_per_share')  # always in reported_currency
    gap_dcf = row.get('gap_dcf_price')          # in trading currency (if gap analysis done)
    market = row.get('gap_market_price')         # in trading currency
    gap = row.get('gap_pct')
    adj = row.get('gap_adjusted_price')          # in trading currency
    engine_tag = f" · {row['ai_engine']}" if pd.notna(row.get('ai_engine')) else ""
    ticker_tag = f" ({row['ticker']})" if row.get('ticker') else ""
    reported_cur = row.get('reported_currency') or ''
    stock_cur = row.get('currency') or ''
    # Trading currency: if currency field is set and differs, gap values are in that currency
    _dual = (stock_cur and reported_cur and stock_cur != reported_cur)
    trading_cur = stock_cur if _dual else (reported_cur or stock_cur or '')
    ttm_tag = f" · {row['ttm_label']}" if row.get('ttm_label') else ""

    header = f"**{row['company_name']}**{ticker_tag}  ·  {row['valuation_date']}  ·  {row['mode'].upper()}{engine_tag}{ttm_tag}"

    with st.expander(header, expanded=False):
        # Key metrics
        if _dual:
            # Use stored forex_rate (historical, from valuation time).
            # Fallback to implied rate from gap_dcf_price / price_per_share.
            # Never use live rate — it wouldn't reflect historical data.
            _stored_fx = row.get('forex_rate')
            _card_fx = None
            if _v(_stored_fx) and _stored_fx > 0:
                _card_fx = _stored_fx  # stored at valuation time
            elif _v(intrinsic_raw) and intrinsic_raw > 0 and _v(gap_dcf) and gap_dcf > 0:
                _card_fx = gap_dcf / intrinsic_raw  # implied from gap analysis

            # Trading-currency IV: prefer gap_dcf_price, then stored forex conversion
            iv_trade = gap_dcf if _v(gap_dcf) else (
                intrinsic_raw * _card_fx if _v(intrinsic_raw) and intrinsic_raw and _card_fx else None)
            # Market price: prefer gap_market_price, fallback to market_price (from profile)
            mkt_display = market if _v(market) else row.get('market_price')

            # Dual currency: show reporting IV + trading IV, market/gap/adj in trading
            cols = st.columns(5)
            with cols[0]: st.metric(f"Intrinsic Value ({reported_cur})",
                                     _fmt_price(intrinsic_raw) if _v(intrinsic_raw) else "—")
            with cols[1]: st.metric(f"Intrinsic Value ({stock_cur})",
                                     _fmt_price(iv_trade) if _v(iv_trade) else "—")
            with cols[2]: st.metric(f"Market Price ({stock_cur})",
                                     _fmt_price(mkt_display) if _v(mkt_display) else "—")
            with cols[3]:
                if _v(gap):
                    st.metric("Gap", f"{gap:+.1f}%", delta=f"{gap:+.1f}%",
                              delta_color="normal")
                else: st.metric("Gap", "—")
            with cols[4]: st.metric(f"Adjusted Intrinsic Value ({stock_cur})",
                                     _fmt_price(adj) if _v(adj) else "—")
        else:
            # Single currency
            cur_label = f" ({trading_cur})" if trading_cur else ""
            intrinsic = intrinsic_raw if _v(intrinsic_raw) else gap_dcf
            cols = st.columns(4)
            with cols[0]: st.metric(f"Intrinsic Value{cur_label}", _fmt_price(intrinsic))
            with cols[1]: st.metric(f"Market Price{cur_label}", _fmt_price(market))
            with cols[2]:
                if _v(gap):
                    st.metric("Gap", f"{gap:+.1f}%", delta=f"{gap:+.1f}%",
                              delta_color="normal")
                else: st.metric("Gap", "—")
            with cols[3]: st.metric(f"Adjusted Intrinsic Value{cur_label}",
                                     _fmt_price(adj) if _v(adj) else "—")

        # Detail (from batch-fetched map)
        d = _detail_map.get(row['id'])
        if d is None: continue

        # Reuse card forex rate for breakdown (already computed above for dual)
        _bd_fx = _card_fx if _dual else None

        # Build tabs
        tab_names = ["Historical", "DCF Breakdown", "AI Reasoning", "Sensitivity", "Gap Analysis"]
        tabs = st.tabs(tab_names)

        # ── Tab: Historical Financials ──
        with tabs[0]:
            fin_html = _render_financial_table(d.get('summary_json'))
            if fin_html:
                st.markdown(f'<div class="section-hdr">Historical Financial Data (in millions)</div>',
                            unsafe_allow_html=True)
                st.markdown(fin_html, unsafe_allow_html=True)
            else:
                st.info("Historical financial data not available for this valuation. (Available for new live valuations.)")

        # ── Tab: DCF Breakdown ──
        with tabs[1]:
            dcf_html = _render_dcf_table(d.get('dcf_table_json'), d.get('ttm_label') or '', base_year=d.get('base_year'))
            if dcf_html:
                st.markdown('<div class="section-hdr">Cash Flow Forecast (in millions)</div>',
                            unsafe_allow_html=True)
                st.markdown(dcf_html, unsafe_allow_html=True)

            st.markdown('<div class="section-hdr">Valuation Breakdown (in millions)</div>',
                        unsafe_allow_html=True)
            st.markdown(_render_valuation_breakdown(d, forex_rate=_bd_fx), unsafe_allow_html=True)

            st.markdown('<div class="section-hdr">Valuation Parameters</div>',
                        unsafe_allow_html=True)
            params_html = '<div class="val-breakdown">'
            for label, val in [
                ('Revenue Growth Y1', _fmt_pct(d.get('revenue_growth_1'))),
                ('Revenue Growth Y2-5', _fmt_pct(d.get('revenue_growth_2'))),
                ('Target EBIT Margin', _fmt_pct(d.get('ebit_margin'))),
                ('Convergence', f"{d['convergence']:.0f} yrs" if _v(d.get('convergence')) else '—'),
                ('Rev/IC Y1-2', _fmt_ratio(d.get('rev_ic_ratio_1'))),
                ('Rev/IC Y3-5', _fmt_ratio(d.get('rev_ic_ratio_2'))),
                ('Rev/IC Y5-10', _fmt_ratio(d.get('rev_ic_ratio_3'))),
                ('Tax Rate', _fmt_pct(d.get('tax_rate'))),
                ('WACC', _fmt_pct(d.get('wacc'))),
                ('Terminal WACC', _fmt_ratio(d.get('terminal_wacc'))),
                ('RONIC', _fmt_ratio(d.get('ronic'))),
                ('Risk-free Rate', _fmt_ratio(d.get('risk_free_rate'))),
                ('Beta', _fmt_ratio(d.get('beta'))),
            ]:
                params_html += f'<div class="row"><span>{label}</span><span>{val}</span></div>'
            params_html += '</div>'
            st.markdown(params_html, unsafe_allow_html=True)

        # ── Tab: AI Reasoning ──
        with tabs[2]:
            ai_params_md = _render_ai_reasoning(d.get('ai_parameters_json'))
            ai_raw = d.get('ai_raw_text')
            if ai_params_md:
                st.markdown('<div class="section-hdr">AI Parameter Analysis</div>',
                            unsafe_allow_html=True)
                st.markdown(ai_params_md)
            if ai_raw and pd.notna(ai_raw):
                label = 'Full AI Analysis' if ai_params_md else 'AI Analysis'
                st.markdown(f'<div class="section-hdr">{label}</div>', unsafe_allow_html=True)
                if _HAS_MD:
                    rendered = _md.markdown(ai_raw, extensions=['tables'])
                    st.markdown(f'<div class="ai-card">{rendered}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(ai_raw)
            if not ai_params_md and (not ai_raw or pd.isna(ai_raw)):
                st.info("No AI reasoning available (manual mode or data not captured).")

        # ── Tab: Sensitivity ──
        with tabs[3]:
            base_growth = d.get('revenue_growth_2') or 0
            base_margin = d.get('ebit_margin') or 0
            sens_html = _render_sensitivity_table(d.get('sensitivity_json'), base_growth, base_margin)
            if sens_html:
                st.markdown('<div class="section-hdr">Revenue Growth × EBIT Margin Sensitivity</div>',
                            unsafe_allow_html=True)
                st.markdown(sens_html, unsafe_allow_html=True)
            else:
                st.info("No sensitivity data available.")
            wacc_html = _render_wacc_sensitivity(d.get('wacc_sensitivity_json'), d.get('wacc_base'))
            if wacc_html:
                st.markdown('<div class="section-hdr">WACC Sensitivity</div>',
                            unsafe_allow_html=True)
                st.markdown(wacc_html, unsafe_allow_html=True)

        # ── Tab: Gap Analysis ──
        with tabs[4]:
            gap_text = d.get('gap_analysis_text')
            if gap_text and pd.notna(gap_text):
                bar_html = '<div class="gap-bar">'
                if _v(d.get('gap_dcf_price')):
                    bar_html += f'<div><span class="label">Intrinsic Value</span><br><span class="val">{d["gap_dcf_price"]:,.2f}</span></div>'
                if _v(d.get('gap_market_price')):
                    bar_html += f'<div><span class="label">Market Price</span><br><span class="val">{d["gap_market_price"]:,.2f}</span></div>'
                if _v(d.get('gap_pct')):
                    cls = 'positive' if d['gap_pct'] > 0 else 'negative'
                    bar_html += f'<div><span class="label">Gap</span><br><span class="val {cls}">{d["gap_pct"]:+.1f}%</span></div>'
                if _v(d.get('gap_adjusted_price')):
                    bar_html += f'<div><span class="label">Adjusted Price</span><br><span class="val">{d["gap_adjusted_price"]:,.2f}</span></div>'
                bar_html += '</div>'
                st.markdown(bar_html, unsafe_allow_html=True)
                rendered = _render_gap_analysis(gap_text)
                if _HAS_MD and rendered:
                    st.markdown(f'<div class="ai-card">{rendered}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(gap_text)
            else:
                st.info("No gap analysis available for this valuation.")

        # Delete button (two-step confirmation)
        st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)
        _del_key = f"del_{row['id']}"
        _confirming = st.session_state.get('confirm_delete') == row['id']
        _del_cols = st.columns([7, 1, 1] if _confirming else [8, 1])
        if _confirming:
            with _del_cols[1]:
                if st.button("✓ Confirm", key=f"{_del_key}_yes", type="primary"):
                    st.session_state.pop('confirm_delete', None)
                    _delete_record(row['id'])
                    st.rerun()
            with _del_cols[2]:
                if st.button("✗ Cancel", key=f"{_del_key}_no"):
                    st.session_state.pop('confirm_delete', None)
                    st.rerun()
        else:
            with _del_cols[-1]:
                if st.button("🗑 Delete", key=_del_key, type="secondary",
                             help="Permanently delete this valuation record"):
                    st.session_state['confirm_delete'] = row['id']
                    st.rerun()

# Footer
st.divider()
st.caption(f"Database: {DB_PATH} · {len(df)} records shown")
st.markdown(
    '<div style="text-align:center;color:gray;font-size:11px;'
    'font-family:monospace;padding:16px 0 8px;opacity:0.5;">'
    '© 2026 Alan He. All rights reserved.</div>',
    unsafe_allow_html=True,
)
