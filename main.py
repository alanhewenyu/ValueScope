# Copyright (c) 2025 Alan He. Licensed under MIT.

import argparse
import os
import re
import sys
from datetime import date
from modeling.data import get_historical_financials, get_company_share_float, fetch_company_profile, fetch_forex_data, format_summary_df, validate_ticker, _normalize_ticker, is_a_share, is_hk_stock
from modeling.dcf import calculate_dcf, print_dcf_results, sensitivity_analysis, print_sensitivity_table, wacc_sensitivity_analysis, print_wacc_sensitivity, calculate_wacc, print_wacc_details, get_risk_free_rate
from modeling.constants import HISTORICAL_DATA_PERIODS_ANNUAL, HISTORICAL_DATA_PERIODS_QUARTER, TERMINAL_RISK_PREMIUM, TERMINAL_RONIC_PREMIUM
from modeling.ai_analyst import analyze_company, interactive_review, analyze_valuation_gap, _AI_ENGINE, set_ai_engine, _ai_engine_display_name
from modeling import excel_export as _excel
from modeling.excel_export import write_to_excel, init_paths as _init_excel_paths
from modeling import style as S

# Initialise Excel export paths
_init_excel_paths(os.path.dirname(os.path.abspath(__file__)))


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _input_float(prompt_text, default=None):
    """Prompt user for a float value with retry on invalid input.

    If *default* is provided, pressing Enter without input returns the default.
    """
    while True:
        raw = input(prompt_text).strip()
        if raw == '' and default is not None:
            return default
        try:
            return float(raw)
        except ValueError:
            print(S.error(f"  输入无效，请输入数字。"))


def _auto_accept_params(ai_result):
    """Extract AI-suggested parameters without interactive confirmation.

    Returns dict in the same format as interactive_review(), or None on failure.
    """
    params = ai_result["parameters"]

    if params is None:
        print(f"\n{S.error('Auto 模式: 无法解析 AI 返回的参数。')}")
        print(S.divider())
        print(ai_result.get("raw_text", "（无内容）"))
        print(S.divider())
        return None

    param_keys = [
        "revenue_growth_1", "revenue_growth_2", "ebit_margin", "convergence",
        "revenue_invested_capital_ratio_1", "revenue_invested_capital_ratio_2",
        "revenue_invested_capital_ratio_3", "tax_rate", "wacc",
    ]

    final_params = {}
    print(f"\n{S.header('Auto 模式: 直接采用 AI 建议参数')}")
    for key in param_keys:
        param_data = params.get(key, {})
        if isinstance(param_data, dict):
            value = param_data.get("value")
        else:
            value = param_data
        if value is None:
            print(S.error(f"  AI 未提供 {key} 的建议值，无法继续。"))
            return None
        final_params[key] = float(value)
        print(f"  {key}: {value}")

    # RONIC
    ronic_data = params.get("ronic_match_wacc", {})
    if isinstance(ronic_data, dict):
        ronic_match = ronic_data.get("value", True)
    else:
        ronic_match = ronic_data if isinstance(ronic_data, bool) else True
    final_params["ronic_match_wacc"] = ronic_match
    print(f"  ronic_match_wacc: {ronic_match}")

    return final_params


# ────────────────────────────────────────────────────────────────────
# Input collection
# ────────────────────────────────────────────────────────────────────

def _prompt_ticker(auto_mode):
    """Prompt for ticker symbol. Returns normalized ticker string."""
    print(f"\n{S.title('Please enter the stock symbol to continue...')}\n")
    while True:
        ticker = input(f'{S.prompt("Enter the stock symbol (e.g., AAPL, 0700.HK, 600519.SS): ")}').strip()
        is_valid, error_msg = validate_ticker(ticker)
        if is_valid:
            break
        print(S.error(f"  {error_msg}"))
    return _normalize_ticker(ticker)


def _show_quarterly_reference(ticker, apikey, company_name):
    """Optionally fetch and display quarterly data as reference (not used for valuation)."""
    view_q = input(f'{S.prompt("View quarterly financial data? (y/N, Enter to skip): ")}').strip().lower()
    if view_q not in ('y', 'yes'):
        return

    # HK quarter requires FMP API key
    if is_hk_stock(ticker) and not apikey:
        print(S.muted("  ⓘ 港股季度数据需要 FMP API key（yfinance 无法提供港股季度数据），跳过。"))
        return

    print(S.info("\n  正在获取季度数据..."))
    quarter_data = get_historical_financials(ticker, 'quarter', apikey, HISTORICAL_DATA_PERIODS_QUARTER)
    if quarter_data is None:
        print(S.warning("  ⚠ 无法获取季度数据。"))
        return

    quarter_summary_df = quarter_data['summary']
    print(f"\n{S.header(f'{company_name} Quarterly Financial Data (Reference Only, in millions)')}")
    formatted_q_df = format_summary_df(quarter_summary_df)
    print(formatted_q_df.to_string())
    print()
    print(S.muted("  ⓘ 季度数据仅供参考，估值使用年度数据。"))


