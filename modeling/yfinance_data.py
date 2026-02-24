# Copyright (c) 2025 Alan He. Licensed under MIT.
"""yfinance data module: primary data source for HK stocks (.HK) and
cross-validation for FMP data (US/other markets)."""

import pandas as pd
from . import style as S
from .constants import HK_DEFAULT_BETA

# ---------------------------------------------------------------------------
# Lazy import — yfinance is only loaded when user opts in
# ---------------------------------------------------------------------------

_yf = None


def _get_yf():
    """Lazy import yfinance on first use."""
    global _yf
    if _yf is None:
        import yfinance as yf
        _yf = yf
    return _yf


# ---------------------------------------------------------------------------
# Field mapping: FMP summary row name → (yfinance_attr, yf_field, sign)
# ---------------------------------------------------------------------------
# sign: multiplier applied to yfinance raw value so that the result matches
# the convention used in FMP summary (see data.py lines 930-943).
#   Revenue          → / 1M, as-is                  → +1
#   CapitalExpenditure → yfinance reports negative   → -1 (negate to match FMP positive)
#   ChangeInWorkingCapital → negate to match FMP     → -1
#   D&A              → positive in both              → +1

FIELD_MAP = {
    # --- Income Statement ---
    'Revenue':                 ('income_stmt',    'Total Revenue',              1),
    'EBIT':                    ('income_stmt',    'Total Operating Income As Reported', 1),
    # --- Cash Flow ---
    '(+) Capital Expenditure': ('cashflow',       'Capital Expenditure',       -1),
    '(-) D&A':                 ('cashflow',       'Depreciation And Amortization', 1),
    '(+) ΔWorking Capital':    ('cashflow',       'Change In Working Capital', -1),
    # --- Balance Sheet ---
    '(+) Total Debt':          ('balance_sheet',  'Total Debt',                 1),
    '(+) Total Equity':        ('balance_sheet',  'Total Equity Gross Minority Interest', 1),
    '(-) Cash & Equivalents':  ('balance_sheet',  'Cash And Cash Equivalents',  1),
    # (-) Total Investments is computed separately below (sum of components)
    'Minority Interest':       ('balance_sheet',  'Minority Interest',          1),
}

# Fields to compare, in display order
COMPARE_FIELDS = [
    'Revenue', 'EBIT', 'EBIT Margin (%)', 'Tax Rate (%)',
    '(+) Capital Expenditure', '(-) D&A', '(+) ΔWorking Capital',
    '(+) Total Debt', '(+) Total Equity',
    '(-) Cash & Equivalents', '(-) Total Investments',
    'Minority Interest',
]

AMOUNT_FIELDS = {
    'Revenue', 'EBIT',
    '(+) Capital Expenditure', '(-) D&A', '(+) ΔWorking Capital',
    '(+) Total Debt', '(+) Total Equity',
    '(-) Cash & Equivalents', '(-) Total Investments',
    'Minority Interest',
}

PCT_FIELDS = {'EBIT Margin (%)', 'Tax Rate (%)'}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_get(df, field_name, col):
    """Safely retrieve a value from a yfinance DataFrame.

    Returns float or None.
    """
    if df is None or df.empty or field_name not in df.index:
        return None
    try:
        val = df.loc[field_name, col]
    except KeyError:
        return None
    if pd.isna(val):
        return None
    return float(val)


