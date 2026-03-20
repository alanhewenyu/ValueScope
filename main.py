# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.

import argparse
import os
import re
import sys
from datetime import date
from modeling.data import get_historical_financials, get_company_share_float, fetch_company_profile, fetch_forex_data, format_summary_df, validate_ticker, _normalize_ticker, is_a_share, is_hk_stock, is_jpn_stock, _fill_profile_from_financial_data, _calculate_beta_akshare
from modeling.dcf import calculate_dcf, print_dcf_results, sensitivity_analysis, print_sensitivity_table, wacc_sensitivity_analysis, print_wacc_sensitivity, calculate_wacc, print_wacc_details, get_risk_free_rate
from modeling.constants import HISTORICAL_DATA_PERIODS_ANNUAL, HISTORICAL_DATA_PERIODS_QUARTER, TERMINAL_RISK_PREMIUM, TERMINAL_RONIC_PREMIUM
from modeling.ai_analyst import analyze_company, interactive_review, analyze_valuation_gap, _ensure_ai_engine, set_ai_engine, _ai_engine_display_name
from modeling import excel_export as _excel
from modeling.excel_export import write_to_excel, init_paths as _init_excel_paths
from modeling.terminal_charts import print_key_drivers, print_relative_valuation, fetch_relative_valuation_data
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

def _search_fmp(query, apikey, limit=8):
    """Search FMP API for matching tickers. Returns list of dicts or []."""
    if not apikey or not query:
        return []
    try:
        import urllib.request, json as _json
        url = f"https://financialmodelingprep.com/api/v3/search?query={query}&limit={limit}&apikey={apikey}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = _json.loads(resp.read().decode())
        return [r for r in data if r.get('symbol')] if isinstance(data, list) else []
    except Exception:
        return []


def _prompt_ticker(auto_mode, apikey=None):
    """Prompt for ticker symbol with FMP search support.

    If *apikey* is available, non-ticker inputs trigger an FMP search so the
    user can pick from matching results instead of typing the exact symbol.
    """
    print(f"\n{S.title('Please enter the stock symbol to continue...')}\n")
    while True:
        raw = input(f'{S.prompt("Enter stock symbol or search by name (e.g., AAPL, apple): ")}').strip()
        if not raw:
            continue

        is_valid, _ = validate_ticker(raw)

        # With FMP key: always search first so user can type lowercase
        # tickers ("aapl") or company names ("apple") interchangeably.
        # If the top result is an exact match for what the user typed,
        # accept it automatically without showing the list.
        if apikey:
            results = _search_fmp(raw, apikey)
            # Exact symbol match → accept directly (e.g. "aapl" → AAPL)
            if results and results[0].get('symbol', '').upper() == raw.upper():
                top = results[0]['symbol']
                v, _ = validate_ticker(top)
                if v:
                    return _normalize_ticker(top)

            if results:
                # Display search results for user to pick
                print()
                for i, r in enumerate(results, 1):
                    sym = r.get('symbol', '')
                    name = r.get('name', '')
                    exch = r.get('exchangeShortName', '')
                    print(f"  {S.info(f'[{i}]')} {S.value(sym):16s} {name}" + (f"  ({exch})" if exch else ""))
                print(f"  {S.muted('[0] Search again')}")
                print()

                choice = input(f'{S.prompt("Select a number (or 0 to search again): ")}').strip()
                if choice == '0' or not choice:
                    continue
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(results):
                        selected = results[idx]['symbol']
                        v2, err = validate_ticker(selected)
                        if v2:
                            return _normalize_ticker(selected)
                        else:
                            print(S.error(f"  {err}"))
                    else:
                        print(S.error("  Invalid selection."))
                except ValueError:
                    v3, err = validate_ticker(choice)
                    if v3:
                        return _normalize_ticker(choice)
                    print(S.error(f"  {err}"))
                continue

            # No search results — fall through to direct validation
            if is_valid:
                return _normalize_ticker(raw)
            _has_cjk = any('\u4e00' <= c <= '\u9fff' for c in raw)
            if _has_cjk:
                print(S.error(f"  No results for \"{raw}\". Chinese names are not supported — please search in English (e.g., \"moutai\")."))
            else:
                print(S.error(f"  No results found for \"{raw}\". Try a different keyword or enter the ticker directly."))
            continue

        # No FMP key — accept valid tickers directly
        if is_valid:
            return _normalize_ticker(raw)
        print(S.error(f"  Invalid symbol. Please enter a valid ticker (e.g., AAPL, 0700.HK, 600519.SS)."))


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

    cont = input(f'{S.prompt("ROIC 是否在终值期回归 WACC? (y/N, Enter=N): ")}').strip().lower()
    if cont in ('y', 'yes'):
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

