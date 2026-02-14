from urllib.request import urlopen
import json, traceback
import pandas as pd
import requests
from . import style as S

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False

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

def get_company_share_float(ticker, apikey):
    url = f'https://financialmodelingprep.com/api/v4/shares_float?symbol={ticker}&apikey={apikey}'
    company_info = get_jsonparsed_data(url)
    if not company_info:
        raise ValueError(f"No company information found for ticker {ticker}.")
    return company_info[0]

def fetch_company_profile(ticker, apikey):
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

def _calc_akshare_ebit(row):
    """Calculate EBIT from a single akshare profit sheet row (China GAAP).

    EBIT = 营业利润 - 投资收益 - 公允价值变动收益 - 其他收益
           - 资产处置收益 - 信用减值损失 - 资产减值损失 + 财务费用
    """
    fields = ['OPERATE_PROFIT', 'INVEST_INCOME', 'FAIRVALUE_CHANGE_INCOME',
              'OTHER_INCOME', 'ASSET_DISPOSAL_INCOME', 'CREDIT_IMPAIRMENT_INCOME',
              'ASSET_IMPAIRMENT_INCOME', 'FINANCE_EXPENSE']
    vals = {f: pd.to_numeric(row.get(f, 0), errors='coerce') or 0 for f in fields}
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


def fetch_akshare_ebit(ticker, historical_periods=5, period='annual'):
    """Fetch EBIT from akshare (东方财富) for Chinese A-shares.

    For annual: uses stock_profit_sheet_by_report_em (filtered to 年报).
    For quarter: uses stock_profit_sheet_by_quarterly_em (single-quarter data).

    Returns dict:
        annual:  {calendar_year: ebit_in_millions}      e.g. {'2024': 85432.5}
        quarter: {'YYYY-QN': ebit_in_millions}           e.g. {'2024-Q3': 21500.0}
    """
    if not HAS_AKSHARE:
        print(S.warning("akshare not installed. Falling back to FMP EBIT for Chinese stocks."))
        return {}

    ak_symbol = _ticker_to_ak_symbol(ticker)
    if ak_symbol is None:
        return {}

    try:
        if period == 'annual':
            print(S.info(f"Fetching annual EBIT from akshare (东方财富) for {ak_symbol}..."))
            df = ak.stock_profit_sheet_by_report_em(symbol=ak_symbol)
            df = df[df['REPORT_TYPE'] == '年报'].copy()
        else:
            print(S.info(f"Fetching quarterly EBIT from akshare (东方财富) for {ak_symbol}..."))
            df = ak.stock_profit_sheet_by_quarterly_em(symbol=ak_symbol)

        df = df.sort_values('REPORT_DATE', ascending=False).head(historical_periods)

        month_to_quarter = {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}
        result = {}
        for _, row in df.iterrows():
            # Use REPORT_DATE ('2025-09-30 00:00:00') for reliable parsing
            # REPORT_DATE_NAME format differs: annual='2024-12-31', quarterly='2025三季度'
            date_str = str(row['REPORT_DATE'])[:10]  # '2025-09-30'
            year = date_str[:4]

            if period == 'annual':
                key = year
            else:
                month = int(date_str[5:7])
                quarter = month_to_quarter.get(month, f'Q{(month - 1) // 3 + 1}')
                key = f"{year}-{quarter}"

            result[key] = _calc_akshare_ebit(row) / 1_000_000

        print(f"  akshare EBIT fetched for: {', '.join(sorted(result.keys(), reverse=True))}")
        return result

    except Exception as e:
        print(S.warning(f"Failed to fetch akshare EBIT for {ak_symbol}: {e}"))
        return {}