def _safe_get_fallback(df, field_names, col):
    """Try multiple field names in order, return first non-None."""
    for name in field_names:
        val = _safe_get(df, name, col)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_yfinance_data(ticker, target_year=None):
    """Fetch annual financial data from yfinance.

    If *target_year* (e.g. "2024" or 2024) is given, pick the column whose
    year matches; otherwise use the most recent column.

    Returns (data_dict, fiscal_year_str) or None on failure.
    data_dict keys match FMP summary row names; values are in millions.
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)

    inc = t.income_stmt
    bs = t.balance_sheet
    cf = t.cashflow

    if inc is None or inc.empty:
        return None

    # Pick the column that matches target_year, or default to latest
    col = None
    if target_year is not None:
        ty = str(target_year)[:4]
        for c in inc.columns:
            c_year = str(c.year) if hasattr(c, 'year') else str(c)[:4]
            if c_year == ty:
                col = c
                break
    if col is None:
        col = inc.columns[0]  # fallback: latest
    fiscal_year_str = str(col.date()) if hasattr(col, 'date') else str(col)

    # Fetch mapped fields
    data = {}
    stmts = {'income_stmt': inc, 'balance_sheet': bs, 'cashflow': cf}

    for fmp_name, (stmt_key, yf_field, sign) in FIELD_MAP.items():
        df = stmts.get(stmt_key)
        raw = _safe_get(df, yf_field, col)

        # Fallbacks for common field name variants
        if raw is None and fmp_name == 'EBIT':
            # 'Total Operating Income As Reported' is the annual-report figure;
            # fall back to yfinance's own 'Operating Income' (close but may differ
            # slightly), and only as last resort to 'EBIT' (which for HK/IFRS
            # stocks includes associates/JV/investment income — unreliable).
            raw = _safe_get(df, 'Operating Income', col)
            if raw is None:
                raw = _safe_get(df, 'EBIT', col)
        if raw is not None:
            data[fmp_name] = raw * sign / 1_000_000
        else:
            data[fmp_name] = None

    # --- Total Investments: always sum components (no single reliable field) ---
    # yfinance's 'Investments And Advances' excludes short-term investments for
    # some stocks, so we always compute the sum ourselves.
    _inv_components = [
        'Investmentin Financial Assets',        # FVOCI + FVPL
        'Long Term Equity Investment',           # Associates + JV
        'Other Short Term Investments',           # Treasury / term deposits
    ]
    _inv_total = 0
    _inv_found = False
    for _comp in _inv_components:
        _v = _safe_get(bs, _comp, col)
        if _v is not None:
            _inv_total += _v
            _inv_found = True
    if _inv_found:
        data['(-) Total Investments'] = _inv_total / 1_000_000
    else:
        data['(-) Total Investments'] = None

    # Derived: Tax Rate (%)
    tax_provision = _safe_get_fallback(inc, ['Tax Provision', 'Income Tax Expense'], col)
    pretax_income = _safe_get(inc, 'Pretax Income', col)
    if tax_provision is not None and pretax_income and pretax_income != 0:
        data['Tax Rate (%)'] = tax_provision / pretax_income * 100
    else:
        data['Tax Rate (%)'] = None

    # Derived: EBIT Margin (%)
    if data.get('Revenue') and data.get('EBIT') is not None and data['Revenue'] != 0:
        data['EBIT Margin (%)'] = data['EBIT'] / data['Revenue'] * 100
    else:
        data['EBIT Margin (%)'] = None

    return data, fiscal_year_str


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

def _compute_diff_pct(fmp_val, yf_val):
    """Compute percentage difference. Returns float or None."""
    if fmp_val is None or yf_val is None:
        return None
    if fmp_val == 0 and yf_val == 0:
        return 0.0
    if fmp_val == 0:
        return None  # Cannot compute % diff when base is 0
    return abs(fmp_val - yf_val) / abs(fmp_val) * 100


def compare_fmp_yfinance(fmp_series, yf_data, threshold_pct=5.0):
    """Build comparison data.

    Returns list of dicts: [{field, fmp, yfinance, diff_pct, flag}, ...]
    """
    rows = []
    for field in COMPARE_FIELDS:
        # FMP value
        fmp_raw = fmp_series.get(field)
        try:
            fmp_val = float(fmp_raw) if fmp_raw is not None and not pd.isna(fmp_raw) else None
        except (ValueError, TypeError):
            fmp_val = None

        # yfinance value
        yf_val = yf_data.get(field)

        diff_pct = _compute_diff_pct(fmp_val, yf_val)
        flag = diff_pct is not None and diff_pct > threshold_pct

        rows.append({
            'field': field,
            'fmp': fmp_val,
            'yfinance': yf_val,
            'diff_pct': diff_pct,
            'flag': flag,
        })

    return rows


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _fmt_val(val, field):
    """Format a single value for display."""
    if val is None:
        return 'N/A'
    if field in PCT_FIELDS:
        return f'{val:.1f}'
    return f'{int(round(val)):,}'


def print_comparison_table(rows, primary_year, secondary_year,
                           primary_label='FMP', secondary_label='yfinance'):
    """Print formatted comparison table to terminal.

    *primary_label* / *secondary_label* control column headers.
    For US stocks: primary=FMP, secondary=yfinance (default).
    For HK stocks: primary=yfinance, secondary=FMP.
    """
    print(f"\n{S.header(f'Cross-Validation: {primary_label} vs {secondary_label} ({primary_label}: {primary_year}, {secondary_label}: {secondary_year})')}")

    # Column widths
    lbl_w = 26
    val_w = 14
    diff_w = 10

    # Header
    header = (f"  {'':>{lbl_w}}  "
              f"{primary_label:>{val_w}}  "
              f"{secondary_label:>{val_w}}  "
              f"{'Diff%':>{diff_w}}")
    print(header)
    print(f"  {'─' * (lbl_w + val_w * 2 + diff_w + 8)}")

    flag_count = 0
    for row in rows:
        field = row['field']
        primary_str = _fmt_val(row['fmp'], field)
        secondary_str = _fmt_val(row['yfinance'], field)

        if row['diff_pct'] is not None:
            diff_str = f"{row['diff_pct']:.1f}%"
        else:
            diff_str = '--'

        line = (f"  {field:<{lbl_w}}  "
                f"{primary_str:>{val_w}}  "
                f"{secondary_str:>{val_w}}  "
                f"{diff_str:>{diff_w}}")

        if row['flag']:
            print(S.warning(f"{line}  ◄"))
            flag_count += 1
        else:
            print(line)

    print(f"  {'─' * (lbl_w + val_w * 2 + diff_w + 8)}")
    if flag_count > 0:
        print(S.muted(f"  ◄ = 差异 > 5%（共 {flag_count} 项）"))
    else:
        print(S.muted("  两个数据源差异较小，数据质量良好。"))
    print()


# ---------------------------------------------------------------------------
# Entry point (called from main.py)
# ---------------------------------------------------------------------------

def cross_validate_with_yfinance(ticker, summary_df, is_ttm=False):
    """Fetch yfinance data and display comparison table.

    When *is_ttm* is True the first summary_df column is TTM data which has
    no direct yfinance equivalent.  We fall back to the second column (latest
    full-year annual data) and tell yfinance to match that year.

    Never raises — all errors handled internally.
    """
    try:
        # Decide which FMP column to compare against
        if is_ttm and len(summary_df.columns) >= 2:
            fmp_col_idx = 1  # skip TTM, use latest full-year
        else:
            fmp_col_idx = 0

        fmp_year = str(summary_df.columns[fmp_col_idx])
        fmp_series = summary_df.iloc[:, fmp_col_idx]

        if is_ttm:
            print(S.muted(f"  ⓘ 基年为 TTM，交叉验证将使用最近完整年报 ({fmp_year}) 进行对比。"))

        print(f"\n{S.info('正在从 yfinance (Yahoo Finance / Morningstar) 获取数据...')}")
        result = fetch_yfinance_data(ticker, target_year=fmp_year)

        if result is None:
            print(S.warning("  yfinance 未返回有效数据，跳过交叉验证。"))
            return

        yf_data, yf_year = result

        # Fiscal year alignment check
        yf_year_short = yf_year[:4]  # e.g. "2024-09-28" → "2024"
        if yf_year_short != fmp_year[:4]:
            print(S.muted(f"  ⓘ 注意: FMP 年报为 {fmp_year}，yfinance 匹配到 {yf_year}，年份可能不完全对齐。"))

        rows = compare_fmp_yfinance(fmp_series, yf_data)
        print_comparison_table(rows, fmp_year, yf_year)

    except ImportError:
        print(S.warning("  yfinance 未安装，跳过交叉验证。安装: pip install yfinance"))
    except Exception as e:
        print(S.warning(f"  yfinance 交叉验证出错: {e}. 继续使用 FMP 数据。"))


# ===========================================================================
# HK Stock Primary Data Source (yfinance)
# ===========================================================================
# For Hong Kong stocks (.HK), yfinance is the primary data source for all
# financial data. The functions below return FMP-compatible data structures
# so the downstream DCF/Excel code works unchanged.
# ===========================================================================


def _get_yf_currency(ticker_obj):
    """Get financial reporting currency from a yfinance Ticker object.

    Uses ``financialCurrency`` (the currency used in financial statements,
    e.g. CNY for some HK-listed companies) with ``currency`` (trading
    currency, e.g. HKD) as fallback.
    """
    info = ticker_obj.info or {}
    return info.get('financialCurrency') or info.get('currency', 'HKD')


def _yf_col_to_date_str(col):
    """Convert a yfinance column (Timestamp or str) to 'YYYY-MM-DD'."""
    if hasattr(col, 'strftime'):
        return col.strftime('%Y-%m-%d')
    return str(col)[:10]


def _yf_col_to_quarter(col):
    """Derive quarter label ('Q1'..'Q4') from a yfinance Timestamp column."""
    if hasattr(col, 'month'):
        month = col.month
    else:
        month = int(str(col)[5:7])
    return f'Q{(month - 1) // 3 + 1}'


def _yf_total_investments(bs_df, col):
    """Compute totalInvestments by summing yfinance balance-sheet components.

    Reuses the same logic as the cross-validation code (lines 160-175).
    Returns raw value (NOT divided by 1M).
    """
    components = [
        'Investmentin Financial Assets',
        'Long Term Equity Investment',
        'Other Short Term Investments',
    ]
    total = 0
    found = False
    for comp in components:
        v = _safe_get(bs_df, comp, col)
        if v is not None:
            total += v
            found = True
    return total if found else 0


# ---------------------------------------------------------------------------
# Company profile & share float
# ---------------------------------------------------------------------------

def fetch_yfinance_hk_company_profile(ticker):
    """Fetch company profile from yfinance for HK stocks.

    Returns dict with same keys as FMP ``fetch_company_profile()``,
    plus ``outstandingShares`` to avoid a separate API call.
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)
    info = t.info or {}

    print(S.info(f"Fetching company profile from yfinance for {ticker}..."))

    beta = info.get('beta')
    if beta is None or pd.isna(beta):
        beta = HK_DEFAULT_BETA

    return {
        'companyName': info.get('longName') or info.get('shortName') or ticker,
        'marketCap': info.get('marketCap', 0) or 0,
        'beta': beta,
        'country': 'Hong Kong',
        'currency': info.get('currency', 'HKD'),
        'exchange': info.get('exchange', 'HKG'),
        'price': info.get('currentPrice') or info.get('regularMarketPrice', 0) or 0,
        'outstandingShares': info.get('sharesOutstanding', 0) or 0,
    }