def _collect_manual_params(average_tax_rate, wacc, wacc_details, risk_free_rate):
    """Interactively collect valuation parameters in manual mode.

    Returns a dict with raw parameter values (before building full valuation_params).
    """
    print(f"\n{S.title('Enter the following inputs...')}\n")
    revenue_growth_1 = _input_float(f'{S.prompt("Enter the annual revenue growth rate for Year 1 (%): ")}')
    revenue_growth_2 = _input_float(f'{S.prompt("Enter the Compound annual revenue growth rate for Years 2-5 (%): ")}')
    ebit_margin = _input_float(f'{S.prompt("Enter the target EBIT margin (%): ")}')
    convergence = _input_float(f'{S.prompt("Enter the number of years to reach the target EBIT margin: ")}')
    revenue_invested_capital_ratio_1 = _input_float(f'{S.prompt("Enter the revenue to invested capital ratio for Year 1: ")}')
    revenue_invested_capital_ratio_2 = _input_float(f'{S.prompt("Enter the revenue to invested capital ratio for Years 3-5: ")}')
    revenue_invested_capital_ratio_3 = _input_float(f'{S.prompt("Enter the revenue to invested capital ratio for Years 5-10: ")}')

    tax_rate = _input_float(
        f"\n{S.prompt(f'Calculated Average Tax Rate: {average_tax_rate:.1%}. Press Enter to accept or enter a new value (e.g., 25 for 25%): ')}",
        default=average_tax_rate * 100)

    print_wacc_details(wacc_details)
    wacc_val = _input_float(
        f"\n{S.prompt(f'Calculated WACC: {wacc:.1%}. Press Enter to accept or enter a new value (e.g., 8 for 8%): ')}",
        default=wacc * 100)

    cont = input(f'{S.prompt("Will ROIC match terminal WACC beyond year 10? (y/n): ")}').strip().lower()
    if cont == 'y':
        ronic = risk_free_rate + TERMINAL_RISK_PREMIUM
    else:
        ronic = risk_free_rate + TERMINAL_RISK_PREMIUM + TERMINAL_RONIC_PREMIUM

    return {
        'revenue_growth_1': revenue_growth_1,
        'revenue_growth_2': revenue_growth_2,
        'ebit_margin': ebit_margin,
        'convergence': convergence,
        'revenue_invested_capital_ratio_1': revenue_invested_capital_ratio_1,
        'revenue_invested_capital_ratio_2': revenue_invested_capital_ratio_2,
        'revenue_invested_capital_ratio_3': revenue_invested_capital_ratio_3,
        'tax_rate': tax_rate,
        'wacc': wacc_val,
        'ronic': ronic,
    }


# ────────────────────────────────────────────────────────────────────
# Valuation parameter building
# ────────────────────────────────────────────────────────────────────

def _build_valuation_params(raw_params, base_year, risk_free_rate, _is_ttm, _ttm_quarter, _ttm_label):
    """Build the full valuation_params dict from raw parameter values."""
    return {
        'base_year': base_year,
        'ttm_quarter': _ttm_quarter if _is_ttm else '',
        'ttm_label': _ttm_label if _is_ttm else '',
        'revenue_growth_1': raw_params['revenue_growth_1'],
        'revenue_growth_2': raw_params['revenue_growth_2'],
        'ebit_margin': raw_params['ebit_margin'],
        'convergence': raw_params['convergence'],
        'revenue_invested_capital_ratio_1': raw_params['revenue_invested_capital_ratio_1'],
        'revenue_invested_capital_ratio_2': raw_params['revenue_invested_capital_ratio_2'],
        'revenue_invested_capital_ratio_3': raw_params['revenue_invested_capital_ratio_3'],
        'tax_rate': raw_params['tax_rate'],
        'wacc': raw_params['wacc'],
        'terminal_wacc': risk_free_rate + TERMINAL_RISK_PREMIUM,
        'ronic': raw_params['ronic'],
        'risk_free_rate': risk_free_rate,
    }


