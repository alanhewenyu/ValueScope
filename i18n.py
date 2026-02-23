# Copyright (c) 2026 Alan He. Licensed under MIT.
"""ValuX i18n — lightweight Chinese/English UI translations."""

import streamlit as st

# ──────────────────────────────────────────────────────────────
# Translation dictionary — keys grouped by UI area
# ──────────────────────────────────────────────────────────────
_STRINGS = {
    'en': {
        # ── Sidebar ──
        'sidebar_brand_sub': 'AI-Powered Interactive DCF Valuation',
        'sidebar_ticker_label': 'Enter a stock symbol below to start',
        'sidebar_ticker_placeholder': 'e.g. AAPL, 0700.HK, or 600519.SS',
        'sidebar_manual_btn': '\U0001f4dd Manual Valuation',
        'sidebar_manual_help': 'We fetch the data \u2014 you review it and set each assumption yourself for full control.',
        'sidebar_or': 'or',
        'sidebar_oneclick_btn': '\U0001f916 AI Valuation',
        'sidebar_oneclick_help': 'Fully automated: AI researches the company, sets all assumptions, and runs the DCF.',
        'sidebar_mode_prompt': '\U0001f446 Choose a valuation mode above to start',
        'sidebar_ai_engine': 'AI Engine',
        'sidebar_ai_speed': 'AI Analysis Speed',
        'sidebar_speed_quality_claude': 'Quality (Opus)',
        'sidebar_speed_balanced_claude': 'Balanced (Sonnet)',
        'sidebar_speed_help_claude': 'Quality uses Opus + web search. Balanced uses Sonnet + web search.',
        'sidebar_speed_quality_qwen': '\U0001f50d Quality (+ Web)',
        'sidebar_speed_fast_qwen': '\u26a1 Fast (data only)',
        'sidebar_speed_help_qwen': 'Quality enables web search via Tavily. Fast uses only the financial data provided \u2014 no web access, much faster.',
        'sidebar_no_engine': ('**AI Valuation is not available in the web version.**\n\n'
                               'AI Valuation requires a locally installed AI CLI '
                               '(Claude Code, Gemini CLI, or Qwen CLI).\n\n'
                               'To use AI Valuation, download and run ValuX locally:\n\n'
                               '```\ngit clone https://github.com/alanhewenyu/ValuX.git\ncd ValuX && pip install -r requirements.txt\nstreamlit run web_app.py\n```\n\n'
                               'You can still use **Manual Valuation** on this page \u2014 it works the same way, '
                               'you just set the assumptions yourself.'),
        'sidebar_language': 'Language',
        'sidebar_language_help': 'Interface & AI output language. EN = English, CN = \u4e2d\u6587.',
        'sidebar_fmp_label': 'Financial Modeling Prep (FMP) API Key',
        'sidebar_fmp_placeholder': 'Enter your FMP key (Required for US stocks)',
        'sidebar_fmp_hint': '\U0001f4a1 HK & A-shares do not require an API key.',
        'sidebar_engine_not_installed': '**{engine}** is not installed.',

        # ── Welcome page ──
        'welcome_instruction': 'Enter a stock symbol in the sidebar, then click<br>'
                               '<b>\U0001f4dd Manual Valuation</b> or <b>\U0001f916 AI Valuation</b> to begin.',
        'welcome_instruction_web': 'Enter a stock symbol in the sidebar, then click<br>'
                                   '<b>\U0001f4dd Manual Valuation</b> to begin.',
        'welcome_us': '\U0001f1fa\U0001f1f8 US \u2014 e.g. AAPL',
        'welcome_hk': '\U0001f1ed\U0001f1f0 HK \u2014 e.g. 0700.HK',
        'welcome_cn': '\U0001f1e8\U0001f1f3 A-shares \u2014 e.g. 600519.SS',
        'welcome_api_note': 'HK &amp; A-shares do not require an API key.',
        'welcome_empty_warning': '\u26a0\ufe0f Please enter a stock symbol in the sidebar first, then click a valuation button.',

        # ── Header buttons ──
        'btn_collapse_fin': '\U0001f4cb Collapse\nFinancial Data',
        'btn_view_fin': '\U0001f4cb View Historical\nFinancial Data',
        'btn_gap_analysis': '\U0001f4ca Analyze DCF\nvs Market Price',
        'btn_download': '\U0001f4e5 Download\nValuation Report',
        'btn_run_dcf': '\u25b6\ufe0f Run DCF Valuation',

        # ── Hero bar ──
        'hero_title': 'Valuation Results',
        'hero_intrinsic': 'Intrinsic Value',
        'hero_market': 'Market Price',
        'hero_undervalued': 'Undervalued',
        'hero_overvalued': 'Overvalued',
        'verdict_sig_under': 'significantly undervalued',
        'verdict_mod_under': 'moderately undervalued',
        'verdict_fair': 'fairly valued',
        'verdict_mod_over': 'moderately overvalued',
        'verdict_sig_over': 'significantly overvalued',
        'hero_summary': '{g1:.1f}% Y1 growth, {g2:.1f}% Y2-5 CAGR, {m:.1f}% operating margin, {w:.1f}% WACC \u2192 <b>{verdict}</b>',

        # ── Section headers ──
        'section_hist_data': 'Historical Financial Data (in millions)',
        'section_valuation_params': 'Valuation Parameters',
        'section_cashflow': 'Cash Flow Forecast (in millions)',
        'section_breakdown': 'Valuation Breakdown (in millions)',
        'section_sensitivity': 'Sensitivity Analysis',

        # ── Financial table captions ──
        'fin_ttm_caption': 'Using {ttm_label}{date_str} as base year {base_year}. Forecast Year 1 = {fy1}.',
        'fin_base_caption': 'Base year: {base_year}',
        'fin_ttm_note': 'TTM: {note}',

        # ── Valuation parameters ──
        'param_growth_margins': '**Growth & Margins**',
        'param_efficiency': '**Efficiency & Discount Rate**',
        'param_rg1_ttm': 'Revenue Growth, Year 1 from {start} (%)',
        'param_rg2_ttm': 'Revenue Growth, Year 2\u20135 CAGR (%)',
        'param_rg1_fy': 'Revenue Growth FY{fy1} (%)',
        'param_rg2_fy': 'Revenue Growth FY{fy1_1}\u2013{fy1_4} CAGR (%)',
        'param_ebit_margin': 'Target Operating Profit Margin (EBIT) (%)',
        'param_convergence': 'Years to Target Operating Margin (EBIT)',
        'param_tax_rate': 'Tax Rate (%)',
        'param_wacc': 'WACC (%)',
        'param_ric1_ttm': 'Revenue / Invested Capital (Year 1\u20132)',
        'param_ric2_ttm': 'Revenue / Invested Capital (Year 3\u20135)',
        'param_ric3_ttm': 'Revenue / Invested Capital (Year 5\u201310)',
        'param_ric1_fy': 'Revenue / Invested Capital (FY{fy1}\u2013{fy1_1})',
        'param_ric2_fy': 'Revenue / Invested Capital (FY{fy1_2}\u2013{fy1_4})',
        'param_ric3_fy': 'Revenue / Invested Capital (FY{fy1_4}\u2013{fy1_9})',
        'help_rg1_ttm': 'Projected revenue growth for the next 12 months starting from {start} (Year 1).',
        'help_rg2_ttm': 'Annual compounded average growth rate (CAGR) for Year 2 through Year 5.',
        'help_rg1_fy': 'Projected revenue growth rate for fiscal year {fy1}.',
        'help_rg2_fy': 'Annual compounded average growth rate (CAGR) from FY{fy1_1} to FY{fy1_4}.',
        'help_ebit_margin': 'The sustainable operating margin the company is expected to reach by the end of the transition period.',
        'help_convergence': 'The number of years it will take for the current margin to reach the target margin.',
        'help_tax_rate': 'The expected effective corporate tax rate (typically 15%-25%).',
        'help_ric': 'Capital Efficiency: Amount of revenue generated per unit of invested capital. Higher means less capital intensive.',
        'help_wacc': 'Weighted Average Cost of Capital (Discount Rate). Higher risk warrants a higher rate (usually 8%-12%).',
        'param_ronic_label': 'ROIC = WACC in perpetuity',
        'param_ronic_help': 'ROIC tends to converge to WACC over time as competition erodes excess returns. '
                            'Only firms with strong, durable moats may sustain a modest premium.',
        'param_ronic_note': '\u2610 Unchecked = ROIC = WACC + {prem:.0f}% (modest excess returns) '
                            '&nbsp;|&nbsp; \u2611 Checked = ROIC = WACC (no excess returns)',
        'param_modified_hint': '\u26a1 AI: {ai_val} \u2192 You: {user_val}',
        'param_n_modified': '\u26a0 {n} parameter{s} modified from AI suggestion',
        'wacc_reference': '\U0001f4ca WACC Calculation Reference',

        # ── Slider hint ──
        'slider_hint': '\U0001f39a\ufe0f Drag sliders to adjust \u2014 valuation in header updates instantly',
        'defaults_warning_title': '\u26a0\ufe0f Default values are based on historical averages \u2014 not recommendations',
        'defaults_warning_body': 'These are starting points derived from the company\'s historical financials. '
                                 'Please <b>drag the sliders above</b> to adjust each parameter based on your own analysis, '
                                 'then click <b>Run DCF Valuation</b> below.',

        # ── Historical reference labels ──
        'hist_latest': '{label}: {val}{suffix}',
        'hist_avg': '{n}yr Avg: {val}{suffix}',
        'hist_range': '{n}yr Range: {min}\u2013{max}{suffix}',

        # ── AI reasoning ──
        'ai_reasoning_hint': 'AI analysis by {engine} \u2014 reasoning for each parameter \u2014 <b>{action}</b>',
        'ai_reasoning_expander': 'AI Reasoning (per parameter)',
        'ai_hint_expand': 'click below to expand',
        'ai_hint_collapse': 'click below to collapse',
        'ai_label_rg1': 'Year 1 Revenue Growth',
        'ai_label_rg2': 'Years 2-5 CAGR',
        'ai_label_ebit': 'Target EBIT Margin',
        'ai_label_conv': 'Convergence Years',
        'ai_label_ric1': 'Revenue / Invested Capital (Y1-2)',
        'ai_label_ric2': 'Revenue / Invested Capital (Y3-5)',
        'ai_label_ric3': 'Revenue / Invested Capital (Y5-10)',
        'ai_label_tax': 'Tax Rate',
        'ai_label_wacc': 'WACC',
        'ai_label_ronic': 'RONIC',
        'ai_label_rg1_icon': '\U0001f4c8 Year 1 Revenue Growth',
        'ai_label_rg2_icon': '\U0001f4ca Years 2-5 CAGR',
        'ai_label_ebit_icon': '\U0001f4b0 Target EBIT Margin',
        'ai_label_conv_icon': '\U0001f504 Convergence Years',
        'ai_label_ric1_icon': '\U0001f3ed Revenue / Invested Capital (Y1-2)',
        'ai_label_ric2_icon': '\U0001f3d7\ufe0f Revenue / Invested Capital (Y3-5)',
        'ai_label_ric3_icon': '\U0001f527 Revenue / Invested Capital (Y5-10)',
        'ai_label_tax_icon': '\U0001f4cb Tax Rate',
        'ai_label_wacc_icon': '\u2696\ufe0f WACC',
        'ai_label_ronic_icon': '\U0001f3af RONIC',
        'ai_ronic_yes': 'Yes',
        'ai_ronic_no': 'No',

        # ── AI progress / streaming ──
        'ai_live_title': '\U0001f916 AI Analysis \u2014 Live Reasoning',
        'ai_analyzing': '{engine} is analyzing... {elapsed:.0f}s elapsed',
        'ai_revealing': 'Revealing analysis... {idx}/{total} parameters',
        'ai_revealing_status': 'Revealing reasoning... {idx}/{total} \u00b7 {elapsed:.0f}s total',
        'ai_all_done': '\u2705 All {total} parameters analyzed ({elapsed:.0f}s)',
        'ai_complete': '\u2705 Analysis complete via {engine} ({elapsed:.0f}s)',
        'ai_toast_complete_title': '\u2705 {label} Complete',
        'ai_toast_complete_msg': 'Analysis finished via {engine}',
        'ai_status_label': 'Analyzing {company}',
        'ai_patience': '\u2615 This may take 1\u20133 minutes. Please be patient\u2026',
        'ai_elapsed': '\u23f1 {elapsed:.0f}s elapsed',
        'ai_lines_received': '\u23f1 {elapsed:.0f}s elapsed  \u00b7  {lines} lines received',

        # Phase labels (compact streaming)
        'phase_starting': 'Starting AI analysis...',
        'phase_searching': 'Searching for market data & analyst estimates...',
        'phase_parameters': 'Analyzing valuation parameters...',
        'phase_generating': 'Generating structured output...',
        'phase_init_engine': 'Initializing {engine}...',

        # Rotating wait messages
        'wait_1': '\U0001f50d Searching for latest earnings guidance and analyst consensus...',
        'wait_2': '\U0001f4ca Analyzing revenue growth trends and industry benchmarks...',
        'wait_3': '\U0001f4b0 Evaluating EBIT margin potential and operating leverage...',
        'wait_4': '\U0001f3ed Assessing capital efficiency and reinvestment requirements...',
        'wait_5': '\u2696\ufe0f Cross-referencing WACC estimates from multiple sources...',
        'wait_6': '\U0001f4cb Reviewing tax structure and effective rates...',
        'wait_7': '\U0001f3af Determining terminal value assumptions...',
        'wait_8': '\U0001f504 Synthesizing all data into valuation parameters...',

        # ── DCF table fields ──
        'dcf_base': 'Base ({ttm})',
        'dcf_base_plain': 'Base',
        'dcf_terminal': 'Terminal',
        'dcf_rev_growth': 'Revenue Growth',
        'dcf_revenue': 'Revenue',
        'dcf_ebit_margin': 'EBIT Margin',
        'dcf_ebit': 'EBIT',
        'dcf_tax_rate': 'Tax Rate',
        'dcf_ebit_1t': 'EBIT(1-t)',
        'dcf_reinvestments': 'Reinvestments',
        'dcf_fcff': 'FCFF',
        'dcf_wacc': 'WACC',
        'dcf_discount_factor': 'Discount Factor',
        'dcf_pv_fcff': 'PV (FCFF)',

        # ── Breakdown items ──
        'bd_pv_fcff': 'PV of FCFF (10 years)',
        'bd_pv_terminal': 'PV of Terminal Value',
        'bd_sum_pv': 'Sum of Present Values',
        'bd_cash': '+ Cash & Equivalents',
        'bd_investments': '+ Total Investments',
        'bd_ev': 'Enterprise Value',
        'bd_debt': '\u2212 Total Debt',
        'bd_minority': '\u2212 Minority Interest',
        'bd_equity': 'Equity Value',
        'bd_shares': 'Outstanding Shares (millions)',
        'bd_iv_per_share': 'Intrinsic Value per Share',
        'bd_iv_per_share_cur': 'Intrinsic Value per Share ({cur})',

        # ── Sensitivity ──
        'sens_rev_vs_ebit': '**Revenue Growth vs EBIT Margin** (Price / Share, {cur})',
        'sens_ebit_axis': 'EBIT Margin \u25b8',
        'sens_growth_axis': 'Growth \u25be',
        'sens_wacc_title': '**WACC Sensitivity** (Price / Share, {cur})',
        'sens_wacc_label': 'WACC',
        'sens_price_share': 'Price / Share',

        # ── Gap analysis ──
        'gap_hint': '\U0001f4ca DCF vs Market \u2014 Gap Analysis{adj} \u2014 <b>click below to expand</b>',
        'gap_expander': 'Gap Analysis Details',
        'gap_adjusted': 'Adjusted valuation: **{val:,.2f} {cur}**',
        'gap_status_label': 'Gap Analysis',
        'gap_no_price': 'Cannot get current stock price \u2014 skipping gap analysis.',

        # ── Error / warning messages ──
        'err_fetch_failed': 'Failed to fetch financial data. Check your API key and ticker symbol.',
        'err_ai_parse': 'AI Analysis succeeded but failed to parse parameters. The model might have returned an invalid format.',
        'err_ai_failed': 'AI Analysis failed: {msg}',
        'err_gap_failed': 'Gap analysis failed: {msg}',
        'warn_ai_no_params': 'AI could not produce parameters. Please switch to Manual Input.',
        'fetching_data': 'Fetching data for {ticker}...',
        'fetching_fin_data': 'Fetching financial data for {ticker}...',
        'calculating_dcf': 'Calculating DCF...',

        # ── Footer ──
        'footer_tagline': '<b>ValuX</b> \u2014 AI-Powered Interactive DCF Valuation',

        # ── Financial table row labels ──
        'fin_reported_currency': 'Reported Currency',
        'fin_sec_profitability': '\u25b8 Profitability',
        'fin_sec_reinvestment': '\u25b8 Reinvestment',
        'fin_sec_capital': '\u25b8 Capital Structure',
        'fin_sec_ratios': '\u25b8 Key Ratios',
        'fin_revenue': 'Revenue',
        'fin_ebit': 'EBIT',
        'fin_rev_growth': 'Revenue Growth (%)',
        'fin_ebit_growth': 'EBIT Growth (%)',
        'fin_ebit_margin': 'EBIT Margin (%)',
        'fin_tax_rate': 'Tax Rate (%)',
        'fin_capex': '(+) Capital Expenditure',
        'fin_da': '(-) D&A',
        'fin_wc': '(+) \u0394Working Capital',
        'fin_total_reinv': 'Total Reinvestment',
        'fin_total_debt': '(+) Total Debt',
        'fin_total_equity': '(+) Total Equity',
        'fin_cash': '(-) Cash & Equivalents',
        'fin_investments': '(-) Total Investments',
        'fin_invested_capital': 'Invested Capital',
        'fin_minority': 'Minority Interest',
        'fin_rev_ic': 'Revenue / IC',
        'fin_debt_assets': 'Debt to Assets (%)',
        'fin_cost_debt': 'Cost of Debt (%)',
        'fin_roic': 'ROIC (%)',
        'fin_roe': 'ROE (%)',
        'fin_div_yield': 'Dividend Yield (%)',
        'fin_payout': 'Payout Ratio (%)',
    },

    'zh': {
        # ── Sidebar ──
        'sidebar_brand_sub': 'AI \u667a\u80fd\u4ea4\u4e92\u5f0f DCF \u4f30\u503c',
        'sidebar_ticker_label': '\u5728\u4e0b\u65b9\u8f93\u5165\u80a1\u7968\u4ee3\u7801\u5f00\u59cb',
        'sidebar_ticker_placeholder': '\u4f8b\u5982 AAPL, 0700.HK, 600519.SS',
        'sidebar_manual_btn': '\U0001f4dd \u624b\u52a8\u4f30\u503c',
        'sidebar_manual_help': '\u6211\u4eec\u83b7\u53d6\u6570\u636e\u2014\u2014\u60a8\u5ba1\u9605\u5e76\u81ea\u884c\u8bbe\u5b9a\u6bcf\u4e2a\u5047\u8bbe\uff0c\u5b8c\u5168\u638c\u63a7\u3002',
        'sidebar_or': '\u6216',
        'sidebar_oneclick_btn': '\U0001f916 AI \u4f30\u503c',
        'sidebar_oneclick_help': '\u5168\u81ea\u52a8\uff1aAI \u8c03\u7814\u516c\u53f8\u3001\u8bbe\u5b9a\u6240\u6709\u5047\u8bbe\u5e76\u8fd0\u884c DCF\u3002',
        'sidebar_mode_prompt': '\U0001f446 \u8bf7\u5728\u4e0a\u65b9\u9009\u62e9\u4f30\u503c\u6a21\u5f0f',
        'sidebar_ai_engine': 'AI \u5f15\u64ce',
        'sidebar_ai_speed': 'AI \u5206\u6790\u901f\u5ea6',
        'sidebar_speed_quality_claude': '\u7cbe\u7ec6 (Opus)',
        'sidebar_speed_balanced_claude': '\u5747\u8861 (Sonnet)',
        'sidebar_speed_help_claude': '\u7cbe\u7ec6\u6a21\u5f0f\u4f7f\u7528 Opus + \u7f51\u7edc\u641c\u7d22\u3002\u5747\u8861\u6a21\u5f0f\u4f7f\u7528 Sonnet + \u7f51\u7edc\u641c\u7d22\u3002',
        'sidebar_speed_quality_qwen': '\U0001f50d \u7cbe\u7ec6 (+ \u7f51\u7edc\u641c\u7d22)',
        'sidebar_speed_fast_qwen': '\u26a1 \u5feb\u901f (\u4ec5\u6570\u636e)',
        'sidebar_speed_help_qwen': '\u7cbe\u7ec6\u6a21\u5f0f\u901a\u8fc7 Tavily \u542f\u7528\u7f51\u7edc\u641c\u7d22\u3002\u5feb\u901f\u6a21\u5f0f\u4ec5\u4f7f\u7528\u63d0\u4f9b\u7684\u8d22\u52a1\u6570\u636e\u2014\u2014\u65e0\u7f51\u7edc\u8bbf\u95ee\uff0c\u901f\u5ea6\u66f4\u5feb\u3002',
        'sidebar_no_engine': ('**\u7f51\u9875\u7248\u6682\u4e0d\u652f\u6301 AI \u4f30\u503c\u3002**\n\n'
                               'AI \u4f30\u503c\u9700\u8981\u672c\u5730\u5b89\u88c5 AI CLI\uff08Claude Code\u3001Gemini CLI \u6216 Qwen CLI\uff09\u3002\n\n'
                               '\u5982\u9700\u4f7f\u7528 AI \u4f30\u503c\uff0c\u8bf7\u4e0b\u8f7d\u5e76\u5728\u672c\u5730\u8fd0\u884c ValuX\uff1a\n\n'
                               '```\ngit clone https://github.com/alanhewenyu/ValuX.git\ncd ValuX && pip install -r requirements.txt\nstreamlit run web_app.py\n```\n\n'
                               '\u60a8\u4ecd\u53ef\u4ee5\u5728\u6b64\u9875\u9762\u4f7f\u7528 **\u624b\u52a8\u4f30\u503c** \u2014\u2014 \u529f\u80fd\u5b8c\u5168\u76f8\u540c\uff0c'
                               '\u53ea\u662f\u9700\u8981\u60a8\u81ea\u5df1\u8bbe\u5b9a\u5047\u8bbe\u53c2\u6570\u3002'),
        'sidebar_language': '\u8bed\u8a00',
        'sidebar_language_help': '\u754c\u9762\u548c AI \u8f93\u51fa\u8bed\u8a00\u3002EN = English\uff0cCN = \u4e2d\u6587\u3002',
        'sidebar_fmp_label': 'FMP API 密钥',
        'sidebar_fmp_placeholder': '输入 FMP 密钥（美股必填）',
        'sidebar_fmp_hint': '\U0001f4a1 \u6e2f\u80a1\u548c A \u80a1\u65e0\u9700 API \u5bc6\u94a5\u3002',
        'sidebar_engine_not_installed': '**{engine}** \u672a\u5b89\u88c5\u3002',

        # ── Welcome page ──
        'welcome_instruction': '\u5728\u4fa7\u8fb9\u680f\u8f93\u5165\u80a1\u7968\u4ee3\u7801\uff0c\u7136\u540e\u70b9\u51fb<br>'
                               '<b>\U0001f4dd \u624b\u52a8\u4f30\u503c</b> \u6216 <b>\U0001f916 AI \u4f30\u503c</b> \u5f00\u59cb\u3002',
        'welcome_instruction_web': '\u5728\u4fa7\u8fb9\u680f\u8f93\u5165\u80a1\u7968\u4ee3\u7801\uff0c\u7136\u540e\u70b9\u51fb<br>'
                                   '<b>\U0001f4dd \u624b\u52a8\u4f30\u503c</b> \u5f00\u59cb\u3002',
        'welcome_us': '\U0001f1fa\U0001f1f8 \u7f8e\u80a1 \u2014 \u4f8b\u5982 AAPL',
        'welcome_hk': '\U0001f1ed\U0001f1f0 \u6e2f\u80a1 \u2014 \u4f8b\u5982 0700.HK',
        'welcome_cn': '\U0001f1e8\U0001f1f3 A \u80a1 \u2014 \u4f8b\u5982 600519.SS',
        'welcome_api_note': '\u6e2f\u80a1\u548c A \u80a1\u65e0\u9700 API \u5bc6\u94a5\u3002',
        'welcome_empty_warning': '\u26a0\ufe0f \u8bf7\u5148\u5728\u4fa7\u8fb9\u680f\u8f93\u5165\u80a1\u7968\u4ee3\u7801\uff0c\u7136\u540e\u70b9\u51fb\u4f30\u503c\u6309\u94ae\u3002',

        # ── Header buttons ──
        'btn_collapse_fin': '\U0001f4cb \u6536\u8d77\n\u8d22\u52a1\u6570\u636e',
        'btn_view_fin': '\U0001f4cb \u67e5\u770b\u5386\u53f2\n\u8d22\u52a1\u6570\u636e',
        'btn_gap_analysis': '\U0001f4ca \u5206\u6790 DCF\n\u4e0e\u5e02\u573a\u4ef7\u5dee\u5f02',
        'btn_download': '\U0001f4e5 \u4e0b\u8f7d\n\u4f30\u503c\u62a5\u544a',
        'btn_run_dcf': '\u25b6\ufe0f \u8fd0\u884c DCF \u4f30\u503c',

        # ── Hero bar ──
        'hero_title': '\u4f30\u503c\u7ed3\u679c',
        'hero_intrinsic': '\u5185\u5728\u4ef7\u503c',
        'hero_market': '\u5e02\u573a\u4ef7\u683c',
        'hero_undervalued': '\u4f4e\u4f30',
        'hero_overvalued': '\u9ad8\u4f30',
        'verdict_sig_under': '\u663e\u8457\u4f4e\u4f30',
        'verdict_mod_under': '\u9002\u5ea6\u4f4e\u4f30',
        'verdict_fair': '\u4f30\u503c\u5408\u7406',
        'verdict_mod_over': '\u9002\u5ea6\u9ad8\u4f30',
        'verdict_sig_over': '\u663e\u8457\u9ad8\u4f30',
        'hero_summary': '{g1:.1f}% \u7b2c1\u5e74\u589e\u957f, {g2:.1f}% 2-5\u5e74 CAGR, {m:.1f}% \u8425\u4e1a\u5229\u6da6\u7387, {w:.1f}% WACC \u2192 <b>{verdict}</b>',

        # ── Section headers ──
        'section_hist_data': '\u5386\u53f2\u8d22\u52a1\u6570\u636e\uff08\u767e\u4e07\uff09',
        'section_valuation_params': '\u4f30\u503c\u53c2\u6570',
        'section_cashflow': '\u73b0\u91d1\u6d41\u9884\u6d4b\uff08\u767e\u4e07\uff09',
        'section_breakdown': '\u4f30\u503c\u660e\u7ec6\uff08\u767e\u4e07\uff09',
        'section_sensitivity': '\u654f\u611f\u6027\u5206\u6790',

        # ── Financial table captions ──
        'fin_ttm_caption': '\u4f7f\u7528 {ttm_label}{date_str} \u4f5c\u4e3a\u57fa\u51c6\u5e74 {base_year}\u3002\u9884\u6d4b\u7b2c1\u5e74 = {fy1}\u3002',
        'fin_base_caption': '\u57fa\u51c6\u5e74\uff1a{base_year}',
        'fin_ttm_note': 'TTM\uff1a{note}',

        # ── Valuation parameters ──
        'param_growth_margins': '**\u589e\u957f\u4e0e\u5229\u6da6\u7387**',
        'param_efficiency': '**\u8d44\u672c\u6548\u7387\u4e0e\u8d34\u73b0\u7387**',
        'param_rg1_ttm': '\u8425\u6536\u589e\u957f\uff0c\u7b2c1\u5e74\u4ece {start} \u5f00\u59cb (%)',
        'param_rg2_ttm': '\u8425\u6536\u589e\u957f\uff0c\u7b2c2\u20135\u5e74 CAGR (%)',
        'param_rg1_fy': '\u8425\u6536\u589e\u957f FY{fy1} (%)',
        'param_rg2_fy': '\u8425\u6536\u589e\u957f FY{fy1_1}\u2013{fy1_4} CAGR (%)',
        'param_ebit_margin': '\u76ee\u6807\u8425\u4e1a\u5229\u6da6\u7387 (EBIT) (%)',
        'param_convergence': '\u8fbe\u5230\u76ee\u6807\u8425\u4e1a\u5229\u6da6\u7387\u5e74\u6570 (EBIT)',
        'param_tax_rate': '\u7a0e\u7387 (%)',
        'param_wacc': 'WACC (%)',
        'param_ric1_ttm': '\u8425\u6536 / \u6295\u5165\u8d44\u672c\uff08\u7b2c1\u20132\u5e74\uff09',
        'param_ric2_ttm': '\u8425\u6536 / \u6295\u5165\u8d44\u672c\uff08\u7b2c3\u20135\u5e74\uff09',
        'param_ric3_ttm': '\u8425\u6536 / \u6295\u5165\u8d44\u672c\uff08\u7b2c5\u201310\u5e74\uff09',
        'param_ric1_fy': '\u8425\u6536 / \u6295\u5165\u8d44\u672c (FY{fy1}\u2013{fy1_1})',
        'param_ric2_fy': '\u8425\u6536 / \u6295\u5165\u8d44\u672c (FY{fy1_2}\u2013{fy1_4})',
        'param_ric3_fy': '\u8425\u6536 / \u6295\u5165\u8d44\u672c (FY{fy1_4}\u2013{fy1_9})',
        'help_rg1_ttm': '\u4ece {start} \u5f00\u59cb\u672a\u67126\u4e2a\u6708\u7684\u9884\u671f\u8425\u6536\u589e\u957f\u7387\uff08\u7b2c1\u5e74\uff09\u3002',
        'help_rg2_ttm': '\u7b2c2\u81f3\u7b2c5\u5e74\u7684\u5e74\u5747\u590d\u5408\u589e\u957f\u7387 (CAGR)\u3002',
        'help_rg1_fy': '{fy1} \u8d22\u5e74\u7684\u9884\u671f\u8425\u6536\u589e\u957f\u7387\u3002',
        'help_rg2_fy': '\u4ece FY{fy1_1} \u5230 FY{fy1_4} \u7684\u5e74\u5747\u590d\u5408\u589e\u957f\u7387 (CAGR)\u3002',
        'help_ebit_margin': '\u516c\u53f8\u5728\u8fc7\u6e21\u671f\u672b\u9884\u671f\u8fbe\u5230\u7684\u53ef\u6301\u7eed\u8425\u4e1a\u5229\u6da6\u7387\u3002',
        'help_convergence': '\u5f53\u524d\u5229\u6da6\u7387\u8fbe\u5230\u76ee\u6807\u5229\u6da6\u7387\u6240\u9700\u7684\u5e74\u6570\u3002',
        'help_tax_rate': '\u9884\u671f\u6709\u6548\u4f01\u4e1a\u7a0e\u7387\uff08\u901a\u5e38 15%-25%\uff09\u3002',
        'help_ric': '\u8d44\u672c\u6548\u7387\uff1a\u6bcf\u5355\u4f4d\u6295\u5165\u8d44\u672c\u4ea7\u751f\u7684\u8425\u6536\u3002\u8d8a\u9ad8\u8868\u660e\u8d44\u672c\u5bc6\u96c6\u5ea6\u8d8a\u4f4e\u3002',
        'help_wacc': '\u52a0\u6743\u5e73\u5747\u8d44\u672c\u6210\u672c\uff08\u8d34\u73b0\u7387\uff09\u3002\u98ce\u9669\u8d8a\u9ad8\uff0c\u8d34\u73b0\u7387\u8d8a\u9ad8\uff08\u901a\u5e38 8%-12%\uff09\u3002',
        'param_ronic_label': 'ROIC = WACC\uff08\u6c38\u7eed\u671f\uff09',
        'param_ronic_help': 'ROIC \u968f\u65f6\u95f4\u8d8b\u4e8e\u6536\u655b\u81f3 WACC\uff0c\u56e0\u4e3a\u7ade\u4e89\u4f1a\u4fb5\u8680\u8d85\u989d\u56de\u62a5\u3002'
                            '\u53ea\u6709\u5177\u6709\u5f3a\u5927\u800c\u6301\u4e45\u62a4\u57ce\u6cb3\u7684\u4f01\u4e1a\u624d\u80fd\u7ef4\u6301\u9002\u5ea6\u6ea2\u4ef7\u3002',
        'param_ronic_note': '\u2610 \u672a\u52fe\u9009 = ROIC = WACC + {prem:.0f}%\uff08\u9002\u5ea6\u8d85\u989d\u56de\u62a5\uff09 '
                            '&nbsp;|&nbsp; \u2611 \u52fe\u9009 = ROIC = WACC\uff08\u65e0\u8d85\u989d\u56de\u62a5\uff09',
        'param_modified_hint': '\u26a1 AI\uff1a{ai_val} \u2192 \u60a8\uff1a{user_val}',
        'param_n_modified': '\u26a0 {n} \u4e2a\u53c2\u6570\u5df2\u4ece AI \u5efa\u8bae\u4e2d\u4fee\u6539',
        'wacc_reference': '\U0001f4ca WACC \u8ba1\u7b97\u53c2\u8003',

        # ── Slider hint ──
        'slider_hint': '\U0001f39a\ufe0f \u62d6\u52a8\u6ed1\u5757\u8c03\u6574\u2014\u2014\u9876\u90e8\u4f30\u503c\u5b9e\u65f6\u66f4\u65b0',
        'defaults_warning_title': '\u26a0\ufe0f \u9ed8\u8ba4\u503c\u57fa\u4e8e\u5386\u53f2\u5e73\u5747\u503c\u2014\u2014\u5e76\u975e\u63a8\u8350',
        'defaults_warning_body': '\u8fd9\u4e9b\u662f\u6839\u636e\u516c\u53f8\u5386\u53f2\u8d22\u52a1\u6570\u636e\u63a8\u5bfc\u7684\u8d77\u59cb\u70b9\u3002'
                                 '\u8bf7<b>\u62d6\u52a8\u4e0a\u65b9\u6ed1\u5757</b>\u6839\u636e\u60a8\u7684\u5206\u6790\u8c03\u6574\u6bcf\u4e2a\u53c2\u6570\uff0c'
                                 '\u7136\u540e\u70b9\u51fb\u4e0b\u65b9\u7684<b>\u8fd0\u884c DCF \u4f30\u503c</b>\u3002',

        # ── Historical reference labels ──
        'hist_latest': '{label}: {val}{suffix}',
        'hist_avg': '{n}\u5e74\u5747\u503c: {val}{suffix}',
        'hist_range': '{n}\u5e74\u8303\u56f4: {min}\u2013{max}{suffix}',

        # ── AI reasoning ──
        'ai_reasoning_hint': '{engine} AI \u5206\u6790\u2014\u2014\u6bcf\u4e2a\u53c2\u6570\u7684\u63a8\u7406\u2014\u2014<b>{action}</b>',
        'ai_reasoning_expander': 'AI \u63a8\u7406\uff08\u6309\u53c2\u6570\uff09',
        'ai_hint_expand': '\u70b9\u51fb\u4e0b\u65b9\u5c55\u5f00',
        'ai_hint_collapse': '\u70b9\u51fb\u4e0b\u65b9\u6536\u8d77',
        'ai_label_rg1': '\u7b2c1\u5e74\u8425\u6536\u589e\u957f',
        'ai_label_rg2': '\u7b2c2-5\u5e74 CAGR',
        'ai_label_ebit': '\u76ee\u6807 EBIT \u5229\u6da6\u7387',
        'ai_label_conv': '\u6536\u655b\u5e74\u6570',
        'ai_label_ric1': '\u8425\u6536/\u6295\u5165\u8d44\u672c (Y1-2)',
        'ai_label_ric2': '\u8425\u6536/\u6295\u5165\u8d44\u672c (Y3-5)',
        'ai_label_ric3': '\u8425\u6536/\u6295\u5165\u8d44\u672c (Y5-10)',
        'ai_label_tax': '\u7a0e\u7387',
        'ai_label_wacc': 'WACC',
        'ai_label_ronic': 'RONIC',
        'ai_label_rg1_icon': '\U0001f4c8 \u7b2c1\u5e74\u8425\u6536\u589e\u957f',
        'ai_label_rg2_icon': '\U0001f4ca \u7b2c2-5\u5e74 CAGR',
        'ai_label_ebit_icon': '\U0001f4b0 \u76ee\u6807 EBIT \u5229\u6da6\u7387',
        'ai_label_conv_icon': '\U0001f504 \u6536\u655b\u5e74\u6570',
        'ai_label_ric1_icon': '\U0001f3ed \u8425\u6536/\u6295\u5165\u8d44\u672c (Y1-2)',
        'ai_label_ric2_icon': '\U0001f3d7\ufe0f \u8425\u6536/\u6295\u5165\u8d44\u672c (Y3-5)',
        'ai_label_ric3_icon': '\U0001f527 \u8425\u6536/\u6295\u5165\u8d44\u672c (Y5-10)',
        'ai_label_tax_icon': '\U0001f4cb \u7a0e\u7387',
        'ai_label_wacc_icon': '\u2696\ufe0f WACC',
        'ai_label_ronic_icon': '\U0001f3af RONIC',
        'ai_ronic_yes': '\u662f',
        'ai_ronic_no': '\u5426',

        # ── AI progress / streaming ──
        'ai_live_title': '\U0001f916 AI \u5206\u6790\u2014\u2014\u5b9e\u65f6\u63a8\u7406',
        'ai_analyzing': '{engine} \u5206\u6790\u4e2d\u2026 \u5df2\u7528\u65f6 {elapsed:.0f}\u79d2',
        'ai_revealing': '\u5c55\u793a\u5206\u6790\u7ed3\u679c\u2026 {idx}/{total} \u4e2a\u53c2\u6570',
        'ai_revealing_status': '\u5c55\u793a\u63a8\u7406\u2026 {idx}/{total} \u00b7 \u603b\u8ba1 {elapsed:.0f}\u79d2',
        'ai_all_done': '\u2705 \u5168\u90e8 {total} \u4e2a\u53c2\u6570\u5206\u6790\u5b8c\u6210\uff08{elapsed:.0f}\u79d2\uff09',
        'ai_complete': '\u2705 \u5206\u6790\u5b8c\u6210\uff0c\u4f7f\u7528 {engine}\uff08{elapsed:.0f}\u79d2\uff09',
        'ai_toast_complete_title': '\u2705 {label} \u5b8c\u6210',
        'ai_toast_complete_msg': '\u5206\u6790\u5b8c\u6210\uff0c\u4f7f\u7528 {engine}',
        'ai_status_label': '\u5206\u6790\u4e2d {company}',
        'ai_patience': '\u2615 \u53ef\u80fd\u9700\u89811\u20133\u5206\u949f\uff0c\u8bf7\u8010\u5fc3\u7b49\u5f85\u2026',
        'ai_elapsed': '\u23f1 \u5df2\u7528\u65f6 {elapsed:.0f}\u79d2',
        'ai_lines_received': '\u23f1 \u5df2\u7528\u65f6 {elapsed:.0f}\u79d2  \u00b7  \u5df2\u63a5\u6536 {lines} \u884c',

        # Phase labels (compact streaming)
        'phase_starting': '\u6b63\u5728\u542f\u52a8 AI \u5206\u6790\u2026',
        'phase_searching': '\u6b63\u5728\u641c\u7d22\u5e02\u573a\u6570\u636e\u548c\u5206\u6790\u5e08\u9884\u6d4b\u2026',
        'phase_parameters': '\u6b63\u5728\u5206\u6790\u4f30\u503c\u53c2\u6570\u2026',
        'phase_generating': '\u6b63\u5728\u751f\u6210\u7ed3\u6784\u5316\u8f93\u51fa\u2026',
        'phase_init_engine': '\u6b63\u5728\u521d\u59cb\u5316 {engine}\u2026',

        # Rotating wait messages
        'wait_1': '\U0001f50d \u6b63\u5728\u641c\u7d22\u6700\u65b0\u4e1a\u7ee9\u6307\u5f15\u548c\u5206\u6790\u5e08\u5171\u8bc6\u2026',
        'wait_2': '\U0001f4ca \u6b63\u5728\u5206\u6790\u8425\u6536\u589e\u957f\u8d8b\u52bf\u548c\u884c\u4e1a\u57fa\u51c6\u2026',
        'wait_3': '\U0001f4b0 \u6b63\u5728\u8bc4\u4f30 EBIT \u5229\u6da6\u7387\u6f5c\u529b\u548c\u7ecf\u8425\u6760\u6746\u2026',
        'wait_4': '\U0001f3ed \u6b63\u5728\u8bc4\u4f30\u8d44\u672c\u6548\u7387\u548c\u518d\u6295\u8d44\u9700\u6c42\u2026',
        'wait_5': '\u2696\ufe0f \u6b63\u5728\u4ea4\u53c9\u5bf9\u6bd4\u591a\u6765\u6e90 WACC \u4f30\u7b97\u2026',
        'wait_6': '\U0001f4cb \u6b63\u5728\u5ba1\u67e5\u7a0e\u52a1\u7ed3\u6784\u548c\u6709\u6548\u7a0e\u7387\u2026',
        'wait_7': '\U0001f3af \u6b63\u5728\u786e\u5b9a\u7ec8\u503c\u5047\u8bbe\u2026',
        'wait_8': '\U0001f504 \u6b63\u5728\u5c06\u6240\u6709\u6570\u636e\u7efc\u5408\u4e3a\u4f30\u503c\u53c2\u6570\u2026',

        # ── DCF table fields ──
        'dcf_base': '\u57fa\u51c6 ({ttm})',
        'dcf_base_plain': '\u57fa\u51c6',
        'dcf_terminal': '\u7ec8\u503c',
        'dcf_rev_growth': '\u8425\u6536\u589e\u957f',
        'dcf_revenue': '\u8425\u6536',
        'dcf_ebit_margin': 'EBIT \u5229\u6da6\u7387',
        'dcf_ebit': 'EBIT',
        'dcf_tax_rate': '\u7a0e\u7387',
        'dcf_ebit_1t': 'EBIT(1-t)',
        'dcf_reinvestments': '\u518d\u6295\u8d44',
        'dcf_fcff': 'FCFF',
        'dcf_wacc': 'WACC',
        'dcf_discount_factor': '\u8d34\u73b0\u56e0\u5b50',
        'dcf_pv_fcff': 'PV (FCFF)',

        # ── Breakdown items ──
        'bd_pv_fcff': 'FCFF \u73b0\u503c\uff0810\u5e74\uff09',
        'bd_pv_terminal': '\u7ec8\u503c\u73b0\u503c',
        'bd_sum_pv': '\u73b0\u503c\u6c47\u603b',
        'bd_cash': '+ \u73b0\u91d1\u53ca\u7b49\u4ef7\u7269',
        'bd_investments': '+ \u603b\u6295\u8d44',
        'bd_ev': '\u4f01\u4e1a\u4ef7\u503c',
        'bd_debt': '\u2212 \u603b\u503a\u52a1',
        'bd_minority': '\u2212 \u5c11\u6570\u80a1\u4e1c\u6743\u76ca',
        'bd_equity': '\u80a1\u6743\u4ef7\u503c',
        'bd_shares': '\u6d41\u901a\u80a1\u672c\uff08\u767e\u4e07\uff09',
        'bd_iv_per_share': '\u6bcf\u80a1\u5185\u5728\u4ef7\u503c',
        'bd_iv_per_share_cur': '\u6bcf\u80a1\u5185\u5728\u4ef7\u503c ({cur})',

        # ── Sensitivity ──
        'sens_rev_vs_ebit': '**\u8425\u6536\u589e\u957f vs EBIT \u5229\u6da6\u7387** (\u6bcf\u80a1\u4ef7\u683c, {cur})',
        'sens_ebit_axis': 'EBIT \u5229\u6da6\u7387 \u25b8',
        'sens_growth_axis': '\u589e\u957f\u7387 \u25be',
        'sens_wacc_title': '**WACC \u654f\u611f\u6027** (\u6bcf\u80a1\u4ef7\u683c, {cur})',
        'sens_wacc_label': 'WACC',
        'sens_price_share': '\u6bcf\u80a1\u4ef7\u683c',

        # ── Gap analysis ──
        'gap_hint': '\U0001f4ca DCF vs \u5e02\u573a\u4ef7\u2014\u2014\u5dee\u5f02\u5206\u6790{adj}\u2014\u2014<b>\u70b9\u51fb\u4e0b\u65b9\u5c55\u5f00</b>',
        'gap_expander': '\u5dee\u5f02\u5206\u6790\u8be6\u60c5',
        'gap_adjusted': '\u8c03\u6574\u540e\u4f30\u503c\uff1a**{val:,.2f} {cur}**',
        'gap_status_label': '\u5dee\u5f02\u5206\u6790',
        'gap_no_price': '\u65e0\u6cd5\u83b7\u53d6\u5f53\u524d\u80a1\u4ef7\u2014\u2014\u8df3\u8fc7\u5dee\u5f02\u5206\u6790\u3002',

        # ── Error / warning messages ──
        'err_fetch_failed': '\u83b7\u53d6\u8d22\u52a1\u6570\u636e\u5931\u8d25\u3002\u8bf7\u68c0\u67e5 API \u5bc6\u94a5\u548c\u80a1\u7968\u4ee3\u7801\u3002',
        'err_ai_parse': 'AI \u5206\u6790\u6210\u529f\u4f46\u53c2\u6570\u89e3\u6790\u5931\u8d25\u3002\u6a21\u578b\u53ef\u80fd\u8fd4\u56de\u4e86\u65e0\u6548\u683c\u5f0f\u3002',
        'err_ai_failed': 'AI \u5206\u6790\u5931\u8d25\uff1a{msg}',
        'err_gap_failed': '\u5dee\u5f02\u5206\u6790\u5931\u8d25\uff1a{msg}',
        'warn_ai_no_params': 'AI \u65e0\u6cd5\u751f\u6210\u53c2\u6570\u3002\u8bf7\u5207\u6362\u5230\u624b\u52a8\u8f93\u5165\u3002',
        'fetching_data': '\u6b63\u5728\u83b7\u53d6 {ticker} \u7684\u6570\u636e\u2026',
        'fetching_fin_data': '\u6b63\u5728\u83b7\u53d6 {ticker} \u7684\u8d22\u52a1\u6570\u636e\u2026',
        'calculating_dcf': '\u6b63\u5728\u8ba1\u7b97 DCF\u2026',

        # ── Footer ──
        'footer_tagline': '<b>ValuX</b> \u2014 AI \u667a\u80fd\u4ea4\u4e92\u5f0f DCF \u4f30\u503c',

        # ── Financial table row labels ──
        'fin_reported_currency': '\u62a5\u544a\u8d27\u5e01',
        'fin_sec_profitability': '\u25b8 \u76c8\u5229\u80fd\u529b',
        'fin_sec_reinvestment': '\u25b8 \u518d\u6295\u8d44',
        'fin_sec_capital': '\u25b8 \u8d44\u672c\u7ed3\u6784',
        'fin_sec_ratios': '\u25b8 \u5173\u952e\u6bd4\u7387',
        'fin_revenue': '\u8425\u6536',
        'fin_ebit': 'EBIT',
        'fin_rev_growth': '\u8425\u6536\u589e\u957f (%)',
        'fin_ebit_growth': 'EBIT \u589e\u957f (%)',
        'fin_ebit_margin': 'EBIT \u5229\u6da6\u7387 (%)',
        'fin_tax_rate': '\u7a0e\u7387 (%)',
        'fin_capex': '(+) \u8d44\u672c\u652f\u51fa',
        'fin_da': '(-) \u6298\u65e7\u4e0e\u644a\u9500',
        'fin_wc': '(+) \u0394\u8425\u8fd0\u8d44\u672c',
        'fin_total_reinv': '\u603b\u518d\u6295\u8d44',
        'fin_total_debt': '(+) \u603b\u503a\u52a1',
        'fin_total_equity': '(+) \u603b\u80a1\u672c',
        'fin_cash': '(-) \u73b0\u91d1\u53ca\u7b49\u4ef7\u7269',
        'fin_investments': '(-) \u603b\u6295\u8d44',
        'fin_invested_capital': '\u6295\u5165\u8d44\u672c',
        'fin_minority': '\u5c11\u6570\u80a1\u4e1c\u6743\u76ca',
        'fin_rev_ic': '\u8425\u6536 / IC',
        'fin_debt_assets': '\u8d44\u4ea7\u8d1f\u503a\u7387 (%)',
        'fin_cost_debt': '\u503a\u52a1\u6210\u672c (%)',
        'fin_roic': 'ROIC (%)',
        'fin_roe': 'ROE (%)',
        'fin_div_yield': '\u80a1\u606f\u7387 (%)',
        'fin_payout': '\u6d3e\u606f\u7387 (%)',
    },
}

