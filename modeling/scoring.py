# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""4-Dimension Scoring System (Diamond/Snowflake) for stock analysis.

All data sourced from financial statements + price history.
Zero external API dependency beyond the base financial data.

┌──────────────────────────────────────────────────────────────────────┐
│                        SCORING METHODOLOGY                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Total Score = equal-weighted average of 4 dimensions (0-100 each)   │
│                                                                      │
│  1. VALUE (25%)  — Relative Valuation                                │
│     PE TTM Historical Percentile  40%   self-referential cheapness   │
│     Forward PE (absolute)         30%   most forward-looking         │
│     Operating PE (absolute)       30%   strips non-recurring items   │
│                                                                      │
│     Operating PE = Price / (Trailing EPS × EBIT Margin / Net Margin) │
│     All PE metrics use piecewise linear interpolation                │
│                                                                      │
│  2. QUALITY (25%)  — Financial Quality                               │
│     ROE Level                     20%   absolute return on equity    │
│     ROE Trend (WLS)               15%   capital efficiency trajectory│
│     Revenue Trend (WLS)           15%   top-line growth trajectory   │
│     Margin Trend (WLS)            15%   operating margin trajectory  │
│     Piotroski F-Score             10%   fundamental health (0-9)     │
│     Income Quality (FCFF/NI)      10%   earnings backed by cash     │
│     Leverage (D/E Ratio)          15%   lower debt = higher quality  │
│                                                                      │
│     Trends: recency-weighted WLS (2^i weights), slope-based buckets  │
│     Piotroski: score/9 × 100                                        │
│     FCFF = EBIT×(1-tax) − Reinvestment (available for all markets)   │
│     Absolute-level floors: ROE>20% → trend min 50, ROE>15% → min 35 │
│                                                                      │
│  3. GROWTH (25%)  — Growth Trajectory                                │
│     Revenue CAGR (3yr)            30%   backward-looking track record│
│     Forward EPS Growth            40%   analyst consensus outlook    │
│     Latest Revenue Growth         30%   most recent single year      │
│                                                                      │
│  4. MOMENTUM (25%)  — Price Performance (skip recent 1 month)        │
│     12-1M Return                  50%                                │
│     6-1M Return                   50%                                │
│                                                                      │
│  Data Sources:                                                       │
│     Financial statements: FMP API / yfinance / akshare               │
│     Price history: yfinance                                          │
│                                                                      │
│  Missing Data Policy:                                                │
│     - Each sub-factor weight is down-weighted when data unavailable  │
│     - Remaining weights are renormalized                             │
│     - Complete absence → neutral 50                                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
"""

import logging
from datetime import date

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Top-level weights — 4 dimensions, equal weight
# ────────────────────────────────────────────────────────────────

W_VALUE = 0.25            # Relative Valuation
W_QUALITY = 0.25          # Financial Quality
W_GROWTH = 0.25           # Growth
W_MOMENTUM = 0.25         # Momentum (price-only)


def compute_scores(financial_data, profile, valuation_data=None,
                   historical_valuations=None, **kwargs):
    """Compute 4-dimension scores for a stock.

    Args:
        financial_data: Full dict from get_historical_financials
                        (contains 'summary', 'income_statement', 'balance_sheet',
                         'cashflow_statement')
        profile: dict from fetch_company_profile
        valuation_data: dict from get_current_valuation (optional)
        historical_valuations: dict from get_historical_valuations (optional)

    Returns:
        dict with dimension scores and total score
    """
    # Extract components
    df = financial_data.get('summary') if isinstance(financial_data, dict) else financial_data
    income_stmt = financial_data.get('income_statement') if isinstance(financial_data, dict) else None
    balance_stmt = financial_data.get('balance_sheet') if isinstance(financial_data, dict) else None
    cashflow_stmt = financial_data.get('cashflow_statement') if isinstance(financial_data, dict) else None

    value_score = _score_value(df, valuation_data, historical_valuations)
    quality_score = _score_quality(df, income_stmt, balance_stmt, cashflow_stmt)
    growth_score = _score_growth(df, valuation_data)
    momentum_score = _score_momentum(profile, valuation_data)

    # Weighted total (0-100)
    total = (
        value_score * W_VALUE +
        quality_score * W_QUALITY +
        growth_score * W_GROWTH +
        momentum_score * W_MOMENTUM
    )

    return {
        'dimensions': {
            'value': {'score': round(value_score, 1), 'weight': int(W_VALUE * 100), 'label': 'Valuation'},
            'quality': {'score': round(quality_score, 1), 'weight': int(W_QUALITY * 100), 'label': 'Quality'},
            'growth': {'score': round(growth_score, 1), 'weight': int(W_GROWTH * 100), 'label': 'Growth'},
            'momentum': {'score': round(momentum_score, 1), 'weight': int(W_MOMENTUM * 100), 'label': 'Momentum'},
        },
        'total_score': round(total, 0),
    }


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _safe_get_row(df, row_name, col_idx=0, default=None):
    """Safely get a value from a DataFrame by row name and column index."""
    try:
        if df is not None and row_name in df.index:
            val = df.loc[row_name].iloc[col_idx]
            if pd.notna(val):
                return float(val)
    except Exception:
        pass
    return default


def _safe_get_row_series(df, row_name):
    """Get a full row as a list of floats (most-recent-first)."""
    try:
        if df is not None and row_name in df.index:
            vals = df.loc[row_name].values
            return [float(v) if pd.notna(v) else None for v in vals]
    except Exception:
        pass
    return []


def _safe_get_stmt(stmt, field, col_idx=0, default=None):
    """Safely get a value from a raw financial statement (income/balance/cashflow)."""
    try:
        if stmt is not None and field in stmt.index:
            val = stmt.loc[field].iloc[col_idx]
            if pd.notna(val):
                return float(val)
    except Exception:
        pass
    return default


def _safe_get_stmt_series(stmt, field):
    """Get a full row from a raw statement as a list of floats (most-recent-first)."""
    try:
        if stmt is not None and field in stmt.index:
            vals = stmt.loc[field].values
            return [float(v) if pd.notna(v) else None for v in vals]
    except Exception:
        pass
    return []


def _piecewise_linear(value, breakpoints):
    """Interpolate value through piecewise-linear breakpoints.

    breakpoints: list of (x, score) tuples, sorted by x ascending.
    Returns score in [breakpoints[0][1], breakpoints[-1][1]].
    """
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]
    if value >= breakpoints[-1][0]:
        return breakpoints[-1][1]

    for i in range(len(breakpoints) - 1):
        x_lo, s_lo = breakpoints[i]
        x_hi, s_hi = breakpoints[i + 1]
        if value <= x_hi:
            t = (value - x_lo) / (x_hi - x_lo)
            return round(s_lo + t * (s_hi - s_lo), 1)

    return breakpoints[-1][1]


def _wls_trend_score(values, metric_type='roe'):
    """Score a trend using recency-weighted WLS regression.

    Adapted from value-screen: each more-recent year gets 2x the weight
    of the prior year. Uses piecewise linear interpolation to avoid
    cliff effects at bucket boundaries.

    Args:
        values: list of floats, most-recent-first
        metric_type: 'roe' (percentage points/yr), 'revenue' (log growth), 'margin'

    Returns score 0-100.
    """
    clean = [v for v in values if v is not None and np.isfinite(v)]
    if len(clean) < 2:
        return 50  # neutral

    # For revenue, need positive values for log regression
    if metric_type == 'revenue':
        clean = [v for v in clean if v > 0]
        if len(clean) < 2:
            return 50

    # Reverse to chronological order (oldest → newest)
    chronological = list(reversed(clean))
    xs = np.arange(len(chronological), dtype=float)
    ys = np.array(chronological, dtype=float)

    # Recency-weighted regression
    weights = np.array([2.0 ** i for i in range(len(chronological))])

    if metric_type == 'revenue':
        # Log-linear regression → approximate CAGR
        slope = np.polyfit(xs, np.log(ys), 1, w=weights)[0]
        growth_pct = slope * 100

        # Piecewise linear — smooth interpolation, no cliffs
        _REVENUE_TREND_BP = [
            (-15, 5), (-10, 15), (-5, 25), (0, 40),
            (5, 55), (10, 75), (15, 90), (25, 100),
        ]
        return _piecewise_linear(growth_pct, _REVENUE_TREND_BP)
    else:
        # ROE / Margin: percentage points per year
        slope = np.polyfit(xs, ys * 100, 1, w=weights)[0]

        # Piecewise linear — smooth interpolation, no cliffs
        _ROE_MARGIN_TREND_BP = [
            (-3, 5), (-2, 15), (-1, 25), (-0.3, 40),
            (0, 50), (0.5, 60), (1, 75), (2, 90), (3, 100),
        ]
        return _piecewise_linear(slope, _ROE_MARGIN_TREND_BP)


# ────────────────────────────────────────────────────────────────
# Value Score (0-100) — 20% weight
# Aligned with value-screen relative_valuation.py:
#   PE hist percentile(30%) + Forward PE(20%)
#   + Operating PE(20%) + EV/EBITDA vs industry(30%)
# ────────────────────────────────────────────────────────────────

# PE absolute scoring breakpoints (from value-screen v4)
_PE_BREAKPOINTS = [
    (5, 100),
    (10, 85),
    (15, 72),
    (20, 60),
    (25, 50),   # neutral anchor (tech companies live here)
    (30, 40),
    (40, 25),
    (50, 15),
]


def _score_pe_historical_percentile(percentile):
    """Score PE historical percentile. Lower percentile = cheaper = higher score.

    Piecewise linear from value-screen:
      0%  → 100, 25% → 80, 50% → 55, 75% → 30, 100% → 5
    """
    if percentile is None:
        return 50

    pct = percentile / 100.0  # convert to 0-1
    _MAP = [(0.0, 100), (0.25, 80), (0.50, 55), (0.75, 30), (1.0, 5)]
    return _piecewise_linear(pct, _MAP)


def _score_value(df, valuation_data, historical_valuations):
    """Value dimension: PE-based valuation scoring.

    Sub-weights:
      PE TTM Historical Percentile  40%   self-referential cheapness
      Forward PE (absolute)         30%   most forward-looking
      Operating PE (absolute)       30%   strips non-recurring items
    """
    scores = []
    weights = []

    # 1. PE TTM Historical Percentile (40%) — self-referential
    pe_pctl = None
    if historical_valuations:
        pe_pctl = historical_valuations.get('pe_percentile')
    s = _score_pe_historical_percentile(pe_pctl)
    w = 0.40 if pe_pctl is not None else 0.16
    scores.append(s)
    weights.append(w)

    # 2. Forward PE Absolute (30%) — most forward-looking
    forward_pe = None
    if valuation_data:
        forward_pe = valuation_data.get('forward_pe')
    if forward_pe and forward_pe > 0:
        s = _piecewise_linear(forward_pe, _PE_BREAKPOINTS)
        scores.append(s)
        weights.append(0.30)
    else:
        scores.append(50)
        weights.append(0.12)

    # 3. Operating PE (30%) — strips non-recurring items
    #    Op EPS = Trailing EPS × (EBIT Margin / Net Margin)
    operating_pe = None
    if valuation_data:
        teps = valuation_data.get('trailing_eps')
        price = valuation_data.get('price')
        net_margin = valuation_data.get('profit_margins')  # net profit margin
        ebit_margin_pct = _safe_get_row(df, 'EBIT Margin (%)', 0)
        op_margin = ebit_margin_pct / 100.0 if ebit_margin_pct is not None else None

        if (teps and teps > 0 and price and price > 0
                and op_margin and op_margin > 0
                and net_margin and net_margin > 0):
            op_eps = teps * (op_margin / net_margin)
            if op_eps > 0:
                operating_pe = price / op_eps

    if operating_pe and 0 < operating_pe < 500:
        s = _piecewise_linear(operating_pe, _PE_BREAKPOINTS)
        scores.append(s)
        weights.append(0.30)
    elif valuation_data and valuation_data.get('trailing_pe') and valuation_data['trailing_pe'] > 0:
        # Fallback to trailing PE if operating PE unavailable
        s = _piecewise_linear(valuation_data['trailing_pe'], _PE_BREAKPOINTS)
        scores.append(s)
        weights.append(0.30)
    else:
        scores.append(50)
        weights.append(0.12)

    total_w = sum(weights)
    if total_w > 0:
        return sum(s * w for s, w in zip(scores, weights)) / total_w
    return 50


# ────────────────────────────────────────────────────────────────
# Quality Score (0-100) — 25% weight
# Aligned with value-screen financial_quality.py:
#   ROE Level (20%), ROE Trend (15%), Revenue Trend (15%),
#   Margin Trend (15%), Piotroski (10%), Income Quality (10%),
#   Leverage/D/E (15%)
# ────────────────────────────────────────────────────────────────

# ROE level breakpoints — piecewise linear, no cliffs
_ROE_BREAKPOINTS = [
    (0.05, 10), (0.10, 30), (0.12, 40), (0.15, 55),
    (0.20, 70), (0.25, 85), (0.30, 95), (0.40, 100),
]

# Operating margin level breakpoints
_MARGIN_BREAKPOINTS = [
    (0.0, 5), (0.05, 20), (0.10, 40), (0.15, 55),
    (0.20, 70), (0.25, 80), (0.30, 90), (0.40, 100),
]

# Debt-to-Equity ratio breakpoints — lower D/E = higher quality
# D/E ≈ 1.0 (~50% debt ratio, S&P 500 median) anchored at neutral 50.
# Gentle slope in 0.5-1.5 range where most healthy companies cluster.
_DE_BREAKPOINTS = [
    (0.0, 90), (0.30, 80), (0.50, 70), (0.80, 60),
    (1.00, 50), (1.50, 35), (2.00, 20), (3.00, 10),
]


def _compute_piotroski(df, income_stmt, balance_stmt, cashflow_stmt):
    """Compute Piotroski F-Score (0-9) from financial statements.

    Resilient to missing raw statement fields — falls back to summary data
    when raw statements are incomplete (common for yfinance/akshare sources).

    9 binary signals:
      Profitability (4):
        1. Positive ROA (or positive ROE from summary)
        2. Positive Operating Cash Flow (or EBIT from summary)
        3. ROA / ROE improving (vs prior year)
        4. Accruals: OCF > Net Income (or FCFF > 0 from summary)
      Leverage/Liquidity (3):
        5. Debt ratio decreasing (from summary Debt to Assets %)
        6. Current ratio improving (raw stmt only, skip if unavailable)
        7. No new share issuance (raw stmt only, skip if unavailable)
      Efficiency (2):
        8. EBIT margin improving (from summary, replaces gross margin)
        9. Asset turnover (Revenue/IC) improving (from summary)

    Returns (score, max_possible) — normalized to 0-9 equivalent.
    """
    score = 0
    tested = 0  # how many signals we could actually test

    # === Helper: get value from raw stmt OR summary ===
    def _get(stmt, field, col, summary_field=None, summary_col=None):
        val = _safe_get_stmt(stmt, field, col)
        if val is None and summary_field is not None:
            val = _safe_get_row(df, summary_field, summary_col if summary_col is not None else col)
        return val

    # --- Profitability ---

    # 1. Positive ROA (or positive ROE)
    roe_0 = _safe_get_row(df, 'ROE (%)', 0)
    ni_0 = _safe_get_stmt(income_stmt, 'netIncome', 0)
    ta_0 = _safe_get_stmt(balance_stmt, 'totalAssets', 0)

    if ni_0 is not None and ta_0 and ta_0 > 0:
        roa_0 = ni_0 / ta_0
        tested += 1
        if roa_0 > 0:
            score += 1
    elif roe_0 is not None:
        # Fallback: use ROE from summary
        tested += 1
        if roe_0 > 0:
            score += 1

    # 2. Positive Operating Cash Flow
    ocf = _safe_get_stmt(cashflow_stmt, 'operatingCashFlow', 0)
    if ocf is None:
        ocf = _safe_get_stmt(cashflow_stmt, 'netCashProvidedByOperatingActivities', 0)
    if ocf is not None:
        tested += 1
        if ocf > 0:
            score += 1
    else:
        # Fallback: positive EBIT from summary (weaker proxy)
        ebit_0 = _safe_get_row(df, 'EBIT', 0)
        if ebit_0 is not None:
            tested += 1
            if ebit_0 > 0:
                score += 1

    # 3. ROA / ROE improving
    roe_1 = _safe_get_row(df, 'ROE (%)', 1)
    if ni_0 is not None and ta_0 and ta_0 > 0:
        roa_0 = ni_0 / ta_0
        ni_1 = _safe_get_stmt(income_stmt, 'netIncome', 1)
        ta_1 = _safe_get_stmt(balance_stmt, 'totalAssets', 1)
        if ni_1 is not None and ta_1 and ta_1 > 0:
            roa_1 = ni_1 / ta_1
            tested += 1
            if roa_0 > roa_1:
                score += 1
        elif roe_0 is not None and roe_1 is not None:
            tested += 1
            if roe_0 > roe_1:
                score += 1
    elif roe_0 is not None and roe_1 is not None:
        tested += 1
        if roe_0 > roe_1:
            score += 1

    # 4. Accruals: OCF > Net Income (or FCFF positive from summary)
    if ocf is not None and ni_0 is not None:
        tested += 1
        if ocf > ni_0:
            score += 1
    else:
        # Fallback: FCFF from summary (EBIT*(1-tax) - reinvestment > 0)
        ebit_val = _safe_get_row(df, 'EBIT', 0)
        tax_rate = _safe_get_row(df, 'Tax Rate (%)', 0)
        reinv = _safe_get_row(df, 'Total Reinvestment', 0)
        if ebit_val is not None and tax_rate is not None and reinv is not None:
            nopat = ebit_val * (1 - tax_rate / 100.0)
            fcff = nopat - reinv
            tested += 1
            if fcff > 0:
                score += 1

    # --- Leverage / Liquidity ---

    # 5. Debt ratio decreasing (use summary Debt to Assets %)
    da_series = _safe_get_row_series(df, 'Debt to Assets (%)')
    if len(da_series) >= 2 and da_series[0] is not None and da_series[1] is not None:
        tested += 1
        if da_series[0] < da_series[1]:
            score += 1
    else:
        # Try raw statements
        tl_0 = _safe_get_stmt(balance_stmt, 'totalLiabilities', 0)
        tl_1 = _safe_get_stmt(balance_stmt, 'totalLiabilities', 1)
        ta_1_val = _safe_get_stmt(balance_stmt, 'totalAssets', 1)
        if ta_0 and ta_0 > 0 and tl_0 is not None and tl_1 is not None and ta_1_val and ta_1_val > 0:
            dr_0 = tl_0 / ta_0
            dr_1 = tl_1 / ta_1_val
            tested += 1
            if dr_0 < dr_1:
                score += 1

    # 6. Current ratio improving (raw stmt only)
    ca_0 = _safe_get_stmt(balance_stmt, 'totalCurrentAssets', 0)
    cl_0 = _safe_get_stmt(balance_stmt, 'totalCurrentLiabilities', 0)
    ca_1 = _safe_get_stmt(balance_stmt, 'totalCurrentAssets', 1)
    cl_1 = _safe_get_stmt(balance_stmt, 'totalCurrentLiabilities', 1)
    if ca_0 and cl_0 and cl_0 > 0 and ca_1 and cl_1 and cl_1 > 0:
        cr_0 = ca_0 / cl_0
        cr_1 = ca_1 / cl_1
        tested += 1
        if cr_0 > cr_1:
            score += 1

    # 7. No new share issuance
    shares_0 = _safe_get_stmt(income_stmt, 'weightedAverageShsOut', 0)
    shares_1 = _safe_get_stmt(income_stmt, 'weightedAverageShsOut', 1)
    if shares_0 is not None and shares_1 is not None:
        tested += 1
        if shares_0 <= shares_1:
            score += 1

    # --- Efficiency ---

    # 8. EBIT margin improving (from summary, more available than gross margin)
    margin_series = _safe_get_row_series(df, 'EBIT Margin (%)')
    if len(margin_series) >= 2 and margin_series[0] is not None and margin_series[1] is not None:
        tested += 1
        if margin_series[0] > margin_series[1]:
            score += 1
    else:
        # Try raw: gross margin
        gp_0 = _safe_get_stmt(income_stmt, 'grossProfit', 0)
        rev_0 = _safe_get_stmt(income_stmt, 'revenue', 0)
        gp_1 = _safe_get_stmt(income_stmt, 'grossProfit', 1)
        rev_1 = _safe_get_stmt(income_stmt, 'revenue', 1)
        if gp_0 is not None and rev_0 and rev_0 > 0 and gp_1 is not None and rev_1 and rev_1 > 0:
            tested += 1
            if (gp_0 / rev_0) > (gp_1 / rev_1):
                score += 1

    # 9. Asset turnover improving (Revenue/IC from summary)
    ric_series = _safe_get_row_series(df, 'Revenue / IC')
    if len(ric_series) >= 2 and ric_series[0] is not None and ric_series[1] is not None:
        tested += 1
        if ric_series[0] > ric_series[1]:
            score += 1
    else:
        # Try raw: revenue / total assets
        rev_0 = _safe_get_stmt(income_stmt, 'revenue', 0)
        rev_1 = _safe_get_stmt(income_stmt, 'revenue', 1)
        ta_1_val = _safe_get_stmt(balance_stmt, 'totalAssets', 1)
        if rev_0 and ta_0 and ta_0 > 0 and rev_1 and ta_1_val and ta_1_val > 0:
            tested += 1
            if (rev_0 / ta_0) > (rev_1 / ta_1_val):
                score += 1

    # Normalize: if we tested fewer than 9 signals, scale proportionally
    if tested == 0:
        return 5  # neutral (5/9 ≈ 55%)
    # Scale to 0-9 equivalent
    return round(score / tested * 9)


def _score_quality(df, income_stmt=None, balance_stmt=None, cashflow_stmt=None):
    """Quality dimension: aligned with value-screen financial_quality.py.

    Sub-factors:
      - ROE Level (20%)           — absolute return on equity
      - ROE Trend (15%)           — WLS with absolute-level floor
      - Revenue Trend (15%)       — WLS log-linear regression
      - Margin Trend (15%)        — WLS operating margin trajectory
      - Piotroski F-Score (10%)   — fundamental health (0-9 → 0-100)
      - Income Quality (10%)      — FCFF/NI, earnings backed by cash
      - Leverage (15%)            — D/E ratio, lower = better
    """
    scores = []
    weights = []

    # ── 1. ROE Level (20%) — piecewise linear ──
    roe = _safe_get_row(df, 'ROE (%)', 0)
    roe_decimal = (roe / 100.0) if roe is not None else None
    if roe_decimal is not None:
        s = _piecewise_linear(roe_decimal, _ROE_BREAKPOINTS)
        scores.append(s)
        weights.append(0.20)

    # ── 2. ROE Trend (15%) — WLS with absolute-level floor ──
    roe_series = _safe_get_row_series(df, 'ROE (%)')
    roe_values = [v / 100.0 if v is not None else None for v in roe_series]
    if len([v for v in roe_values if v is not None]) >= 2:
        s = _wls_trend_score(roe_values, 'roe')
        # Absolute-level floor: excellent ROE should not get penalized
        if roe_decimal is not None:
            if roe_decimal > 0.20:
                s = max(s, 50)
            elif roe_decimal > 0.15:
                s = max(s, 35)
        scores.append(s)
        weights.append(0.15)

    # ── 3. Revenue Trend (15%) — WLS log-linear regression ──
    rev_series = _safe_get_row_series(df, 'Revenue')
    if len([v for v in rev_series if v is not None and v > 0]) >= 2:
        s = _wls_trend_score(rev_series, 'revenue')
        scores.append(s)
        weights.append(0.15)

    # ── 4. Margin Trend (15%) — WLS operating margin trajectory ──
    margin_series = _safe_get_row_series(df, 'EBIT Margin (%)')
    margin_values = [v / 100.0 if v is not None else None for v in margin_series]
    margin_decimal = (margin_values[0]) if margin_values and margin_values[0] is not None else None
    if len([v for v in margin_values if v is not None]) >= 2:
        s = _wls_trend_score(margin_values, 'margin')
        # Absolute-level floor
        if margin_decimal is not None:
            if margin_decimal > 0.20:
                s = max(s, 50)
            elif margin_decimal > 0.15:
                s = max(s, 35)
        scores.append(s)
        weights.append(0.15)

    # ── 5. Piotroski F-Score (10%) ──
    piotroski = _compute_piotroski(df, income_stmt, balance_stmt, cashflow_stmt)
    s = max(0, min(100, piotroski / 9.0 * 100))
    scores.append(round(s, 1))
    weights.append(0.10)

    # ── 6. Income Quality: FCFF / Net Income (10%) ──
    # FCFF = EBIT × (1-tax) − Reinvestment (works for all markets)
    # IMPORTANT: use same unit source for numerator and denominator!
    fcf = None
    net_income = None

    # Strategy: FCFF from summary uses summary units (millions).
    # Net Income must also come from summary-compatible units.
    # We compute NI as EBIT × (1 - tax_rate) from summary (same units).
    ebit_val = _safe_get_row(df, 'EBIT', 0)
    tax_rate = _safe_get_row(df, 'Tax Rate (%)', 0)
    reinvestment = _safe_get_row(df, 'Total Reinvestment', 0)
    if ebit_val is not None and tax_rate is not None and reinvestment is not None:
        nopat = ebit_val * (1 - tax_rate / 100.0)
        fcf = nopat - reinvestment
        # Use NOPAT as proxy for net income (same units as FCFF)
        net_income = nopat

    # Fallback: both from raw statements (same units)
    if fcf is None:
        fcf = _safe_get_stmt(cashflow_stmt, 'freeCashFlow', 0)
        net_income = _safe_get_stmt(income_stmt, 'netIncome', 0)
        if net_income is None:
            ibt = _safe_get_stmt(income_stmt, 'incomeBeforeTax', 0)
            tax = _safe_get_stmt(income_stmt, 'incomeTaxExpense', 0)
            if ibt is not None and tax is not None:
                net_income = ibt - tax
    if fcf is None:
        fcf = _safe_get_row(df, 'Free Cash Flow', 0)
    if net_income is None:
        net_income = _safe_get_row(df, 'Net Income', 0)

    if fcf is not None and net_income is not None and net_income > 0:
        iq = fcf / net_income
        # Matching value-screen: clamp to [0, 1.5], linear scale
        clamped = max(0, min(1.5, iq))
        s = min(100, clamped / 1.0 * 100)
        scores.append(round(s, 1))
        weights.append(0.10)

    # ── 7. Leverage / D/E Ratio (15%) ──
    # Try summary first, then raw balance sheet
    da_pct = _safe_get_row(df, 'Debt to Assets (%)', 0)
    if da_pct is not None and da_pct >= 0:
        # Convert Debt/Assets % to D/E: D/E = D/A / (1 - D/A)
        da_ratio = da_pct / 100.0
        if da_ratio < 1.0:
            de_ratio = da_ratio / (1.0 - da_ratio)
        else:
            de_ratio = 10.0  # extreme leverage
        s = _piecewise_linear(de_ratio, _DE_BREAKPOINTS)
        scores.append(round(s, 1))
        weights.append(0.15)
    else:
        # Fallback: raw balance sheet
        total_debt = _safe_get_stmt(balance_stmt, 'totalDebt', 0)
        if total_debt is None:
            total_debt = _safe_get_stmt(balance_stmt, 'longTermDebt', 0)
        total_equity = _safe_get_stmt(balance_stmt, 'totalStockholdersEquity', 0)
        if total_debt is not None and total_equity is not None:
            if total_equity <= 0:
                s = 5.0  # negative equity → worst
            else:
                de_ratio = total_debt / total_equity
                s = _piecewise_linear(de_ratio, _DE_BREAKPOINTS)
            scores.append(round(s, 1))
            weights.append(0.15)

    total_w = sum(weights)
    if total_w > 0:
        return sum(s * w for s, w in zip(scores, weights)) / total_w
    return 50


# ────────────────────────────────────────────────────────────────
# Growth Score (0-100) — 20% weight
# Aligned with value-screen:
#   Revenue CAGR(30%) + Forward Rev Growth(30%) + Forward EPS(40%)
# ────────────────────────────────────────────────────────────────

# Revenue CAGR breakpoints (from value-screen)
_CAGR_BREAKPOINTS = [
    (-0.10, 5), (-0.03, 15), (0.0, 25), (0.05, 50),
    (0.10, 70), (0.15, 85), (0.20, 95), (0.30, 100),
]

# Forward EPS growth breakpoints (from value-screen)
_FWD_EPS_BREAKPOINTS = [
    (-0.10, 5), (0.0, 15), (0.05, 40), (0.10, 60),
    (0.15, 78), (0.20, 90), (0.30, 100),
]


def _score_growth(df, valuation_data):
    """Growth dimension with piecewise linear scoring from value-screen."""
    scores = []
    weights = []

    # 1. Revenue CAGR (30%) — backward-looking 3yr
    rev_series = _safe_get_row_series(df, 'Revenue')
    rev_clean = [v for v in rev_series if v is not None and v > 0]
    if len(rev_clean) >= 2:
        years = min(3, len(rev_clean) - 1)
        latest = rev_clean[0]
        base = rev_clean[years]
        if base > 0:
            cagr = (latest / base) ** (1.0 / years) - 1.0
            s = _piecewise_linear(cagr, _CAGR_BREAKPOINTS)
            scores.append(s)
            weights.append(0.30)

    # 2. Forward EPS Growth (40%)
    if valuation_data:
        feps = valuation_data.get('forward_eps')
        teps = valuation_data.get('trailing_eps')
        if feps and teps and teps > 0:
            growth = (feps - teps) / abs(teps)
            s = _piecewise_linear(growth, _FWD_EPS_BREAKPOINTS)
            scores.append(s)
            weights.append(0.40)

    # 3. Latest Revenue Growth (30%) — single year
    rev_growth = _safe_get_row(df, 'Revenue Growth (%)', 0)
    if rev_growth is not None:
        s = _piecewise_linear(rev_growth / 100.0, _CAGR_BREAKPOINTS)
        scores.append(s)
        weights.append(0.30)

    total_w = sum(weights)
    if total_w > 0:
        return sum(s * w for s, w in zip(scores, weights)) / total_w
    return 50


# ────────────────────────────────────────────────────────────────
# Momentum Score (0-100) — 25% weight
# Price-only momentum (no social sentiment).
# Sub-factors: 12-1M return (50%), 6-1M return (50%)
#
# Following MSCI/S&P/Morningstar standard: skip the most recent
# 1 month (~21 trading days) to avoid short-term reversal effect.
# ────────────────────────────────────────────────────────────────

# Price return breakpoints (from value-screen sentiment factor)
_RETURN_BREAKPOINTS = [
    (-30, 5), (-20, 15), (-10, 30), (0, 45),
    (10, 60), (20, 75), (30, 90), (50, 100),
]

_SKIP_DAYS = 21  # ~1 month of trading days to skip (short-term reversal)


def _score_momentum(profile, valuation_data):
    """Momentum dimension based on price performance.

    Uses the standard "skip-1-month" formulation (12-1 and 6-1 month):
      - 12-1M return (50%): price 12 months ago → price 1 month ago
      - 6-1M return (50%): price 6 months ago → price 1 month ago

    Skipping the most recent month avoids short-term mean reversion,
    a well-documented effect that contaminates raw momentum signals.
    """
    scores = []
    weights = []

    ticker = None
    if valuation_data and valuation_data.get('ticker'):
        ticker = valuation_data['ticker']
    elif profile and profile.get('Symbol'):
        ticker = profile['Symbol']

    if ticker:
        try:
            import yfinance as yf
            from datetime import datetime, timedelta

            t = yf.Ticker(ticker)
            end = datetime.now()
            start_12m = end - timedelta(days=395)  # ~13 months to have enough data
            hist = t.history(start=start_12m.strftime('%Y-%m-%d'),
                             end=end.strftime('%Y-%m-%d'))

            if not hist.empty and len(hist) > _SKIP_DAYS + 20:
                # "Current" = 1 month ago (skip recent month)
                ref_price = float(hist['Close'].iloc[-_SKIP_DAYS])

                # 12-1M return (50%)
                price_12m_ago = float(hist['Close'].iloc[0])
                if price_12m_ago > 0:
                    ret_12_1 = (ref_price - price_12m_ago) / price_12m_ago * 100
                    s = _piecewise_linear(ret_12_1, _RETURN_BREAKPOINTS)
                    scores.append(s)
                    weights.append(0.50)

                # 6-1M return (50%)
                idx_6m = len(hist) // 2
                if idx_6m > 0:
                    price_6m_ago = float(hist['Close'].iloc[idx_6m])
                    if price_6m_ago > 0:
                        ret_6_1 = (ref_price - price_6m_ago) / price_6m_ago * 100
                        s = _piecewise_linear(ret_6_1, _RETURN_BREAKPOINTS)
                        scores.append(s)
                        weights.append(0.50)

        except Exception:
            pass

    total_w = sum(weights)
    if total_w > 0:
        return sum(s * w for s, w in zip(scores, weights)) / total_w
    return 50
