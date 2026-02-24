from urllib.request import urlopen
import re, json, traceback
import pandas as pd
from . import style as S
from .constants import CHINA_DEFAULT_BETA

# Lazy-loaded: akshare is only needed for A-shares and takes ~1s to import
ak = None

def _get_ak():
    """Lazy import akshare on first use."""
    global ak
    if ak is None:
        import akshare as _ak
        ak = _ak
    return ak


def _normalize_ticker(ticker):
    """Normalize ticker: convert .SH alias to .SS for internal consistency.

    Shanghai Stock Exchange uses .SS (Yahoo/FMP convention). Users may also enter
    .SH (intuitive Chinese abbreviation 上海=SH). Both are accepted, but .SH is
    auto-converted to .SS internally since FMP and other data sources use .SS.
    """
    t = ticker.strip().upper()
    if t.endswith('.SH'):
        return t[:-3] + '.SS'
    return t


def is_a_share(ticker):
    """Return True if ticker is a Chinese A-share (SSE/SZSE)."""
    t = _normalize_ticker(ticker)
    return t.endswith('.SS') or t.endswith('.SZ')


def is_hk_stock(ticker):
    """Return True if ticker is a Hong Kong stock (.HK)."""
    t = _normalize_ticker(ticker)
    return t.endswith('.HK')


