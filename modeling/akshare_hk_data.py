"""Hong Kong stock financial data from akshare (东方财富 EastMoney).

Primary data source for HK stocks. yfinance is retained as a secondary
cross-validation source and can be removed once enough stocks are verified.

API: ak.stock_financial_hk_report_em(stock, symbol, indicator)
  - stock: "00700" (5-digit padded code)
  - symbol: "利润表" | "资产负债表" | "现金流量表"
  - indicator: "年度" (annual) | "报告期" (all periods, cumulative YTD)

Data format: flat rows with (REPORT_DATE, STD_ITEM_CODE, STD_ITEM_NAME, AMOUNT).
Each report date has multiple rows (one per financial item).
Quarterly data is cumulative (YTD), same as A-shares.
"""

import pandas as pd

# Lazy akshare import — reuse the global instance from data.py
ak = None


def _get_ak():
    global ak
    if ak is None:
        import akshare as _ak
        ak = _ak
    return ak


def _safe(val):
    """Convert to float, treating None/NaN as 0."""
    if val is None:
        return 0.0
    try:
        v = float(val)
        return 0.0 if pd.isna(v) else v
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Ticker conversion
# ---------------------------------------------------------------------------

def _ticker_hk_to_ak(ticker):
    """Convert '0700.HK' or '00700.HK' to '00700' (5-digit padded)."""
    code = ticker.upper().replace('.HK', '')
    return code.zfill(5)


# ---------------------------------------------------------------------------
# Internal pivot helper
# ---------------------------------------------------------------------------

def _pivot_report(df):
    """Pivot flat akshare HK data into {report_date: {item_code: amount}}.

    Returns dict of dicts, plus sorted list of report dates (descending).
    """
    grouped = {}
    for _, row in df.iterrows():
        date_str = str(row['REPORT_DATE'])[:10]
        code = str(row['STD_ITEM_CODE'])
        amount = _safe(row.get('AMOUNT'))
        grouped.setdefault(date_str, {})[code] = amount
    dates = sorted(grouped.keys(), reverse=True)
    return grouped, dates


def _build_raw_excel_df(df):
    """Build transposed DataFrame for Excel export from HK akshare data.

    Pivot: rows = STD_ITEM_NAME, columns = REPORT_DATE.
    """
    # Get unique dates and items
    dates = sorted(df['REPORT_DATE'].unique(), reverse=True)

    pivot = df.pivot_table(
        index='STD_ITEM_NAME',
        columns='REPORT_DATE',
        values='AMOUNT',
        aggfunc='first',
    )
    # Sort columns by date descending
    pivot = pivot.reindex(columns=sorted(pivot.columns, reverse=True))
    # Format column names
    pivot.columns = [str(c)[:10] for c in pivot.columns]
    return pivot


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

# STD_ITEM_CODE mapping for income statement
_IS_CODES = {
    'revenue':        '004001999',  # 营运收入
    'operating':      '004010999',  # 经营溢利 (≈ EBIT)
    'int_income':     '004011200',  # 利息收入
    'fin_cost':       '004011201',  # 融资成本
    'ebt':            '004011999',  # 除税前溢利
    'tax':            '004012001',  # 税项
}


def _get_fy_dates(df):
    """Identify FY dates from a DataFrame using DATE_TYPE_CODE='001'."""
    fy_dates = set()
    for _, row in df.iterrows():
        if str(row.get('DATE_TYPE_CODE', '')) == '001':
            fy_dates.add(str(row['REPORT_DATE'])[:10])
    return fy_dates