# ── Mapping: English DataFrame index → translation key ──
_FIN_ROW_MAP = {
    'Reported Currency': 'fin_reported_currency',
    '\u25b8 Profitability': 'fin_sec_profitability',
    '\u25b8 Reinvestment': 'fin_sec_reinvestment',
    '\u25b8 Capital Structure': 'fin_sec_capital',
    '\u25b8 Key Ratios': 'fin_sec_ratios',
    'Revenue': 'fin_revenue',
    'EBIT': 'fin_ebit',
    'Revenue Growth (%)': 'fin_rev_growth',
    'EBIT Growth (%)': 'fin_ebit_growth',
    'EBIT Margin (%)': 'fin_ebit_margin',
    'Tax Rate (%)': 'fin_tax_rate',
    '(+) Capital Expenditure': 'fin_capex',
    '(-) D&A': 'fin_da',
    '(+) \u0394Working Capital': 'fin_wc',
    'Total Reinvestment': 'fin_total_reinv',
    '(+) Total Debt': 'fin_total_debt',
    '(+) Total Equity': 'fin_total_equity',
    '(-) Cash & Equivalents': 'fin_cash',
    '(-) Total Investments': 'fin_investments',
    'Invested Capital': 'fin_invested_capital',
    'Minority Interest': 'fin_minority',
    'Revenue / IC': 'fin_rev_ic',
    'Debt to Assets (%)': 'fin_debt_assets',
    'Cost of Debt (%)': 'fin_cost_debt',
    'ROIC (%)': 'fin_roic',
    'ROE (%)': 'fin_roe',
    'Dividend Yield (%)': 'fin_div_yield',
    'Payout Ratio (%)': 'fin_payout',
}


def lang():
    """Return current UI language code ('en' or 'zh')."""
    return st.session_state.get('_lang', 'en')


def t(key, **kw):
    """Translate a key, optionally formatting with keyword arguments.

    Usage:
        t('sidebar_brand_sub')             → 'AI-Powered Interactive DCF Valuation'
        t('hero_summary', g1=12.3, ...)    → formatted string
    """
    _l = lang()
    text = _STRINGS.get(_l, _STRINGS['en']).get(key)
    if text is None:
        # Fallback to English
        text = _STRINGS['en'].get(key, key)
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError):
            return text
    return text


def t_fin_row(english_label):
    """Translate a financial table row label. Returns translated label."""
    _l = lang()
    if _l == 'en':
        return english_label
    key = _FIN_ROW_MAP.get(english_label)
    if key is None:
        return english_label
    return _STRINGS['zh'].get(key, english_label)