# ---------------------------------------------------------------------------
# Income statement
# ---------------------------------------------------------------------------

def _extract_yf_income_row(df, col, currency):
    """Extract a single income statement row from a yfinance DataFrame column."""
    date_str = _yf_col_to_date_str(col)
    year = date_str[:4]

    revenue = _safe_get(df, 'Total Revenue', col) or 0
    ebit = _safe_get(df, 'Total Operating Income As Reported', col)
    if ebit is None:
        ebit = _safe_get(df, 'Operating Income', col)
    if ebit is None:
        ebit = _safe_get(df, 'EBIT', col)
    ebit = ebit or 0

    interest_expense = _safe_get(df, 'Interest Expense', col) or 0
    interest_income = _safe_get(df, 'Interest Income', col) or 0
    pretax_income = _safe_get(df, 'Pretax Income', col) or 0
    tax_provision = _safe_get_fallback(df, ['Tax Provision', 'Income Tax Expense'], col) or 0

    return {
        'calendarYear': year,
        'date': date_str,
        'reportedCurrency': currency,
        'revenue': revenue,
        'operatingIncome': ebit,
        'interestExpense': interest_expense,
        'interestIncome': interest_income,
        'incomeBeforeTax': pretax_income,
        'incomeTaxExpense': tax_provision,
    }


def _compute_h2_income(fy_row, h1_row):
    """Compute H2 = FY - H1 for income statement fields."""
    flow_fields = ['revenue', 'operatingIncome', 'interestExpense', 'interestIncome',
                   'incomeBeforeTax', 'incomeTaxExpense']
    h2 = {
        'calendarYear': fy_row['calendarYear'],
        'date': fy_row['date'],
        'period': 'H2',
        'reportedCurrency': fy_row['reportedCurrency'],
    }
    for f in flow_fields:
        h2[f] = (fy_row.get(f, 0) or 0) - (h1_row.get(f, 0) or 0)
    return h2


def _scale_row(row, factor):
    """Scale all numeric flow fields in a row dict by *factor*.

    Used to convert a single-quarter Q2 value → estimated H1 (factor=2).
    Non-numeric / non-flow keys (calendarYear, date, period, reportedCurrency)
    are preserved as-is.
    """
    _keep = {'calendarYear', 'date', 'period', 'reportedCurrency'}
    out = {}
    for k, v in row.items():
        if k in _keep:
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = v * factor
        else:
            out[k] = v
    return out