def fetch_akshare_hk_income_statement(ticker, period='annual', historical_periods=5):
    """Fetch HK income statements from akshare.

    Always fetches '报告期' (all periods) to support TTM computation.
    For annual mode, filters to FY dates using DATE_TYPE_CODE.

    Returns (result_list, raw_df, full_cumulative_df) — same triple as A-share version.
    """
    stock = _ticker_hk_to_ak(ticker)
    from . import style as S
    print(S.info(f"Fetching HK income statement from akshare for {stock}..."))

    # Always fetch all periods for TTM support
    full_df = _get_ak().stock_financial_hk_report_em(
        stock=stock, symbol='利润表', indicator='报告期')

    full_cumulative_df = full_df.copy()
    grouped, dates = _pivot_report(full_df)

    if period == 'annual':
        # Filter to FY dates only (DATE_TYPE_CODE='001')
        fy_dates = _get_fy_dates(full_df)
        dates = [d for d in dates if d in fy_dates]

    dates = dates[:historical_periods]

    month_to_quarter = {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}
    result = []

    for date_str in dates:
        items = grouped.get(date_str, {})
        year = date_str[:4]
        month = int(date_str[5:7])

        if period == 'annual':
            period_name = 'FY'
        else:
            period_name = month_to_quarter.get(month, f'Q{(month - 1) // 3 + 1}')

        result.append({
            'calendarYear': year,
            'date': date_str,
            'period': period_name,
            'reportedCurrency': 'HKD',  # default; may be CNY for some stocks
            'revenue':          items.get(_IS_CODES['revenue'], 0),
            'operatingIncome':  items.get(_IS_CODES['operating'], 0),
            'interestExpense':  items.get(_IS_CODES['fin_cost'], 0),
            'interestIncome':   items.get(_IS_CODES['int_income'], 0),
            'incomeBeforeTax':  items.get(_IS_CODES['ebt'], 0),
            'incomeTaxExpense': items.get(_IS_CODES['tax'], 0),
        })

    # Build raw_df for Excel (only the selected dates)
    selected_dates_set = set(dates)
    mask = full_df['REPORT_DATE'].apply(lambda x: str(x)[:10] in selected_dates_set)
    raw_df = _build_raw_excel_df(full_df[mask])

    return result, raw_df, full_cumulative_df


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------

# STD_ITEM_CODE mapping for balance sheet
_BS_CODES = {
    # Debt components
    'short_loan':        '004011010',  # 短期贷款
    'notes_current':     '004011002',  # 应付票据
    'lease_current':     '004011006',  # 融资租赁负债(流动)
    'long_loan':         '004020001',  # 长期贷款
    'notes_noncurrent':  '004020018',  # 应付票据(非流动)
    'lease_noncurrent':  '004020005',  # 融资租赁负债(非流动)
    'conv_bonds':        '004020007',  # 可转换票据及债券 (e.g. Alibaba)
    # Equity — use 总权益 (incl. minority) to match yfinance's
    # "Total Equity Gross Minority Interest" convention
    'equity':            '004036999',  # 总权益 (shareholders + minority)
    'minority':          '004027999',  # 少数股东权益
    # Cash — only cash & equivalents (no short-term deposits, matching yfinance)
    'cash':              '004002010',  # 现金及等价物
    # Investments — include deposits (matching yfinance convention)
    'associates':        '004001013',  # 联营公司权益
    'jv':                '004001016',  # 合营公司权益
    'fv_assets':         '004001022',  # 指定以公允价值记账之金融资产
    'fv_assets_current': '004002013',  # 指定以公允价值记账之金融资产(流动)
    'other_fin_nc':      '004001031',  # 其他金融资产(非流动)
    'other_fin_current': '004002022',  # 其他金融资产(流动)
    'short_deposits':    '004002011',  # 短期存款
    'long_deposits':     '004001030',  # 中长期存款
    'long_invest':       '004001017',  # 长期投资
    'other_invest':      '004001019',  # 其他投资
    'short_invest':      '004002008',  # 短期投资
    'securities':        '004001018',  # 证券投资 (e.g. Alibaba)
    # Total
    'total_assets':      '004009999',  # 总资产
}


