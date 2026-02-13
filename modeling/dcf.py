import pandas as pd
from .data import fetch_market_risk_premium, fetch_company_profile, fetch_forex_data
from .constants import MARGINAL_TAX_RATE, TERMINAL_RISK_PREMIUM, RISK_FREE_RATE_US, RISK_FREE_RATE_CHINA, RISK_FREE_RATE_INTERNATIONAL

def get_risk_free_rate(country):
    """
    根据国家返回无风险利率。
    """
    if country in ['United States', 'US']:
        return RISK_FREE_RATE_US
    elif country in ['China', 'CN']:
        return RISK_FREE_RATE_CHINA
    else:
        return RISK_FREE_RATE_INTERNATIONAL

def calculate_wacc(base_year_data, company_profile, apikey):
    forex_data = fetch_forex_data(apikey)
    country_mapping = {'CN': 'China', 'US': 'United States'}
    country = company_profile.get('country', 'United States')
    mapped_country = country_mapping.get(country, country)

    market_risk_premium_data = fetch_market_risk_premium(apikey)
    total_equity_risk_premium = market_risk_premium_data.get(mapped_country, 5.0) / 100

    total_debt = float(base_year_data.get('Total Debt', 0))
    market_cap = float(company_profile.get('marketCap', 0))
    reporting_currency = base_year_data.get('Reported Currency', 'USD')
    company_currency = company_profile.get('currency', 'USD')

    if company_currency != reporting_currency:
        forex_key = f"{company_currency}/{reporting_currency}"
        exchange_rate = forex_data.get(forex_key, 1.0)
        market_cap = market_cap * exchange_rate

    beta = float(company_profile.get('beta', 1.0))
    cost_of_debt = float(base_year_data.get('Cost of Debt', 0)) / 100

    if pd.isna(total_debt) or total_debt == 0:
        print("Warning: Total Debt is NaN or 0. Setting Debt Weighting to 0.")
        debt_weighting = 0
    else:
        debt_weighting = total_debt / (total_debt + market_cap) if (total_debt + market_cap) != 0 else 0

    if pd.isna(market_cap) or market_cap == 0:
        print("Warning: Market Cap is NaN or 0. Setting Equity Weighting to 0.")
        equity_weighting = 0
    else:
        equity_weighting = market_cap / (total_debt + market_cap) if (total_debt + market_cap) != 0 else 0

    risk_free_rate = get_risk_free_rate(company_profile.get('country', 'United States'))
    cost_of_equity = risk_free_rate + total_equity_risk_premium * beta
    wacc = cost_of_debt * (1 - MARGINAL_TAX_RATE) * debt_weighting + cost_of_equity * equity_weighting

    print("\nWACC Calculation Parameters:")
    wacc_params = [
        ("Risk-free rate", f"{risk_free_rate:.1%}"),
        ("Total equity risk premium", f"{total_equity_risk_premium:.1%}"),
        ("Beta", f"{beta:.1f}"),
        ("Cost of debt", f"{cost_of_debt:.1%}"),
        ("Marginal tax rate", f"{MARGINAL_TAX_RATE:.0%}"),
        ("Debt weighting", f"{debt_weighting:.0%}"),
        ("Equity weighting", f"{equity_weighting:.0%}"),
        ("Calculated WACC", f"{wacc:.1%}")
    ]

    max_label_length = max(len(label) for label, _ in wacc_params)
    max_value_length = max(len(value) for _, value in wacc_params)

    for label, value in wacc_params:
        print(f"{label.ljust(max_label_length)} : {value.rjust(max_value_length)}")

    return wacc, total_equity_risk_premium