def fetch_yfinance_hk_income_statement(ticker, period='annual', historical_periods=5):
    """Fetch income statements from yfinance for HK stocks.

    For ``period='annual'``, returns annual (FY) data.
    For ``period='quarter'``, returns semi-annual (H1/H2) data because HK stocks
    under HKFRS/IFRS typically only publish semi-annual reports.

    **Important**: yfinance ``quarterly_income_stmt`` for semi-annual reporters
    returns *Q2 standalone* figures (single quarter, ~3 months), **not**
    cumulative H1 (6-month) figures.  We therefore estimate H1 ≈ Q2 × 2, and
    derive H2 = FY − H1_est.  For the most recent year where FY is not yet
    available, we use TTM − H2_prev if TTM data exists, otherwise Q2 × 2.

    Returns ``(list_of_dicts, raw_df)`` where *list_of_dicts* uses FMP-compatible
    keys and *raw_df* is the original yfinance DataFrame for Excel export.
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)
    print(S.info(f"Fetching income statement from yfinance for {ticker}..."))

    if period == 'quarter':
        # --- Semi-annual mode for HK stocks: build H1/H2 from annual + quarterly ---
        annual_df = t.income_stmt
        quarterly_df = t.quarterly_income_stmt
        if annual_df is None or annual_df.empty:
            raise ValueError(f"No income statement data from yfinance for {ticker}")

        currency = _get_yf_currency(t)

        # Collect all valid annual columns
        fy_cols = [col for col in annual_df.columns if _safe_get(annual_df, 'Total Revenue', col) is not None]
        # Collect all valid quarterly columns with month <= 6 (Q2 standalone data)
        q2_cols = {}  # year -> col
        if quarterly_df is not None and not quarterly_df.empty:
            for col in quarterly_df.columns:
                if _safe_get(quarterly_df, 'Total Revenue', col) is not None:
                    month = col.month if hasattr(col, 'month') else int(str(col)[5:7])
                    year = str(col.year if hasattr(col, 'year') else str(col)[:4])
                    if month <= 6:
                        if year not in q2_cols:
                            q2_cols[year] = col

        # Build set of years that have FY data
        fy_years = set()
        fy_by_year = {}  # year_str -> col
        for col in fy_cols:
            yr = str(col.year if hasattr(col, 'year') else str(col)[:4])
            fy_years.add(yr)
            fy_by_year[yr] = col

        result = []
        raw_cols = []

        # ---- Build paired H2/H1 for historical years (FY + Q2 both exist) ----
        # We need these first to compute H2_prev for the TTM-based latest H1.
        h2_by_year = {}  # year_str -> h2_row (for TTM derivation)
        h1_by_year = {}  # year_str -> h1_row
        for fy_col in fy_cols:
            fy_year = str(fy_col.year if hasattr(fy_col, 'year') else str(fy_col)[:4])
            fy_row = _extract_yf_income_row(annual_df, fy_col, currency)
            fy_row['period'] = 'FY'

            q2_col = q2_cols.get(fy_year)
            if q2_col is not None:
                q2_row = _extract_yf_income_row(quarterly_df, q2_col, currency)
                # H1_est = Q2 × 2  (double single-quarter to approximate half-year)
                h1_row = _scale_row(q2_row, 2)
                h1_row['period'] = 'H1'
                h2_row = _compute_h2_income(fy_row, h1_row)
                h2_by_year[fy_year] = h2_row
                h1_by_year[fy_year] = h1_row

        # ---- Latest year H1: years with Q2 but no FY yet ----
        for q2_year in sorted(q2_cols.keys(), reverse=True):
            if q2_year not in fy_years:
                q2_col = q2_cols[q2_year]
                q2_row = _extract_yf_income_row(quarterly_df, q2_col, currency)

                # Try TTM-based derivation: H1 = TTM - H2_prev
                h1_row = None
                # Find the most recent prior year with H2 data
                prev_year = str(int(q2_year) - 1)
                h2_prev = h2_by_year.get(prev_year)
                if h2_prev is not None:
                    ttm_data = fetch_yfinance_hk_ttm(ticker)
                    if ttm_data and ttm_data.get('has_ttm_income'):
                        flow_fields = ['revenue', 'operatingIncome', 'interestExpense',
                                       'interestIncome', 'incomeBeforeTax', 'incomeTaxExpense']
                        h1_row = {
                            'calendarYear': q2_year,
                            'date': _yf_col_to_date_str(q2_col),
                            'period': 'H1',
                            'reportedCurrency': currency,
                        }
                        for f in flow_fields:
                            ttm_val = ttm_data.get(f, 0) or 0
                            h2_val = h2_prev.get(f, 0) or 0
                            h1_row[f] = ttm_val - h2_val

                # Fallback: H1 = Q2 × 2
                if h1_row is None:
                    h1_row = _scale_row(q2_row, 2)
                    h1_row['period'] = 'H1'

                result.append(h1_row)
                if len(result) >= historical_periods:
                    break

        # ---- Append historical H2/H1 pairs (or FY fallback) ----
        for fy_col in fy_cols:
            if len(result) >= historical_periods:
                break
            fy_year = str(fy_col.year if hasattr(fy_col, 'year') else str(fy_col)[:4])
            h2_row = h2_by_year.get(fy_year)
            h1_row = h1_by_year.get(fy_year)
            if h2_row is not None and h1_row is not None:
                result.append(h2_row)
                if len(result) < historical_periods:
                    result.append(h1_row)
                raw_cols.append(fy_col)
            else:
                # No Q2 data for this year → include as FY entry
                fy_row = _extract_yf_income_row(annual_df, fy_col, currency)
                fy_row['period'] = 'FY'
                result.append(fy_row)
                raw_cols.append(fy_col)

        if not result:
            print(S.muted(f"  ⓘ No semi-annual income statement data available for {ticker}"))
            return [], pd.DataFrame()

        # Build raw_df from annual data for Excel export
        raw_df = annual_df[raw_cols].copy() if raw_cols else pd.DataFrame()
        return result, raw_df

    # --- Annual mode ---
    df = t.income_stmt
    if df is None or df.empty:
        raise ValueError(f"No income statement data from yfinance for {ticker}")

    currency = _get_yf_currency(t)

    # Take all available columns (if fewer than historical_periods, use what's available)
    valid_cols = []
    for col in df.columns:
        rev = _safe_get(df, 'Total Revenue', col)
        if rev is not None:
            valid_cols.append(col)
        if len(valid_cols) >= historical_periods:
            break

    if not valid_cols:
        raise ValueError(f"No valid income statement data from yfinance for {ticker}")

    result = []
    for col in valid_cols:
        row = _extract_yf_income_row(df, col, currency)
        row['period'] = 'FY'
        result.append(row)

    raw_df = df[valid_cols].copy()
    return result, raw_df


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------

def _extract_yf_bs_row(df, col):
    """Extract a single balance sheet row from a yfinance DataFrame column."""
    total_debt = _safe_get(df, 'Total Debt', col) or 0
    total_equity = _safe_get_fallback(
        df, ['Total Equity Gross Minority Interest', 'Stockholders Equity'], col) or 0
    minority = _safe_get(df, 'Minority Interest', col) or 0
    cash = _safe_get_fallback(
        df, ['Cash And Cash Equivalents', 'Cash Cash Equivalents And Short Term Investments'], col) or 0
    total_assets = _safe_get(df, 'Total Assets', col) or 0
    total_investments = _yf_total_investments(df, col)
    date_str = _yf_col_to_date_str(col)
    return {
        'calendarYear': date_str[:4],
        'date': date_str,
        'totalDebt': total_debt,
        'totalEquity': total_equity,
        'minorityInterest': minority,
        'cashAndCashEquivalents': cash,
        'totalInvestments': total_investments,
        'totalAssets': total_assets,
    }


def fetch_yfinance_hk_balance_sheet(ticker, period='annual', historical_periods=5):
    """Fetch balance sheet from yfinance for HK stocks.

    For ``period='quarter'``, returns semi-annual (H1/H2) snapshots.
    Balance sheet is point-in-time, so H1 = mid-year snapshot, H2 = year-end (=FY).

    Returns ``(list_of_dicts, raw_df)``.
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)
    print(S.info(f"Fetching balance sheet from yfinance for {ticker}..."))

    if period == 'quarter':
        # --- Semi-annual mode: collect H1 (mid-year) and H2 (year-end) snapshots ---
        annual_df = t.balance_sheet
        quarterly_df = t.quarterly_balance_sheet
        if annual_df is None or annual_df.empty:
            raise ValueError(f"No balance sheet data from yfinance for {ticker}")

        fy_cols = [col for col in annual_df.columns if _safe_get(annual_df, 'Total Assets', col) is not None]
        h1_cols = {}  # year -> col
        if quarterly_df is not None and not quarterly_df.empty:
            for col in quarterly_df.columns:
                if _safe_get(quarterly_df, 'Total Assets', col) is not None:
                    month = col.month if hasattr(col, 'month') else int(str(col)[5:7])
                    year = str(col.year if hasattr(col, 'year') else str(col)[:4])
                    if month <= 6:
                        if year not in h1_cols:
                            h1_cols[year] = col

        fy_years = set()
        for col in fy_cols:
            fy_years.add(str(col.year if hasattr(col, 'year') else str(col)[:4]))

        result = []
        raw_cols = []

        # Standalone H1 for years without FY (current year)
        for h1_year in sorted(h1_cols.keys(), reverse=True):
            if h1_year not in fy_years:
                h1_col = h1_cols[h1_year]
                h1_row = _extract_yf_bs_row(quarterly_df, h1_col)
                h1_row['period'] = 'H1'
                result.append(h1_row)
                if len(result) >= historical_periods:
                    break

        # Paired H2/H1 (or FY fallback)
        for fy_col in fy_cols:
            if len(result) >= historical_periods:
                break
            fy_year = str(fy_col.year if hasattr(fy_col, 'year') else str(fy_col)[:4])
            fy_row = _extract_yf_bs_row(annual_df, fy_col)

            h1_col = h1_cols.get(fy_year)
            if h1_col is not None:
                fy_row['period'] = 'H2'  # year-end BS = H2 snapshot
                h1_row = _extract_yf_bs_row(quarterly_df, h1_col)
                h1_row['period'] = 'H1'
                result.append(fy_row)  # H2 first (more recent)
                if len(result) < historical_periods:
                    result.append(h1_row)
                raw_cols.append(fy_col)
            else:
                # No H1 data for this year → include as FY entry
                fy_row['period'] = 'FY'
                result.append(fy_row)
                raw_cols.append(fy_col)

        if not result:
            print(S.muted(f"  ⓘ No semi-annual balance sheet data available for {ticker}"))
            return [], pd.DataFrame()

        raw_df = annual_df[raw_cols].copy() if raw_cols else pd.DataFrame()
        return result, raw_df

    # --- Annual mode ---
    df = t.balance_sheet
    if df is None or df.empty:
        raise ValueError(f"No balance sheet data from yfinance for {ticker}")

    valid_cols = []
    for col in df.columns:
        val = _safe_get(df, 'Total Assets', col)
        if val is not None:
            valid_cols.append(col)
        if len(valid_cols) >= historical_periods:
            break
    if not valid_cols:
        raise ValueError(f"No valid balance sheet data from yfinance for {ticker}")

    result = []
    for col in valid_cols:
        row = _extract_yf_bs_row(df, col)
        row['period'] = 'FY'
        result.append(row)

    raw_df = df[valid_cols].copy()
    return result, raw_df