def get_historical_financials(ticker, period='annual', apikey='', historical_periods=5):
    period_str = f"{historical_periods} years" if period == 'annual' else f"{historical_periods} quarters"
    print(f"\n{S.info(f'Fetching financial data for {ticker} ({period_str})...')}")
    
    try:
        income_statement = get_jsonparsed_data(get_api_url('income-statement', ticker, period, apikey))[:historical_periods]
        balance_sheet = get_jsonparsed_data(get_api_url('balance-sheet-statement', ticker, period, apikey))[:historical_periods]
        cashflow_statement = get_jsonparsed_data(get_api_url('cash-flow-statement', ticker, period, apikey))[:historical_periods]
        key_metrics = get_jsonparsed_data(get_api_url('key-metrics', ticker, period, apikey))[:historical_periods]
        financial_growth = get_jsonparsed_data(get_api_url('financial-growth', ticker, period, apikey))[:historical_periods]
        company_info = get_company_share_float(ticker, apikey)
        company_profile = fetch_company_profile(ticker, apikey)

        summary_data = []
        tax_rates = []
        ebit_comparison = []

        # For Chinese A-shares, fetch EBIT from akshare
        exchange = company_profile.get('exchange', 'NASDAQ')
        is_china_stock = exchange in ['Shenzhen Stock Exchange', 'Shanghai Stock Exchange']
        akshare_ebit_data = {}
        if is_china_stock:
            akshare_ebit_data = fetch_akshare_ebit(ticker, historical_periods, period)

        for i in range(len(income_statement)):
            fmp_ebit = (income_statement[i].get('operatingIncome', 0) or 0)
            if is_china_stock:
                fmp_ebit += (income_statement[i].get('interestExpense', 0) or 0) - (income_statement[i].get('interestIncome', 0) or 0)

            calendar_year = income_statement[i].get('calendarYear', 'N/A')
            period_name = income_statement[i].get('period', 'N/A')
            ak_key = f"{calendar_year}-{period_name}" if period == 'quarter' else str(calendar_year)
            ak_ebit = akshare_ebit_data.get(ak_key)
            if ak_ebit is not None:
                ebit = ak_ebit * 1_000_000  # Convert back to absolute for consistency
                fmp_ebit_m = fmp_ebit / 1_000_000
                ak_ebit_m = ak_ebit
                diff_pct = ((ak_ebit_m - fmp_ebit_m) / fmp_ebit_m * 100) if fmp_ebit_m != 0 else 0
                ebit_comparison.append({
                    'year': ak_key,
                    'akshare_ebit': ak_ebit_m,
                    'fmp_ebit': fmp_ebit_m,
                    'diff_pct': diff_pct
                })
            else:
                ebit = fmp_ebit

            income_before_tax = income_statement[i].get('incomeBeforeTax', 0) or 0
            income_tax_expense = income_statement[i].get('incomeTaxExpense', 0) or 0
            tax_rate = income_tax_expense / income_before_tax if income_before_tax != 0 else 0
            tax_rates.append(tax_rate)

            invested_capital = (balance_sheet[i].get('totalDebt', 0) or 0) + \
                              (balance_sheet[i].get('totalEquity', 0) or 0) - \
                              (balance_sheet[i].get('cashAndCashEquivalents', 0) or 0) - \
                              (balance_sheet[i].get('totalInvestments', 0) or 0)
            revenue_to_invested_capital = (income_statement[i].get('revenue', 0) or 0) / invested_capital if invested_capital != 0 else 0
            total_reinvestments = (-cashflow_statement[i].get('investmentsInPropertyPlantAndEquipment', 0) or 0) + \
                                 (-cashflow_statement[i].get('changeInWorkingCapital', 0) or 0) - \
                                 (cashflow_statement[i].get('depreciationAndAmortization', 0) or 0)

            interest_expense = income_statement[i].get('interestExpense', 0) or 0
            total_debt = balance_sheet[i].get('totalDebt', 0) or 0
            prev_total_debt = balance_sheet[i - 1].get('totalDebt', 0) or 0 if i > 0 else total_debt
            cost_of_debt = interest_expense / ((total_debt + prev_total_debt) / 2) if (total_debt + prev_total_debt) != 0 else 0

            if i < len(income_statement) - 1:
                prev_index = i + 1 if period == 'annual' else i + 4
                if prev_index < len(income_statement):
                    prev_revenue = income_statement[prev_index].get('revenue', 0) or 0
                    current_revenue = income_statement[i].get('revenue', 0) or 0
                    revenue_growth = (current_revenue - prev_revenue) / prev_revenue * 100 if prev_revenue != 0 else 0

                    prev_year = income_statement[prev_index].get('calendarYear', 'N/A')
                    prev_period_name = income_statement[prev_index].get('period', 'N/A')
                    prev_ak_key = f"{prev_year}-{prev_period_name}" if period == 'quarter' else str(prev_year)
                    prev_ak_ebit = akshare_ebit_data.get(prev_ak_key)
                    if prev_ak_ebit is not None:
                        prev_ebit = prev_ak_ebit * 1_000_000
                    else:
                        prev_ebit = income_statement[prev_index].get('operatingIncome', 0) or 0
                    current_ebit = ebit or 0
                    ebit_growth = (current_ebit - prev_ebit) / prev_ebit * 100 if prev_ebit != 0 else 0
                else:
                    revenue_growth = 0
                    ebit_growth = 0
            else:
                revenue_growth = 0
                ebit_growth = 0

            data = {
                'Calendar Year': income_statement[i].get('calendarYear', 'N/A'),
                'Date': income_statement[i].get('date', 'N/A'),
                'Period': income_statement[i].get('period', 'N/A'),
                'Reported Currency': income_statement[i].get('reportedCurrency', 'N/A'),
                'Revenue': (income_statement[i].get('revenue', 0) or 0) / 1_000_000,
                'EBIT': (ebit or 0) / 1_000_000,
                'Depreciation & Amortization': (cashflow_statement[i].get('depreciationAndAmortization', 0) or 0) / 1_000_000,
                'Increase in Working Capital': (-cashflow_statement[i].get('changeInWorkingCapital', 0) or 0) / 1_000_000,
                'Capital Expenditure': (-cashflow_statement[i].get('investmentsInPropertyPlantAndEquipment', 0) or 0) / 1_000_000,
                'Total Reinvestments': (total_reinvestments or 0) / 1_000_000,
                'Total Debt': (total_debt or 0) / 1_000_000,
                'Total Equity': (balance_sheet[i].get('totalEquity', 0) or 0) / 1_000_000,
                'Minority Interest': (balance_sheet[i].get('minorityInterest', 0) or 0) / 1_000_000,
                'Cash & Cash Equivalents': (balance_sheet[i].get('cashAndCashEquivalents', 0) or 0) / 1_000_000,
                'Total Investments': (balance_sheet[i].get('totalInvestments', 0) or 0) / 1_000_000,
                'Invested Capital': (invested_capital or 0) / 1_000_000,
                '[break line]': '',
                'Revenue Growth': revenue_growth,
                'EBIT Growth': ebit_growth,
                'EBIT Margin': (ebit / (income_statement[i].get('revenue', 0) or 1)) * 100 if income_statement[i].get('revenue', 0) != 0 else 0,
                'Tax Rate': tax_rate * 100,
                'Revenue to Invested Capital': revenue_to_invested_capital,
                'Debt to Assets': (key_metrics[i].get('debtToAssets', 0) or 0) * 100,
                'Cost of Debt': cost_of_debt * 100,              
                'ROIC': (key_metrics[i].get('roic', 0) or 0) * 100,
                'ROE': (key_metrics[i].get('roe', 0) or 0) * 100,
                'Dividend Yield': (key_metrics[i].get('dividendYield', 0) or 0) * 100,
                'Payout Ratio': (key_metrics[i].get('payoutRatio', 0) or 0) * 100,
            }
            summary_data.append(data)
  
        # --- TTM column for quarterly data (if latest quarter is not Q4) ---
        if period == 'quarter' and len(summary_data) >= 4:
            latest_period = summary_data[0].get('Period', '')
            if latest_period not in ('Q4', 'FY'):
                flow_items = ['Revenue', 'EBIT', 'Depreciation & Amortization',
                              'Increase in Working Capital', 'Capital Expenditure',
                              'Total Reinvestments']
                bs_items = ['Total Debt', 'Total Equity', 'Minority Interest',
                            'Cash & Cash Equivalents', 'Total Investments', 'Invested Capital']

                ttm_data = {
                    'Calendar Year': 'TTM',
                    'Date': summary_data[0]['Date'],
                    'Period': 'TTM',
                    'Reported Currency': summary_data[0]['Reported Currency'],
                }

                for item in flow_items:
                    ttm_data[item] = sum(summary_data[j][item] for j in range(4))

                for item in bs_items:
                    ttm_data[item] = summary_data[0][item]

                ttm_data['[break line]'] = ''

                ttm_revenue = ttm_data['Revenue']
                ttm_ebit = ttm_data['EBIT']

                # YoY growth: TTM vs previous TTM (quarters [4..7])
                if len(summary_data) >= 8:
                    prev_ttm_revenue = sum(summary_data[j]['Revenue'] for j in range(4, 8))
                    ttm_data['Revenue Growth'] = ((ttm_revenue - prev_ttm_revenue) / prev_ttm_revenue * 100) if prev_ttm_revenue != 0 else 0
                    prev_ttm_ebit = sum(summary_data[j]['EBIT'] for j in range(4, 8))
                    ttm_data['EBIT Growth'] = ((ttm_ebit - prev_ttm_ebit) / prev_ttm_ebit * 100) if prev_ttm_ebit != 0 else 0
                else:
                    ttm_data['Revenue Growth'] = 0
                    ttm_data['EBIT Growth'] = 0

                ttm_data['EBIT Margin'] = (ttm_ebit / ttm_revenue * 100) if ttm_revenue != 0 else 0

                # Point-in-time ratios: use latest quarter
                for ratio in ['Tax Rate', 'Debt to Assets', 'Cost of Debt', 'ROIC', 'ROE',
                              'Dividend Yield', 'Payout Ratio']:
                    ttm_data[ratio] = summary_data[0][ratio]

                ttm_invested_capital = ttm_data['Invested Capital']
                ttm_data['Revenue to Invested Capital'] = (ttm_revenue / ttm_invested_capital) if ttm_invested_capital != 0 else 0

                summary_data.insert(0, ttm_data)

                # TTM-level EBIT comparison (if all 4 quarters have akshare data)
                if ebit_comparison:
                    ttm_quarter_keys = set()
                    for j in range(1, 5):  # indices 1..4 in summary_data after TTM insert
                        yr = summary_data[j].get('Calendar Year', '')
                        pr = summary_data[j].get('Period', '')
                        ttm_quarter_keys.add(f"{yr}-{pr}")
                    ttm_ak_items = [e for e in ebit_comparison if e['year'] in ttm_quarter_keys]
                    if len(ttm_ak_items) == 4:
                        ttm_ak = sum(e['akshare_ebit'] for e in ttm_ak_items)
                        ttm_fmp = sum(e['fmp_ebit'] for e in ttm_ak_items)
                        ttm_diff = ((ttm_ak - ttm_fmp) / ttm_fmp * 100) if ttm_fmp != 0 else 0
                        ebit_comparison.insert(0, {
                            'year': 'TTM',
                            'akshare_ebit': ttm_ak,
                            'fmp_ebit': ttm_fmp,
                            'diff_pct': ttm_diff
                        })

        avg_tax_rate = sum(tax_rates) / len(tax_rates) if tax_rates else 0

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
            'average_tax_rate': avg_tax_rate
        }
        if ebit_comparison:
            result['ebit_comparison'] = ebit_comparison
        return result
    except Exception as e:
        print(f"Error fetching financial data: {e}")
        return None

def format_summary_df(summary_df):
    """Format summary_df for terminal display. Returns a new formatted copy; original is NOT modified."""
    df = summary_df.copy()

    AMOUNT_ROWS = ['Revenue', 'EBIT', 'Depreciation & Amortization', 'Increase in Working Capital',
                   'Capital Expenditure', 'Total Reinvestments', 'Total Debt', 'Total Equity',
                   'Minority Interest', 'Cash & Cash Equivalents', 'Total Investments', 'Invested Capital']
    RATIO_ROWS = ['Revenue Growth', 'EBIT Growth', 'EBIT Margin', 'Tax Rate', 'Revenue to Invested Capital',
                  'Debt to Assets', 'Cost of Debt', 'ROIC', 'ROE', 'Dividend Yield', 'Payout Ratio']

    for index in df.index:
        if index in AMOUNT_ROWS:
            df.loc[index] = pd.to_numeric(df.loc[index], errors='coerce').apply(
                lambda x: f"{int(x):,}" if pd.notnull(x) else 'N/A')
        elif index in RATIO_ROWS:
            df.loc[index] = pd.to_numeric(df.loc[index], errors='coerce').apply(
                lambda x: f"{x:.2f}" if pd.notnull(x) else 'N/A')

    return df