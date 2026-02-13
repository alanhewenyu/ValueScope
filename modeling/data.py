from urllib.request import urlopen
import json, traceback
import pandas as pd
import requests

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
        'exchange': data[0].get('exchange', 'NASDAQ')
    }

def get_historical_financials(ticker, period='annual', apikey='', historical_periods=5):
    period_str = f"{historical_periods} years" if period == 'annual' else f"{historical_periods} quarters"
    print(f"\nFetching financial data for {ticker} ({period_str})...")
    
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
        for i in range(len(income_statement)):
            exchange = company_profile.get('exchange', 'NASDAQ')
            ebit = (income_statement[i].get('operatingIncome', 0) or 0)
            if exchange in ['Shenzhen', 'Shanghai']:
                ebit += (income_statement[i].get('interestExpense', 0) or 0) - (income_statement[i].get('interestIncome', 0) or 0)

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
  
        avg_tax_rate = sum(tax_rates) / len(tax_rates) if tax_rates else 0

        summary_df = pd.DataFrame(summary_data).T
        summary_df.columns = summary_df.iloc[0]
        summary_df = summary_df[1:]
        
        income_df = pd.DataFrame(income_statement).T
        balance_df = pd.DataFrame(balance_sheet).T
        cashflow_df = pd.DataFrame(cashflow_statement).T

        return {
            'income_statement': income_df,
            'balance_sheet': balance_df,
            'cashflow_statement': cashflow_df,
            'summary': summary_df,
            'average_tax_rate': avg_tax_rate
        }
    except Exception as e:
        print(f"Error fetching financial data: {e}")
        return None

def format_summary_df(summary_df):
    numeric_columns = ['Revenue', 'EBIT', 'Depreciation & Amortization', 'Increase in Working Capital', 
                      'Capital Expenditure', 'Total Reinvestments', 'Total Debt', 'Total Equity', 
                      'Minority Interest', 'Cash & Cash Equivalents', 'Total Investments', 'Invested Capital',
                      'Revenue Growth', 'EBIT Growth', 'EBIT Margin', 'Tax Rate', 'Revenue to Invested Capital',
                      'Debt to Assets', 'Cost of Debt', 'ROIC', 'ROE', 'Dividend Yield', 'Payout Ratio']

    for col in summary_df.columns:
        if col in numeric_columns:
            summary_df[col] = pd.to_numeric(summary_df[col], errors='coerce')

    for index, row in summary_df.iterrows():
        if index in numeric_columns:
            if index in ['Revenue', 'EBIT', 'Depreciation & Amortization', 'Increase in Working Capital', 
                        'Capital Expenditure', 'Total Reinvestments', 'Total Debt', 'Total Equity', 
                        'Minority Interest', 'Cash & Cash Equivalents', 'Total Investments', 'Invested Capital']:
                summary_df.loc[index] = row.apply(lambda x: f"{int(x):,}" if pd.notnull(x) else 'N/A')
            else:
                summary_df.loc[index] = row.apply(lambda x: f"{x:.2f}" if pd.notnull(x) else 'N/A')
        else:
            summary_df.loc[index] = row

    return summary_df