# ---------------------------------------------------------------------------
# Cash flow statement
# ---------------------------------------------------------------------------

def _extract_yf_cf_row(df, col):
    """Extract a single cash flow row from a yfinance DataFrame column."""
    da = _safe_get(df, 'Depreciation And Amortization', col) or 0
    capex = _safe_get(df, 'Capital Expenditure', col) or 0  # negative
    wc = _safe_get(df, 'Change In Working Capital', col) or 0
    date_str = _yf_col_to_date_str(col)
    return {
        'calendarYear': date_str[:4],
        'date': date_str,
        'depreciationAndAmortization': da,
        'investmentsInPropertyPlantAndEquipment': capex,
        'changeInWorkingCapital': wc,
    }


def _compute_h2_cashflow(fy_row, h1_row):
    """Compute H2 = FY - H1 for cash flow fields."""
    flow_fields = ['depreciationAndAmortization', 'investmentsInPropertyPlantAndEquipment',
                   'changeInWorkingCapital']
    h2 = {
        'calendarYear': fy_row['calendarYear'],
        'date': fy_row['date'],
        'period': 'H2',
    }
    for f in flow_fields:
        h2[f] = (fy_row.get(f, 0) or 0) - (h1_row.get(f, 0) or 0)
    return h2


def fetch_yfinance_hk_cashflow(ticker, period='annual', historical_periods=5):
    """Fetch cash flow statement from yfinance for HK stocks.

    For ``period='quarter'``, returns semi-annual (H1/H2) data.

    **Important**: Same Q2×2 scaling as income statement — yfinance quarterly
    data for semi-annual reporters is Q2 standalone, not cumulative H1.
    H1_est = Q2 × 2;  H2 = FY − H1_est.
    For the latest year without FY: H1 = TTM_cf − H2_prev if available,
    else Q2 × 2.

    Returns ``(list_of_dicts, raw_df)``.

    Sign conventions (matching FMP/data.py expectations):
    - ``Capital Expenditure``: yfinance reports negative → stored as-is (negative)
    - ``Change In Working Capital``: yfinance sign convention matches FMP
    - ``Depreciation And Amortization``: positive in both
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)
    print(S.info(f"Fetching cash flow statement from yfinance for {ticker}..."))

    if period == 'quarter':
        # --- Semi-annual mode: derive H1/H2 from annual + quarterly ---
        annual_df = t.cashflow
        quarterly_df = t.quarterly_cashflow
        if annual_df is None or annual_df.empty:
            raise ValueError(f"No cash flow data from yfinance for {ticker}")

        fy_cols = []
        for col in annual_df.columns:
            val = _safe_get(annual_df, 'Capital Expenditure', col)
            if val is None:
                val = _safe_get(annual_df, 'Depreciation And Amortization', col)
            if val is not None:
                fy_cols.append(col)

        q2_cols = {}  # year -> col
        if quarterly_df is not None and not quarterly_df.empty:
            for col in quarterly_df.columns:
                val = _safe_get(quarterly_df, 'Capital Expenditure', col)
                if val is None:
                    val = _safe_get(quarterly_df, 'Depreciation And Amortization', col)
                if val is not None:
                    month = col.month if hasattr(col, 'month') else int(str(col)[5:7])
                    year = str(col.year if hasattr(col, 'year') else str(col)[:4])
                    if month <= 6:
                        if year not in q2_cols:
                            q2_cols[year] = col

        fy_years = set()
        for col in fy_cols:
            fy_years.add(str(col.year if hasattr(col, 'year') else str(col)[:4]))

        result = []
        raw_cols = []

        # ---- Build paired H2/H1 for historical years first (need H2 for TTM) ----
        h2_by_year = {}
        h1_by_year = {}
        for fy_col in fy_cols:
            fy_year = str(fy_col.year if hasattr(fy_col, 'year') else str(fy_col)[:4])
            fy_row = _extract_yf_cf_row(annual_df, fy_col)
            fy_row['period'] = 'FY'

            q2_col = q2_cols.get(fy_year)
            if q2_col is not None:
                q2_row = _extract_yf_cf_row(quarterly_df, q2_col)
                h1_row = _scale_row(q2_row, 2)
                h1_row['period'] = 'H1'
                h2_row = _compute_h2_cashflow(fy_row, h1_row)
                h2_by_year[fy_year] = h2_row
                h1_by_year[fy_year] = h1_row

        # ---- Latest year H1: Q2 exists but no FY ----
        for q2_year in sorted(q2_cols.keys(), reverse=True):
            if q2_year not in fy_years:
                q2_col = q2_cols[q2_year]
                q2_row = _extract_yf_cf_row(quarterly_df, q2_col)

                # Try TTM-based: H1 = TTM_cf - H2_prev
                h1_row = None
                prev_year = str(int(q2_year) - 1)
                h2_prev = h2_by_year.get(prev_year)
                if h2_prev is not None:
                    ttm_data = fetch_yfinance_hk_ttm(ticker)
                    if ttm_data and ttm_data.get('has_ttm_cashflow'):
                        cf_fields = ['depreciationAndAmortization',
                                     'investmentsInPropertyPlantAndEquipment',
                                     'changeInWorkingCapital']
                        h1_row = {
                            'calendarYear': q2_year,
                            'date': _yf_col_to_date_str(q2_col),
                            'period': 'H1',
                        }
                        for f in cf_fields:
                            ttm_val = ttm_data.get(f, 0) or 0
                            h2_val = h2_prev.get(f, 0) or 0
                            h1_row[f] = ttm_val - h2_val

                # Fallback: H1 = Q2 × 2
                if h1_row is None:
                    h1_row = _scale_row(q2_row, 2)
                    h1_row['period'] = 'H1'

                result.append(h1_row)
                if len(result) >= historical_periods:
                    break

        # ---- Append historical H2/H1 pairs (or FY fallback) ----
        for fy_col in fy_cols:
            if len(result) >= historical_periods:
                break
            fy_year = str(fy_col.year if hasattr(fy_col, 'year') else str(fy_col)[:4])
            h2_row = h2_by_year.get(fy_year)
            h1_row = h1_by_year.get(fy_year)
            if h2_row is not None and h1_row is not None:
                result.append(h2_row)
                if len(result) < historical_periods:
                    result.append(h1_row)
                raw_cols.append(fy_col)
            else:
                # No Q2 data for this year → include as FY entry
                fy_row = _extract_yf_cf_row(annual_df, fy_col)
                fy_row['period'] = 'FY'
                result.append(fy_row)
                raw_cols.append(fy_col)

        if not result:
            print(S.muted(f"  ⓘ No semi-annual cash flow data available for {ticker}"))
            return [], pd.DataFrame()

        raw_df = annual_df[raw_cols].copy() if raw_cols else pd.DataFrame()
        return result, raw_df

    # --- Annual mode ---
    df = t.cashflow
    if df is None or df.empty:
        raise ValueError(f"No cash flow data from yfinance for {ticker}")

    # Filter out columns with no data
    valid_cols = []
    for col in df.columns:
        val = _safe_get(df, 'Capital Expenditure', col)
        if val is None:
            val = _safe_get(df, 'Depreciation And Amortization', col)
        if val is not None:
            valid_cols.append(col)
        if len(valid_cols) >= historical_periods:
            break
    if not valid_cols:
        raise ValueError(f"No valid cash flow data from yfinance for {ticker}")

    result = []
    for col in valid_cols:
        row = _extract_yf_cf_row(df, col)
        row['period'] = 'FY'
        result.append(row)

    raw_df = df[valid_cols].copy()
    return result, raw_df


# ---------------------------------------------------------------------------
# Key metrics (computed from income + balance sheet data)
# ---------------------------------------------------------------------------

def fetch_yfinance_hk_key_metrics(ticker, balance_sheets, income_statements,
                                   period='annual', historical_periods=5):
    """Compute key metrics for HK stocks from yfinance data.

    Returns list of FMP-compatible dicts.
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)
    info = t.info or {}
    print(S.info(f"Computing key metrics from yfinance for {ticker}..."))

    # Use trailingAnnualDividendYield (more reliable than forward dividendYield)
    div_yield = info.get('trailingAnnualDividendYield', 0) or 0
    payout = info.get('payoutRatio', 0) or 0

    result = []
    for i in range(len(balance_sheets)):
        bs = balance_sheets[i]
        inc = income_statements[i] if i < len(income_statements) else {}

        total_assets = bs.get('totalAssets', 0) or 1
        total_debt = bs.get('totalDebt', 0) or 0
        debt_to_assets = total_debt / total_assets if total_assets != 0 else 0

        ebit = inc.get('operatingIncome', 0) or 0
        pbt = inc.get('incomeBeforeTax', 0) or 0
        tax = inc.get('incomeTaxExpense', 0) or 0
        tax_rate = tax / pbt if pbt != 0 else 0.25

        total_equity = bs.get('totalEquity', 0) or 0
        cash = bs.get('cashAndCashEquivalents', 0) or 0
        investments = bs.get('totalInvestments', 0) or 0
        ic = total_debt + total_equity - cash - investments
        roic = ebit * (1 - tax_rate) / ic if ic != 0 else 0

        net_income = pbt - tax
        roe = net_income / total_equity if total_equity != 0 else 0

        result.append({
            'debtToAssets': debt_to_assets,
            'roic': roic,
            'roe': roe,
            'dividendYield': div_yield,
            'payoutRatio': payout,
        })

    return result