def _parse_hk_bs(items):
    """Parse balance sheet items dict into FMP-compatible dict.

    Convention alignment with yfinance:
    - totalEquity = 总权益 (includes minority interest)
    - cashAndCashEquivalents = 现金及等价物 only (no deposits)
    - totalInvestments includes deposits (short + long term)
    """
    total_debt = (
        items.get(_BS_CODES['short_loan'], 0) +
        items.get(_BS_CODES['notes_current'], 0) +
        items.get(_BS_CODES['lease_current'], 0) +
        items.get(_BS_CODES['long_loan'], 0) +
        items.get(_BS_CODES['notes_noncurrent'], 0) +
        items.get(_BS_CODES['lease_noncurrent'], 0) +
        items.get(_BS_CODES['conv_bonds'], 0)
    )

    cash = items.get(_BS_CODES['cash'], 0)

    total_investments = (
        items.get(_BS_CODES['associates'], 0) +
        items.get(_BS_CODES['jv'], 0) +
        items.get(_BS_CODES['fv_assets'], 0) +
        items.get(_BS_CODES['fv_assets_current'], 0) +
        items.get(_BS_CODES['other_fin_nc'], 0) +
        items.get(_BS_CODES['other_fin_current'], 0) +
        items.get(_BS_CODES['short_deposits'], 0) +
        items.get(_BS_CODES['long_deposits'], 0) +
        items.get(_BS_CODES['long_invest'], 0) +
        items.get(_BS_CODES['other_invest'], 0) +
        items.get(_BS_CODES['short_invest'], 0) +
        items.get(_BS_CODES['securities'], 0)
    )

    return {
        'totalDebt':                total_debt,
        'totalEquity':              items.get(_BS_CODES['equity'], 0),
        'minorityInterest':         items.get(_BS_CODES['minority'], 0),
        'cashAndCashEquivalents':   cash,
        'totalInvestments':         total_investments,
        'totalAssets':              items.get(_BS_CODES['total_assets'], 0),
    }


def fetch_akshare_hk_balance_sheet(ticker, period='annual', historical_periods=5):
    """Fetch HK balance sheet from akshare.

    Always fetches '报告期' (all periods) so that full_df contains quarterly BS
    for TTM balance-sheet lookups. For annual mode, filters to FY dates via
    DATE_TYPE_CODE.

    Returns (result_list, raw_df, full_df) — same triple as A-share version.
    """
    stock = _ticker_hk_to_ak(ticker)
    from . import style as S
    print(S.info(f"Fetching HK balance sheet from akshare for {stock}..."))

    # Always fetch all periods (needed for TTM BS lookup)
    full_df = _get_ak().stock_financial_hk_report_em(
        stock=stock, symbol='资产负债表', indicator='报告期')

    grouped, dates = _pivot_report(full_df)

    if period == 'annual':
        # Filter to FY dates only (DATE_TYPE_CODE='001')
        fy_dates = _get_fy_dates(full_df)
        dates = [d for d in dates if d in fy_dates]

    dates = dates[:historical_periods]

    result = []
    for date_str in dates:
        items = grouped.get(date_str, {})
        bs_dict = _parse_hk_bs(items)
        bs_dict['date'] = date_str          # add date for matching
        result.append(bs_dict)

    selected_dates_set = set(dates)
    mask = full_df['REPORT_DATE'].apply(lambda x: str(x)[:10] in selected_dates_set)
    raw_df = _build_raw_excel_df(full_df[mask])

    return result, raw_df, full_df


# ---------------------------------------------------------------------------
# Cash Flow Statement
# ---------------------------------------------------------------------------

# STD_ITEM_CODE mapping for cash flow
_CF_CODES = {
    'da':              '001009',  # 折旧及摊销
    'capex_fixed':     '005005',  # 购建固定资产
    'capex_intang':    '005007',  # 购建无形资产及其他资产
    # Working capital change items (002xxx, excluding subtotal 002999)
}

# Working capital item codes prefix
_WC_PREFIX = '002'
_WC_SUBTOTAL = '002999'