def _build_valuation_params(raw_params, base_year, risk_free_rate, _is_ttm, _ttm_quarter, _ttm_label,
                            forecast_year_1=None, fy_end_month=12):
    """Build the full valuation_params dict from raw parameter values."""
    return {
        'base_year': base_year,
        'forecast_year_1': forecast_year_1 if forecast_year_1 is not None else base_year + 1,
        'fy_end_month': fy_end_month,
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

        # Fallback 1: yfinance (useful for HK stocks without FMP API key)
        if forex_rate is None:
            from modeling.yfinance_data import fetch_forex_yfinance
            forex_rate = fetch_forex_yfinance(reported_currency, stock_currency)

        # Fallback 2: SSE 沪港通结算汇率 (CNY↔HKD only, no API key needed)
        if forex_rate is None:
            from modeling.data import fetch_forex_akshare
            forex_rate = fetch_forex_akshare(reported_currency, stock_currency)

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

    run_gap = input(f"\n{S.prompt('Run DCF vs Market Price gap analysis? (Y/n): ')}").strip().lower()
    if run_gap not in ('n', 'no'):
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
    """Handle Excel export (auto or prompted). Returns True if exported."""
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
        return True
    else:
        export_to_excel = input(f"\n{S.prompt('Do you want to export the valuation results to Excel? (y/n): ')}").strip().lower()
        if export_to_excel == 'y':
            _do_export()
            return True
        else:
            print(f"\n{S.muted('Skipping Excel export.')}")
            return False


# ────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────

def main(args):
    auto_mode = getattr(args, 'auto', False)
    use_ai = not args.manual

    while True:
        # ── Ticker ──
        ticker = _prompt_ticker(auto_mode, apikey=args.apikey)
        args.t = ticker
        args.period = 'annual'

        # ── Fetch annual financial data + company profile + relative valuation (parallel) ──
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as _pool:
            _f_data = _pool.submit(get_historical_financials, args.t, 'annual', args.apikey, HISTORICAL_DATA_PERIODS_ANNUAL)
            _f_prof = _pool.submit(fetch_company_profile, args.t, args.apikey)
            _f_relval = _pool.submit(fetch_relative_valuation_data, args.t, args.apikey)
            financial_data = _f_data.result()
            company_profile = _f_prof.result()
        if financial_data is None:
            if is_hk_stock(args.t):
                print(S.error("Error: Failed to fetch HK stock data. yfinance may be rate-limited — please wait a moment and try again."))
            elif is_a_share(args.t):
                print(S.error("Error: Failed to fetch A-share data. akshare data source may be temporarily unavailable — please try again later."))
            else:
                print(S.error("Error: Failed to fetch financial data. Please check your FMP API key and ticker symbol."))
            if auto_mode:
                sys.exit(1)
            continue
        # Freshness check — detect stale data, supplement from akshare if available
        try:
            from modeling.freshness import check_data_freshness
            financial_data, _freshness = check_data_freshness(args.t, financial_data, args.apikey)
            _ds = _freshness.get("data_source", "api")
            _ep = _freshness.get("expected_period", "")
            if _freshness.get("is_stale") and _ds == "api":
                print(S.warning(f"  ⚠ 数据滞后: {_ep} 财报已披露，当前数据尚未更新。请参阅公司最新公告。"))
            elif _freshness.get("is_stale") and "akshare" in _ds:
                print(S.info(f"  ⓘ 已补充最新数据: {_ep} 数据来源: 东方财富。原数据源更新后将自动切换。"))
        except Exception:
            pass

        summary_df = financial_data['summary']
        company_profile = _fill_profile_from_financial_data(company_profile, financial_data)

        # ── Phase 2: Parallel — freshness, share_float, beta, AI detect (while user reads data) ──
        from concurrent.futures import ThreadPoolExecutor as _TP2
        _phase2_pool = _TP2(max_workers=4)
        _f_share_float = _phase2_pool.submit(get_company_share_float, args.t, args.apikey, company_profile)
        _f_beta = _phase2_pool.submit(_calculate_beta_akshare, args.t) if is_a_share(args.t) else None
        if use_ai:
            _ai_detect_future = _phase2_pool.submit(_ensure_ai_engine)
        else:
            _ai_detect_future = None

        company_name = company_profile.get('companyName', 'N/A')
        base_year_col = summary_df.columns[0]
        base_year_data = summary_df.iloc[:, 0].copy()
        base_year_data.name = base_year_col

        # ── Display annual historical summary (user reads while Phase 2 runs) ──
        print(f"\n{S.header(f'{company_name} Historical Financial Data (Summary, in millions)')}")
        formatted_summary_df = format_summary_df(summary_df)
        print(formatted_summary_df.to_string())
        print()

        ttm_note = financial_data.get('ttm_note', '')
        if ttm_note:
            print(S.muted(f"  ⓘ Note: {ttm_note}"))
            print()

        # ── Key financial driver charts ──
        print_key_drivers(summary_df, company_name)

        # ── Relative valuation & historical percentiles ──
        _relval_data = _f_relval.result()  # already fetched in parallel
        print_relative_valuation(ticker, apikey=args.apikey, prefetched=_relval_data)

        # ── Collect Phase 2 results (should be done by now) ──
        if _f_beta:
            company_profile['beta'] = _f_beta.result()
        company_info = _f_share_float.result()

        # ── Detect TTM & base year (fast, no I/O) ──
        _ttm_quarter = financial_data.get('ttm_latest_quarter', '')
        _ttm_end_date = financial_data.get('ttm_end_date', '')
        _is_ttm = bool(_ttm_quarter and _ttm_end_date)
        _fy_end_month = financial_data.get('fy_end_month', 12)
        base_year = int(str(base_year_col).replace('FY', ''))
        _ttm_label = ''
        if _is_ttm:
            _ttm_end_month = int(_ttm_end_date[5:7])
            _ttm_end_year = int(_ttm_end_date[:4])
            forecast_year_1 = _ttm_end_year if _ttm_end_month <= 6 else _ttm_end_year + 1
        else:
            forecast_year_1 = base_year if _fy_end_month <= 6 else base_year + 1

        # ── Prepare base year data ──
        outstanding_shares = company_info.get('outstandingShares', 0) or 0
        if outstanding_shares <= 0:
            print(f"\n{S.warning('⚠ 无法获取流通股数 (Outstanding Shares)，每股价格将显示为 0。')}")
            print(S.muted("    请确认 FMP 是否提供该股票的流通股数据。"))
        base_year_data['Outstanding Shares'] = outstanding_shares
        base_year_data['Average Tax Rate'] = financial_data['average_tax_rate']
        base_year_data['Revenue Growth (%)'] = summary_df.iloc[summary_df.index.get_loc('Revenue Growth (%)'), 0]
        base_year_data['Total Reinvestment'] = summary_df.iloc[summary_df.index.get_loc('Total Reinvestment'), 0]

        # ── Start forex + WACC in background (runs while user reads data) ──
        def _compute_wacc_bg():
            fx = _compute_forex_rate(
                {'reported_currency': base_year_data.get('Reported Currency', '')},
                company_profile, args.apikey)
            _rfr = get_risk_free_rate(company_profile.get('country', 'United States'))
            _w, _erp, _wd = calculate_wacc(
                base_year_data, company_profile, args.apikey, verbose=False, forex_rate=fx)
            return fx, _rfr, _w, _erp, _wd
        _f_wacc = _phase2_pool.submit(_compute_wacc_bg)

        if _is_ttm:
            _ttm_label = f'{base_year_col}{_ttm_quarter} TTM'
            _ttm_date_str = f' (data through {_ttm_end_date})' if _ttm_end_date else ''
            print(f"\n{S.info(f'Using {_ttm_label}{_ttm_date_str} as base year {base_year}. Forecast Year 1 ≈ {forecast_year_1}.')}")
        else:
            print(f"\n{S.info(f'The base year used for cashflow forecast is {base_year}.')}")

        # ── Optional: view quarterly data as reference (WACC computes in background) ──
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

        # ── Collect WACC result (should be done by now — user was reading data) ──
        forex_rate, risk_free_rate, wacc, total_equity_risk_premium, wacc_details = _f_wacc.result()
        average_tax_rate = base_year_data['Average Tax Rate']

        # ── Collect valuation parameters (AI or manual) ──
        use_ai = not args.manual
        ai_params = None
        ai_result = None

        # ── AI engine check (detection started earlier in background) ──
        if use_ai and (_ai_detect_future.result() if _ai_detect_future else _ensure_ai_engine()) is None:
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
            use_ai = False

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
                    fy_end_month=_fy_end_month,
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
            raw_params, base_year, risk_free_rate, _is_ttm, _ttm_quarter, _ttm_label,
            forecast_year_1=forecast_year_1, fy_end_month=_fy_end_month)

        # ── DCF calculation & output ──
        results = calculate_dcf(base_year_data, valuation_params, financial_data, company_info, company_profile)
        stock_currency = company_profile.get('currency', 'USD')

        print_dcf_results(results, company_name, ttm_label=valuation_params.get('ttm_label', ''),
                          forex_rate=forex_rate, stock_currency=stock_currency)

        # ── Sensitivity analysis ──
        reported_currency = results.get('reported_currency', '')
        # Determine display currency for sensitivity tables
        sensitivity_currency = stock_currency if (forex_rate and reported_currency and reported_currency != stock_currency) else (reported_currency or stock_currency)

        print(f"\n{S.info('Running sensitivity analysis...')}")
        sensitivity_table = sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile)
        print(f"\n{S.subheader(f'Sensitivity Analysis - Revenue Growth vs EBIT Margin (Price per Share, {sensitivity_currency})')}")
        print_sensitivity_table(sensitivity_table, valuation_params,
                                forex_rate=forex_rate, stock_currency=stock_currency,
                                reported_currency=reported_currency)

        print(f"\n{S.info('Running WACC sensitivity analysis...')}")
        wacc_results, wacc_base = wacc_sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile)
        print(f"\n{S.subheader(f'Sensitivity Analysis - WACC (Price per Share, {sensitivity_currency})')}")
        print_wacc_sensitivity(wacc_results, wacc_base,
                               forex_rate=forex_rate, stock_currency=stock_currency,
                               reported_currency=reported_currency)

        # ── Gap analysis (first run) ──
        gap_analysis_result = _run_gap_analysis(
            auto_mode, ticker, company_profile, results, valuation_params,
            summary_df, base_year, forecast_year_1, forex_rate)

        # ── Exit or continue ──
        if auto_mode:
            print(f"\n{S.success('Auto 模式完成。')}")
            break

        # ── Interactive parameter adjustment loop ──
        _param_keys = [
            ('1', 'revenue_growth_1', 'Revenue Growth Yr1 (%)'),
            ('2', 'revenue_growth_2', 'Revenue Growth Yr2-5 (%)'),
            ('3', 'ebit_margin', 'Target EBIT Margin (%)'),
            ('4', 'convergence', 'Convergence Years'),
            ('5', 'wacc', 'WACC (%)'),
            ('6', 'tax_rate', 'Tax Rate (%)'),
            ('7', 'revenue_invested_capital_ratio_1', 'Rev/IC Ratio Yr1'),
            ('8', 'revenue_invested_capital_ratio_2', 'Rev/IC Ratio Yr3-5'),
            ('9', 'revenue_invested_capital_ratio_3', 'Rev/IC Ratio Yr5-10'),
        ]
        while True:
            print(f"\n{S.subheader('Adjust Parameters')}")
            print(f"  {S.muted('Current parameters:')}")
            for key, param, label in _param_keys:
                val = valuation_params.get(param, raw_params.get(param, '?'))
                if isinstance(val, float):
                    val_str = f"{val:.2f}" if val < 10 else f"{val:.1f}"
                else:
                    val_str = str(val)
                print(f"    [{key}] {label}: {val_str}")
            print(f"    [e] Export to {'DB' if os.environ.get('VS_DB_PATH') else 'Excel'}")
            print(f"    [g] Gap Analysis (AI)")
            print(f"    [q] Exit")

            choice = input(f"\n{S.prompt('Enter number to modify, or [e]xport/[g]ap/[q]uit: ')}").strip().lower()

            if choice == 'q':
                print("Exiting...")
                break
            elif choice == 'e':
                _db_path = os.environ.get('VS_DB_PATH')
                if _db_path:
                    from modeling.db_export import maybe_save_to_db
                    maybe_save_to_db(
                        ticker=ticker, company_name=company_name,
                        mode='auto' if (use_ai and auto_mode) else ('copilot' if use_ai else 'manual'),
                        ai_engine=_ai_engine_display_name() if use_ai else None,
                        valuation_params=valuation_params, results=results,
                        company_profile=company_profile,
                        gap_analysis_result=gap_analysis_result, ai_result=ai_result,
                        sensitivity_table=sensitivity_table,
                        wacc_sensitivity=(wacc_results, wacc_base),
                        financial_data=financial_data,
                        forex_rate=forex_rate,
                    )
                    print(f"\n{S.success('Valuation saved to database.')}")
                else:
                    _export_excel(auto_mode, use_ai, company_name, base_year_data, financial_data,
                                  valuation_params, company_profile, total_equity_risk_premium,
                                  gap_analysis_result, ai_result, wacc_results, wacc_base)
                continue
            elif choice == 'g':
                gap_analysis_result = _run_gap_analysis(
                    False, ticker, company_profile, results, valuation_params,
                    summary_df, base_year, forecast_year_1, forex_rate)
                continue

            # Find matching param
            matched = None
            for key, param, label in _param_keys:
                if choice == key:
                    matched = (param, label)
                    break

            if not matched:
                print(f"  {S.error('Invalid choice.')}")
                continue

            param_name, param_label = matched
            current_val = valuation_params.get(param_name, raw_params.get(param_name, 0))
            new_val = _input_float(
                f"  {S.prompt(f'{param_label} (current: {current_val:.2f}): ')}",
                default=current_val)

            if new_val == current_val:
                continue

            # Update raw_params and rebuild
            raw_params[param_name] = new_val
            valuation_params = _build_valuation_params(
                raw_params, base_year, risk_free_rate, _is_ttm, _ttm_quarter, _ttm_label,
                forecast_year_1=forecast_year_1, fy_end_month=_fy_end_month)

            # Recalculate DCF
            print(f"\n{S.info('Recalculating...')}")
            results = calculate_dcf(base_year_data, valuation_params, financial_data, company_info, company_profile)
            print_dcf_results(results, company_name, ttm_label=valuation_params.get('ttm_label', ''),
                              forex_rate=forex_rate, stock_currency=stock_currency)

            # Recalculate sensitivity
            sensitivity_table = sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile)
            print(f"\n{S.subheader(f'Sensitivity Analysis - Revenue Growth vs EBIT Margin ({sensitivity_currency})')}")
            print_sensitivity_table(sensitivity_table, valuation_params,
                                    forex_rate=forex_rate, stock_currency=stock_currency,
                                    reported_currency=reported_currency)

            wacc_results, wacc_base = wacc_sensitivity_analysis(base_year_data, valuation_params, financial_data, company_info, company_profile)
            print(f"\n{S.subheader(f'Sensitivity Analysis - WACC ({sensitivity_currency})')}")
            print_wacc_sensitivity(wacc_results, wacc_base,
                                   forex_rate=forex_rate, stock_currency=stock_currency,
                                   reported_currency=reported_currency)
        break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apikey', help='API key for financialmodelingprep.com', default=os.environ.get('FMP_API_KEY'))

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('-m', '--manual', action='store_true', help='Force manual input mode (skip AI analysis)')
    mode_group.add_argument('-a', '--auto', action='store_true', help='Full auto mode: AI analysis + auto accept + auto export')

    parser.add_argument('--engine', choices=['claude', 'gemini', 'qwen'], help='Force a specific AI engine (default: auto-detect)')
    parser.add_argument('--vivid', action='store_true', help='Use vivid (bright/bold) terminal colors')

    args = parser.parse_args()

    # Apply --vivid before any output
    if args.vivid:
        S.enable_vivid_mode()

    # Apply --engine override before main()
    if args.engine:
        set_ai_engine(args.engine)

    main(args)