def _is_web_mode():
    """Check if running inside Streamlit web app (vs terminal CLI).

    Used to select HK data source:
    - Terminal → yfinance (richer Morningstar data)
    - Web (local + Cloud) → akshare (东方财富)
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            import logging
            _st_logger = logging.getLogger('streamlit.runtime.scriptrunner_utils.script_run_context')
            _prev_level = _st_logger.level
            _st_logger.setLevel(logging.ERROR)
            try:
                return get_script_run_ctx() is not None
            finally:
                _st_logger.setLevel(_prev_level)
    except Exception:
        return False


def _is_cloud_mode():
    """Check if running on Streamlit Community Cloud (vs local Streamlit or terminal).

    Cloud has restricted network: push2.eastmoney.com, push2his.eastmoney.com,
    stock_individual_info_em, and yfinance are all blocked.
    Local Streamlit and terminal have full network access.

    Detection: Cloud runs as ``/home/appuser`` with source mounted at ``/mount/src``.
    """
    import os
    return os.environ.get('HOME') == '/home/appuser' or os.path.exists('/mount/src')


def validate_ticker(ticker):
    """Validate stock ticker format. Returns (is_valid, error_message).

    Accepts .SH as alias for .SS (Shanghai Stock Exchange).
    """
    if not ticker or not ticker.strip():
        return False, "股票代码不能为空"

    t = _normalize_ticker(ticker)

    # A-share: 6 digits + .SS or .SZ (also accepts .SH → auto-converted to .SS)
    if t.endswith('.SS') or t.endswith('.SZ'):
        code = t.split('.')[0]
        if not re.match(r'^\d{6}$', code):
            return False, f"A股代码应为6位数字，如 600519.SS 或 000333.SZ（当前: {ticker}）"
        return True, ""

    # HK stock: 4-5 digits + .HK
    if t.endswith('.HK'):
        code = t.split('.')[0]
        if not re.match(r'^\d{4,5}$', code):
            return False, f"港股代码应为4-5位数字，如 0700.HK 或 9988.HK（当前: {ticker}）"
        return True, ""

    # US stock: 1-5 letters (no suffix needed)
    if re.match(r'^[A-Z]{1,5}$', t):
        return True, ""

    # US stock with exchange suffix (e.g., AAPL.US, AAPL.O)
    if re.match(r'^[A-Z]{1,5}\.[A-Z]{1,3}$', t):
        return True, ""

    return False, (
        f"无法识别的股票代码格式: {ticker}\n"
        f"  支持格式:  美股 AAPL | 港股 0700.HK | A股 600519.SS / 000333.SZ"
    )

def get_api_url(requested_data, ticker, period, apikey):
    base_url = f'https://financialmodelingprep.com/api/v3/{requested_data}/{ticker}?apikey={apikey}'
    return base_url if period == 'annual' else f'{base_url}&period=quarter'

def get_jsonparsed_data(url):
    try:
        response = urlopen(url)
        data = response.read().decode('utf-8')
        json_data = json.loads(data)
        if "Error Message" in json_data:
            raise ValueError(f"Error while requesting data from '{url}'. Error Message: '{json_data['Error Message']}'.")
        return json_data
    except Exception as e:
        print(f"Error retrieving {url}: {e}")
        raise

def fetch_forex_data(apikey):
    url = f'https://financialmodelingprep.com/api/v3/quotes/forex?apikey={apikey}'
    data = get_jsonparsed_data(url)
    return {item['name']: item['price'] for item in data}

def fetch_market_risk_premium(apikey):
    url = f'https://financialmodelingprep.com/api/v4/market_risk_premium?apikey={apikey}'
    data = get_jsonparsed_data(url)
    return {item['country']: item['totalEquityRiskPremium'] for item in data}

def get_company_share_float(ticker, apikey='', company_profile=None):
    if is_a_share(ticker):
        # For A-shares, reuse outstandingShares from company_profile to avoid duplicate API call
        if company_profile and 'outstandingShares' in company_profile:
            return {'outstandingShares': company_profile['outstandingShares'], 'symbol': ticker}
        return fetch_akshare_share_float(ticker)
    if is_hk_stock(ticker):
        # For HK stocks, reuse outstandingShares from company_profile (same pattern as A-shares)
        if company_profile and 'outstandingShares' in company_profile:
            return {'outstandingShares': company_profile['outstandingShares'], 'symbol': ticker}
        # Fallback: fetch company profile
        if _is_cloud_mode():
            from .akshare_hk_data import fetch_akshare_hk_company_profile
            profile = fetch_akshare_hk_company_profile(ticker)
        else:
            from .yfinance_data import fetch_yfinance_hk_company_profile
            profile = fetch_yfinance_hk_company_profile(ticker)
        return {'outstandingShares': profile.get('outstandingShares', 0), 'symbol': ticker}
    url = f'https://financialmodelingprep.com/api/v4/shares_float?symbol={ticker}&apikey={apikey}'
    company_info = get_jsonparsed_data(url)
    if not company_info:
        raise ValueError(f"No company information found for ticker {ticker}.")
    return company_info[0]

def fetch_company_profile(ticker, apikey=''):
    if is_a_share(ticker):
        try:
            return fetch_akshare_company_profile(ticker)
        except Exception as e:
            print(S.warning(f"⚠ fetch_akshare_company_profile failed ({type(e).__name__}: {e}). Using minimal profile."))
            exchange = 'Shanghai Stock Exchange' if ticker.upper().endswith('.SS') else 'Shenzhen Stock Exchange'
            return {'companyName': ticker, 'marketCap': 0, 'beta': 1.0,
                    'country': 'China', 'currency': 'CNY', 'exchange': exchange,
                    'price': 0, 'outstandingShares': 0}
    if is_hk_stock(ticker):
        try:
            if _is_cloud_mode():
                from .akshare_hk_data import fetch_akshare_hk_company_profile
                return fetch_akshare_hk_company_profile(ticker)
            else:
                from .yfinance_data import fetch_yfinance_hk_company_profile
                return fetch_yfinance_hk_company_profile(ticker)
        except Exception as e:
            print(S.warning(f"⚠ HK company profile failed ({type(e).__name__}: {e}). Using minimal profile."))
            return {'companyName': ticker, 'marketCap': 0, 'beta': 1.0,
                    'country': 'China', 'currency': 'HKD', 'exchange': 'HKSE',
                    'price': 0, 'outstandingShares': 0}
    url = f'https://financialmodelingprep.com/api/v3/profile/{ticker}?apikey={apikey}'
    data = get_jsonparsed_data(url)
    if not data:
        raise ValueError(f"No company profile data found for ticker {ticker}.")

    market_cap = data[0].get('mktCap', 0)
    if pd.isna(market_cap) or market_cap == 0:
        print(f"Warning: Market Cap for {ticker} is NaN or 0. Setting to default value.")
        market_cap = 0

    return {
        'companyName': data[0]['companyName'],
        'marketCap': market_cap,
        'beta': data[0]['beta'],
        'country': data[0]['country'],
        'currency': data[0].get('currency', 'USD'),
        'exchange': data[0].get('exchange', 'NASDAQ'),
        'price': data[0].get('price', 0),
    }

def _safe_numeric(val, default=0):
    """Convert a value to float, returning default if NaN/None/error."""
    result = pd.to_numeric(val, errors='coerce')
    return default if pd.isna(result) else float(result)


def _build_raw_excel_df(df):
    """Build a transposed DataFrame from raw akshare data for Excel export.

    - Uses REPORT_DATE (year portion) as column headers
    - Drops metadata columns (SECUCODE, SECURITY_CODE, etc.)
    - Drops columns that are entirely NaN/None
    - Returns transposed DataFrame: fields as rows, dates as columns
    """
    DROP_COLS = {'SECUCODE', 'SECURITY_CODE', 'SECURITY_NAME_ABBR',
                 'ORG_CODE', 'ORG_TYPE', 'REPORT_TYPE', 'REPORT_DATE_NAME',
                 'SECURITY_TYPE_CODE', 'NOTICE_DATE', 'UPDATE_DATE',
                 'CURRENCY'}
    raw = df.copy()

    # Set REPORT_DATE as readable year labels
    dates = pd.to_datetime(raw['REPORT_DATE']).dt.strftime('%Y-%m-%d')
    raw = raw.drop(columns=[c for c in DROP_COLS if c in raw.columns], errors='ignore')
    raw = raw.drop(columns=['REPORT_DATE'], errors='ignore')

    # Drop columns that are entirely NaN
    raw = raw.dropna(axis=1, how='all')

    # Transpose: fields as rows, each column is a date period
    raw = raw.T
    raw.columns = dates.values

    return raw


def _calc_akshare_ebit(row):
    """Calculate EBIT from a single akshare profit sheet row (China GAAP).

    EBIT = 营业利润 - 投资收益 - 公允价值变动收益 - 其他收益
           - 资产处置收益 - 信用减值损失 - 资产减值损失 + 财务费用
    """
    fields = ['OPERATE_PROFIT', 'INVEST_INCOME', 'FAIRVALUE_CHANGE_INCOME',
              'OTHER_INCOME', 'ASSET_DISPOSAL_INCOME', 'CREDIT_IMPAIRMENT_INCOME',
              'ASSET_IMPAIRMENT_INCOME', 'FINANCE_EXPENSE']
    vals = {f: _safe_numeric(row.get(f, 0)) for f in fields}
    return (vals['OPERATE_PROFIT']
            - vals['INVEST_INCOME']
            - vals['FAIRVALUE_CHANGE_INCOME']
            - vals['OTHER_INCOME']
            - vals['ASSET_DISPOSAL_INCOME']
            - vals['CREDIT_IMPAIRMENT_INCOME']
            - vals['ASSET_IMPAIRMENT_INCOME']
            + vals['FINANCE_EXPENSE'])


def _ticker_to_ak_symbol(ticker):
    """Convert FMP ticker to akshare symbol: 600519.SS -> SH600519, 002594.SZ -> SZ002594."""
    t = ticker.upper()
    if t.endswith('.SS'):
        return 'SH' + t.replace('.SS', '')
    elif t.endswith('.SZ'):
        return 'SZ' + t.replace('.SZ', '')
    return None



def _ticker_to_bare_code(ticker):
    """Convert to bare stock code: 600519.SS -> 600519"""
    return ticker.split('.')[0]


def _calculate_beta_akshare(ticker, years=3):
    """Calculate beta for an A-share stock against CSI 300 index using daily returns.

    Uses `years` years of daily data. Returns CHINA_DEFAULT_BETA on failure.
    Only called in local mode (terminal + local Streamlit); skipped on Cloud.

    Both stock and index data use **Sina Finance** (finance.sina.com.cn) to avoid
    Eastmoney push2his rate-limiting after parallel financial statement fetches.
    Financial statements use datacenter-web.eastmoney.com (different host, no conflict).
    """
    import time
    from datetime import datetime, timedelta

    bare_code = _ticker_to_bare_code(ticker)
    market_prefix = 'sh' if ticker.upper().endswith('.SS') else 'sz'
    sina_symbol = f'{market_prefix}{bare_code}'
    start_dt = datetime.now() - timedelta(days=years * 365)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print()  # newline after tqdm progress bars
                print(S.info(f"Calculating beta for {bare_code} vs CSI 300 ({years}Y daily)..."), end="")
                time.sleep(0.5)
            else:
                delay = attempt * 2
                print(S.info(f"  Retrying beta (attempt {attempt + 1}/{max_retries}, wait {delay}s)..."), end="")
                time.sleep(delay)

            ak = _get_ak()
            # Both APIs use Sina Finance — no conflict with Eastmoney rate limits
            stock_df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust='qfq')
            index_df = ak.stock_zh_index_daily(symbol='sh000300')

            # Both return English column names: date, open, high, low, close, volume
            stock_df['date'] = pd.to_datetime(stock_df['date'])
            stock_df = stock_df[stock_df['date'] >= pd.Timestamp(start_dt)]
            stock_df['stock_return'] = stock_df['close'].pct_change()

            index_df['date'] = pd.to_datetime(index_df['date'])
            index_df = index_df[index_df['date'] >= pd.Timestamp(start_dt)]
            index_df['index_return'] = index_df['close'].pct_change()

            merged = pd.merge(stock_df[['date', 'stock_return']],
                              index_df[['date', 'index_return']], on='date').dropna()

            if len(merged) < 60:
                print(S.warning(f"Insufficient data for beta calculation ({len(merged)} days). Using default."))
                return CHINA_DEFAULT_BETA

            cov = merged['stock_return'].cov(merged['index_return'])
            var = merged['index_return'].var()
            beta = cov / var if var != 0 else CHINA_DEFAULT_BETA

            beta = round(beta, 2)
            print(f" done. β = {beta}")
            return beta

        except Exception as e:
            err_str = str(e).lower()
            is_conn_err = any(kw in err_str for kw in [
                'connection', 'remote', 'disconnected', 'reset', 'aborted',
                'timeout', 'refused', 'broken pipe',
            ]) or isinstance(e, (ConnectionError, ConnectionResetError, ConnectionAbortedError, OSError))
            if is_conn_err and attempt < max_retries - 1:
                print(f" connection error, will retry.")
                continue
            if is_conn_err:
                print(S.warning(f"Beta failed after {max_retries} attempts: {e}. Using default {CHINA_DEFAULT_BETA}."))
            else:
                print(S.warning(f"Beta calculation failed: {e}. Using default {CHINA_DEFAULT_BETA}."))
            return CHINA_DEFAULT_BETA

    return CHINA_DEFAULT_BETA


def fetch_akshare_company_profile(ticker):
    """Fetch company profile + share float from akshare for A-shares.

    Primary: ``stock_individual_info_em`` (works locally).
    Fallback: piece together from lightweight APIs that work on Streamlit Cloud
    (same strategy as HK company profile).
    """
    bare_code = _ticker_to_bare_code(ticker)
    exchange = 'Shanghai Stock Exchange' if ticker.upper().endswith('.SS') else 'Shenzhen Stock Exchange'

    _cloud = _is_cloud_mode()

    # --- Primary: stock_individual_info_em (works locally, blocked on Cloud) ---
    # Skip on Cloud to avoid ~15-30s timeout from a guaranteed-to-fail connection.
    # Note: beta is NOT calculated here — it runs after parallel fetch completes
    # to avoid concurrent connection contention with financial data APIs.
    if not _cloud:
        try:
            print(S.info(f"Fetching company profile from akshare for {bare_code}..."))
            info_df = _get_ak().stock_individual_info_em(symbol=bare_code)
            info_dict = dict(zip(info_df['item'], info_df['value']))
            return {
                'companyName': str(info_dict.get('股票简称', ticker)),
                'marketCap': float(info_dict.get('总市值', 0)),
                'beta': CHINA_DEFAULT_BETA,
                'country': 'China',
                'currency': 'CNY',
                'exchange': exchange,
                'price': float(info_dict.get('最新', 0)),
                'outstandingShares': float(info_dict.get('总股本', 0)),
            }
        except Exception as e:
            print(S.muted(f"  ⓘ stock_individual_info_em failed ({type(e).__name__}), building profile from alternative sources..."))

    # --- Cloud / fallback path ---
    print(S.info(f"Fetching company profile for {bare_code} (lightweight mode)..."))
    profile = {
        'companyName': ticker,
        'marketCap': 0,
        'beta': CHINA_DEFAULT_BETA,
        'country': 'China',
        'currency': 'CNY',
        'exchange': exchange,
        'price': 0,
        'outstandingShares': 0,
    }

    # --- Price + shares ---
    # On Cloud, skip eastmoney push2 endpoints (blocked); go straight to Sina.
    # Locally (fallback), try eastmoney first, then Sina.

    if not _cloud:
        # eastmoney historical (push2his.eastmoney.com) — only try locally
        try:
            hist_df = _get_ak().stock_zh_a_hist(symbol=bare_code, period='daily', adjust='qfq')
            if hist_df is not None and not hist_df.empty:
                profile['price'] = float(hist_df.iloc[-1]['收盘'])
                print(S.muted(f"  ✓ Price from eastmoney daily: {profile['price']}"))
        except Exception as e1:
            print(S.muted(f"  ⓘ stock_zh_a_hist failed ({type(e1).__name__})"))

    # Sina Finance (finance.sina.com.cn — works on Cloud)
    if profile['price'] <= 0:
        try:
            _sina_prefix = 'sh' if ticker.upper().endswith('.SS') else 'sz'
            _sina_df = _get_ak().stock_zh_a_daily(symbol=f'{_sina_prefix}{bare_code}', adjust='qfq')
            if _sina_df is not None and not _sina_df.empty:
                _last = _sina_df.iloc[-1]
                profile['price'] = float(_last['close'])
                _sina_shares = float(_last.get('outstanding_share', 0) or 0)
                if _sina_shares > 0 and not profile.get('outstandingShares'):
                    profile['outstandingShares'] = _sina_shares
                print(S.muted(f"  ✓ Price from Sina: {profile['price']}"))
        except Exception as e2:
            print(S.muted(f"  ⓘ stock_zh_a_daily (Sina) failed ({type(e2).__name__})"))

    # Note: company name and outstanding shares will also be filled from
    # already-fetched financial data by _fill_profile_from_financial_data().

    if profile['price'] > 0:
        print(S.info(f"  ✓ Partial company profile assembled (name/shares pending)"))
    else:
        print(S.muted(f"  ⓘ Partial company profile — all price sources failed"))
    return profile


def _fill_profile_from_financial_data(profile, financial_data):
    """Fill missing company profile fields from already-fetched financial data.

    Called after get_historical_financials() succeeds — avoids duplicate API calls.
    Uses pre-extracted values (_company_name_from_data, _shares_from_data) stored
    in financial_data by get_historical_financials().
    """
    if profile is None or financial_data is None:
        return profile

    # Company name: fill if missing or looks like a raw ticker symbol
    _name = profile.get('companyName', '')
    _looks_like_ticker = (not _name
                          or re.match(r'^\d{5,6}\.\w{1,2}$', _name))  # e.g. 600519.SS / 00700.HK
    if _looks_like_ticker:
        data_name = financial_data.get('_company_name_from_data')
        if data_name:
            profile['companyName'] = data_name

    # Outstanding shares: fill if missing or zero
    if not profile.get('outstandingShares'):
        data_shares = financial_data.get('_shares_from_data')
        if data_shares and data_shares > 0:
            profile['outstandingShares'] = data_shares

    # Market cap = price × shares
    if not profile.get('marketCap') and profile.get('price', 0) > 0 and profile.get('outstandingShares', 0) > 0:
        profile['marketCap'] = profile['price'] * profile['outstandingShares']

    return profile


def fetch_akshare_share_float(ticker):
    """Fetch outstanding shares from akshare for A-shares.
    Note: For A-shares, prefer using fetch_akshare_company_profile() which
    includes outstandingShares and avoids a duplicate API call."""
    try:
        bare_code = _ticker_to_bare_code(ticker)
        info_df = _get_ak().stock_individual_info_em(symbol=bare_code)
        info_dict = dict(zip(info_df['item'], info_df['value']))
        return {
            'outstandingShares': float(info_dict.get('总股本', 0)),
            'symbol': ticker,
        }
    except Exception:
        # Fallback: try spot_em
        try:
            bare_code = _ticker_to_bare_code(ticker)
            spot_df = _get_ak().stock_zh_a_spot_em()
            row = spot_df[spot_df['代码'] == bare_code]
            if not row.empty:
                return {
                    'outstandingShares': float(row.iloc[0].get('总股本', 0) or 0),
                    'symbol': ticker,
                }
        except Exception:
            pass
        return {'outstandingShares': 0, 'symbol': ticker}


def fetch_akshare_income_statement(ticker, period='annual', historical_periods=5):
    """Fetch income statements from akshare, returning (FMP-compatible dicts, raw DataFrame, full cumulative DataFrame).

    The third return value (full_cumulative_df) is the complete cumulative report DataFrame
    before annual filtering, used for TTM calculation to avoid duplicate API calls.
    For quarter mode, it is None (quarter data uses a different API).
    """
    ak_symbol = _ticker_to_ak_symbol(ticker)
    print(S.info(f"Fetching income statement from akshare for {ak_symbol}..."))

    full_cumulative_df = None
    if period == 'annual':
        full_cumulative_df = _get_ak().stock_profit_sheet_by_report_em(symbol=ak_symbol)
        df = full_cumulative_df[full_cumulative_df['REPORT_TYPE'] == '年报'].copy()
    else:
        df = _get_ak().stock_profit_sheet_by_quarterly_em(symbol=ak_symbol)

    df = df.sort_values('REPORT_DATE', ascending=False).head(historical_periods)

    month_to_quarter = {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}
    result = []

    for _, row in df.iterrows():
        date_str = str(row['REPORT_DATE'])[:10]
        year = date_str[:4]
        month = int(date_str[5:7])

        if period == 'annual':
            period_name = 'FY'
        else:
            period_name = month_to_quarter.get(month, f'Q{(month - 1) // 3 + 1}')

        revenue = _safe_numeric(row.get('OPERATE_INCOME', 0))
        ebit = _calc_akshare_ebit(row)

        interest_expense_val = _safe_numeric(row.get('FE_INTEREST_EXPENSE', 0))
        interest_income_val = _safe_numeric(row.get('FE_INTEREST_INCOME', 0))
        total_profit = _safe_numeric(row.get('TOTAL_PROFIT', 0))
        income_tax = _safe_numeric(row.get('INCOME_TAX', 0))

        result.append({
            'calendarYear': year,
            'date': date_str,
            'period': period_name,
            'reportedCurrency': 'CNY',
            'revenue': revenue,
            'operatingIncome': ebit,
            'interestExpense': interest_expense_val,
            'interestIncome': interest_income_val,
            'incomeBeforeTax': total_profit,
            'incomeTaxExpense': income_tax,
        })

    # Build raw DataFrame for Excel export (transposed: fields as rows, dates as columns)
    raw_df = _build_raw_excel_df(df)

    return result, raw_df, full_cumulative_df


def _parse_akshare_bs_row(row):
    """Parse a single akshare balance sheet row into FMP-compatible dict."""
    short_loan = _safe_numeric(row.get('SHORT_LOAN', 0))
    long_loan = _safe_numeric(row.get('LONG_LOAN', 0))
    bond_payable = _safe_numeric(row.get('BOND_PAYABLE', 0))
    noncurrent_1year = _safe_numeric(row.get('NONCURRENT_LIAB_1YEAR', 0))
    lease_liab = _safe_numeric(row.get('LEASE_LIAB', 0))
    total_debt = short_loan + long_loan + bond_payable + noncurrent_1year + lease_liab

    total_equity = _safe_numeric(row.get('TOTAL_EQUITY', 0))
    minority_equity = _safe_numeric(row.get('MINORITY_EQUITY', 0))

    # Cash: 货币资金 + 财务公司类现金净额
    #   净额 = 发放贷款及垫款 - 吸收存款及同业存放 + 拆出资金 - 拆入资金
    cash_monetary = _safe_numeric(row.get('MONETARYFUNDS', 0))
    loan_advance = _safe_numeric(row.get('LOAN_ADVANCE', 0))
    accept_deposit = _safe_numeric(row.get('ACCEPT_DEPOSIT_INTERBANK', 0))
    lend_fund = _safe_numeric(row.get('LEND_FUND', 0))
    borrow_fund = _safe_numeric(row.get('BORROW_FUND', 0))
    fin_company_net = loan_advance - accept_deposit + lend_fund - borrow_fund
    cash = cash_monetary + fin_company_net

    # Investments: 金融资产 (IFRS 9 一般企业字段)
    trade_fin = _safe_numeric(row.get('TRADE_FINASSET_NOTFVTPL', 0))     # FVTPL
    creditor_invest = _safe_numeric(row.get('CREDITOR_INVEST', 0))        # AC 债权投资
    other_creditor = _safe_numeric(row.get('OTHER_CREDITOR_INVEST', 0))   # FVOCI 其他债权投资
    other_equity_inv = _safe_numeric(row.get('OTHER_EQUITY_INVEST', 0))   # FVOCI 其他权益工具
    other_nc_fin = _safe_numeric(row.get('OTHER_NONCURRENT_FINASSET', 0)) # 其他非流动金融资产
    long_equity = _safe_numeric(row.get('LONG_EQUITY_INVEST', 0))         # 长期股权投资
    total_investments = trade_fin + creditor_invest + other_creditor + other_equity_inv + other_nc_fin + long_equity

    total_assets = _safe_numeric(row.get('TOTAL_ASSETS', 0))

    return {
        'totalDebt': total_debt,
        'totalEquity': total_equity,
        'minorityInterest': minority_equity,
        'cashAndCashEquivalents': cash,
        'totalInvestments': total_investments,
        'totalAssets': total_assets,
    }


def fetch_akshare_balance_sheet(ticker, period='annual', historical_periods=5):
    """Fetch balance sheet from akshare, returning (FMP-compatible dicts, raw DataFrame, full DataFrame).

    The third return value is the full (unfiltered) DataFrame, used by TTM to
    retrieve the latest quarterly balance sheet even when period='annual'.
    """
    ak_symbol = _ticker_to_ak_symbol(ticker)
    print(S.info(f"Fetching balance sheet from akshare for {ak_symbol}..."))

    df = _get_ak().stock_balance_sheet_by_report_em(symbol=ak_symbol)
    full_df = df.copy()  # Keep unfiltered for TTM quarterly lookups
    if period == 'annual':
        months = pd.to_datetime(df['REPORT_DATE']).dt.month
        df = df[months == 12].copy()
    df = df.sort_values('REPORT_DATE', ascending=False).head(historical_periods)

    result = []
    for _, row in df.iterrows():
        result.append(_parse_akshare_bs_row(row))

    # Build raw DataFrame for Excel export
    raw_df = _build_raw_excel_df(df)

    return result, raw_df, full_df


def _extract_cashflow_fields(row):
    """Extract D&A, capex, WC change from a single akshare cashflow row.
    Returns (da, capex, change_in_wc) — all in raw akshare units.
    D&A and WC fields may be NaN in Q1/Q3 reports (indirect method not disclosed).
    """
    fa_depr = _safe_numeric(row.get('FA_IR_DEPR', 0))
    ia_amort = _safe_numeric(row.get('IA_AMORTIZE', 0))
    lpe_amort = _safe_numeric(row.get('LPE_AMORTIZE', 0))
    ura_amort = _safe_numeric(row.get('USERIGHT_ASSET_AMORTIZE', 0))
    da = fa_depr + ia_amort + lpe_amort + ura_amort

    # akshare: CONSTRUCT_LONG_ASSET is positive (cash outflow for capex)
    # FMP: investmentsInPropertyPlantAndEquipment is negative
    capex_raw = _safe_numeric(row.get('CONSTRUCT_LONG_ASSET', 0))
    capex = -capex_raw

    inv_reduce = _safe_numeric(row.get('INVENTORY_REDUCE', 0))
    recv_reduce = _safe_numeric(row.get('OPERATE_RECE_REDUCE', 0))
    payable_add = _safe_numeric(row.get('OPERATE_PAYABLE_ADD', 0))
    change_in_wc = inv_reduce + recv_reduce + payable_add

    return da, capex, change_in_wc


def fetch_akshare_cashflow(ticker, period='annual', historical_periods=5):
    """Fetch cash flow statement from akshare, returning (FMP-compatible dicts, raw DataFrame, full cumulative DataFrame).

    IMPORTANT: akshare cash flow data from stock_cash_flow_sheet_by_report_em is
    *cumulative* (YTD). For annual mode this is fine (full year).
    For quarter mode, the returned dicts still contain YTD cumulative values.
    TTM calculation in get_historical_financials() handles this via the cumulative method.

    The third return value (full_cumulative_df) is the complete cumulative report DataFrame
    before annual filtering, used for TTM calculation to avoid duplicate API calls.
    For quarter mode, it is the same as the fetched df (already cumulative).
    """
    ak_symbol = _ticker_to_ak_symbol(ticker)
    print(S.info(f"Fetching cash flow statement from akshare for {ak_symbol}..."))

    full_cumulative_df = _get_ak().stock_cash_flow_sheet_by_report_em(symbol=ak_symbol)
    if period == 'annual':
        months = pd.to_datetime(full_cumulative_df['REPORT_DATE']).dt.month
        df = full_cumulative_df[months == 12].copy()
    else:
        df = full_cumulative_df
    df = df.sort_values('REPORT_DATE', ascending=False).head(historical_periods)

    result = []
    for _, row in df.iterrows():
        da, capex, change_in_wc = _extract_cashflow_fields(row)
        result.append({
            'depreciationAndAmortization': da,
            'investmentsInPropertyPlantAndEquipment': capex,
            'changeInWorkingCapital': change_in_wc,
        })

    raw_df = _build_raw_excel_df(df)
    return result, raw_df, full_cumulative_df


def fetch_akshare_key_metrics(ticker, balance_sheets, income_statements, period='annual', historical_periods=5):
    """Compute key metrics for A-shares from already-fetched data.

    No additional API call needed — computed from BS and IS data.
    Same approach as HK version (fetch_akshare_hk_key_metrics).
    """
    result = []
    for i in range(len(balance_sheets)):
        bs = balance_sheets[i]

        total_assets = bs.get('totalAssets', 0) or 1
        total_debt = bs.get('totalDebt', 0) or 0
        total_equity = bs.get('totalEquity', 0) or 0
        debt_to_assets = total_debt / total_assets if total_assets != 0 else 0

        # ROIC and ROE computed from IS + BS (same as HK version)
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


def _compute_akshare_ttm_income(ticker, df=None):
    """Compute TTM income values for A-shares using the YTD cumulative method.

    TTM = latest YTD + (prior FY − prior same-period YTD)
    Uses stock_profit_sheet_by_report_em (cumulative reports).

    Args:
        ticker: Stock ticker string.
        df: Optional pre-fetched cumulative DataFrame from stock_profit_sheet_by_report_em.
            If None, fetches from API (for backward compatibility).

    Returns dict with keys: revenue, operatingIncome (EBIT), incomeBeforeTax,
    incomeTaxExpense (all in raw akshare units), or None if unable to compute.
    """
    if df is None:
        ak_symbol = _ticker_to_ak_symbol(ticker)
        df = _get_ak().stock_profit_sheet_by_report_em(symbol=ak_symbol)
    df = df.sort_values('REPORT_DATE', ascending=False).copy()
    df['_date'] = pd.to_datetime(df['REPORT_DATE'])
    df['_year'] = df['_date'].dt.year
    df['_month'] = df['_date'].dt.month

    if len(df) < 2:
        return None

    latest = df.iloc[0]
    latest_month = int(latest['_month'])
    latest_year = int(latest['_year'])

    if latest_month == 12:
        return None  # Already full year
    if latest_month == 3:
        return None  # Q1: too early for meaningful TTM, use annual data as base

    # Build lookup
    ytd_lookup = {}
    for _, row in df.iterrows():
        key = (int(row['_year']), int(row['_month']))
        if key not in ytd_lookup:
            ytd_lookup[key] = row

    prior_fy = ytd_lookup.get((latest_year - 1, 12))
    prior_same = ytd_lookup.get((latest_year - 1, latest_month))
    if prior_fy is None:
        return None

    def _ytd_val(row, field):
        return _safe_numeric(row.get(field, 0))

    rev_latest = _ytd_val(latest, 'OPERATE_INCOME')
    rev_fy = _ytd_val(prior_fy, 'OPERATE_INCOME')
    rev_same = _ytd_val(prior_same, 'OPERATE_INCOME') if prior_same is not None else 0

    ebit_latest = _calc_akshare_ebit(latest)
    ebit_fy = _calc_akshare_ebit(prior_fy)
    ebit_same = _calc_akshare_ebit(prior_same) if prior_same is not None else 0

    pbt_latest = _ytd_val(latest, 'TOTAL_PROFIT')
    pbt_fy = _ytd_val(prior_fy, 'TOTAL_PROFIT')
    pbt_same = _ytd_val(prior_same, 'TOTAL_PROFIT') if prior_same is not None else 0

    tax_latest = _ytd_val(latest, 'INCOME_TAX')
    tax_fy = _ytd_val(prior_fy, 'INCOME_TAX')
    tax_same = _ytd_val(prior_same, 'INCOME_TAX') if prior_same is not None else 0

    latest_date_str = str(latest['REPORT_DATE'])[:10]

    # Also compute prior-year TTM for YoY growth
    prior_year_fy = ytd_lookup.get((latest_year - 2, 12))
    prior_year_same = ytd_lookup.get((latest_year - 2, latest_month))
    if prior_same is not None and prior_year_fy is not None:
        rev_prior_same = _ytd_val(prior_same, 'OPERATE_INCOME')
        rev_prior_fy = _ytd_val(prior_year_fy, 'OPERATE_INCOME')
        rev_prior_year_same = _ytd_val(prior_year_same, 'OPERATE_INCOME') if prior_year_same is not None else 0
        prior_ttm_revenue = rev_prior_same + (rev_prior_fy - rev_prior_year_same)

        ebit_prior_same = _calc_akshare_ebit(prior_same)
        ebit_prior_fy = _calc_akshare_ebit(prior_year_fy)
        ebit_prior_year_same = _calc_akshare_ebit(prior_year_same) if prior_year_same is not None else 0
        prior_ttm_ebit = ebit_prior_same + (ebit_prior_fy - ebit_prior_year_same)
    else:
        prior_ttm_revenue = None
        prior_ttm_ebit = None

    return {
        'revenue': rev_latest + (rev_fy - rev_same),
        'operatingIncome': ebit_latest + (ebit_fy - ebit_same),
        'incomeBeforeTax': pbt_latest + (pbt_fy - pbt_same),
        'incomeTaxExpense': tax_latest + (tax_fy - tax_same),
        '_latest_quarter': f'Q{latest_month // 3}',
        '_latest_date': latest_date_str,
        '_prior_ttm_revenue': prior_ttm_revenue,
        '_prior_ttm_ebit': prior_ttm_ebit,
    }


def _compute_akshare_ttm_cashflow(ticker, df=None):
    """Compute TTM cashflow values for A-shares using the YTD cumulative method.

    TTM = latest YTD + (prior FY − prior same-period YTD)

    Args:
        ticker: Stock ticker string.
        df: Optional pre-fetched cumulative DataFrame from stock_cash_flow_sheet_by_report_em.
            If None, fetches from API (for backward compatibility).

    Returns dict with keys: depreciationAndAmortization,
    investmentsInPropertyPlantAndEquipment, changeInWorkingCapital
    (all in raw akshare units, i.e., yuan), or None if unable to compute.

    For indirect-method items (D&A, WC change), only H1 and FY reports have data.
    If the latest report is Q1 or Q3, those items fall back to the most recent FY value.
    """
    if df is None:
        ak_symbol = _ticker_to_ak_symbol(ticker)
        df = _get_ak().stock_cash_flow_sheet_by_report_em(symbol=ak_symbol)
    df = df.sort_values('REPORT_DATE', ascending=False).copy()
    df['_date'] = pd.to_datetime(df['REPORT_DATE'])
    df['_year'] = df['_date'].dt.year
    df['_month'] = df['_date'].dt.month

    if len(df) < 2:
        return None

    latest = df.iloc[0]
    latest_month = int(latest['_month'])
    latest_year = int(latest['_year'])

    if latest_month == 12:
        # Already full year, no TTM needed
        return None
    if latest_month == 3:
        # Q1: too early for meaningful TTM, use annual data as base
        return None

    # Build lookup: (year, month) -> row
    ytd_lookup = {}
    for _, row in df.iterrows():
        key = (int(row['_year']), int(row['_month']))
        if key not in ytd_lookup:
            ytd_lookup[key] = row

    # Prior FY (most recent annual report before the latest)
    prior_fy_key = (latest_year - 1, 12)
    prior_fy = ytd_lookup.get(prior_fy_key)
    if prior_fy is None:
        return None

    # Prior same-period YTD
    prior_same_key = (latest_year - 1, latest_month)
    prior_same = ytd_lookup.get(prior_same_key)

    da_latest, capex_latest, wc_latest = _extract_cashflow_fields(latest)
    da_fy, capex_fy, wc_fy = _extract_cashflow_fields(prior_fy)

    if prior_same is not None:
        da_same, capex_same, wc_same = _extract_cashflow_fields(prior_same)
    else:
        da_same, capex_same, wc_same = 0, 0, 0

    # Capex (CONSTRUCT_LONG_ASSET) is always available — use cumulative method
    capex_ttm = capex_latest + (capex_fy - capex_same)

    # D&A and WC: only available in H1 (month=6) and FY (month=12)
    # Check if latest report has indirect-method data by inspecting a key field
    latest_raw = latest
    has_indirect = pd.notna(latest_raw.get('FA_IR_DEPR'))

    note = ''
    if has_indirect and prior_same is not None and pd.notna(prior_same.get('FA_IR_DEPR')):
        # Both ends have data — cumulative method works
        da_ttm = da_latest + (da_fy - da_same)
        wc_ttm = wc_latest + (wc_fy - wc_same)
    else:
        # Q1/Q3: indirect-method items not available — fall back to prior FY
        da_ttm = da_fy
        wc_ttm = wc_fy
        note = f'D&A and WC use FY{latest_year-1} annual data (Q{latest_month//3} indirect CF unavailable); Capex is TTM'

    return {
        'depreciationAndAmortization': da_ttm,
        'investmentsInPropertyPlantAndEquipment': capex_ttm,
        'changeInWorkingCapital': wc_ttm,
        '_note': note,
    }


def _decumulate_quarterly_cf_if_needed(q_cf, summary_data=None):
    """Detect and fix cumulative YTD cashflow data from FMP.

    Under IAS 34 / HKFRS, interim cash flow statements are presented on a cumulative
    year-to-date basis (Q2 = H1, Q3 = 9 months, Q4 = full year). Some data providers
    return these raw values labeled as "quarterly" without de-cumulating.

    Detection uses two complementary methods:
    1. Monotonic check: within a fiscal year sorted chronologically, if abs(capex)
       increases for every successive quarter (Q1 ≤ Q2 ≤ Q3 ≤ Q4), the data is
       likely cumulative. Requires ≥3 quarters in a year.
    2. Sum check (optional): if summary_data is provided (annual mode), compare the
       quarterly sum for a full FY against the known annual capex. If >1.6x, cumulative.

    De-cumulation: Within each fiscal year (sorted chronologically), subtract the prior
    period's cumulative value to get single-quarter values.
    """
    if not q_cf:
        return q_cf

    from collections import defaultdict

    cf_fields = ['investmentsInPropertyPlantAndEquipment', 'depreciationAndAmortization', 'changeInWorkingCapital']
    capex_field = 'investmentsInPropertyPlantAndEquipment'

    # Group by fiscal year, sort chronologically
    by_year = defaultdict(list)
    for d in q_cf:
        by_year[d.get('calendarYear', '')].append(d)
    for year in by_year:
        by_year[year].sort(key=lambda x: x.get('date', ''))

    is_cumulative = False

    # Method 1: Monotonic check — within any year with ≥3 quarters,
    # if abs(capex) is non-decreasing for all consecutive pairs, it's cumulative.
    for year, quarters in by_year.items():
        if len(quarters) >= 3:
            capex_vals = [abs(q.get(capex_field, 0) or 0) for q in quarters]
            if capex_vals[0] == 0:
                continue  # Skip if Q1 capex is 0 (can't detect pattern)
            # Check if non-decreasing (allowing small tolerance for rounding)
            if all(capex_vals[i+1] >= capex_vals[i] * 0.95 for i in range(len(capex_vals) - 1)):
                # Additional check: the last value should be significantly larger than the first
                if capex_vals[-1] > capex_vals[0] * 1.8:
                    is_cumulative = True
                    break

    # Method 2: Sum check — compare against known annual capex (when summary_data available)
    if not is_cumulative and summary_data:
        annual_capex = abs(summary_data[0].get('(+) Capital Expenditure', 0))
        annual_year = str(summary_data[0].get('Calendar Year', ''))[:4]
        if annual_capex > 0:
            fy_quarters = by_year.get(annual_year, [])
            if len(fy_quarters) >= 4:
                quarterly_sum = sum(abs(d.get(capex_field, 0) or 0) for d in fy_quarters)
                ratio = quarterly_sum / (annual_capex * 1_000_000)
                if ratio > 1.6:
                    is_cumulative = True

    if not is_cumulative:
        return q_cf

    # De-cumulate: within each fiscal year, subtract prior period's cumulative values
    result = []
    for year, quarters in by_year.items():
        for idx, q in enumerate(quarters):
            if idx == 0:
                # Q1 (or first quarter in year): already single-quarter
                result.append(q)
            else:
                # Subtract prior cumulative to get single-quarter
                prev = quarters[idx - 1]
                decum = dict(q)  # shallow copy
                for field in cf_fields:
                    curr_val = q.get(field, 0) or 0
                    prev_val = prev.get(field, 0) or 0
                    decum[field] = curr_val - prev_val
                result.append(decum)

    # Re-sort in descending date order (most recent first, matching FMP convention)
    result.sort(key=lambda x: x.get('date', ''), reverse=True)

    print(S.muted(f"  ⓘ Detected cumulative YTD cashflow data. De-cumulated to single-quarter values."))

    return result


def get_historical_financials(ticker, period='annual', apikey='', historical_periods=5):
    from concurrent.futures import ThreadPoolExecutor

    if period == 'annual':
        period_str = f"{historical_periods} years"
    else:
        period_str = f"{historical_periods} quarters"
    print(f"\n{S.info(f'Fetching financial data for {ticker} ({period_str})...')}")

    try:
        if is_a_share(ticker):
            # --- A-share path: all data from akshare (parallel fetching) ---
            print(S.info("检测到A股，使用 akshare 数据源..."))
            with ThreadPoolExecutor(max_workers=3) as executor:
                _f_inc = executor.submit(fetch_akshare_income_statement, ticker, period, historical_periods)
                _f_bs  = executor.submit(fetch_akshare_balance_sheet, ticker, period, historical_periods)
                _f_cf  = executor.submit(fetch_akshare_cashflow, ticker, period, historical_periods)
            income_statement, raw_income_df, _full_income_df = _f_inc.result()
            balance_sheet, raw_balance_df, _full_bs_df = _f_bs.result()
            cashflow_statement, raw_cashflow_df, _full_cf_df = _f_cf.result()
            # Key metrics computed from already-fetched data (no API call)
            key_metrics = fetch_akshare_key_metrics(ticker, balance_sheet, income_statement, period, historical_periods)
        elif is_hk_stock(ticker):
            _hk_use_akshare = _is_cloud_mode()
            if _hk_use_akshare:
                # --- HK web path: akshare (东方财富, works on Streamlit Cloud) ---
                from .akshare_hk_data import (
                    fetch_akshare_hk_income_statement,
                    fetch_akshare_hk_balance_sheet,
                    fetch_akshare_hk_cashflow,
                    fetch_akshare_hk_key_metrics,
                )
                print(S.info("检测到港股（网页版），使用 akshare (东方财富) 数据源..."))
                with ThreadPoolExecutor(max_workers=3) as executor:
                    _f_inc = executor.submit(fetch_akshare_hk_income_statement, ticker, period, historical_periods)
                    _f_bs  = executor.submit(fetch_akshare_hk_balance_sheet, ticker, period, historical_periods)
                    _f_cf  = executor.submit(fetch_akshare_hk_cashflow, ticker, period, historical_periods)
                income_statement, raw_income_df, _full_income_df = _f_inc.result()
                balance_sheet, raw_balance_df, _full_bs_df = _f_bs.result()
                cashflow_statement, raw_cashflow_df, _full_cf_df = _f_cf.result()
                key_metrics = fetch_akshare_hk_key_metrics(ticker, balance_sheet, income_statement, period, historical_periods)
            else:
                # --- HK terminal path: yfinance (richer Morningstar data) ---
                from .yfinance_data import (
                    fetch_yfinance_hk_income_statement,
                    fetch_yfinance_hk_balance_sheet,
                    fetch_yfinance_hk_cashflow,
                    fetch_yfinance_hk_key_metrics,
                )
                print(S.info("检测到港股，使用 yfinance 数据源..."))
                income_statement, raw_income_df = fetch_yfinance_hk_income_statement(ticker, period, historical_periods)
                balance_sheet, raw_balance_df = fetch_yfinance_hk_balance_sheet(ticker, period, historical_periods)
                cashflow_statement, raw_cashflow_df = fetch_yfinance_hk_cashflow(ticker, period, historical_periods)
                key_metrics = fetch_yfinance_hk_key_metrics(ticker, balance_sheet, income_statement, period, historical_periods)
                _full_income_df = None  # yfinance TTM uses pre-computed data, not cumulative DFs
                _full_bs_df = None
                _full_cf_df = None
        else:
            # --- Non-A-share path: all data from FMP (parallel requests) ---
            urls = {
                'income': get_api_url('income-statement', ticker, period, apikey),
                'balance': get_api_url('balance-sheet-statement', ticker, period, apikey),
                'cashflow': get_api_url('cash-flow-statement', ticker, period, apikey),
                'metrics': get_api_url('key-metrics', ticker, period, apikey),
            }
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {k: executor.submit(get_jsonparsed_data, v) for k, v in urls.items()}
            income_statement = futures['income'].result()[:historical_periods]
            balance_sheet = futures['balance'].result()[:historical_periods]
            cashflow_statement = futures['cashflow'].result()[:historical_periods]
            key_metrics = futures['metrics'].result()[:historical_periods]

            # FMP totalDebt already includes capitalLeaseObligations — no adjustment needed

            # Detect and fix cumulative YTD cashflow data (common for HK/IFRS stocks)
            cashflow_statement = _decumulate_quarterly_cf_if_needed(cashflow_statement)

            # FMP may return different numbers of quarters for each statement
            # (e.g., HK stocks: income has Q3 but cashflow only up to Q2).
            # Build date-based lookups so we always pair by date, not by index.
            bs_by_date = {d.get('date'): d for d in reversed(balance_sheet)}
            cf_by_date = {d.get('date'): d for d in reversed(cashflow_statement)}
            km_by_date = {d.get('date'): d for d in reversed(key_metrics)}
            _empty_cf = {'depreciationAndAmortization': 0, 'investmentsInPropertyPlantAndEquipment': 0, 'changeInWorkingCapital': 0}
            _empty_km = {'debtToAssets': 0, 'roic': 0, 'roe': 0, 'dividendYield': 0, 'payoutRatio': 0}

        # HK akshare: lists aligned by index (same as A-shares), no date lookup needed
        if is_hk_stock(ticker):
            _empty_cf = {'depreciationAndAmortization': 0, 'investmentsInPropertyPlantAndEquipment': 0, 'changeInWorkingCapital': 0}
            _empty_km = {'debtToAssets': 0, 'roic': 0, 'roe': 0, 'dividendYield': 0, 'payoutRatio': 0}

        summary_data = []
        tax_rates = []

        for i in range(len(income_statement)):
            inc = income_statement[i]
            inc_date = inc.get('date', '')

            if is_a_share(ticker) or is_hk_stock(ticker):
                # A-shares & HK (akshare): lists always aligned by index
                bs = balance_sheet[i] if i < len(balance_sheet) else {}
                cf = cashflow_statement[i] if i < len(cashflow_statement) else _empty_cf
                km = key_metrics[i] if i < len(key_metrics) else _empty_km
            else:
                bs = bs_by_date.get(inc_date) or (balance_sheet[i] if i < len(balance_sheet) else {})
                cf = cf_by_date.get(inc_date) or _empty_cf
                km = km_by_date.get(inc_date) or (key_metrics[i] if i < len(key_metrics) else _empty_km)

            ebit = (inc.get('operatingIncome', 0) or 0)

            income_before_tax = inc.get('incomeBeforeTax', 0) or 0
            income_tax_expense = inc.get('incomeTaxExpense', 0) or 0
            tax_rate = income_tax_expense / income_before_tax if income_before_tax != 0 else 0
            tax_rates.append(tax_rate)

            invested_capital = (bs.get('totalDebt', 0) or 0) + \
                              (bs.get('totalEquity', 0) or 0) - \
                              (bs.get('cashAndCashEquivalents', 0) or 0) - \
                              (bs.get('totalInvestments', 0) or 0)
            revenue_to_invested_capital = (inc.get('revenue', 0) or 0) / invested_capital if invested_capital != 0 else 0
            total_reinvestments = -(cf.get('investmentsInPropertyPlantAndEquipment', 0) or 0) + \
                                 -(cf.get('changeInWorkingCapital', 0) or 0) - \
                                 (cf.get('depreciationAndAmortization', 0) or 0)

            interest_expense = inc.get('interestExpense', 0) or 0
            total_debt = bs.get('totalDebt', 0) or 0
            # For prev_total_debt, look up the previous income_statement date
            if i > 0:
                prev_inc_date = income_statement[i - 1].get('date', '')
                if is_a_share(ticker) or is_hk_stock(ticker):
                    prev_total_debt = balance_sheet[i - 1].get('totalDebt', 0) or 0 if i - 1 < len(balance_sheet) else total_debt
                else:
                    prev_bs = bs_by_date.get(prev_inc_date)
                    prev_total_debt = (prev_bs.get('totalDebt', 0) or 0) if prev_bs else total_debt
            else:
                prev_total_debt = total_debt
            avg_total_debt = (total_debt + prev_total_debt) / 2

            # Fallback: when FMP reports interestExpense=0 but company has debt,
            # estimate net interest from operatingIncome - incomeBeforeTax
            if interest_expense == 0 and total_debt > 0:
                _op_inc = inc.get('operatingIncome', 0) or 0
                _pbt = inc.get('incomeBeforeTax', 0) or 0
                net_interest = _op_inc - _pbt  # positive = net interest expense
                if net_interest > 0:
                    interest_expense = net_interest

            cost_of_debt = interest_expense / avg_total_debt if avg_total_debt != 0 else 0
            # Cap cost_of_debt: when debt is trivially small relative to total assets,
            # the ratio is meaningless (e.g., finance charges / tiny lease liability = 13%).
            # Also cap at 15% to avoid distortions from data anomalies.
            total_assets = bs.get('totalAssets', 0) or 0
            if total_assets > 0 and total_debt / total_assets < 0.01:
                cost_of_debt = 0
            elif cost_of_debt > 0.15:
                cost_of_debt = 0.15

            if i < len(income_statement) - 1:
                if period == 'annual':
                    prev_index = i + 1
                else:
                    prev_index = i + 4
                if prev_index < len(income_statement):
                    prev_revenue = income_statement[prev_index].get('revenue', 0) or 0
                    current_revenue = inc.get('revenue', 0) or 0
                    revenue_growth = (current_revenue - prev_revenue) / prev_revenue * 100 if prev_revenue != 0 else 0

                    prev_ebit = income_statement[prev_index].get('operatingIncome', 0) or 0
                    current_ebit = ebit or 0
                    ebit_growth = (current_ebit - prev_ebit) / prev_ebit * 100 if prev_ebit != 0 else 0
                else:
                    revenue_growth = 0
                    ebit_growth = 0
            else:
                revenue_growth = 0
                ebit_growth = 0

            revenue_val = (inc.get('revenue', 0) or 0) / 1_000_000
            ebit_val = (ebit or 0) / 1_000_000
            da_val = (cf.get('depreciationAndAmortization', 0) or 0) / 1_000_000
            wc_val = -(cf.get('changeInWorkingCapital', 0) or 0) / 1_000_000
            capex_val = -(cf.get('investmentsInPropertyPlantAndEquipment', 0) or 0) / 1_000_000
            reinvest_val = (total_reinvestments or 0) / 1_000_000
            debt_val = (total_debt or 0) / 1_000_000
            equity_val = (bs.get('totalEquity', 0) or 0) / 1_000_000
            minority_val = (bs.get('minorityInterest', 0) or 0) / 1_000_000
            cash_val = (bs.get('cashAndCashEquivalents', 0) or 0) / 1_000_000
            invest_val = (bs.get('totalInvestments', 0) or 0) / 1_000_000
            ic_val = (invested_capital or 0) / 1_000_000
            ebit_margin = (ebit / (inc.get('revenue', 0) or 1)) * 100 if inc.get('revenue', 0) != 0 else 0

            # Tag whether this quarter has actual cashflow data (vs. date-gap fill with zeros)
            _has_cf = is_a_share(ticker) or (is_hk_stock(ticker) and period == 'annual') or (cf is not _empty_cf)

            data = {
                'Calendar Year': inc.get('calendarYear', 'N/A'),
                'Date': inc.get('date', 'N/A'),
                'Period': inc.get('period', 'N/A'),
                'Reported Currency': inc.get('reportedCurrency', 'N/A'),
                '_has_cf': _has_cf,
                # ── Profitability ──
                '▸ Profitability': '',
                'Revenue': revenue_val,
                'EBIT': ebit_val,
                'Revenue Growth (%)': revenue_growth,
                'EBIT Growth (%)': ebit_growth,
                'EBIT Margin (%)': ebit_margin,
                'Tax Rate (%)': tax_rate * 100,
                # ── Reinvestment ──
                '▸ Reinvestment': '',
                '(+) Capital Expenditure': capex_val,
                '(-) D&A': da_val,
                '(+) ΔWorking Capital': wc_val,
                'Total Reinvestment': reinvest_val,
                # ── Capital Structure ──
                '▸ Capital Structure': '',
                '(+) Total Debt': debt_val,
                '(+) Total Equity': equity_val,
                '(-) Cash & Equivalents': cash_val,
                '(-) Total Investments': invest_val,
                'Invested Capital': ic_val,
                'Minority Interest': minority_val,
                # ── Key Ratios ──
                '▸ Key Ratios': '',
                'Revenue / IC': revenue_to_invested_capital,
                'Debt to Assets (%)': (km.get('debtToAssets', 0) or 0) * 100,
                'Cost of Debt (%)': cost_of_debt * 100,
                'ROIC (%)': (km.get('roic', 0) or 0) * 100,
                'ROE (%)': (km.get('roe', 0) or 0) * 100,
            }
            if not is_a_share(ticker):
                data['Dividend Yield (%)'] = (km.get('dividendYield', 0) or 0) * 100
                data['Payout Ratio (%)'] = (km.get('payoutRatio', 0) or 0) * 100
            summary_data.append(data)

        # --- TTM column: prepend to summary_data when latest data is not full-year ---
        # For quarter mode: compute if latest quarter is not Q4
        # For annual mode: always attempt (latest quarterly data may be more recent than latest FY)
        _need_ttm = False
        _ttm_latest_quarter = ''
        if period == 'quarter' and len(summary_data) >= 4:
            if is_hk_stock(ticker):
                pass  # HK quarter mode: no TTM column
            else:
                latest_period = summary_data[0].get('Period', '')
                # Skip TTM for Q1 (too early), Q4/FY (already full year)
                if latest_period not in ('Q4', 'FY', 'Q1'):
                    _need_ttm = True
        elif period == 'annual' and len(summary_data) >= 1:
            _need_ttm = True  # Always attempt TTM for annual; will check quarterly data availability

        _ttm_end_date = ''  # Track TTM end date for output
        _ttm_net_income_m = None  # TTM net income in millions (for ROIC/ROE calculation)

        if _need_ttm:
            # Find the latest full-year Calendar Year from summary_data.
            # Annual mode: summary_data[0] is always FY.
            # Quarter mode: scan for Period='FY' or 'Q4' entry.
            _latest_fy_cal_year = ''
            for _sd in summary_data:
                if _sd.get('Period', '') in ('FY', 'Q4'):
                    _latest_fy_cal_year = str(_sd.get('Calendar Year', ''))
                    break
            if not _latest_fy_cal_year and summary_data:
                # Fallback: use summary_data[0] Calendar Year (annual mode always works)
                _latest_fy_cal_year = str(summary_data[0].get('Calendar Year', ''))

            bs_items = ['(+) Total Debt', '(+) Total Equity',
                        '(-) Cash & Equivalents', '(-) Total Investments',
                        'Invested Capital', 'Minority Interest']
            ttm_data = None
            ttm_note = ''  # Note about data sources for reinvestment items
            _akshare_latest_q_bs = {}  # Latest quarterly BS for A-shares (populated below)

            if is_a_share(ticker):
                # --- A-share TTM: use YTD cumulative method ---
                # Reuse cached full cumulative DataFrames to avoid duplicate API calls
                ttm_income = _compute_akshare_ttm_income(ticker, df=_full_income_df)
                ttm_cf = _compute_akshare_ttm_cashflow(ticker, df=_full_cf_df)

                # Check if latest report is Q1 — show message (ttm_income will be None)
                if ttm_income is None and _full_income_df is not None:
                    _ak_sorted = _full_income_df.sort_values('REPORT_DATE', ascending=False)
                    if not _ak_sorted.empty:
                        _ak_latest_month = int(str(_ak_sorted.iloc[0]['REPORT_DATE'])[5:7])
                        if _ak_latest_month == 3:
                            print(S.muted(f"  ⓘ 最新季度为 Q1，数据不足以计算有意义的 TTM，使用最近年度数据作为估值基础。"))

                if ttm_income:
                    _ttm_latest_date = ttm_income.get('_latest_date', '')
                    _ttm_latest_quarter = ttm_income.get('_latest_quarter', '')
                    _ttm_end_date = _ttm_latest_date
                    # TTM calendar year = latest full-year calendar year + 1
                    _ttm_label_year = str(int(_latest_fy_cal_year) + 1) if _latest_fy_cal_year.isdigit() else (_ttm_latest_date[:4] if _ttm_latest_date else '')
                    ttm_revenue = ttm_income['revenue'] / 1_000_000
                    ttm_ebit = ttm_income['operatingIncome'] / 1_000_000
                    ttm_tax_rate = (ttm_income['incomeTaxExpense'] / ttm_income['incomeBeforeTax'] * 100
                                    ) if ttm_income['incomeBeforeTax'] != 0 else summary_data[0]['Tax Rate (%)']
                    _ttm_net_income_m = (ttm_income['incomeBeforeTax'] - ttm_income['incomeTaxExpense']) / 1_000_000

                    # Growth: TTM vs prior-year TTM (not vs FY)
                    prior_ttm_rev = ttm_income.get('_prior_ttm_revenue')
                    prior_ttm_ebit_raw = ttm_income.get('_prior_ttm_ebit')
                    if prior_ttm_rev is not None:
                        prev_revenue = prior_ttm_rev / 1_000_000
                        prev_ebit = prior_ttm_ebit_raw / 1_000_000
                    else:
                        prev_revenue = summary_data[0]['Revenue']
                        prev_ebit = summary_data[0]['EBIT']

                    _ttm_period_label = f'{_ttm_label_year}{_ttm_latest_quarter}(TTM)' if _ttm_latest_quarter else 'TTM'
                    ttm_data = {
                        'Calendar Year': _ttm_label_year,
                        'Date': _ttm_latest_date,
                        'Period': _ttm_period_label,
                        'Reported Currency': summary_data[0]['Reported Currency'],
                        '▸ Profitability': '',
                        'Revenue': ttm_revenue,
                        'EBIT': ttm_ebit,
                        'Revenue Growth (%)': ((ttm_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue != 0 else 0,
                        'EBIT Growth (%)': ((ttm_ebit - prev_ebit) / prev_ebit * 100) if prev_ebit != 0 else 0,
                        'EBIT Margin (%)': (ttm_ebit / ttm_revenue * 100) if ttm_revenue != 0 else 0,
                        'Tax Rate (%)': ttm_tax_rate,
                    }

                    if ttm_cf:
                        capex_ttm = -ttm_cf['investmentsInPropertyPlantAndEquipment'] / 1_000_000
                        da_ttm = ttm_cf['depreciationAndAmortization'] / 1_000_000
                        wc_ttm = -ttm_cf['changeInWorkingCapital'] / 1_000_000
                        ttm_note = ttm_cf.get('_note', '')
                    else:
                        # Fallback: use most recent FY values
                        capex_ttm = summary_data[0]['(+) Capital Expenditure']
                        da_ttm = summary_data[0]['(-) D&A']
                        wc_ttm = summary_data[0]['(+) ΔWorking Capital']
                        _fy_year = summary_data[0].get('Calendar Year', '?')
                        ttm_note = f'Capex/D&A/WC use FY{_fy_year} annual data (quarterly CF unavailable)'

                    ttm_data['▸ Reinvestment'] = ''
                    ttm_data['(+) Capital Expenditure'] = capex_ttm
                    ttm_data['(-) D&A'] = da_ttm
                    ttm_data['(+) ΔWorking Capital'] = wc_ttm
                    ttm_data['Total Reinvestment'] = capex_ttm - da_ttm + wc_ttm

                    # Look up latest quarterly BS from unfiltered balance sheet DataFrame.
                    # _full_bs_df contains all report periods (Q1/Q2/Q3/FY); match by TTM end date.
                    _akshare_latest_q_bs = {}
                    if _full_bs_df is not None and _ttm_latest_date:
                        _bs_sorted = _full_bs_df.sort_values('REPORT_DATE', ascending=False)
                        _ttm_date_str_short = _ttm_latest_date[:10]  # 'YYYY-MM-DD'
                        for _, _bs_row in _bs_sorted.iterrows():
                            _bs_date = str(_bs_row.get('REPORT_DATE', ''))[:10]
                            if _bs_date <= _ttm_date_str_short:
                                _akshare_latest_q_bs = _parse_akshare_bs_row(_bs_row)
                                break

            elif is_hk_stock(ticker):
                # Set q_inc = None so shared TTM block (FMP path) doesn't run
                q_inc = None

                if _hk_use_akshare:
                    # --- HK web TTM: akshare YTD cumulative method (same as A-shares) ---
                    from .akshare_hk_data import (
                        _compute_hk_ttm_income,
                        _compute_hk_ttm_cashflow,
                        _pivot_report as _hk_pivot,
                        _parse_hk_bs as _parse_hk_bs_items,
                    )
                    ttm_income = None
                    ttm_cf = None
                    if period == 'annual' and _full_income_df is not None:
                        print(S.info(f"Computing TTM from akshare for {ticker}..."))
                        ttm_income = _compute_hk_ttm_income(ticker, _full_income_df)
                        ttm_cf = _compute_hk_ttm_cashflow(ticker, _full_cf_df)

                        # Check if TTM skipped due to insufficient data (not because latest IS FY)
                        if ttm_income is None and _full_income_df is not None:
                            from .akshare_hk_data import _get_fy_dates as _hk_get_fy_dates
                            _hk_grouped, _hk_dates = _hk_pivot(_full_income_df)
                            if _hk_dates:
                                _hk_fy_set = _hk_get_fy_dates(_full_income_df)
                                _hk_latest = _hk_dates[0]
                                if _hk_latest not in _hk_fy_set:
                                    print(S.muted(f"  ⓘ 最新报告期 ({_hk_latest}) 数据不足以计算 TTM，使用最近年度数据作为估值基础。"))

                    if ttm_income:
                        _ttm_latest_date = ttm_income.get('_latest_date', '')
                        _ttm_latest_quarter = ttm_income.get('_latest_quarter', '')
                        _ttm_end_date = _ttm_latest_date
                        _ttm_label_year = str(int(_latest_fy_cal_year) + 1) if _latest_fy_cal_year.isdigit() else (_ttm_latest_date[:4] if _ttm_latest_date else '')

                        ttm_revenue = ttm_income['revenue'] / 1_000_000
                        ttm_ebit = ttm_income['operatingIncome'] / 1_000_000

                        ttm_pbt = ttm_income['incomeBeforeTax']
                        ttm_tax_exp = ttm_income['incomeTaxExpense']
                        ttm_tax_rate = (ttm_tax_exp / ttm_pbt * 100) if ttm_pbt != 0 else summary_data[0]['Tax Rate (%)']
                        _ttm_net_income_m = (ttm_pbt - ttm_tax_exp) / 1_000_000

                        prev_revenue = summary_data[0]['Revenue']
                        prev_ebit = summary_data[0]['EBIT']

                        _ttm_period_label = f'{_ttm_label_year}{_ttm_latest_quarter}(TTM)' if _ttm_latest_quarter else 'TTM'
                        ttm_data = {
                            'Calendar Year': _ttm_label_year,
                            'Date': _ttm_latest_date,
                            'Period': _ttm_period_label,
                            'Reported Currency': summary_data[0]['Reported Currency'],
                            '▸ Profitability': '',
                            'Revenue': ttm_revenue,
                            'EBIT': ttm_ebit,
                            'Revenue Growth (%)': ((ttm_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue != 0 else 0,
                            'EBIT Growth (%)': ((ttm_ebit - prev_ebit) / prev_ebit * 100) if prev_ebit != 0 else 0,
                            'EBIT Margin (%)': (ttm_ebit / ttm_revenue * 100) if ttm_revenue != 0 else 0,
                            'Tax Rate (%)': ttm_tax_rate,
                        }

                        # Reinvestment from TTM CF
                        ttm_data['▸ Reinvestment'] = ''
                        if ttm_cf:
                            capex_ttm = -ttm_cf['investmentsInPropertyPlantAndEquipment'] / 1_000_000
                            da_ttm = ttm_cf['depreciationAndAmortization'] / 1_000_000
                            wc_ttm = -ttm_cf['changeInWorkingCapital'] / 1_000_000
                            ttm_note = ''
                        else:
                            capex_ttm = summary_data[0]['(+) Capital Expenditure']
                            da_ttm = summary_data[0]['(-) D&A']
                            wc_ttm = summary_data[0]['(+) ΔWorking Capital']
                            _fy_year = summary_data[0].get('Calendar Year', '?')
                            ttm_note = f'Capex/D&A/WC use FY{_fy_year} annual data (quarterly CF unavailable)'

                        ttm_data['(+) Capital Expenditure'] = capex_ttm
                        ttm_data['(-) D&A'] = da_ttm
                        ttm_data['(+) ΔWorking Capital'] = wc_ttm
                        ttm_data['Total Reinvestment'] = capex_ttm - da_ttm + wc_ttm

                        # BS: look up latest quarterly BS from full_bs_df
                        _akshare_latest_q_bs = {}
                        if _full_bs_df is not None and _ttm_latest_date:
                            _hk_bs_grouped, _hk_bs_dates = _hk_pivot(_full_bs_df)
                            for _bd in _hk_bs_dates:
                                if _bd <= _ttm_latest_date:
                                    _akshare_latest_q_bs = _parse_hk_bs_items(_hk_bs_grouped[_bd])
                                    break
                    else:
                        if period == 'annual':
                            print(S.muted(f"  ⓘ No TTM data available for {ticker}; TTM skipped."))

                else:
                    # --- HK terminal TTM: yfinance pre-computed TTM ---
                    if period == 'annual':
                        from .yfinance_data import fetch_yfinance_hk_ttm
                        print(S.info(f"Fetching TTM data from yfinance for {ticker}..."))
                        yf_ttm = fetch_yfinance_hk_ttm(ticker)

                        if yf_ttm and yf_ttm.get('has_ttm_income'):
                            _ttm_latest_date = yf_ttm['ttm_end_date']
                            _ttm_latest_quarter = yf_ttm['ttm_quarter']
                            _ttm_end_date = _ttm_latest_date
                            _ttm_label_year = str(int(_latest_fy_cal_year) + 1) if _latest_fy_cal_year.isdigit() else (_ttm_latest_date[:4] if _ttm_latest_date else '')

                            ttm_revenue = yf_ttm['revenue'] / 1_000_000
                            ttm_ebit = yf_ttm['operatingIncome'] / 1_000_000

                            ttm_pbt = yf_ttm['incomeBeforeTax']
                            ttm_tax_exp = yf_ttm['incomeTaxExpense']
                            ttm_tax_rate = (ttm_tax_exp / ttm_pbt * 100) if ttm_pbt != 0 else summary_data[0]['Tax Rate (%)']
                            _ttm_net_income_m = (ttm_pbt - ttm_tax_exp) / 1_000_000

                            prev_revenue = summary_data[0]['Revenue']
                            prev_ebit = summary_data[0]['EBIT']

                            _ttm_period_label = f'{_ttm_label_year}{_ttm_latest_quarter}(TTM)' if _ttm_latest_quarter else 'TTM'
                            ttm_data = {
                                'Calendar Year': _ttm_label_year,
                                'Date': _ttm_latest_date,
                                'Period': _ttm_period_label,
                                'Reported Currency': summary_data[0]['Reported Currency'],
                                '▸ Profitability': '',
                                'Revenue': ttm_revenue,
                                'EBIT': ttm_ebit,
                                'Revenue Growth (%)': ((ttm_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue != 0 else 0,
                                'EBIT Growth (%)': ((ttm_ebit - prev_ebit) / prev_ebit * 100) if prev_ebit != 0 else 0,
                                'EBIT Margin (%)': (ttm_ebit / ttm_revenue * 100) if ttm_revenue != 0 else 0,
                                'Tax Rate (%)': ttm_tax_rate,
                            }

                            # Reinvestment from TTM CF
                            ttm_data['▸ Reinvestment'] = ''
                            if yf_ttm.get('has_ttm_cashflow') and yf_ttm.get('depreciationAndAmortization') is not None:
                                capex_raw = yf_ttm['investmentsInPropertyPlantAndEquipment'] or 0
                                capex_ttm = -capex_raw / 1_000_000  # yfinance capex is negative
                                da_ttm = (yf_ttm['depreciationAndAmortization'] or 0) / 1_000_000
                                wc_raw = yf_ttm['changeInWorkingCapital'] or 0
                                wc_ttm = -wc_raw / 1_000_000
                                ttm_note = ''
                            else:
                                capex_ttm = summary_data[0]['(+) Capital Expenditure']
                                da_ttm = summary_data[0]['(-) D&A']
                                wc_ttm = summary_data[0]['(+) ΔWorking Capital']
                                _fy_year = summary_data[0].get('Calendar Year', '?')
                                ttm_note = f'Capex/D&A/WC use FY{_fy_year} annual data (quarterly CF unavailable)'

                            ttm_data['(+) Capital Expenditure'] = capex_ttm
                            ttm_data['(-) D&A'] = da_ttm
                            ttm_data['(+) ΔWorking Capital'] = wc_ttm
                            ttm_data['Total Reinvestment'] = capex_ttm - da_ttm + wc_ttm

                            # BS: fetch latest quarterly BS from yfinance
                            _akshare_latest_q_bs = {}
                            try:
                                from .yfinance_data import _extract_yf_bs_row, _get_yf
                                _yf_mod = _get_yf()
                                _yf_t = _yf_mod.Ticker(ticker)
                                _qbs_df = _yf_t.quarterly_balance_sheet
                                if _qbs_df is not None and not _qbs_df.empty:
                                    _akshare_latest_q_bs = _extract_yf_bs_row(_qbs_df, _qbs_df.columns[0])
                            except Exception:
                                pass  # Fallback to annual BS in shared finalize block
                        else:
                            print(S.muted(f"  ⓘ No TTM data available for {ticker}; TTM skipped."))

            else:
                # --- FMP TTM: fetch quarterly data and sum 4 quarters ---
                # For annual mode, we need to fetch quarterly data separately
                if period == 'annual':
                    q_urls = {
                        'income': get_api_url('income-statement', ticker, 'quarter', apikey),
                        'balance': get_api_url('balance-sheet-statement', ticker, 'quarter', apikey),
                        'cashflow': get_api_url('cash-flow-statement', ticker, 'quarter', apikey),
                    }
                    with ThreadPoolExecutor(max_workers=3) as ex:
                        q_futures = {k: ex.submit(get_jsonparsed_data, v) for k, v in q_urls.items()}
                    q_inc = q_futures['income'].result()[:8]
                    q_bs = q_futures['balance'].result()[:8]
                    q_cf = q_futures['cashflow'].result()[:8]

                    # FMP totalDebt already includes capitalLeaseObligations — no adjustment needed

                    # Detect and fix cumulative YTD cashflow data (common for HK/IFRS stocks).
                    # Under IAS 34, interim CF statements are cumulative YTD. Some data providers
                    # return these raw without de-cumulating to single-quarter values.
                    q_cf = _decumulate_quarterly_cf_if_needed(q_cf, summary_data)

                    # Only compute TTM if latest quarter is Q2 or Q3
                    # (Q1: too early, use annual; Q4/FY: already full year)
                    _latest_q_period = q_inc[0].get('period', '') if q_inc else ''
                    if _latest_q_period not in ('Q4', 'FY', 'Q1') and q_inc:
                        q_cf_by_date = {d.get('date'): d for d in reversed(q_cf)}
                        q_bs_by_date = {d.get('date'): d for d in reversed(q_bs)}
                    else:
                        if _latest_q_period == 'Q1':
                            print(S.muted(f"  ⓘ 最新季度为 Q1，数据不足以计算有意义的 TTM，使用最近年度数据作为估值基础。"))
                        q_inc = None  # Signal: no TTM needed
                else:
                    # Quarter mode: reuse already-fetched data
                    q_inc = income_statement
                    q_bs_by_date = bs_by_date
                    q_cf_by_date = cf_by_date

            # --- Shared TTM computation for FMP stocks ---
            # (A-shares use YTD cumulative method above; HK stocks use yfinance TTM APIs above)
            if not is_a_share(ticker) and not is_hk_stock(ticker):
                # Detect semi-annual reporting: if data only has Q2/Q4 entries,
                # the company reports semi-annually.
                _is_semi_annual = False
                if q_inc and len(q_inc) >= 2:
                    _first_periods = [q_inc[j].get('period', '') for j in range(min(6, len(q_inc)))]
                    _has_q1_or_q3 = any(p in ('Q1', 'Q3') for p in _first_periods)
                    if not _has_q1_or_q3:
                        _is_semi_annual = True

                if _is_semi_annual and q_inc and len(q_inc) >= 2:
                    # --- Semi-annual TTM: FY + (latest_Q - prior_year_Q) ---
                    # yfinance quarterly data for semi-annual reporters contains single-
                    # quarter figures (each ~3 months). We cannot simply sum 2 records
                    # (that gives 6 months). Instead use the standard analyst method:
                    # TTM = Latest FY + (latest quarter - same quarter prior year)
                    print(S.muted(f"  ⓘ 检测到半年报公司，使用 FY + Δ 方法计算 TTM"))

                    _ttm_q_date = q_inc[0].get('date', '')
                    _ttm_latest_quarter = q_inc[0].get('period', '')
                    _ttm_end_date = _ttm_q_date
                    _ttm_label_year = str(int(_latest_fy_cal_year) + 1) if _latest_fy_cal_year.isdigit() else (_ttm_q_date[:4] if _ttm_q_date else '')

                    # q_inc[0] = latest quarter (e.g., Q2 2025)
                    # q_inc[1] = same quarter prior year (e.g., Q2 2024)
                    # summary_data[0] = latest FY (e.g., FY 2024)
                    _q_latest = q_inc[0]
                    _q_prior = q_inc[1]
                    _fy = summary_data[0]

                    # Revenue: TTM = FY + (Q_latest - Q_prior)
                    _fy_rev_raw = _fy['Revenue'] * 1_000_000  # back to raw from millions
                    _q_latest_rev = _q_latest.get('revenue', 0) or 0
                    _q_prior_rev = _q_prior.get('revenue', 0) or 0
                    ttm_revenue = (_fy_rev_raw + _q_latest_rev - _q_prior_rev) / 1_000_000

                    # EBIT: same FY+delta approach
                    _fy_ebit_raw = _fy['EBIT'] * 1_000_000
                    _q_latest_ebit = _q_latest.get('operatingIncome', 0) or 0
                    _q_prior_ebit = _q_prior.get('operatingIncome', 0) or 0
                    ttm_ebit = (_fy_ebit_raw + _q_latest_ebit - _q_prior_ebit) / 1_000_000

                    # Tax rate: FY+delta for PBT and tax
                    _fy_tax_rate = _fy['Tax Rate (%)'] / 100
                    _fy_pbt_raw = _fy_ebit_raw  # approximate (EBIT ≈ PBT for tax estimation)
                    _q_latest_pbt = _q_latest.get('incomeBeforeTax', 0) or 0
                    _q_prior_pbt = _q_prior.get('incomeBeforeTax', 0) or 0
                    _q_latest_tax = _q_latest.get('incomeTaxExpense', 0) or 0
                    _q_prior_tax = _q_prior.get('incomeTaxExpense', 0) or 0
                    # Use actual PBT from income data for more accurate TTM tax rate
                    _fy_inc_raw = income_statement[0]  # latest FY income data
                    _fy_pbt_actual = _fy_inc_raw.get('incomeBeforeTax', 0) or 0
                    _fy_tax_actual = _fy_inc_raw.get('incomeTaxExpense', 0) or 0
                    ttm_pbt = _fy_pbt_actual + _q_latest_pbt - _q_prior_pbt
                    ttm_tax_exp = _fy_tax_actual + _q_latest_tax - _q_prior_tax
                    ttm_tax_rate = (ttm_tax_exp / ttm_pbt * 100) if ttm_pbt != 0 else _fy['Tax Rate (%)']
                    _ttm_net_income_m = (ttm_pbt - ttm_tax_exp) / 1_000_000

                    # Growth: TTM vs prior FY
                    prev_revenue = _fy['Revenue']
                    prev_ebit = _fy['EBIT']

                    _ttm_period_label = f'{_ttm_label_year}{_ttm_latest_quarter}(TTM)' if _ttm_latest_quarter else 'TTM'
                    ttm_data = {
                        'Calendar Year': _ttm_label_year,
                        'Date': _ttm_q_date,
                        'Period': _ttm_period_label,
                        'Reported Currency': q_inc[0].get('reportedCurrency', _fy['Reported Currency']),
                        '▸ Profitability': '',
                        'Revenue': ttm_revenue,
                        'EBIT': ttm_ebit,
                        'Revenue Growth (%)': ((ttm_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue != 0 else 0,
                        'EBIT Growth (%)': ((ttm_ebit - prev_ebit) / prev_ebit * 100) if prev_ebit != 0 else 0,
                        'EBIT Margin (%)': (ttm_ebit / ttm_revenue * 100) if ttm_revenue != 0 else 0,
                        'Tax Rate (%)': ttm_tax_rate,
                    }

                    # Reinvestment: no quarterly CF available for semi-annual reporters,
                    # fall back to FY data
                    ttm_data['▸ Reinvestment'] = ''
                    ttm_data['(+) Capital Expenditure'] = _fy['(+) Capital Expenditure']
                    ttm_data['(-) D&A'] = _fy['(-) D&A']
                    ttm_data['(+) ΔWorking Capital'] = _fy['(+) ΔWorking Capital']
                    ttm_data['Total Reinvestment'] = _fy['Total Reinvestment']
                    _fy_year_str = _fy.get('Calendar Year', '?')
                    ttm_note = f'Capex/D&A/WC use FY{_fy_year_str} annual data (quarterly CF unavailable for semi-annual reporters)'

                    # BS: use quarterly BS if available, else FY
                    latest_q_bs = q_bs_by_date.get(_ttm_q_date) if q_bs_by_date else {}
                    if not latest_q_bs and q_bs:
                        latest_q_bs = q_bs[0] if isinstance(q_bs, list) and q_bs else {}

                elif not _is_semi_annual and q_inc and len(q_inc) >= 4:
                    # --- Quarterly TTM: standard sum of 4 quarters ---
                    n = 4
                    _ttm_q_date = q_inc[0].get('date', '')
                    _ttm_latest_quarter = q_inc[0].get('period', '')
                    _ttm_end_date = _ttm_q_date
                    _ttm_label_year = str(int(_latest_fy_cal_year) + 1) if _latest_fy_cal_year.isdigit() else (_ttm_q_date[:4] if _ttm_q_date else '')

                    # Revenue & EBIT: sum 4 quarters
                    ttm_revenue = sum((q_inc[j].get('revenue', 0) or 0) for j in range(n)) / 1_000_000
                    ttm_ebit = sum((q_inc[j].get('operatingIncome', 0) or 0) for j in range(n)) / 1_000_000

                    # TTM tax rate = sum(4 quarters tax) / sum(4 quarters pbt)
                    ttm_pbt = sum((q_inc[j].get('incomeBeforeTax', 0) or 0) for j in range(n))
                    ttm_tax_exp = sum((q_inc[j].get('incomeTaxExpense', 0) or 0) for j in range(n))
                    ttm_tax_rate = (ttm_tax_exp / ttm_pbt * 100) if ttm_pbt != 0 else summary_data[0]['Tax Rate (%)']
                    _ttm_net_income_m = (ttm_pbt - ttm_tax_exp) / 1_000_000

                    # Growth: TTM vs prior-year TTM (next 4 quarters if available)
                    if len(q_inc) >= 2 * n:
                        prev_revenue = sum((q_inc[j].get('revenue', 0) or 0) for j in range(n, 2 * n)) / 1_000_000
                        prev_ebit = sum((q_inc[j].get('operatingIncome', 0) or 0) for j in range(n, 2 * n)) / 1_000_000
                    else:
                        prev_revenue = summary_data[0]['Revenue']
                        prev_ebit = summary_data[0]['EBIT']

                    _ttm_period_label = f'{_ttm_label_year}{_ttm_latest_quarter}(TTM)' if _ttm_latest_quarter else 'TTM'
                    ttm_data = {
                        'Calendar Year': _ttm_label_year,
                        'Date': _ttm_q_date,
                        'Period': _ttm_period_label,
                        'Reported Currency': q_inc[0].get('reportedCurrency', summary_data[0]['Reported Currency']),
                        '▸ Profitability': '',
                        'Revenue': ttm_revenue,
                        'EBIT': ttm_ebit,
                        'Revenue Growth (%)':((ttm_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue != 0 else 0,
                        'EBIT Growth (%)': ((ttm_ebit - prev_ebit) / prev_ebit * 100) if prev_ebit != 0 else 0,
                        'EBIT Margin (%)': (ttm_ebit / ttm_revenue * 100) if ttm_revenue != 0 else 0,
                        'Tax Rate (%)': ttm_tax_rate,
                    }

                    # Reinvestment: match CF by date, skip periods without CF data
                    _q_empty_cf = {'depreciationAndAmortization': 0, 'investmentsInPropertyPlantAndEquipment': 0, 'changeInWorkingCapital': 0}
                    q_cf_matched = []
                    for j in range(len(q_inc)):
                        qd = q_inc[j].get('date', '')
                        matched_cf = q_cf_by_date.get(qd)
                        q_cf_matched.append((j, matched_cf is not None, matched_cf or _q_empty_cf))

                    # Find 4 quarters with actual CF data
                    cf_quarters = [(j, cf_d) for j, has, cf_d in q_cf_matched if has][:n]

                    ttm_data['▸ Reinvestment'] = ''
                    if len(cf_quarters) >= n:
                        ttm_capex = sum(-(cf_d.get('investmentsInPropertyPlantAndEquipment', 0) or 0) for _, cf_d in cf_quarters) / 1_000_000
                        ttm_da = sum((cf_d.get('depreciationAndAmortization', 0) or 0) for _, cf_d in cf_quarters) / 1_000_000
                        ttm_wc = sum(-(cf_d.get('changeInWorkingCapital', 0) or 0) for _, cf_d in cf_quarters) / 1_000_000
                        # Build detailed note: distinguish Capex/D&A vs WC data sources
                        _note_parts = []
                        skipped_dates = [q_inc[j].get('date','?') for j, has, _ in q_cf_matched[:n] if not has]
                        if skipped_dates:
                            used_dates = [q_inc[j].get('date','?') for j, _ in cf_quarters]
                            _note_parts.append(f'Capex/D&A: using {", ".join(used_dates)} ({", ".join(skipped_dates)} CF unavailable)')
                        # Check WC: how many of the used periods have non-zero WC?
                        wc_nonzero = [(j, cf_d) for j, cf_d in cf_quarters if (cf_d.get('changeInWorkingCapital', 0) or 0) != 0]
                        if len(wc_nonzero) < len(cf_quarters):
                            wc_dates = [q_inc[j].get('date','?') for j, _ in wc_nonzero] if wc_nonzero else ['N/A']
                            _note_parts.append(f'WC: only {", ".join(wc_dates)} has data (other periods = 0)')
                        if _note_parts:
                            ttm_note = '; '.join(_note_parts)
                    else:
                        # Fallback: use FY data for reinvestment
                        ttm_data['(+) Capital Expenditure'] = summary_data[0]['(+) Capital Expenditure']
                        ttm_data['(-) D&A'] = summary_data[0]['(-) D&A']
                        ttm_data['(+) ΔWorking Capital'] = summary_data[0]['(+) ΔWorking Capital']
                        ttm_data['Total Reinvestment'] = summary_data[0]['Total Reinvestment']
                        available_count = sum(1 for _, has, _ in q_cf_matched[:n] if has)
                        _fy_year_str = summary_data[0].get('Calendar Year', '?')
                        ttm_note = f'Capex/D&A/WC use FY{_fy_year_str} annual data (only {available_count}/4 quarters have CF data)'

                    if 'Total Reinvestment' not in ttm_data:
                        ttm_data['(+) Capital Expenditure'] = ttm_capex
                        ttm_data['(-) D&A'] = ttm_da
                        ttm_data['(+) ΔWorking Capital'] = ttm_wc
                        ttm_data['Total Reinvestment'] = ttm_capex - ttm_da + ttm_wc

                    # Use latest quarterly BS for capital structure
                    if period == 'annual':
                        latest_q_bs = q_bs_by_date.get(q_inc[0].get('date', '')) or (q_bs[0] if q_bs else {})
                    else:
                        latest_q_bs = q_bs_by_date.get(q_inc[0].get('date', '')) or {}

                else:
                    pass  # Not enough quarterly data for TTM; silently skip

            # Finalize TTM: capital structure, key ratios
            if ttm_data is not None:
                # Capital Structure: point-in-time from latest quarterly BS
                ttm_data['▸ Capital Structure'] = ''
                # Determine quarterly BS source:
                #   FMP/HK stocks (annual mode): latest_q_bs from quarterly API/yfinance
                #   A-shares (annual mode): _akshare_latest_q_bs from unfiltered akshare DataFrame
                #   Quarter mode: from existing quarterly data (already handled above)
                _use_quarterly_bs = False
                if (is_a_share(ticker) or is_hk_stock(ticker)) and period == 'annual':
                    _lbs = _akshare_latest_q_bs if _akshare_latest_q_bs else {}
                    _use_quarterly_bs = bool(_lbs)
                    _q_scale = 1_000_000  # akshare returns raw values in currency units
                elif period == 'annual':
                    _lbs = latest_q_bs
                    _use_quarterly_bs = bool(_lbs)
                    _q_scale = 1_000_000  # FMP returns raw values in reporting currency

                if _use_quarterly_bs:
                    ttm_data['(+) Total Debt'] = (_lbs.get('totalDebt', 0) or 0) / _q_scale
                    ttm_data['(+) Total Equity'] = (_lbs.get('totalEquity', 0) or 0) / _q_scale
                    ttm_data['(-) Cash & Equivalents'] = (_lbs.get('cashAndCashEquivalents', 0) or 0) / _q_scale
                    ttm_data['(-) Total Investments'] = (_lbs.get('totalInvestments', 0) or 0) / _q_scale
                    ttm_data['Invested Capital'] = (ttm_data['(+) Total Debt'] + ttm_data['(+) Total Equity']
                                                    - ttm_data['(-) Cash & Equivalents'] - ttm_data['(-) Total Investments'])
                    ttm_data['Minority Interest'] = (_lbs.get('minorityInterest', 0) or 0) / _q_scale
                else:
                    for item in bs_items:
                        ttm_data[item] = summary_data[0][item]

                # Key Ratios
                ttm_data['▸ Key Ratios'] = ''
                ttm_ic = ttm_data['Invested Capital']
                ttm_data['Revenue / IC'] = (ttm_data['Revenue'] / ttm_ic) if ttm_ic != 0 else 0

                # ROIC and ROE: compute from TTM data using average denominators
                # Average = (latest quarter-end + prior year-end) / 2
                prior_fy_ic = summary_data[0].get('Invested Capital', 0)
                prior_fy_equity = summary_data[0].get('(+) Total Equity', 0)
                avg_ic = (ttm_ic + prior_fy_ic) / 2 if (ttm_ic + prior_fy_ic) != 0 else 0
                avg_equity = (ttm_data.get('(+) Total Equity', 0) + prior_fy_equity) / 2

                ttm_ebit_val = ttm_data['EBIT']
                ttm_tax_pct = ttm_data['Tax Rate (%)']
                ttm_data['ROIC (%)'] = ((ttm_ebit_val * (1 - ttm_tax_pct / 100)) / avg_ic * 100) if avg_ic != 0 else 0
                if _ttm_net_income_m is not None and avg_equity != 0:
                    ttm_data['ROE (%)'] = (_ttm_net_income_m / avg_equity * 100)
                else:
                    ttm_data['ROE (%)'] = summary_data[0].get('ROE (%)', 0)

                # Other point-in-time ratios
                # Debt to Assets: recompute from quarterly BS when available
                if _use_quarterly_bs:
                    _total_assets_raw = (_lbs.get('totalAssets', 0) or 0) / _q_scale
                    _total_debt_raw = ttm_data['(+) Total Debt']
                    ttm_data['Debt to Assets (%)'] = (_total_debt_raw / _total_assets_raw * 100) if _total_assets_raw != 0 else 0
                else:
                    ttm_data['Debt to Assets (%)'] = summary_data[0].get('Debt to Assets (%)', 0)
                ttm_data['Cost of Debt (%)'] = summary_data[0].get('Cost of Debt (%)', 0)
                if not is_a_share(ticker):
                    for ratio in ['Dividend Yield (%)', 'Payout Ratio (%)']:
                        ttm_data[ratio] = summary_data[0].get(ratio, 0)

                # Add note about reinvestment data sources (if any)
                if ttm_note:
                    ttm_data['_ttm_note'] = ttm_note

                summary_data.insert(0, ttm_data)

        avg_tax_rate = sum(tax_rates) / len(tax_rates) if tax_rates else 0

        # Remove internal flags before building DataFrame
        ttm_note = ''
        for d in summary_data:
            d.pop('_has_cf', None)
            if '_ttm_note' in d:
                ttm_note = d.pop('_ttm_note')

        summary_df = pd.DataFrame(summary_data).T
        summary_df.columns = summary_df.iloc[0]
        summary_df = summary_df[1:]

        income_df = pd.DataFrame(income_statement).T
        balance_df = pd.DataFrame(balance_sheet).T
        cashflow_df = pd.DataFrame(cashflow_statement).T

        result = {
            'income_statement': income_df,
            'balance_sheet': balance_df,
            'cashflow_statement': cashflow_df,
            'summary': summary_df,
            'average_tax_rate': avg_tax_rate,
            'ttm_note': ttm_note,
            'ttm_latest_quarter': _ttm_latest_quarter if _need_ttm else '',
            'ttm_end_date': _ttm_end_date,
        }

        # For A-shares and HK stocks, include complete raw financial statements for Excel export
        if is_a_share(ticker) or is_hk_stock(ticker):
            result['raw_income_statement'] = raw_income_df
            result['raw_balance_sheet'] = raw_balance_df
            result['raw_cashflow_statement'] = raw_cashflow_df

            # Extract company name and outstanding shares from ORIGINAL (un-transposed)
            # full DataFrames.  These are used by _fill_profile_from_financial_data()
            # to enrich the company profile when APIs fail on Streamlit Cloud.
            try:
                if _full_income_df is not None and not _full_income_df.empty:
                    if 'SECURITY_NAME_ABBR' in _full_income_df.columns:
                        _names = _full_income_df['SECURITY_NAME_ABBR'].dropna()
                        if not _names.empty:
                            result['_company_name_from_data'] = str(_names.iloc[0])
                if _full_bs_df is not None and not _full_bs_df.empty:
                    if 'SHARE_CAPITAL' in _full_bs_df.columns:
                        _sc = _full_bs_df.sort_values('REPORT_DATE', ascending=False)['SHARE_CAPITAL'].dropna()
                        if not _sc.empty:
                            result['_shares_from_data'] = float(_sc.iloc[0])
            except Exception:
                pass  # Non-critical; profile will use defaults

        return result
    except Exception as e:
        print(f"Error fetching financial data: {e}")
        traceback.print_exc()
        return None

def format_summary_df(summary_df):
    """Format summary_df for terminal display. Returns a new formatted copy; original is NOT modified."""
    df = summary_df.copy()

    AMOUNT_ROWS = ['Revenue', 'EBIT',
                   '(+) Capital Expenditure', '(-) D&A', '(+) ΔWorking Capital', 'Total Reinvestment',
                   '(+) Total Debt', '(+) Total Equity',
                   '(-) Cash & Equivalents', '(-) Total Investments',
                   'Invested Capital', 'Minority Interest']
    RATIO_ROWS = ['Revenue Growth (%)', 'EBIT Growth (%)', 'EBIT Margin (%)', 'Tax Rate (%)',
                  'Revenue / IC', 'Debt to Assets (%)', 'Cost of Debt (%)',
                  'ROIC (%)', 'ROE (%)', 'Dividend Yield (%)', 'Payout Ratio (%)']
    SECTION_HEADERS = ['▸ Profitability', '▸ Reinvestment', '▸ Capital Structure', '▸ Key Ratios']

    for index in df.index:
        if index in AMOUNT_ROWS:
            df.loc[index] = pd.to_numeric(df.loc[index], errors='coerce').apply(
                lambda x: f"{int(x):,}" if pd.notnull(x) else 'N/A')
        elif index in RATIO_ROWS:
            df.loc[index] = pd.to_numeric(df.loc[index], errors='coerce').apply(
                lambda x: f"{x:.1f}" if pd.notnull(x) else 'N/A')
        elif index in SECTION_HEADERS:
            df.loc[index] = [''] * len(df.columns)

    return df