def _parse_hk_cf(items):
    """Parse cash flow items dict into FMP-compatible dict."""
    da = items.get(_CF_CODES['da'], 0)

    # CapEx: negative (FMP convention: cash outflow is negative)
    capex_fixed = items.get(_CF_CODES['capex_fixed'], 0)
    capex_intang = items.get(_CF_CODES['capex_intang'], 0)
    capex = -(capex_fixed + capex_intang)

    # Working capital change: sum all 002xxx items except 002999 subtotal
    wc_change = sum(
        v for k, v in items.items()
        if k.startswith(_WC_PREFIX) and k != _WC_SUBTOTAL
    )

    return {
        'depreciationAndAmortization': da,
        'investmentsInPropertyPlantAndEquipment': capex,
        'changeInWorkingCapital': wc_change,
    }


def fetch_akshare_hk_cashflow(ticker, period='annual', historical_periods=5):
    """Fetch HK cash flow statement from akshare.

    Always fetches '报告期' (all periods) for TTM support.
    For annual mode, filters to FY dates using DATE_TYPE_CODE.

    Returns (result_list, raw_df, full_cumulative_df).
    IMPORTANT: quarterly data from akshare is cumulative (YTD), same as A-shares.
    """
    stock = _ticker_hk_to_ak(ticker)
    from . import style as S
    print(S.info(f"Fetching HK cash flow statement from akshare for {stock}..."))

    # Always fetch all periods for TTM support
    full_df = _get_ak().stock_financial_hk_report_em(
        stock=stock, symbol='现金流量表', indicator='报告期')

    full_cumulative_df = full_df.copy()
    grouped, dates = _pivot_report(full_df)

    if period == 'annual':
        # Filter to FY dates only (DATE_TYPE_CODE='001')
        fy_dates = _get_fy_dates(full_df)
        dates = [d for d in dates if d in fy_dates]

    dates = dates[:historical_periods]

    result = []
    for date_str in dates:
        items = grouped.get(date_str, {})
        result.append(_parse_hk_cf(items))

    selected_dates_set = set(dates)
    mask = full_df['REPORT_DATE'].apply(lambda x: str(x)[:10] in selected_dates_set)
    raw_df = _build_raw_excel_df(full_df[mask])

    return result, raw_df, full_cumulative_df


# ---------------------------------------------------------------------------
# Key Metrics (computed from balance sheet + income statement data)
# ---------------------------------------------------------------------------

def fetch_akshare_hk_key_metrics(ticker, balance_sheets, income_statements,
                                  period='annual', historical_periods=5):
    """Compute key metrics for HK stocks from already-fetched data.

    No additional API call needed — computed from BS and IS data.
    Returns list of dicts with same keys as A-share version.
    """
    result = []
    for i in range(len(balance_sheets)):
        bs = balance_sheets[i]

        total_assets = bs.get('totalAssets', 0) or 1
        total_debt = bs.get('totalDebt', 0) or 0
        total_equity = bs.get('totalEquity', 0) or 0
        debt_to_assets = total_debt / total_assets if total_assets else 0

        # ROIC = EBIT * (1 - tax rate) / invested capital
        roic_val = 0
        roe_val = 0
        if i < len(income_statements):
            inc = income_statements[i]
            ebit = inc.get('operatingIncome', 0) or 0
            ebt = inc.get('incomeBeforeTax', 0) or 0
            tax = inc.get('incomeTaxExpense', 0) or 0
            tax_rate = tax / ebt if ebt else 0

            cash = bs.get('cashAndCashEquivalents', 0) or 0
            investments = bs.get('totalInvestments', 0) or 0
            invested_capital = total_debt + total_equity - cash - investments
            if invested_capital > 0:
                roic_val = ebit * (1 - tax_rate) / invested_capital

            net_income = ebt - tax
            if total_equity > 0:
                roe_val = net_income / total_equity

        result.append({
            'debtToAssets': debt_to_assets,
            'roic': roic_val,
            'roe': roe_val,
        })

    return result