def calculate_dcf(base_year_data, valuation_params, financial_data, company_info, company_profile):
    base_year = valuation_params['base_year']
    revenue = float(base_year_data['Revenue'])
    ebit = float(base_year_data['EBIT'])
    tax_rate = float(base_year_data['Average Tax Rate'])
    invested_capital = float(base_year_data['Invested Capital'])
    cash = float(base_year_data['Cash & Cash Equivalents'])
    total_investments = float(base_year_data['Total Investments'])
    total_debt = float(base_year_data['Total Debt'])
    minority_interest = float(base_year_data['Minority Interest'])
    outstanding_shares = float(base_year_data['Outstanding Shares'])
    reported_currency = base_year_data.get('Reported Currency')
    revenue_growth_rate_base_year = float(base_year_data['Revenue Growth'].replace(',', '')) / 100
    reinvestments_base_year = float(base_year_data['Total Reinvestments'].replace(',', ''))
 
    revenue_growth_1 = valuation_params['revenue_growth_1'] / 100
    revenue_growth_2 = valuation_params['revenue_growth_2'] / 100
    ebit_margin = valuation_params['ebit_margin'] / 100
    convergence = valuation_params['convergence']
    revenue_invested_capital_ratio_1 = valuation_params['revenue_invested_capital_ratio_1']
    revenue_invested_capital_ratio_2 = valuation_params['revenue_invested_capital_ratio_2']
    revenue_invested_capital_ratio_3 = valuation_params['revenue_invested_capital_ratio_3']
    tax_rate = valuation_params['tax_rate'] / 100
    wacc = valuation_params['wacc'] / 100
    terminal_wacc = get_risk_free_rate(company_profile.get('country', 'United States')) + TERMINAL_RISK_PREMIUM
    ronic = valuation_params['ronic']
    risk_free_rate = valuation_params['risk_free_rate']

    dcf_table = pd.DataFrame(columns=[
        'Year', 'Revenue Growth Rate', 'Revenue', 'EBIT Margin', 'EBIT', 'Tax to EBIT', 
        'EBIT(1-t)', 'Reinvestments', 'FCFF', 'WACC', 'Discount Factor', 'PV (FCFF)'
    ])

    dcf_table.loc[0] = [
        base_year, revenue_growth_rate_base_year, revenue, ebit / revenue, ebit, tax_rate, 
        ebit * (1 - tax_rate), reinvestments_base_year, ebit * (1 - tax_rate) - reinvestments_base_year, 
        wacc, 1, (ebit * (1 - tax_rate) - reinvestments_base_year)
    ]

    for year in range(1, 12):
        prev_revenue = dcf_table.loc[year - 1, 'Revenue']
        prev_ebit = dcf_table.loc[year - 1, 'EBIT']
        prev_ebit_margin = dcf_table.loc[year - 1, 'EBIT Margin']

        if year == 1:
            revenue_growth = revenue_growth_1
        elif year <= 5:
            revenue_growth = revenue_growth_2
        elif year <= 10:
            revenue_growth = revenue_growth_2 + (risk_free_rate - revenue_growth_2) * (year - 5) / 5
        else:
            revenue_growth = risk_free_rate           

        if year <= convergence:
            ebit_margin_current = prev_ebit_margin + (ebit_margin - prev_ebit_margin) * year / convergence
        else:
            ebit_margin_current = ebit_margin

        revenue_current = prev_revenue * (1 + revenue_growth)
        ebit_current = revenue_current * ebit_margin_current
        tax_to_ebit = tax_rate
        ebit_after_tax = ebit_current * (1 - tax_to_ebit)
 
        if year == 1:
            if revenue_current > prev_revenue:
                reinvestments = (revenue_current - prev_revenue) / revenue_invested_capital_ratio_1 if revenue_invested_capital_ratio_1 != 0 else 0
            else:
                reinvestments = 0
        elif year <= 2:
            reinvestments = (revenue_current - prev_revenue) / revenue_invested_capital_ratio_1 if revenue_invested_capital_ratio_1 != 0 else 0
        elif year <= 5:
            reinvestments = (revenue_current - prev_revenue) / revenue_invested_capital_ratio_2 if revenue_invested_capital_ratio_2 != 0 else 0
        elif year <= 10:
            reinvestments = (revenue_current - prev_revenue) / revenue_invested_capital_ratio_3 if revenue_invested_capital_ratio_3 != 0 else 0
        else:
            reinvestments = (risk_free_rate / ronic) * ebit_after_tax       

        fcff = ebit_after_tax - reinvestments

        if year <= 5:
            wacc_current = wacc
        elif year <=10:
            wacc_current = wacc + (terminal_wacc - wacc) * (year - 5) / 5
        else:
            wacc_current = terminal_wacc

        if year <= 10:
            discount_factor = 1 / (1 + wacc_current) ** year
        else:
            discount_factor = None     

        if year <= 10:
            pv_fcff = fcff * discount_factor
        else:
            pv_fcff = None

        dcf_table.loc[year] = [
            base_year + year, revenue_growth, revenue_current, ebit_margin_current, ebit_current, 
            tax_to_ebit, ebit_after_tax, reinvestments, fcff, wacc_current, discount_factor, pv_fcff
        ]

    terminal_fcff = dcf_table.loc[11, 'FCFF']
    terminal_value = terminal_fcff / (terminal_wacc - risk_free_rate)
    pv_terminal_value = terminal_value / (1 + terminal_wacc) ** 10

    pv_cf_next_10_years = dcf_table.loc[1:10, 'PV (FCFF)'].sum()
    enterprise_value = pv_cf_next_10_years + pv_terminal_value + cash + total_investments

    equity_value = enterprise_value - total_debt - minority_interest
    price_per_share = (equity_value * 1_000_000) / outstanding_shares

    results = {
        'dcf_table': dcf_table,
        'pv_cf_next_10_years': pv_cf_next_10_years,
        'pv_terminal_value': pv_terminal_value,
        'enterprise_value': enterprise_value,
        'equity_value': equity_value,
        'price_per_share': price_per_share,
        'cash': cash,
        'total_investments': total_investments,
        'total_debt': total_debt,
        'minority_interest': minority_interest,
        'outstanding_shares': outstanding_shares,
        'reported_currency': reported_currency
    }

    return results

def sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile):
    revenue_growth_2_range = [valuation_params['revenue_growth_2'] + i for i in range(-5, 6)]
    ebit_margin_range = [valuation_params['ebit_margin'] + i for i in range(-5, 6)]

    sensitivity_table = pd.DataFrame(index=revenue_growth_2_range, columns=ebit_margin_range)

    for revenue_growth_2 in revenue_growth_2_range:
        for ebit_margin in ebit_margin_range:
            updated_params = valuation_params.copy()
            updated_params['revenue_growth_2'] = revenue_growth_2
            updated_params['ebit_margin'] = ebit_margin

            results = calculate_dcf(base_year_data, updated_params, financial_data, company_info, company_profile)
            sensitivity_table.loc[revenue_growth_2, ebit_margin] = results['price_per_share']

    sensitivity_table.index.name = 'Revenue Growth (%)'
    sensitivity_table.columns.name = 'EBIT Margin (%)'
    sensitivity_table.index = sensitivity_table.index.map(lambda x: f"{int(x)}%")
    sensitivity_table.columns = sensitivity_table.columns.map(lambda x: f"{int(x)}%")
    sensitivity_table = sensitivity_table.applymap(lambda x: f"{x:,.2f}")

    return sensitivity_table

def print_dcf_results(results, company_name):
    dcf_table = results['dcf_table']
    print(f"\n{company_name} Free Cashflow Forecast Results - 10 years, in millions:")

    formatted_dcf_table = dcf_table.copy()
    for col in formatted_dcf_table.columns:
        if col in ['Year']:
            formatted_dcf_table[col] = formatted_dcf_table[col].apply(lambda x: f"{int(x)}")
        elif col in ['Revenue Growth Rate', 'EBIT Margin', 'Tax to EBIT', 'WACC']:
            formatted_dcf_table[col] = formatted_dcf_table[col].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else 'N/A')
        elif col in ['Discount Factor']:
            formatted_dcf_table[col] = formatted_dcf_table[col].apply(lambda x: f"{x:.3f}" if pd.notnull(x) else 'N/A')
        elif col in ['Revenue', 'EBIT', 'EBIT(1-t)', 'Reinvestments', 'FCFF', 'PV (FCFF)']:
            formatted_dcf_table[col] = formatted_dcf_table[col].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else 'N/A')

    formatted_dcf_table.index = ['Base Year'] + list(range(1, 11)) + ['Terminal Year']

    print(formatted_dcf_table.T.to_string())

    print("\nValuation Calculation - in millions:")
    valuation_calculation = [
        ("PV (FCFF over next 10 years)", results['pv_cf_next_10_years']),
        ("PV (Terminal value)", results['pv_terminal_value']),
        ("Sum of PV", results['pv_cf_next_10_years'] + results['pv_terminal_value']),
        ("+ Cash & Cash Equivalents", results['cash']),
        ("+ Total Investments", results['total_investments']),
        ("Enterprise Value", results['enterprise_value']),
        ("- Total Debt", results['total_debt']),
        ("- Minority Interest", results['minority_interest']),
        ("Equity Value", results['equity_value']),
        ("Outstanding Shares", results['outstanding_shares']),
        (f"Equity Price per Share ({results['reported_currency']})" if results['reported_currency'] else "Equity Price per Share", results['price_per_share'])
    ]

    max_label_length = max(len(label) for label, _ in valuation_calculation)
    max_value_length = max(len(f"{value:,.0f}") if isinstance(value, (int, float)) else len(str(value)) for _, value in valuation_calculation)

    for label, value in valuation_calculation:
        if label.startswith("Equity Price per Share"):
            formatted_value = f"{value:,.2f}"
        else:
            formatted_value = f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)
        print(f"{label.ljust(max_label_length)} : {formatted_value.rjust(max_value_length)}")