# ---------------------------------------------------------------------------
# TTM data (yfinance built-in TTM)
# ---------------------------------------------------------------------------

def fetch_yfinance_hk_ttm(ticker):
    """Fetch TTM income statement and cash flow from yfinance for HK stocks.

    yfinance provides pre-computed TTM data via ``Ticker.ttm_income_stmt`` and
    ``Ticker.ttm_cash_flow``.  These may contain Q1/Q3 data that is NOT exposed
    in ``quarterly_income_stmt`` for semi-annual reporters (e.g. Tencent, Xiaomi).

    Returns a dict::

        {
            'has_ttm_income': bool,
            'ttm_end_date': str,           # e.g. '2025-06-30'
            'ttm_quarter': str,            # e.g. 'Q2'
            'revenue': float,              # raw value (not millions)
            'operatingIncome': float,
            'incomeBeforeTax': float,
            'incomeTaxExpense': float,
            'interestExpense': float,
            'interestIncome': float,
            'has_ttm_cashflow': bool,
            'cf_end_date': str,
            'depreciationAndAmortization': float or None,
            'investmentsInPropertyPlantAndEquipment': float or None,
            'changeInWorkingCapital': float or None,
        }

    Returns None if no TTM data is available.
    """
    yf = _get_yf()
    t = yf.Ticker(ticker)

    ttm_inc = t.ttm_income_stmt
    if ttm_inc is None or ttm_inc.empty:
        return None

    col = ttm_inc.columns[0]
    ttm_date = _yf_col_to_date_str(col)
    ttm_quarter = _yf_col_to_quarter(col)
    currency = _get_yf_currency(t)

    def _val(df, field):
        if field not in df.index:
            return None
        v = df.loc[field, col]
        return None if pd.isna(v) else float(v)

    revenue = _val(ttm_inc, 'Total Revenue') or 0
    ebit = _val(ttm_inc, 'Total Operating Income As Reported')
    if ebit is None:
        ebit = _val(ttm_inc, 'Operating Income')
    if ebit is None:
        ebit = _val(ttm_inc, 'EBIT')
    ebit = ebit or 0

    pbt = _val(ttm_inc, 'Pretax Income') or 0
    tax = _safe_get_fallback(ttm_inc, ['Tax Provision', 'Income Tax Expense'], col) or 0
    interest_exp = _val(ttm_inc, 'Interest Expense') or 0
    interest_inc = _val(ttm_inc, 'Interest Income') or 0

    result = {
        'has_ttm_income': True,
        'ttm_end_date': ttm_date,
        'ttm_quarter': ttm_quarter,
        'reportedCurrency': currency,
        'revenue': revenue,
        'operatingIncome': ebit,
        'incomeBeforeTax': pbt,
        'incomeTaxExpense': tax,
        'interestExpense': interest_exp,
        'interestIncome': interest_inc,
    }

    # Cash flow TTM
    ttm_cf = t.ttm_cash_flow
    if ttm_cf is not None and not ttm_cf.empty:
        col_cf = ttm_cf.columns[0]
        cf_date = _yf_col_to_date_str(col_cf)

        def _cf_val(field):
            if field not in ttm_cf.index:
                return None
            v = ttm_cf.loc[field, col_cf]
            return None if pd.isna(v) else float(v)

        da = _cf_val('Depreciation And Amortization')
        capex = _cf_val('Capital Expenditure')  # negative
        wc = _cf_val('Change In Working Capital')

        result['has_ttm_cashflow'] = (da is not None or capex is not None)
        result['cf_end_date'] = cf_date
        result['depreciationAndAmortization'] = da
        result['investmentsInPropertyPlantAndEquipment'] = capex
        result['changeInWorkingCapital'] = wc
    else:
        result['has_ttm_cashflow'] = False
        result['cf_end_date'] = ''
        result['depreciationAndAmortization'] = None
        result['investmentsInPropertyPlantAndEquipment'] = None
        result['changeInWorkingCapital'] = None

    return result