# ────────────────────────────────────────────────────────────────────
# Forex & gap analysis
# ────────────────────────────────────────────────────────────────────

def _compute_forex_rate(results, company_profile, apikey):
    """Compute forex rate if DCF currency differs from stock trading currency.

    Returns forex_rate (float or None).
    """
    reported_currency = results.get('reported_currency', '')
    stock_currency = company_profile.get('currency', 'USD')
    if not (reported_currency and stock_currency and reported_currency != stock_currency):
        return None

    forex_rate = None
    try:
        if apikey:
            forex_data = fetch_forex_data(apikey)
            forex_key = f"{stock_currency}/{reported_currency}"
            rate = forex_data.get(forex_key)
            if rate and rate != 0:
                forex_rate = 1.0 / rate
            else:
                reverse_key = f"{reported_currency}/{stock_currency}"
                reverse_rate = forex_data.get(reverse_key)
                if reverse_rate and reverse_rate != 0:
                    forex_rate = reverse_rate

        # Fallback: use yfinance for forex (useful for HK stocks without FMP API key)
        if forex_rate is None:
            from modeling.yfinance_data import fetch_forex_yfinance
            forex_rate = fetch_forex_yfinance(reported_currency, stock_currency)

        if forex_rate:
            print(S.muted(f"\n  ⓘ 汇率换算: 1 {reported_currency} = {forex_rate:.4f} {stock_currency}"))
        else:
            print(f"\n{S.warning(f'⚠ 无法获取 {reported_currency}/{stock_currency} 汇率，DCF 价格将使用原始 {reported_currency} 值进行比较')}")
        return forex_rate
    except Exception as e:
        print(f"\n{S.warning(f'⚠ 获取汇率失败: {e}，DCF 价格将使用原始 {reported_currency} 值进行比较')}")
        return None


def _run_gap_analysis(auto_mode, ticker, company_profile, results, valuation_params,
                      summary_df, base_year, forecast_year_1, forex_rate):
    """Run AI gap analysis if requested. Returns gap_analysis_result or None."""
    if auto_mode:
        try:
            return analyze_valuation_gap(ticker, company_profile, results, valuation_params,
                                         summary_df, base_year, forecast_year_1=forecast_year_1,
                                         forex_rate=forex_rate)
        except Exception as e:
            print(f"\n{S.error(f'估值差异分析出错: {e}')}")
            return None

    run_gap = input(f"\n{S.prompt('是否运行 DCF 估值 vs 当前股价差异分析? (y/N): ')}").strip().lower()
    if run_gap in ('y', 'yes'):
        try:
            return analyze_valuation_gap(ticker, company_profile, results, valuation_params,
                                         summary_df, base_year, forecast_year_1=forecast_year_1,
                                         forex_rate=forex_rate)
        except Exception as e:
            print(f"\n{S.error(f'估值差异分析出错: {e}')}")
    return None


# ────────────────────────────────────────────────────────────────────
# Excel export
# ────────────────────────────────────────────────────────────────────

def _export_excel(auto_mode, use_ai, company_name, base_year_data, financial_data,
                  valuation_params, company_profile, total_equity_risk_premium,
                  gap_analysis_result, ai_result, wacc_results, wacc_base):
    """Handle Excel export (auto or prompted)."""
    model_suffix = ''
    if use_ai:
        model_tag = _ai_engine_display_name()
        model_tag = re.sub(r'[^\w. ]+', '', model_tag).strip().replace(' ', '_').replace('.', '_')
        if model_tag:
            model_suffix = f'_{model_tag}'

    def _do_export():
        filename = os.path.join(_excel.EXCEL_OUTPUT_DIR, f"{company_name}_valuation_{date.today().strftime('%Y%m%d')}{model_suffix}.xlsx")
        write_to_excel(filename, base_year_data, financial_data, valuation_params,
                       company_profile, total_equity_risk_premium, gap_analysis_result,
                       ai_result=ai_result, wacc_sensitivity=(wacc_results, wacc_base))
        print(f"\n{S.success(f'Valuation results saved to {filename}')}")

    if auto_mode:
        _do_export()
    else:
        export_to_excel = input(f"\n{S.prompt('Do you want to export the valuation results to Excel? (y/n): ')}").strip().lower()
        if export_to_excel == 'y':
            _do_export()
        else:
            print(f"\n{S.muted('Skipping Excel export.')}")


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