# ---------------------------------------------------------------------------
# Company Profile
# ---------------------------------------------------------------------------

def fetch_akshare_hk_company_profile(ticker):
    """Fetch HK company profile from akshare sources.

    Combines data from multiple lightweight APIs:
    - stock_hk_hist: latest price
    - stock_individual_basic_info_hk_xq: company name
    - stock_hk_valuation_baidu: market cap

    Falls back to yfinance for richer data when available.
    Returns dict with same keys as fetch_company_profile.
    """
    from . import style as S
    stock = _ticker_hk_to_ak(ticker)
    print(S.info(f"Fetching HK company profile for {stock}..."))

    # Default values
    profile = {
        'companyName': ticker,
        'marketCap': 0,
        'beta': 1.0,
        'country': 'Hong Kong',
        'currency': 'HKD',
        'exchange': 'HKEX',
        'price': 0,
        'outstandingShares': 0,
    }

    # 1. Try yfinance first (richer data, works locally)
    try:
        from .yfinance_data import fetch_yfinance_hk_company_profile
        yf_profile = fetch_yfinance_hk_company_profile(ticker)
        if yf_profile and yf_profile.get('price', 0):
            print(S.info("  ✓ Company profile from yfinance"))
            return yf_profile
    except Exception:
        pass

    # 2. Fallback: akshare sources
    # Price from historical data (fast, single stock)
    try:
        hist = _get_ak().stock_hk_hist(symbol=stock, period='daily', adjust='')
        if not hist.empty:
            profile['price'] = float(hist.iloc[-1]['收盘'])
    except Exception as e:
        print(S.warning(f"  Failed to get HK price: {e}"))

    # Company name from xueqiu
    try:
        info_df = _get_ak().stock_individual_basic_info_hk_xq(symbol=stock)
        info_dict = dict(zip(info_df['item'], info_df['value']))
        name = info_dict.get('comcnname', '') or info_dict.get('comenname', '')
        if name:
            profile['companyName'] = str(name)
    except Exception:
        pass

    # Market cap from Baidu (unit: 亿港元)
    try:
        val_df = _get_ak().stock_hk_valuation_baidu(
            symbol=stock, indicator='总市值', period='近一年')
        if not val_df.empty:
            mktcap_yi = float(val_df.iloc[-1]['value'])  # 亿港元
            profile['marketCap'] = mktcap_yi * 1e8  # convert to HKD
            if profile['price'] > 0:
                profile['outstandingShares'] = profile['marketCap'] / profile['price']
    except Exception:
        pass

    return profile


# ---------------------------------------------------------------------------
# TTM helpers (reuse cumulative YTD method, same as A-shares)
# ---------------------------------------------------------------------------