# ---------------------------------------------------------------------------
# Forex helper (yfinance fallback when no FMP API key)
# ---------------------------------------------------------------------------

def fetch_forex_yfinance(from_currency, to_currency):
    """Fetch forex rate using yfinance currency pair ticker (e.g. CNYHKD=X).

    Returns float rate or None on failure.
    """
    try:
        yf = _get_yf()
        pair = f"{from_currency}{to_currency}=X"
        t = yf.Ticker(pair)
        info = t.info or {}
        rate = info.get('regularMarketPrice') or info.get('previousClose')
        if rate and not pd.isna(rate):
            return float(rate)
    except Exception:
        pass
    return None


# ===========================================================================
# HK Stock Cross-Validation with FMP
# ===========================================================================
# For Hong Kong stocks, yfinance is the primary data source. These functions
# fetch FMP data as a secondary source for cross-validation comparison.
# ===========================================================================


def fetch_fmp_hk_annual_data(ticker, apikey, target_year=None):
    """Fetch annual financial data from FMP for an HK stock (cross-validation).

    Returns ``(data_dict, fiscal_year_str)`` or None on failure.
    *data_dict* keys match FMP summary row names; values are in millions.
    """
    from concurrent.futures import ThreadPoolExecutor
    from .data import get_api_url, get_jsonparsed_data

    try:
        urls = {
            'income': get_api_url('income-statement', ticker, 'annual', apikey),
            'balance': get_api_url('balance-sheet-statement', ticker, 'annual', apikey),
            'cashflow': get_api_url('cash-flow-statement', ticker, 'annual', apikey),
        }
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {k: ex.submit(get_jsonparsed_data, v) for k, v in urls.items()}
        inc_list = futures['income'].result()
        bs_list = futures['balance'].result()
        cf_list = futures['cashflow'].result()
    except Exception:
        return None

    if not inc_list:
        return None

    # Find the entry matching target_year
    inc = None
    if target_year is not None:
        ty = str(target_year)[:4]
        for entry in inc_list:
            if str(entry.get('calendarYear', ''))[:4] == ty:
                inc = entry
                break
    if inc is None:
        inc = inc_list[0]

    year_str = inc.get('calendarYear', '')
    date_str = inc.get('date', str(year_str))

    # Match BS and CF by calendarYear
    bs = next((b for b in bs_list if str(b.get('calendarYear', ''))[:4] == str(year_str)[:4]), bs_list[0] if bs_list else {})
    cf = next((c for c in cf_list if str(c.get('calendarYear', ''))[:4] == str(year_str)[:4]), cf_list[0] if cf_list else {})

    def _v(d, key):
        val = d.get(key, 0)
        return float(val) if val is not None and not pd.isna(val) else 0

    revenue = _v(inc, 'revenue') / 1_000_000
    ebit = _v(inc, 'operatingIncome') / 1_000_000

    data = {
        'Revenue': revenue,
        'EBIT': ebit,
        'EBIT Margin (%)': (ebit / revenue * 100) if revenue != 0 else None,
        '(+) Capital Expenditure': -_v(cf, 'investmentsInPropertyPlantAndEquipment') / 1_000_000,
        '(-) D&A': _v(cf, 'depreciationAndAmortization') / 1_000_000,
        '(+) ΔWorking Capital': -_v(cf, 'changeInWorkingCapital') / 1_000_000,
        '(+) Total Debt': _v(bs, 'totalDebt') / 1_000_000,
        '(+) Total Equity': _v(bs, 'totalEquity') / 1_000_000,
        '(-) Cash & Equivalents': _v(bs, 'cashAndCashEquivalents') / 1_000_000,
        '(-) Total Investments': _v(bs, 'totalInvestments') / 1_000_000,
        'Minority Interest': _v(bs, 'minorityInterest') / 1_000_000,
    }

    # Tax Rate
    pbt = _v(inc, 'incomeBeforeTax')
    tax = _v(inc, 'incomeTaxExpense')
    data['Tax Rate (%)'] = (tax / pbt * 100) if pbt != 0 else None

    return data, date_str