def main(args):
    auto_mode = getattr(args, 'auto', False)

    # ── AI engine startup check ──
    use_ai = not args.manual
    if use_ai and _AI_ENGINE is None:
        print(f"\n{S.warning('未检测到 AI 引擎。')}")
        print(S.info("  安装任一工具即可启用 AI 自动分析："))
        print(S.info("  1. Claude CLI: https://docs.anthropic.com/en/docs/claude-code"))
        print(S.info("  2. Gemini CLI: npm install -g @google/gemini-cli"))
        print(S.info("     （只需 Google 账号登录，免费使用）"))
        print(S.info("  3. Qwen Code:  npm install -g @qwen-code/qwen-code"))
        print(S.info("     （只需 qwen.ai 账号登录，免费使用）"))
        if auto_mode:
            print(f"\n{S.error('Auto 模式需要 AI 引擎，退出。')}")
            sys.exit(1)
        print(f"\n{S.warning('当前将使用手工输入模式。')}")
        input(f"\n{S.prompt('按 Enter 继续...')}")
        args.manual = True
        use_ai = False

    while True:
        # ── Ticker ──
        ticker = _prompt_ticker(auto_mode)
        args.t = ticker
        args.period = 'annual'

        # ── Fetch annual financial data ──
        financial_data = get_historical_financials(args.t, 'annual', args.apikey, HISTORICAL_DATA_PERIODS_ANNUAL)
        if financial_data is None:
            print(S.error("Error: Failed to fetch financial data. Please check your API key and ticker symbol."))
            continue
        summary_df = financial_data['summary']
        company_profile = fetch_company_profile(args.t, args.apikey)
        company_info = get_company_share_float(args.t, args.apikey, company_profile=company_profile)
        company_name = company_profile.get('companyName', 'N/A')

        base_year_col = summary_df.columns[0]
        base_year_data = summary_df.iloc[:, 0].copy()
        base_year_data.name = base_year_col

        # ── Display annual historical summary ──
        print(f"\n{S.header(f'{company_name} Historical Financial Data (Summary, in millions)')}")
        formatted_summary_df = format_summary_df(summary_df)
        print(formatted_summary_df.to_string())
        print()

        ttm_note = financial_data.get('ttm_note', '')
        if ttm_note:
            print(S.muted(f"  ⓘ TTM Note: {ttm_note}"))
            print()

        # ── Optional: view quarterly data as reference ──
        if not auto_mode:
            _show_quarterly_reference(ticker, args.apikey, company_name)

        if not auto_mode:
            cont = input(f'\n{S.prompt("Proceed with valuation? (Y/n, Enter to proceed): ")}').strip().lower()
            if cont in ('n', 'no'):
                exit_program = input(f'{S.prompt("Exit program? (y/N): ")}').strip().lower()
                if exit_program in ('y', 'yes'):
                    print("Exiting...")
                    break
                else:
                    continue

        # ── Detect TTM & base year ──
        _ttm_quarter = financial_data.get('ttm_latest_quarter', '')
        _ttm_end_date = financial_data.get('ttm_end_date', '')
        _is_ttm = bool(_ttm_quarter and _ttm_end_date)
        base_year = int(base_year_col)
        _ttm_label = ''
        if _is_ttm:
            _ttm_end_month = int(_ttm_end_date[5:7])
            _ttm_end_year = int(_ttm_end_date[:4])
            forecast_year_1 = _ttm_end_year if _ttm_end_month <= 6 else _ttm_end_year + 1
            base_year = forecast_year_1 - 1
        else:
            forecast_year_1 = base_year + 1

        # ── Prepare base year data ──
        outstanding_shares = company_info.get('outstandingShares', 0) or 0
        if outstanding_shares <= 0:
            print(f"\n{S.warning('⚠ 无法获取流通股数 (Outstanding Shares)，每股价格将显示为 0。')}")
            print(S.muted("    请确认 FMP 是否提供该股票的流通股数据。"))
        base_year_data['Outstanding Shares'] = outstanding_shares
        base_year_data['Average Tax Rate'] = financial_data['average_tax_rate']
        base_year_data['Revenue Growth (%)'] = summary_df.iloc[summary_df.index.get_loc('Revenue Growth (%)'), 0]
        base_year_data['Total Reinvestment'] = summary_df.iloc[summary_df.index.get_loc('Total Reinvestment'), 0]

        if _is_ttm:
            _ttm_label = f'{base_year_col}{_ttm_quarter} TTM'
            _ttm_date_str = f' (data through {_ttm_end_date})' if _ttm_end_date else ''
            print(f"\n{S.info(f'Using {_ttm_label}{_ttm_date_str} as base year {base_year}. Forecast Year 1 ≈ {forecast_year_1}.')}")
        else:
            print(f"\n{S.info(f'The base year used for cashflow forecast is {base_year}.')}")

        # ── WACC ──
        average_tax_rate = base_year_data['Average Tax Rate']
        risk_free_rate = get_risk_free_rate(company_profile.get('country', 'United States'))
        wacc, total_equity_risk_premium, wacc_details = calculate_wacc(base_year_data, company_profile, args.apikey, verbose=False)

        # ── Collect valuation parameters (AI or manual) ──
        use_ai = not args.manual
        ai_params = None
        ai_result = None

        if use_ai:
            try:
                ai_result = analyze_company(
                    ticker=ticker,
                    summary_df=summary_df,
                    base_year_data=base_year_data,
                    company_profile=company_profile,
                    calculated_wacc=wacc,
                    calculated_tax_rate=average_tax_rate,
                    base_year=base_year,
                    ttm_quarter=_ttm_quarter if _is_ttm else '',
                    ttm_end_date=_ttm_end_date,
                )
                if auto_mode:
                    ai_params = _auto_accept_params(ai_result)
                    if ai_params is None:
                        print(S.error("Auto 模式: AI 参数解析失败，退出。"))
                        sys.exit(1)
                else:
                    ai_params = interactive_review(ai_result, wacc, average_tax_rate, company_profile, wacc_details)
            except Exception as e:
                print(f"\n{S.error(f'AI 分析出错: {e}')}")
                if auto_mode:
                    sys.exit(1)
                print(S.warning("自动回退到手工输入模式...\n"))

        if ai_params is not None:
            ronic_match = ai_params.pop("ronic_match_wacc", True)
            if ronic_match:
                ronic = risk_free_rate + TERMINAL_RISK_PREMIUM
            else:
                ronic = risk_free_rate + TERMINAL_RISK_PREMIUM + TERMINAL_RONIC_PREMIUM
            raw_params = {**ai_params, 'ronic': ronic}
        else:
            raw_params = _collect_manual_params(average_tax_rate, wacc, wacc_details, risk_free_rate)

        valuation_params = _build_valuation_params(
            raw_params, base_year, risk_free_rate, _is_ttm, _ttm_quarter, _ttm_label)

        # ── DCF calculation & output ──
        results = calculate_dcf(base_year_data, valuation_params, financial_data, company_info, company_profile)
        print_dcf_results(results, company_name, ttm_label=valuation_params.get('ttm_label', ''))

        # ── Sensitivity analysis ──
        print(f"\n{S.info('Running sensitivity analysis...')}")
        sensitivity_table = sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile)
        print(f"\n{S.subheader('Sensitivity Analysis - Revenue Growth vs EBIT Margin (Price per Share)')}")
        print_sensitivity_table(sensitivity_table, valuation_params)

        print(f"\n{S.info('Running WACC sensitivity analysis...')}")
        wacc_results, wacc_base = wacc_sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile)
        print(f"\n{S.subheader('Sensitivity Analysis - WACC (Price per Share)')}")
        print_wacc_sensitivity(wacc_results, wacc_base)

        # ── Gap analysis ──
        forex_rate = _compute_forex_rate(results, company_profile, args.apikey)
        gap_analysis_result = _run_gap_analysis(
            auto_mode, ticker, company_profile, results, valuation_params,
            summary_df, base_year, forecast_year_1, forex_rate)

        # ── Excel export ──
        _export_excel(auto_mode, use_ai, company_name, base_year_data, financial_data,
                      valuation_params, company_profile, total_equity_risk_premium,
                      gap_analysis_result, ai_result, wacc_results, wacc_base)

        # ── Exit or continue ──
        if auto_mode:
            print(f"\n{S.success('Auto 模式完成。')}")
            break

        cont = input(f"\n{S.prompt('Valuation completed. Exit program? (y/n): ')}").strip().lower()
        if cont == 'y':
            print("Exiting...")
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apikey', help='API key for financialmodelingprep.com', default=os.environ.get('FMP_API_KEY'))

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('-m', '--manual', action='store_true', help='Force manual input mode (skip AI analysis)')
    mode_group.add_argument('-a', '--auto', action='store_true', help='Full auto mode: AI analysis + auto accept + auto export')

    parser.add_argument('--engine', choices=['claude', 'gemini', 'qwen'], help='Force a specific AI engine (default: auto-detect)')

    args = parser.parse_args()

    # Apply --engine override before main()
    if args.engine:
        set_ai_engine(args.engine)

    main(args)