def _compute_hk_ttm_income(ticker, full_cumulative_df=None):
    """Compute TTM income for HK stocks using YTD cumulative method.

    TTM = latest YTD + (prior FY − prior same-period YTD)

    Handles non-December fiscal years (e.g. Alibaba March FY) by using
    DATE_TYPE_CODE='001' to identify FY dates instead of hardcoding month 12.

    Returns dict with TTM fields or None if insufficient data.
    """
    if full_cumulative_df is None or full_cumulative_df.empty:
        return None

    grouped, dates = _pivot_report(full_cumulative_df)
    if len(dates) < 2:
        return None

    # Identify FY dates using DATE_TYPE_CODE (works for any FY month)
    fy_dates = _get_fy_dates(full_cumulative_df)

    latest_date = dates[0]
    latest_month = int(latest_date[5:7])
    latest_year = int(latest_date[:4])

    # If latest is already an FY, no TTM needed
    if latest_date in fy_dates:
        return None

    latest_items = grouped[latest_date]

    # Find prior FY date (the most recent FY before the latest date)
    prior_fy_date = None
    for d in dates:
        if d in fy_dates and d < latest_date:
            prior_fy_date = d
            break
    if not prior_fy_date:
        return None
    prior_fy_items = grouped[prior_fy_date]

    # Find prior same-period YTD (same month/day, one year earlier)
    target_mmdd = latest_date[5:]  # "MM-DD"
    prior_same_date = None
    for d in dates:
        if d < latest_date and d[5:] == target_mmdd and d[:4] != latest_date[:4]:
            prior_same_date = d
            break
    if not prior_same_date:
        return None
    prior_same_items = grouped[prior_same_date]

    # TTM = latest YTD + (prior FY - prior same-period YTD)
    def ttm_val(code):
        return (latest_items.get(code, 0) +
                prior_fy_items.get(code, 0) -
                prior_same_items.get(code, 0))

    month_to_quarter = {3: 'Q1', 6: 'Q2', 9: 'Q3'}

    return {
        'calendarYear': str(latest_year),
        'date': latest_date,
        'period': 'TTM',
        'reportedCurrency': 'HKD',
        'revenue':          ttm_val(_IS_CODES['revenue']),
        'operatingIncome':  ttm_val(_IS_CODES['operating']),
        'interestExpense':  ttm_val(_IS_CODES['fin_cost']),
        'interestIncome':   ttm_val(_IS_CODES['int_income']),
        'incomeBeforeTax':  ttm_val(_IS_CODES['ebt']),
        'incomeTaxExpense': ttm_val(_IS_CODES['tax']),
        '_latest_quarter':  month_to_quarter.get(latest_month, f'Q{(latest_month-1)//3+1}'),
        '_latest_date':     latest_date,
    }


def _compute_hk_ttm_cashflow(ticker, full_cumulative_df=None):
    """Compute TTM cash flow for HK stocks using YTD cumulative method.

    Handles non-December fiscal years using DATE_TYPE_CODE='001'.
    Returns dict with TTM cashflow fields or None.
    """
    if full_cumulative_df is None or full_cumulative_df.empty:
        return None

    grouped, dates = _pivot_report(full_cumulative_df)
    if len(dates) < 2:
        return None

    # Identify FY dates using DATE_TYPE_CODE (works for any FY month)
    fy_dates = _get_fy_dates(full_cumulative_df)

    latest_date = dates[0]
    latest_year = int(latest_date[:4])

    # If latest is already an FY, no TTM needed
    if latest_date in fy_dates:
        return None

    latest_items = grouped[latest_date]

    # Find prior FY date (most recent FY before latest date)
    prior_fy_date = None
    for d in dates:
        if d in fy_dates and d < latest_date:
            prior_fy_date = d
            break
    if not prior_fy_date:
        return None
    prior_fy_items = grouped[prior_fy_date]

    # Find prior same-period YTD (same month/day, one year earlier)
    target_mmdd = latest_date[5:]
    prior_same_date = None
    for d in dates:
        if d < latest_date and d[5:] == target_mmdd and d[:4] != latest_date[:4]:
            prior_same_date = d
            break
    if not prior_same_date:
        return None
    prior_same_items = grouped[prior_same_date]

    def ttm_val(code):
        return (latest_items.get(code, 0) +
                prior_fy_items.get(code, 0) -
                prior_same_items.get(code, 0))

    # D&A
    da = ttm_val(_CF_CODES['da'])

    # CapEx
    capex = -(ttm_val(_CF_CODES['capex_fixed']) + ttm_val(_CF_CODES['capex_intang']))

    # Working capital change
    def ttm_wc():
        """Sum all 002xxx items TTM."""
        wc_codes = set()
        for items in [latest_items, prior_fy_items, prior_same_items]:
            wc_codes.update(k for k in items if k.startswith(_WC_PREFIX) and k != _WC_SUBTOTAL)
        return sum(ttm_val(code) for code in wc_codes)

    wc = ttm_wc()

    return {
        'depreciationAndAmortization': da,
        'investmentsInPropertyPlantAndEquipment': capex,
        'changeInWorkingCapital': wc,
    }