def cross_validate_hk_with_fmp(ticker, summary_df, apikey, is_ttm=False):
    """Fetch FMP data for an HK stock and display cross-validation table.

    yfinance is the primary source; FMP is the secondary cross-validation.
    Requires FMP API key. Never raises — all errors handled internally.
    """
    if not apikey:
        print(S.muted("  ⓘ 无 FMP API key，跳过交叉验证。"))
        return

    try:
        # Decide which column to compare (skip TTM if present)
        if is_ttm and len(summary_df.columns) >= 2:
            col_idx = 1  # skip TTM, use latest full-year
        else:
            col_idx = 0

        yf_year = str(summary_df.columns[col_idx])
        yf_series = summary_df.iloc[:, col_idx]

        if is_ttm:
            print(S.muted(f"  ⓘ 基年为 TTM，交叉验证将使用最近完整年报 ({yf_year}) 进行对比。"))

        print(f"\n{S.info('正在从 FMP (Financial Modeling Prep) 获取交叉验证数据...')}")
        result = fetch_fmp_hk_annual_data(ticker, apikey, target_year=yf_year)

        if result is None:
            print(S.warning("  FMP 未返回有效数据，跳过交叉验证。"))
            return

        fmp_data, fmp_year = result

        # Year alignment check
        fmp_year_short = fmp_year[:4]
        if fmp_year_short != str(yf_year)[:4]:
            print(S.muted(f"  ⓘ 注意: yfinance 年报为 {yf_year}，FMP 匹配到 {fmp_year}，年份可能不完全对齐。"))

        # Reuse compare_fmp_yfinance but swap roles:
        # "fmp" slot = yfinance (primary), "yfinance" slot = FMP (secondary)
        rows = compare_fmp_yfinance(yf_series, fmp_data)
        print_comparison_table(rows, yf_year, fmp_year,
                               primary_label='yfinance', secondary_label='FMP')

    except Exception as e:
        print(S.warning(f"  FMP 交叉验证出错: {e}. 继续使用 yfinance 数据。"))
