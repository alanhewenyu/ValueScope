# Copyright (c) 2026 Alan He. Licensed under MIT.
"""ValuX Streamlit Web App — DCF Stock Valuation."""

import io
import os
import re
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Ensure modeling paths are initialised before any excel_export usage ──
from modeling import excel_export as _excel
_excel.init_paths(os.path.dirname(os.path.abspath(__file__)))

from modeling.constants import (
    HISTORICAL_DATA_PERIODS_ANNUAL,
    TERMINAL_RISK_PREMIUM,
    TERMINAL_RONIC_PREMIUM,
)
from modeling.data import (
    fetch_company_profile,
    fetch_forex_data,
    format_summary_df,
    get_company_share_float,
    get_historical_financials,
    is_a_share,
    is_hk_stock,
    validate_ticker,
    _normalize_ticker,
)
from modeling.dcf import (
    calculate_dcf,
    calculate_wacc,
    get_risk_free_rate,
    sensitivity_analysis,
    wacc_sensitivity_analysis,
)
from modeling.ai_analyst import (
    _AI_ENGINE,
    set_ai_engine,
    _ai_engine_display_name,
    ANALYSIS_PROMPT_TEMPLATE,
    GAP_ANALYSIS_PROMPT_TEMPLATE,
    _parse_structured_parameters,
    _ENGINE_LABELS,
    _CLAUDE_MODEL_DISPLAY,
    GEMINI_MODEL,
)
import modeling.ai_analyst as _ai_mod
from modeling.excel_export import write_to_excel
from main import _build_valuation_params
import subprocess
import json
import shutil
import time

# ────────────────────────────────────────────────────────────────
# Page config & global CSS
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ValuX", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

# ── Force sidebar open: clear browser localStorage that caches collapsed state ──
import streamlit.components.v1 as _components
_components.html("""
<script>
(function() {
    Object.keys(window.parent.localStorage).forEach(function(key) {
        if (key.indexOf('stSidebarCollapsed') === 0) {
            window.parent.localStorage.removeItem(key);
        }
    });
    var sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
    if (sidebar && sidebar.getAttribute('aria-expanded') === 'false') {
        var btn = window.parent.document.querySelector('[data-testid="stSidebarCollapsedControl"] button')
                || window.parent.document.querySelector('[data-testid="collapsedControl"] button');
        if (btn) btn.click();
    }
})();
</script>
""", height=0)

st.markdown("""
<style>
/* ══════════════════════════════════════════════════════════════
   ValuX CSS — System theme–aware (light/dark)
   Uses CSS variables so colours adapt automatically.
   ══════════════════════════════════════════════════════════════ */

/* ── CSS custom properties (theme tokens) ── */
:root {
    --vx-bg:            #ffffff;
    --vx-bg-secondary:  #f6f8fa;
    --vx-sidebar-bg:    #f0f2f5;
    --vx-text:          #1f2328;
    --vx-text-secondary:#656d76;
    --vx-text-muted:    #8b949e;
    --vx-border:        #d0d7de;
    --vx-border-light:  #e8ebef;
    --vx-accent:        #0969da;
    --vx-accent-light:  rgba(9,105,218,0.08);
    --vx-table-header:  #0550ae;
    --vx-table-border:  #e8ebef;
    --vx-card-bg:       #f6f8fa;
    --vx-card-border:   #d0d7de;
    --vx-input-bg:      #ffffff;
    --vx-input-border:  #d0d7de;
    --vx-hero-neutral:  linear-gradient(135deg, #f6f8fa 0%, #eef2f7 100%);
    --vx-hero-positive: linear-gradient(135deg, #f0fdf4 0%, #e6f9ed 100%);
    --vx-hero-negative: linear-gradient(135deg, #fef2f2 0%, #fde8e8 100%);
    --vx-ai-card-bg:    #f6f8fa;
    --vx-wacc-item-bg:  #f6f8fa;
    --vx-green:         #1a7f37;
    --vx-red:           #cf222e;
    --vx-intrinsic:     #0550ae;
    --vx-market-num:    #1f2328;
    --vx-shadow:        0 4px 12px rgba(0,0,0,0.08);
}
@media (prefers-color-scheme: dark) {
    :root {
        --vx-bg:            #1a1b26;
        --vx-bg-secondary:  #161b22;
        --vx-sidebar-bg:    #12131c;
        --vx-text:          #e0e0e0;
        --vx-text-secondary:#c9d1d9;
        --vx-text-muted:    #8b949e;
        --vx-border:        #30363d;
        --vx-border-light:  #21262d;
        --vx-accent:        #58a6ff;
        --vx-accent-light:  rgba(88,166,255,0.08);
        --vx-table-header:  #7ec8e3;
        --vx-table-border:  #1a1a2e;
        --vx-card-bg:       linear-gradient(135deg, #1a1a2e, #16213e);
        --vx-card-border:   #333;
        --vx-input-bg:      #161b22;
        --vx-input-border:  #30363d;
        --vx-hero-neutral:  linear-gradient(135deg, #0d1b2a 0%, #1b2838 100%);
        --vx-hero-positive: linear-gradient(135deg, #0d1b2a 0%, #1b3d2f 100%);
        --vx-hero-negative: linear-gradient(135deg, #1b1616 0%, #3d1b1b 100%);
        --vx-ai-card-bg:    #14151f;
        --vx-wacc-item-bg:  #161b22;
        --vx-green:         #2ecc71;
        --vx-red:           #e74c3c;
        --vx-intrinsic:     #58a6ff;
        --vx-market-num:    #e0e0e0;
        --vx-shadow:        0 4px 12px rgba(0,0,0,0.4);
    }
}

/* ── Minimise Streamlit chrome ── */
section.main > div.block-container { padding-top: 0 !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; }
div[data-testid="stMainBlockContainer"] { padding-top: 0 !important; padding-left: 1.5rem !important; padding-right: 1.5rem !important; max-width: 100% !important; }
section[data-testid="stMain"] > div { padding-top: 0 !important; }
#MainMenu { display: none !important; }
div[data-testid="stDecoration"] { display: none !important; }
div[data-testid="stToolbar"] { display: none !important; }
header[data-testid="stHeader"] {
    height: 0 !important; min-height: 0 !important;
    padding: 0 !important; overflow: visible !important;
    background: transparent !important;
}
header[data-testid="stHeader"] button { visibility: visible !important; }

/* ── Sticky header ── */
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr),
div[data-testid="stVerticalBlockBorderWrapper"]:has(div.valux-sticky-hdr) {
    position: sticky !important; top: 0 !important; z-index: 999991 !important;
    background: var(--vx-bg) !important;
    border-bottom: 1px solid var(--vx-border-light);
    box-shadow: var(--vx-shadow);
    padding: 6px 0 !important;
}
div.valux-sticky-hdr { height: 0; overflow: hidden; margin: 0; padding: 0; line-height: 0; font-size: 0; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stVerticalBlock"] { gap: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stElementContainer"] { margin: 0 !important; }

/* ── Header action buttons & company name ── */
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] { align-items: center !important; min-height: 48px; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"] { display: flex !important; align-items: center !important; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"] > div { width: 100%; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stMarkdownContainer"] p { margin-bottom: 0 !important; padding: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] button,
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] a[data-testid="stDownloadButton"] button {
    height: 42px !important; padding: 2px 6px !important; font-size: 0.66rem !important;
    white-space: pre-line !important; display: flex !important; align-items: center !important;
    justify-content: center !important; text-align: center !important; line-height: 1.2 !important;
    background: var(--vx-accent-light) !important;
    border: 1px solid color-mix(in srgb, var(--vx-accent) 30%, transparent) !important;
    color: var(--vx-accent) !important;
    border-radius: 6px !important; transition: all 0.15s ease !important;
}
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] button:hover,
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] a[data-testid="stDownloadButton"] button:hover {
    background: color-mix(in srgb, var(--vx-accent) 18%, transparent) !important;
    border-color: color-mix(in srgb, var(--vx-accent) 50%, transparent) !important;
}

/* ── Global backgrounds — follow system theme ── */
section[data-testid="stSidebar"] > div { padding-top: 0 !important; }
[data-testid="stSidebarContent"] { padding-top: 0 !important; }
[data-testid="stSidebarUserContent"] { padding-top: 0 !important; }
[data-testid="stSidebarHeader"] { display: none !important; }

/* ── Sidebar labels ── */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label {
    font-size: 1.05rem !important; font-weight: 700 !important; letter-spacing: 0.3px !important;
}
section[data-testid="stSidebar"] .stCaption p,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    font-size: 0.88rem !important; font-weight: 600 !important; color: var(--vx-text-muted) !important;
}

/* ── Tooltips ── */
div[data-baseweb="tooltip"], div[data-baseweb="popover"] > div { max-width: 260px !important; white-space: normal !important; word-wrap: break-word !important; }
div[data-baseweb="tooltip"] div[role="tooltip"], div[data-baseweb="popover"] div[data-testid="stTooltipContent"] { max-width: 260px !important; white-space: normal !important; }

/* ── Ticker input ── */
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input {
    border: 1.5px solid #3a7bd5 !important; border-radius: 6px !important;
    font-size: 1rem !important; font-weight: 600 !important; padding: 8px 12px !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input:focus {
    border-color: #5b9bf7 !important; box-shadow: 0 0 0 2px rgba(91, 155, 247, 0.25) !important;
}
div[data-testid="stSidebarCollapsedControl"] { z-index: 999999 !important; }

/* ── Sidebar brand ── */
.sidebar-brand {
    text-align: center; padding: 0 0 12px 0; margin-bottom: 10px;
    border-bottom: 1px solid var(--vx-border-light); margin-top: -0.5rem;
}
.sidebar-brand h1 {
    font-size: 2.2rem; font-weight: 900; margin: 0; letter-spacing: 1px;
    background: linear-gradient(135deg, #00d2ff 0%, #7b2ff7 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.sidebar-brand .sub { font-size: 0.88rem; color: var(--vx-text-muted); margin-top: -2px; letter-spacing: 0.5px; }

/* ── Company header bar ── */
.company-header-bar { background: transparent; padding: 0; margin: 0; display: flex; align-items: center; min-height: 38px; }
.company-header-bar .company-name { font-size: 1.4rem; font-weight: 700; color: var(--vx-text); margin: 0; padding: 0 0 0 8px; line-height: 38px; }

/* ── Hide zero-height iframes ── */
iframe[height="0"] { display: none !important; }
div[data-testid="stCustomComponentV1"]:has(iframe[height="0"]) { height: 0 !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; }

/* ── Param input highlights ── */
div[data-testid="stNumberInput"].param-changed > div { border-color: #f0883e !important; background: rgba(240,136,62,0.06) !important; }
div.param-missing div[data-testid="stNumberInput"] > div { border: 1px solid #ff4b4b !important; background: rgba(255,75,75,0.05) !important; }

/* ── Section headers ── */
.section-hdr {
    font-size: 1.1rem; font-weight: 700; color: var(--vx-text);
    border-bottom: 1px solid var(--vx-border-light); padding-bottom: 6px;
    margin: 1.8rem 0 0.8rem 0; letter-spacing: 0.2px;
}

/* ── Financial data table ── */
.fin-table { width: 100%; border-collapse: collapse; font-size: 13px; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.fin-table th { text-align: right; padding: 3px 10px; color: var(--vx-table-header); font-weight: 600; border-bottom: 1px solid var(--vx-border); white-space: nowrap; }
.fin-table th:first-child { text-align: left; }
.fin-table td { text-align: right; padding: 3px 10px; border-bottom: 1px solid var(--vx-table-border); white-space: nowrap; color: var(--vx-text); }
.fin-table td:first-child { text-align: left; font-weight: 500; }
.fin-table .section-row td { font-weight: 700; color: var(--vx-table-header); padding-top: 10px; border-bottom: none; font-size: 12px; }
.fin-table .amount-row td:not(:first-child) { color: var(--vx-text); }
.fin-table .ratio-row td:not(:first-child) { color: var(--vx-text-secondary); }
.fin-table .currency-row td { color: var(--vx-text-muted); font-size: 12px; font-style: italic; }

/* ── Metric cards ── */
.metric-card {
    background: var(--vx-card-bg); border: 1px solid var(--vx-card-border);
    border-radius: 10px; padding: 16px 20px; text-align: center;
}
.metric-card .label { font-size: 0.75rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.metric-card .value { font-size: 1.6rem; font-weight: 700; color: var(--vx-text); margin: 4px 0; }
.metric-card .delta-pos { font-size: 0.85rem; color: var(--vx-green); }
.metric-card .delta-neg { font-size: 0.85rem; color: var(--vx-red); }
.metric-card .delta-na  { font-size: 0.85rem; color: var(--vx-text-muted); }

/* ── Hero card ── */
.iv-hero { border: 1px solid var(--vx-border); border-radius: 10px; padding: 12px 20px; margin: 4px 0 8px 0; transition: all 0.3s ease; }
.iv-hero.positive { background: var(--vx-hero-positive); border-color: rgba(46,204,113,0.3); }
.iv-hero.negative { background: var(--vx-hero-negative); border-color: rgba(231,76,60,0.3); }
.iv-hero.neutral  { background: var(--vx-hero-neutral); }
.iv-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.iv-block { text-align: center; }
.iv-block .lbl { font-size: 0.68rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 1px; }
.iv-block .num { font-size: 1.7rem; font-weight: 800; }
.iv-block .num.intrinsic { color: var(--vx-intrinsic); }
.iv-block .num.market { color: var(--vx-market-num); }
.iv-vs { font-size: 1.2rem; color: var(--vx-text-muted); font-weight: 300; }
.iv-mos { text-align: center; padding: 8px 18px; border-radius: 8px; min-width: 140px; }
.iv-mos .lbl { font-size: 0.68rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.iv-mos .pct { font-size: 1.5rem; font-weight: 800; }
.iv-mos.positive { background: rgba(46,204,113,0.08); border: 1px solid rgba(46,204,113,0.3); }
.iv-mos.positive .pct { color: var(--vx-green); }
.iv-mos.negative { background: rgba(231,76,60,0.08); border: 1px solid rgba(231,76,60,0.3); }
.iv-mos.negative .pct { color: var(--vx-red); }

/* ── DCF table ── */
.dcf-table { width: 100%; border-collapse: collapse; font-size: 12.5px; font-family: 'SF Mono', monospace; overflow-x: auto; }
.dcf-table th { padding: 4px 8px; color: var(--vx-table-header); border-bottom: 2px solid var(--vx-border); white-space: nowrap; font-weight: 600; text-align: right; }
.dcf-table th:first-child { text-align: left; }
.dcf-table td { padding: 3px 8px; border-bottom: 1px solid var(--vx-table-border); text-align: right; white-space: nowrap; color: var(--vx-text); }
.dcf-table td:first-child { text-align: left; color: var(--vx-text-secondary); }
.dcf-table .base-col { background: color-mix(in srgb, var(--vx-accent) 6%, transparent); }
.dcf-table .terminal-col { background: color-mix(in srgb, var(--vx-accent) 4%, transparent); }

/* ── Valuation breakdown ── */
.val-breakdown { font-size: 14px; font-family: 'SF Mono', monospace; color: var(--vx-text); }
.val-breakdown .row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--vx-table-border); }
.val-breakdown .row.highlight { font-weight: 700; color: var(--vx-green); border-top: 2px solid var(--vx-border); padding-top: 10px; font-size: 15px; }
.val-breakdown .row.subtotal { font-weight: 600; color: var(--vx-accent); }

/* ── AI card ── */
.ai-card { background: var(--vx-ai-card-bg); border: 1px solid var(--vx-border); border-radius: 8px; padding: 20px 24px; margin: 8px 0; line-height: 1.7; }
.ai-param-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; font-size: 14px; margin: 12px 0; }
.ai-param-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: var(--vx-wacc-item-bg); border-radius: 6px; border: 1px solid var(--vx-border-light); }
.ai-param-item .key { color: var(--vx-text-muted); }
.ai-param-item .val { color: var(--vx-accent); font-weight: 600; font-family: 'SF Mono', monospace; }

/* ── WACC tags ── */
.wacc-mini { display: flex; flex-wrap: wrap; gap: 8px; }
.wacc-mini .item { font-size: 13px; padding: 4px 12px; background: var(--vx-wacc-item-bg); border-radius: 4px; border: 1px solid var(--vx-border-light); }
.wacc-mini .item .k { color: var(--vx-text-muted); }
.wacc-mini .item .v { color: var(--vx-text); font-weight: 500; }

/* ── Sensitivity tables ── */
.sens-table { width: 100%; border-collapse: collapse; font-size: 13px; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; }
.sens-table th { padding: 4px 8px; color: var(--vx-text-muted); font-weight: 600; border-bottom: 2px solid var(--vx-border); text-align: right; white-space: nowrap; }
.sens-table th:first-child { text-align: right; color: var(--vx-text-muted); font-weight: 400; }
.sens-table td { padding: 4px 8px; text-align: right; border-bottom: 1px solid var(--vx-table-border); white-space: nowrap; color: var(--vx-text-secondary); }
.sens-table td:first-child { text-align: right; color: var(--vx-text-muted); font-weight: 500; }
.sens-table th.sens-hl-col { color: var(--vx-table-header); font-weight: 700; }
.sens-table td.sens-hl-row-label { color: var(--vx-table-header); font-weight: 700; }
.sens-table td.sens-hl-cross { color: var(--vx-table-header); background: color-mix(in srgb, var(--vx-accent) 6%, transparent); }
.sens-table td.sens-hl-center { color: var(--vx-green); font-weight: 800; background: color-mix(in srgb, var(--vx-green) 10%, transparent); font-size: 14px; }
.sens-table .sens-axis-label { color: var(--vx-text-muted); font-size: 11px; font-style: italic; }
.wacc-sens-table { width: 100%; border-collapse: collapse; font-size: 13px; font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace; text-align: center; }
.wacc-sens-table th { padding: 5px 6px; color: var(--vx-text-muted); font-weight: 600; border-bottom: 2px solid var(--vx-border); }
.wacc-sens-table td { padding: 5px 6px; color: var(--vx-text-secondary); border-bottom: 1px solid var(--vx-table-border); }
.wacc-sens-table th.sens-hl-col { color: var(--vx-table-header); font-weight: 700; }
.wacc-sens-table td.sens-hl-center { color: var(--vx-green); font-weight: 800; background: color-mix(in srgb, var(--vx-green) 10%, transparent); font-size: 14px; }
.wacc-sens-table td.wacc-label { color: var(--vx-text-muted); font-size: 11px; font-style: italic; text-align: left; white-space: nowrap; }

/* ── Expander hints ── */
.expander-hint {
    border-left: 3px solid var(--vx-accent); background: var(--vx-accent-light);
    border-radius: 0 6px 6px 0; padding: 8px 14px; margin: 6px 0 4px 0;
    font-size: 13px; color: var(--vx-text-secondary); cursor: pointer;
}
.expander-hint .icon { color: var(--vx-accent); margin-right: 6px; }
.expander-hint-warn {
    border-left: 3px solid #d29922; background: rgba(210,153,34,0.06);
    border-radius: 0 6px 6px 0; padding: 8px 14px; margin: 6px 0 4px 0;
    font-size: 13px; color: var(--vx-text-secondary);
}
.expander-hint-warn .icon { color: #d29922; margin-right: 6px; }

/* ── Live AI reasoning stream ── */
.ai-live-reasoning {
    border: 1px solid var(--vx-border); border-radius: 10px;
    padding: 20px 24px; margin: 8px 0 16px 0;
    background: var(--vx-ai-card-bg); line-height: 1.7;
    max-height: 600px; overflow-y: auto;
}
.ai-live-reasoning h4 { color: var(--vx-accent); margin: 0 0 12px 0; font-size: 1rem; }
.ai-live-section {
    padding: 12px 16px; margin: 8px 0; border-radius: 8px;
    border-left: 3px solid var(--vx-accent);
    background: color-mix(in srgb, var(--vx-accent) 4%, transparent);
    animation: fadeInSection 0.3s ease-out;
}
.ai-live-section .section-label {
    font-weight: 700; color: var(--vx-accent); font-size: 0.9rem;
    margin-bottom: 4px; display: flex; align-items: center; gap: 6px;
}
.ai-live-section .section-value {
    font-family: 'SF Mono', monospace; font-weight: 600; color: var(--vx-green);
    background: color-mix(in srgb, var(--vx-green) 8%, transparent);
    padding: 2px 8px; border-radius: 4px; font-size: 0.85rem; display: inline-block; margin: 4px 0;
}
.ai-live-section .section-text {
    font-size: 0.85rem; color: var(--vx-text-secondary); margin-top: 4px; line-height: 1.6;
}
.ai-live-status {
    display: flex; align-items: center; gap: 8px; padding: 8px 0;
    font-size: 0.85rem; color: var(--vx-text-muted);
}
.ai-live-status .pulse {
    width: 8px; height: 8px; border-radius: 50%; background: var(--vx-accent);
    animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 0.4; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.2); }
}
@keyframes fadeInSection {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* ── Param modified hint ── */
.param-modified-hint {
    font-size: 11px; color: #f0883e; margin-top: -8px; margin-bottom: 8px;
    padding: 2px 8px; background: rgba(240,136,62,0.06);
    border-left: 2px solid #f0883e; border-radius: 0 4px 4px 0;
}

/* ── UI polish ── */
section[data-testid="stMain"] { scrollbar-width: thin; }
div[data-testid="stAlert"] { border-radius: 8px !important; font-size: 0.95rem; }

/* Sidebar buttons */
section[data-testid="stSidebar"] button[kind="primary"] { font-weight: 600 !important; letter-spacing: 0.3px; }

/* ── Reduce vertical gap between sidebar action buttons (or divider area) ── */
section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(button) {
    margin-bottom: -6px !important;
}

/* ── Hide "press Enter to apply" hint ── */
div[data-testid="InputInstructions"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# Sidebar — ValuX brand at top, then ticker + buttons
# ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <h1>ValuX</h1>
        <div class="sub">AI-Powered DCF Valuation</div>
    </div>
    """, unsafe_allow_html=True)

    ticker_input = st.text_input(
        "Enter stock symbol below to start",
        placeholder="e.g. AAPL, 0700.HK, or 600519.SS",
        label_visibility="visible",
    )

    # ── Action buttons — add spacing above AI button, keep or divider centered ──
    if 'use_ai' not in st.session_state:
        st.session_state.use_ai = True

    st.markdown('<div style="margin-top:16px;"></div>', unsafe_allow_html=True)

    oneclick_btn = st.button("🤖 AI One-Click", type="primary", use_container_width=True,
                              help="Fully Automated: Data Fetch → AI Analysis → DCF Valuation in one click")

    st.markdown(
        '<div style="text-align:center; color:var(--vx-text-muted, #999); font-size:0.75rem; '
        'margin:-4px 0 -4px 0; padding:0; letter-spacing:1px; line-height:1;">— or —</div>',
        unsafe_allow_html=True)

    manual_btn = st.button("📝 Manual Input", use_container_width=True,
                            help="We fetch the data, you set the assumptions — full control over valuation parameters.")

    # Determine internal mode based on button clicks
    if oneclick_btn:
        st.session_state.use_ai = True
    elif manual_btn:
        st.session_state.use_ai = False

    # Detect Enter key on ticker input: if ticker changed and no button was pressed,
    # auto-trigger based on the last-used mode
    _ticker_enter = False
    if ticker_input and not oneclick_btn and not manual_btn:
        _prev_ticker = st.session_state.get('_prev_ticker_input', '')
        if ticker_input != _prev_ticker:
            _ticker_enter = True
    if ticker_input:
        st.session_state._prev_ticker_input = ticker_input

    use_ai = st.session_state.use_ai

    # ── Engine / Settings ──
    st.divider()
    if _AI_ENGINE:
        # Show engine options if AI is enabled or being used
        engine_options = ["claude", "gemini", "qwen"]
        engine_labels = {"claude": "Claude CLI", "gemini": "Gemini CLI", "qwen": "Qwen Code CLI"}
        engine_choice = st.selectbox(
            "AI Engine",
            engine_options,
            format_func=lambda e: engine_labels.get(e, e),
            index=engine_options.index(_AI_ENGINE) if _AI_ENGINE in engine_options else 0,
        )
        set_ai_engine(engine_choice)
    else:
        st.warning("No AI engine detected. Please ensure an AI CLI is installed.")

    # ── API key ──
    _fmp_env = os.environ.get("FMP_API_KEY", "")
    apikey = st.text_input(
        "Financial Modeling Prep (FMP) API Key",
        type="password",
        value=_fmp_env,
        placeholder="Enter your FMP key (Required for US stocks)",
    )
    st.caption("💡 HK & A-shares do not require an API key.")

    # ── Copyright & contact ──
    st.divider()
    st.markdown("""
    <div style="text-align:center; font-size:0.72rem; color:#555; line-height:1.7; padding:4px 0;">
        <div>© 2026 Alan He · <a href="https://opensource.org/licenses/MIT" target="_blank" style="color:#58a6ff;text-decoration:none;">MIT License</a></div>
        <div><a href="https://github.com/alanhewenyu/ValuX" target="_blank" style="color:#58a6ff;text-decoration:none;">GitHub</a>
        · <a href="mailto:alanhe@icloud.com" style="color:#58a6ff;text-decoration:none;">alanhe@icloud.com</a></div>
    </div>
    """, unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def _scroll_to(anchor_id):
    """Inject JS to smooth-scroll to an anchor element via components.html (st.markdown strips scripts)."""
    _components.html(f"""
    <script>
        // Walk up to the Streamlit main scroll container and scroll from there
        function doScroll() {{
            var el = window.parent.document.getElementById("{anchor_id}");
            if (!el) return;
            // Streamlit scroll container is section[data-testid="stMain"]
            var scroller = window.parent.document.querySelector('section[data-testid="stMain"]');
            if (scroller) {{
                var rect = el.getBoundingClientRect();
                var scrollerRect = scroller.getBoundingClientRect();
                scroller.scrollTo({{
                    top: scroller.scrollTop + rect.top - scrollerRect.top - 80,
                    behavior: "smooth"
                }});
            }} else {{
                el.scrollIntoView({{behavior: "smooth", block: "start"}});
            }}
        }}
        // Small delay to let Streamlit DOM settle after rerun
        setTimeout(doScroll, 300);
    </script>
    """, height=0)


def _compute_forex_rate_web(results, company_profile, apikey_val):
    """Compute forex rate; returns (forex_rate, info_msg)."""
    reported_currency = results.get("reported_currency", "")
    stock_currency = company_profile.get("currency", "USD")
    if not (reported_currency and stock_currency and reported_currency != stock_currency):
        return None, None
    forex_rate = None
    try:
        if apikey_val:
            forex_data = fetch_forex_data(apikey_val)
            forex_key = f"{stock_currency}/{reported_currency}"
            rate = forex_data.get(forex_key)
            if rate and rate != 0:
                forex_rate = 1.0 / rate
            else:
                reverse_key = f"{reported_currency}/{stock_currency}"
                reverse_rate = forex_data.get(reverse_key)
                if reverse_rate and reverse_rate != 0:
                    forex_rate = reverse_rate
        if forex_rate is None:
            from modeling.yfinance_data import fetch_forex_yfinance
            forex_rate = fetch_forex_yfinance(reported_currency, stock_currency)
        if forex_rate:
            msg = f"Exchange rate: 1 {reported_currency} = {forex_rate:.4f} {stock_currency}"
        else:
            msg = f"Could not fetch {reported_currency}/{stock_currency} rate."
        return forex_rate, msg
    except Exception as e:
        return None, f"Forex fetch failed: {e}"


SECTION_HEADERS = {'▸ Profitability', '▸ Reinvestment', '▸ Capital Structure', '▸ Key Ratios'}
AMOUNT_ROWS = {'Revenue', 'EBIT',
               '(+) Capital Expenditure', '(-) D&A', '(+) ΔWorking Capital', 'Total Reinvestment',
               '(+) Total Debt', '(+) Total Equity',
               '(-) Cash & Equivalents', '(-) Total Investments',
               'Invested Capital', 'Minority Interest'}
RATIO_ROWS = {'Revenue Growth (%)', 'EBIT Growth (%)', 'EBIT Margin (%)', 'Tax Rate (%)',
              'Revenue / IC', 'Debt to Assets (%)', 'Cost of Debt (%)',
              'ROIC (%)', 'ROE (%)', 'Dividend Yield (%)', 'Payout Ratio (%)'}


def _render_financial_table(summary_df):
    """Render summary_df as a styled HTML table matching the CLI aesthetic."""
    df = summary_df.copy()
    cols = list(df.columns)

    reported_currency = ''
    if 'Reported Currency' in df.index:
        rc_vals = df.loc['Reported Currency'].dropna().unique()
        rc_vals = [v for v in rc_vals if v and str(v).strip()]
        if rc_vals:
            reported_currency = str(rc_vals[0])

    html = '<div style="overflow-x:auto;"><table class="fin-table"><thead><tr>'
    html += '<th></th>'
    for c in cols:
        html += f'<th>{c}</th>'
    html += '</tr></thead><tbody>'

    if reported_currency:
        html += '<tr class="currency-row"><td>Reported Currency</td>'
        for _ in cols:
            html += f'<td>{reported_currency}</td>'
        html += '</tr>'

    for idx in df.index:
        if idx == 'Reported Currency':
            continue
        row_vals = df.loc[idx]

        if idx in SECTION_HEADERS:
            html += f'<tr class="section-row"><td colspan="{len(cols)+1}">{idx}</td></tr>'
            continue

        is_amount = idx in AMOUNT_ROWS
        is_ratio = idx in RATIO_ROWS
        row_class = 'amount-row' if is_amount else ('ratio-row' if is_ratio else '')
        html += f'<tr class="{row_class}"><td>{idx}</td>'
        for c in cols:
            raw = row_vals[c]
            if pd.isna(raw) or raw == '' or raw is None:
                html += '<td>—</td>'
            elif is_amount:
                try:
                    v = float(raw)
                    html += f'<td>{int(v):,}</td>'
                except (ValueError, TypeError):
                    html += f'<td>{raw}</td>'
            elif is_ratio:
                try:
                    v = float(raw)
                    html += f'<td>{v:.1f}</td>'
                except (ValueError, TypeError):
                    html += f'<td>{raw}</td>'
            else:
                html += f'<td>{raw}</td>'
        html += '</tr>'

    html += '</tbody></table></div>'
    return html


def _render_dcf_table(results, valuation_params):
    """Render DCF forecast table as HTML (transposed: rows=fields, cols=years)."""
    dcf = results['dcf_table'].copy()
    ttm_label = valuation_params.get('ttm_label', '')
    base_label = f'Base ({ttm_label})' if ttm_label else 'Base'
    year_labels = [base_label] + [str(i) for i in range(1, 11)] + ['Terminal']

    fields = [
        ('Revenue Growth', 'Revenue Growth Rate', 'pct'),
        ('Revenue', 'Revenue', 'amount'),
        ('EBIT Margin', 'EBIT Margin', 'pct'),
        ('EBIT', 'EBIT', 'amount'),
        ('Tax Rate', 'Tax to EBIT', 'pct'),
        ('EBIT(1-t)', 'EBIT(1-t)', 'amount'),
        ('Reinvestments', 'Reinvestments', 'amount'),
        ('FCFF', 'FCFF', 'amount'),
        ('WACC', 'WACC', 'pct'),
        ('Discount Factor', 'Discount Factor', 'factor'),
        ('PV (FCFF)', 'PV (FCFF)', 'amount'),
    ]

    html = '<div style="overflow-x:auto;"><table class="dcf-table"><thead><tr><th></th>'
    for i, lbl in enumerate(year_labels):
        cls = ' class="base-col"' if i == 0 else (' class="terminal-col"' if i == 12 else '')
        html += f'<th{cls}>{lbl}</th>'
    html += '</tr></thead><tbody>'

    for display_name, col_name, fmt in fields:
        html += f'<tr><td>{display_name}</td>'
        for i in range(len(year_labels)):
            val = dcf.iloc[i][col_name] if col_name in dcf.columns else None
            cls = ' class="base-col"' if i == 0 else (' class="terminal-col"' if i == 12 else '')
            if val is None or (isinstance(val, float) and pd.isna(val)):
                html += f'<td{cls}>—</td>'
            elif fmt == 'pct':
                html += f'<td{cls}>{val:.1%}</td>'
            elif fmt == 'amount':
                html += f'<td{cls}>{val:,.0f}</td>'
            elif fmt == 'factor':
                html += f'<td{cls}>{val:.3f}</td>'
            else:
                html += f'<td{cls}>{val}</td>'
        html += '</tr>'

    html += '</tbody></table></div>'
    return html


def _render_metric_card(label, value, delta=None):
    delta_html = ''
    if delta is not None:
        if isinstance(delta, str):
            delta_html = f'<div class="delta-na">{delta}</div>'
        elif delta >= 0:
            delta_html = f'<div class="delta-pos">+{delta:.1f}%</div>'
        else:
            delta_html = f'<div class="delta-neg">{delta:.1f}%</div>'
    return (f'<div class="metric-card">'
            f'<div class="label">{label}</div>'
            f'<div class="value">{value}</div>'
            f'{delta_html}'
            f'</div>')


def _render_ai_reasoning(params):
    if not params:
        return ''
    PARAM_LABELS = {
        'revenue_growth_1': 'Year 1 Revenue Growth',
        'revenue_growth_2': 'Years 2-5 CAGR',
        'ebit_margin': 'Target EBIT Margin',
        'convergence': 'Convergence Years',
        'revenue_invested_capital_ratio_1': 'Revenue / Invested Capital (Y1-2)',
        'revenue_invested_capital_ratio_2': 'Revenue / Invested Capital (Y3-5)',
        'revenue_invested_capital_ratio_3': 'Revenue / Invested Capital (Y5-10)',
        'tax_rate': 'Tax Rate',
        'wacc': 'WACC',
        'ronic_match_wacc': 'RONIC',
    }
    sections = []
    for key, label in PARAM_LABELS.items():
        p = params.get(key)
        if not isinstance(p, dict):
            continue
        reasoning = p.get('reasoning', '')
        if not reasoning:
            continue
        val = p.get('value', '')
        val_str = ('Yes' if val else 'No') if isinstance(val, bool) else str(val)
        sections.append(f"**{label}** → `{val_str}`\n\n{reasoning}")
    return '\n\n---\n\n'.join(sections)


def _get_ai_val(key, ss):
    if 'ai_result' not in ss:
        return None
    ai_result = ss.get('ai_result')
    if not ai_result or not ai_result.get('parameters'):
        return None
    param = ai_result['parameters'].get(key)
    if param is None:
        return None
    v = param.get('value') if isinstance(param, dict) else param
    return float(v) if v is not None else None


def _fetch_data(ticker_raw, apikey_val):
    """Fetch all data for a ticker; store in session_state. Returns True on success."""
    is_valid, error_msg = validate_ticker(ticker_raw)
    if not is_valid:
        st.error(error_msg)
        return False

    ticker = _normalize_ticker(ticker_raw)
    financial_data = get_historical_financials(ticker, 'annual', apikey_val, HISTORICAL_DATA_PERIODS_ANNUAL)
    if financial_data is None:
        st.error("Failed to fetch financial data. Check your API key and ticker symbol.")
        return False

    company_profile = fetch_company_profile(ticker, apikey_val)
    company_info = get_company_share_float(ticker, apikey_val, company_profile=company_profile)

    summary_df = financial_data['summary']
    base_year_col = summary_df.columns[0]
    base_year_data = summary_df.iloc[:, 0].copy()
    base_year_data.name = base_year_col

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
        _ttm_label = f'{base_year_col}{_ttm_quarter} TTM'
    else:
        forecast_year_1 = base_year + 1

    outstanding_shares = company_info.get('outstandingShares', 0) or 0
    base_year_data['Outstanding Shares'] = outstanding_shares
    base_year_data['Average Tax Rate'] = financial_data['average_tax_rate']
    base_year_data['Revenue Growth (%)'] = summary_df.iloc[summary_df.index.get_loc('Revenue Growth (%)'), 0]
    base_year_data['Total Reinvestment'] = summary_df.iloc[summary_df.index.get_loc('Total Reinvestment'), 0]

    wacc, total_equity_risk_premium, wacc_details = calculate_wacc(
        base_year_data, company_profile, apikey_val, verbose=False)
    risk_free_rate = get_risk_free_rate(company_profile.get('country', 'United States'))

    s = st.session_state
    s.ticker = ticker
    s.financial_data = financial_data
    s.summary_df = summary_df
    s.company_profile = company_profile
    s.company_info = company_info
    s.company_name = company_profile.get('companyName', 'N/A')
    s.base_year_data = base_year_data
    s.base_year = base_year
    s.is_ttm = _is_ttm
    s.ttm_quarter = _ttm_quarter
    s.ttm_end_date = _ttm_end_date
    s.ttm_label = _ttm_label
    s.forecast_year_1 = forecast_year_1
    s.wacc = wacc
    s.wacc_details = wacc_details
    s.total_equity_risk_premium = total_equity_risk_premium
    s.risk_free_rate = risk_free_rate
    s.average_tax_rate = financial_data['average_tax_rate']
    # Clear downstream
    for key in ('ai_result', 'results', 'sensitivity_table', 'wacc_results',
                'wacc_base', 'gap_analysis_result', 'forex_rate', 'user_params_modified'):
        s.pop(key, None)
    return True


def _build_ai_cmd(engine, prompt):
    """Build the CLI command for a given AI engine."""
    if engine == 'claude':
        return ['claude', '-p', prompt, '--output-format', 'json',
                '--allowedTools', 'WebSearch,WebFetch']
    elif engine == 'gemini':
        return ['gemini', '-p', prompt, '--output-format', 'json', '-m', GEMINI_MODEL]
    elif engine == 'qwen':
        return ['qwen', '-p', prompt]
    return None


def _build_analysis_prompt(s):
    """Build the analysis prompt from session state (mirrors analyze_company logic)."""
    company_name = s.company_profile.get('companyName', s.ticker)
    country = s.company_profile.get('country', 'United States')
    beta = s.company_profile.get('beta', 1.0)
    market_cap = s.company_profile.get('marketCap', 0)
    financial_table = s.summary_df.to_string()
    base_year = s.base_year

    ttm_quarter = s.ttm_quarter if s.is_ttm else ''
    ttm_end_date = s.ttm_end_date if s.is_ttm else ''

    if ttm_end_date and ttm_quarter:
        _end_month = int(ttm_end_date[5:7])
        _end_year = int(ttm_end_date[:4])
        forecast_year_1 = _end_year if _end_month <= 6 else _end_year + 1
    else:
        forecast_year_1 = base_year + 1

    _ttm_year_label = str(base_year + 1) if ttm_quarter else ''
    if ttm_quarter:
        _ttm_label = f'{_ttm_year_label}{ttm_quarter} TTM'
        ttm_context = f'，数据为 {_ttm_label}（截至 {ttm_end_date} 的最近十二个月）'
        ttm_base_label = f' ({_ttm_label})'
        forecast_year_guidance = (
            f'DCF 预测 Year 1 覆盖从 {ttm_end_date} 起的未来12个月（大致对应 {forecast_year_1} 日历年）。'
            f'请以 {forecast_year_1} 年作为 Year 1 的参考年份搜索业绩指引和分析师预期。'
        )
    else:
        ttm_context = ''
        ttm_base_label = ''
        forecast_year_guidance = f'Year 1 对应 {forecast_year_1} 年。'

    search_year = forecast_year_1
    search_year_2 = forecast_year_1 + 1

    return ANALYSIS_PROMPT_TEMPLATE.format(
        ticker=s.ticker,
        company_name=company_name,
        country=country,
        beta=beta,
        market_cap=f"{market_cap:,.0f}",
        calculated_wacc=f"{s.wacc:.2%}",
        calculated_tax_rate=f"{s.average_tax_rate:.2%}",
        financial_table=financial_table,
        base_year=base_year,
        forecast_year_guidance=forecast_year_guidance,
        search_year=search_year,
        search_year_2=search_year_2,
        ttm_context=ttm_context,
        ttm_base_label=ttm_base_label,
    )


def _detect_ai_phase(line):
    """Detect which phase the AI is in based on output line content."""
    lower = line.lower()
    if any(kw in lower for kw in ['search', 'websearch', 'web_search', 'fetching', 'webfetch', 'web_fetch']):
        return 'searching'
    if any(kw in lower for kw in ['revenue_growth', 'ebit_margin', 'wacc', 'ronic', 'convergence', 'tax_rate']):
        return 'parameters'
    if any(kw in lower for kw in ['```json', '"value"', '"reasoning"']):
        return 'generating'
    return None


def _run_ai_streaming(prompt, status_label="AI Analysis", live_reasoning=False):
    """Run AI CLI with streaming output, showing real-time progress.

    When live_reasoning=True (used for main analysis), uses stream-json
    for Claude to capture search progress events, then progressively
    reveals reasoning sections after the AI completes.

    When live_reasoning=False (used for gap analysis, etc.), falls back to
    the compact st.status progress indicator.

    Returns (raw_text, engine_used) or raises RuntimeError.
    """
    engine = _ai_mod._AI_ENGINE
    if engine is None:
        raise RuntimeError("No AI engine available.")

    cmd = _build_ai_cmd(engine, prompt)
    if cmd is None:
        raise RuntimeError(f"Unknown engine: {engine}")

    engine_label = _ENGINE_LABELS.get(engine, engine)
    _timeout = 600  # 10 minutes

    start_time = time.time()

    # Preserve full environment to ensure CLI auth/config works,
    # but remove CLAUDECODE to avoid nested-session detection error
    current_env = os.environ.copy()
    current_env.pop('CLAUDECODE', None)
    current_env.pop('CLAUDE_CODE', None)

    if live_reasoning:
        return _run_ai_streaming_live(cmd, engine, engine_label, prompt, status_label,
                                       _timeout, current_env, start_time)
    else:
        return _run_ai_streaming_compact(cmd, engine, engine_label, prompt, status_label,
                                          _timeout, current_env, start_time)


def _run_ai_streaming_compact(cmd, engine, engine_label, prompt, status_label,
                               _timeout, current_env, start_time):
    """Compact streaming: st.status with phase indicators. Used for gap analysis."""
    accumulated = []
    phase_icons = {
        'starting': '🚀', 'searching': '🔍',
        'parameters': '📊', 'generating': '📝',
    }
    phase_labels = {
        'starting': 'Starting AI analysis...',
        'searching': 'Searching for market data & analyst estimates...',
        'parameters': 'Analyzing valuation parameters...',
        'generating': 'Generating structured output...',
    }

    with st.status(f"🤖 {status_label} via {engine_label}", expanded=True) as status:
        current_phase = 'starting'
        st.write(f"{phase_icons['starting']} Initializing {engine_label}...")
        line_count = 0
        progress_placeholder = st.empty()
        output_placeholder = st.empty()

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, env=current_env,
            )
            for line in iter(proc.stdout.readline, ''):
                accumulated.append(line)
                line_count += 1
                elapsed = time.time() - start_time
                new_phase = _detect_ai_phase(line)
                if new_phase and new_phase != current_phase:
                    current_phase = new_phase
                    st.write(f"{phase_icons.get(current_phase, '⏳')} {phase_labels.get(current_phase, 'Processing...')}")
                progress_placeholder.caption(f"⏱ {elapsed:.0f}s elapsed  ·  {line_count} lines received")
                stripped = line.strip()
                if stripped and len(stripped) > 5:
                    if stripped.startswith('{') and '"result":' in stripped:
                        try:
                            peek = json.loads(stripped)
                            msg = peek.get('result', peek.get('error', stripped))
                            if isinstance(msg, str):
                                output_placeholder.code(msg[:120] + ('...' if len(msg) > 120 else ''), language=None)
                        except Exception:
                            output_placeholder.code(stripped[:120] + '...', language=None)
                    else:
                        output_placeholder.code(stripped[:120] + ('...' if len(stripped) > 120 else ''), language=None)

            proc.stdout.close()
            proc.wait(timeout=_timeout)
            stderr_content = proc.stderr.read() if proc.stderr else ''
            proc.stderr.close()
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(f"{engine_label} timed out after {_timeout}s")

        raw = ''.join(accumulated).strip()
        elapsed = time.time() - start_time
        if not raw:
            raise RuntimeError(f"{engine_label} {'failed: ' + stderr_content[:200] if stderr_content else 'returned empty output'}")

        text = _parse_cli_output(raw, engine, engine_label, proc.returncode, stderr_content)
        status.update(label=f"✅ {status_label} complete ({elapsed:.0f}s)", state="complete", expanded=False)
    return text, engine


def _run_ai_streaming_live(cmd, engine, engine_label, prompt, status_label,
                            _timeout, current_env, start_time):
    """Live-reasoning streaming with two phases:

    Phase 1 — While AI is running (subprocess active):
      A background thread reads subprocess stdout while the main thread
      updates the UI with rotating status messages every 2 seconds.
      This keeps the user engaged during the long search/analysis wait.

    Phase 2 — After AI completes:
      Parses the structured parameters and progressively reveals each
      reasoning section one by one with brief pauses, so users can start
      reading immediately instead of seeing everything flash and vanish.
    """
    import threading
    import queue

    # UI containers
    status_placeholder = st.empty()
    reasoning_placeholder = st.empty()

    # Rotating status messages to keep users engaged during the long wait
    _WAIT_MESSAGES = [
        '🔍 Searching for latest earnings guidance and analyst consensus...',
        '📊 Analyzing revenue growth trends and industry benchmarks...',
        '💰 Evaluating EBIT margin potential and operating leverage...',
        '🏭 Assessing capital efficiency and reinvestment requirements...',
        '⚖️ Cross-referencing WACC estimates from multiple sources...',
        '📋 Reviewing tax structure and effective rates...',
        '🎯 Determining terminal value assumptions...',
        '🔄 Synthesizing all data into valuation parameters...',
    ]

    # Shared state between reader thread and main thread
    output_queue = queue.Queue()  # Thread puts lines here, main thread drains
    reader_done = threading.Event()

    def _reader_thread(proc):
        """Background thread: reads subprocess stdout line by line."""
        try:
            for line in iter(proc.stdout.readline, ''):
                output_queue.put(line)
            proc.stdout.close()
        except Exception:
            pass
        finally:
            reader_done.set()

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=current_env,
        )

        # Start background reader
        reader = threading.Thread(target=_reader_thread, args=(proc,), daemon=True)
        reader.start()

        accumulated = []
        _phase = 'init'
        msg_idx = 0

        # Main thread: poll for output and update UI periodically
        while not reader_done.is_set() or not output_queue.empty():
            # Drain all available lines (non-blocking)
            while not output_queue.empty():
                try:
                    line = output_queue.get_nowait()
                    accumulated.append(line)
                    stripped = line.strip()
                    if stripped:
                        new_phase = _detect_ai_phase(stripped)
                        if new_phase == 'searching':
                            _phase = 'searching'
                        elif new_phase in ('parameters', 'generating'):
                            _phase = 'analyzing'
                except queue.Empty:
                    break

            elapsed = time.time() - start_time

            # Rotate messages every ~8 seconds
            msg_idx = min(int(elapsed / 8), len(_WAIT_MESSAGES) - 1)
            current_msg = _WAIT_MESSAGES[msg_idx]

            phase_icon = {'init': '🚀', 'searching': '🔍', 'analyzing': '📊'}.get(_phase, '⏳')

            reasoning_placeholder.markdown(
                '<div class="ai-live-reasoning">'
                '<h4>🤖 AI Analysis — Live Reasoning</h4>'
                f'<div style="padding:16px 0 8px 0; font-size:0.9rem; '
                f'color:var(--vx-text-secondary);">{current_msg}</div>'
                f'<div class="ai-live-status"><div class="pulse"></div> '
                f'{phase_icon} {engine_label} is analyzing... {elapsed:.0f}s elapsed</div>'
                '</div>', unsafe_allow_html=True)

            status_placeholder.markdown(
                f'<div class="ai-live-status"><div class="pulse"></div> '
                f'{phase_icon} AI analyzing... {elapsed:.0f}s elapsed</div>',
                unsafe_allow_html=True)

            # Wait before next UI update (or until reader finishes)
            reader_done.wait(timeout=2.0)

        # Wait for subprocess to fully finish
        proc.wait(timeout=_timeout)
        stderr_content = proc.stderr.read() if proc.stderr else ''
        proc.stderr.close()
        reader.join(timeout=2)

    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"{engine_label} timed out after {_timeout}s")

    raw = ''.join(accumulated).strip()
    elapsed = time.time() - start_time

    if not raw:
        raise RuntimeError(
            f"{engine_label} {'failed: ' + stderr_content[:200] if stderr_content else 'returned empty output'}")

    # --- Parse the CLI output (JSON format) ---
    text = _parse_cli_output(raw, engine, engine_label, proc.returncode, stderr_content)

    # --- Phase 2: Progressive reveal of reasoning ---
    parameters = _parse_structured_parameters(text)
    if parameters:
        _progressive_reveal_reasoning(parameters, reasoning_placeholder, status_placeholder,
                                       engine_label, elapsed)

    status_placeholder.markdown(
        f'<div class="ai-live-status" style="color: var(--vx-green);">'
        f'✅ Analysis complete via {engine_label} ({elapsed:.0f}s)</div>',
        unsafe_allow_html=True)

    return text, engine


def _progressive_reveal_reasoning(parameters, reasoning_placeholder, status_placeholder,
                                   engine_label, elapsed):
    """Progressively reveal AI reasoning sections one by one.

    After the AI finishes and we've parsed the structured parameters,
    this function reveals each reasoning section with a brief pause,
    giving users time to start reading before DCF calculation begins.
    """
    PARAM_LABELS = {
        'revenue_growth_1': '📈 Year 1 Revenue Growth',
        'revenue_growth_2': '📊 Years 2-5 CAGR',
        'ebit_margin': '💰 Target EBIT Margin',
        'convergence': '🔄 Convergence Years',
        'revenue_invested_capital_ratio_1': '🏭 Revenue / Invested Capital (Y1-2)',
        'revenue_invested_capital_ratio_2': '🏗️ Revenue / Invested Capital (Y3-5)',
        'revenue_invested_capital_ratio_3': '🔧 Revenue / Invested Capital (Y5-10)',
        'tax_rate': '📋 Tax Rate',
        'wacc': '⚖️ WACC',
        'ronic_match_wacc': '🎯 RONIC',
    }
    PARAM_ORDER = list(PARAM_LABELS.keys())

    # Collect all sections that have reasoning
    sections_to_show = []
    for key in PARAM_ORDER:
        p = parameters.get(key)
        if not isinstance(p, dict):
            continue
        reasoning = p.get('reasoning', '')
        if not reasoning:
            continue
        val = p.get('value', '')
        val_str = ('Yes' if val else 'No') if isinstance(val, bool) else str(val)
        sections_to_show.append((key, PARAM_LABELS.get(key, key), val_str, reasoning))

    if not sections_to_show:
        return

    total = len(sections_to_show)

    # Reveal sections progressively
    revealed_html_parts = []
    for idx, (key, label, val_str, reasoning) in enumerate(sections_to_show):
        # Build this section's HTML
        preview = reasoning.strip()
        if len(preview) > 500:
            preview = preview[:500] + '...'
        preview = preview.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')

        section_html = (
            f'<div class="ai-live-section">'
            f'<div class="section-label">{label}</div>'
            f'<div class="section-value">{val_str}</div>'
            f'<div class="section-text">{preview}</div>'
            f'</div>'
        )
        revealed_html_parts.append(section_html)

        # Render all revealed sections so far
        progress_frac = (idx + 1) / total
        all_html = (
            '<div class="ai-live-reasoning">'
            '<h4>🤖 AI Analysis — Live Reasoning</h4>'
            + ''.join(revealed_html_parts) +
            f'<div class="ai-live-status" style="color: var(--vx-accent);">'
            f'Revealing analysis... {idx + 1}/{total} parameters</div>'
            '</div>'
        )
        reasoning_placeholder.markdown(all_html, unsafe_allow_html=True)

        status_placeholder.markdown(
            f'<div class="ai-live-status"><div class="pulse"></div> '
            f'Revealing reasoning... {idx + 1}/{total} · {elapsed:.0f}s total</div>',
            unsafe_allow_html=True)

        # Brief pause between sections so users can read
        time.sleep(0.35)

    # Final state: all sections revealed
    final_html = (
        '<div class="ai-live-reasoning">'
        '<h4>🤖 AI Analysis — Live Reasoning</h4>'
        + ''.join(revealed_html_parts) +
        f'<div class="ai-live-status" style="color: var(--vx-green);">'
        f'✅ All {total} parameters analyzed ({elapsed:.0f}s)</div>'
        '</div>'
    )
    reasoning_placeholder.markdown(final_html, unsafe_allow_html=True)


def _parse_cli_output(raw, engine, engine_label, returncode, stderr_content):
    """Parse the CLI output from JSON-wrapped format. Returns the text content."""
    text = raw
    try:
        data = json.loads(raw)
        if engine == 'claude':
            if data.get('is_error') or data.get('type') == 'error':
                err_msg = data.get('error', '')
                res_msg = data.get('result', '')
                detail = f"{err_msg}. {res_msg}".strip('. ')
                if not detail:
                    detail = "Unknown Claude CLI internal error"
                raise RuntimeError(detail)
            text = data.get('result', raw)
            if not _ai_mod._detected_model_name and 'modelUsage' in data:
                models = data['modelUsage']
                primary = max(models, key=lambda m: models[m].get('costUSD', 0))
                _ai_mod._detected_model_name = _CLAUDE_MODEL_DISPLAY.get(primary, primary)
        elif engine == 'gemini':
            if data.get('is_error'):
                raise RuntimeError(f"Gemini CLI Error: {data.get('error', 'Unknown')}")
            text = data.get('response', raw)
            if not _ai_mod._detected_model_name and 'stats' in data:
                model_stats = data['stats'].get('models', {})
                if model_stats:
                    model_id = next(iter(model_stats))
                    pretty = model_id.replace('gemini-', 'Gemini ').replace('-', ' ').title()
                    _ai_mod._detected_model_name = pretty
    except json.JSONDecodeError:
        if returncode != 0:
            raise RuntimeError(f"{engine_label} crashed (exit {returncode}): {stderr_content[:200]}")
    return text


def _run_ai_analysis():
    """Run AI analysis with live reasoning display; store result in session_state. Returns True on success."""
    s = st.session_state
    s._ai_running = True  # Signal that AI is running (disables header buttons)
    try:
        prompt = _build_analysis_prompt(s)
        company_name = s.company_profile.get('companyName', s.ticker)

        # Use live_reasoning=True for the main analysis so users can read
        # AI reasoning progressively while waiting for the full result
        text, engine_used = _run_ai_streaming(
            prompt, status_label=f"Analyzing {company_name}", live_reasoning=True)

        parameters = _parse_structured_parameters(text)
        if parameters is None:
            st.error("AI Analysis succeeded but failed to parse parameters. The model might have returned an invalid format.")
            s._ai_running = False
            return False

        s.ai_result = {
            "parameters": parameters,
            "raw_text": text,
        }
        # Clear user-param-modified flags and old DCF results when AI re-runs
        s.pop('user_params_modified', None)
        for _k in ('results', 'sensitivity_table', 'wacc_results',
                    'wacc_base', 'valuation_params', 'gap_analysis_result'):
            s.pop(_k, None)

        # Flag: show reasoning expander as EXPANDED on first render after AI
        s._reasoning_just_completed = True
        s._ai_running = False
        return True
    except Exception as e:
        s._ai_running = False
        st.error(f"AI Analysis failed: {e}")
        return False


def _run_dcf_from_ai():
    """Build params from AI result and run DCF."""
    s = st.session_state
    params = s.ai_result['parameters']

    def _v(key):
        p = params.get(key)
        if isinstance(p, dict):
            return float(p.get('value', 0))
        return float(p) if p is not None else 0

    ronic_data = params.get('ronic_match_wacc', {})
    if isinstance(ronic_data, dict):
        ronic_match = ronic_data.get('value', True)
    elif isinstance(ronic_data, bool):
        ronic_match = ronic_data
    else:
        ronic_match = True
    ronic = s.risk_free_rate + TERMINAL_RISK_PREMIUM + (0 if ronic_match else TERMINAL_RONIC_PREMIUM)

    raw_params = {
        'revenue_growth_1': _v('revenue_growth_1'),
        'revenue_growth_2': _v('revenue_growth_2'),
        'ebit_margin': _v('ebit_margin'),
        'convergence': _v('convergence'),
        'revenue_invested_capital_ratio_1': _v('revenue_invested_capital_ratio_1'),
        'revenue_invested_capital_ratio_2': _v('revenue_invested_capital_ratio_2'),
        'revenue_invested_capital_ratio_3': _v('revenue_invested_capital_ratio_3'),
        'tax_rate': _v('tax_rate'),
        'wacc': _v('wacc'),
        'ronic': ronic,
    }
    valuation_params = _build_valuation_params(
        raw_params, s.base_year, s.risk_free_rate,
        s.is_ttm, s.ttm_quarter, s.ttm_label,
    )
    s.valuation_params = valuation_params

    results = calculate_dcf(s.base_year_data, valuation_params, s.financial_data, s.company_info, s.company_profile)
    s.results = results
    s.sensitivity_table = sensitivity_analysis(
        s.base_year_data, valuation_params, s.financial_data, s.company_info, s.company_profile)
    wacc_results, wacc_base = wacc_sensitivity_analysis(
        s.base_year_data, valuation_params, s.financial_data, s.company_info, s.company_profile)
    s.wacc_results = wacc_results
    s.wacc_base = wacc_base


def _run_gap_analysis_streaming(ticker, company_profile, results, valuation_params,
                                 summary_df, base_year, forecast_year_1, forex_rate):
    """Run gap analysis with streaming progress. Returns result dict or None."""
    company_name = company_profile.get('companyName', ticker)
    country = company_profile.get('country', 'United States')
    stock_currency = company_profile.get('currency', 'USD')
    current_price = company_profile.get('price', 0)
    dcf_price_raw = results['price_per_share']
    reported_currency = results.get('reported_currency', stock_currency)

    if current_price == 0:
        st.warning("Cannot get current stock price — skipping gap analysis.")
        return None

    currency_converted = False
    if reported_currency and reported_currency != stock_currency and forex_rate and forex_rate != 1.0:
        dcf_price = dcf_price_raw * forex_rate
        currency_converted = True
    else:
        dcf_price = dcf_price_raw

    gap_pct = (dcf_price - current_price) / current_price * 100
    gap_direction = 'DCF 估值高于市场价，市场可能低估' if gap_pct > 0 else 'DCF 估值低于市场价，市场可能高估'

    currency_note = ""
    if currency_converted:
        currency_note = (
            f"\n\n**重要：货币换算说明**\n"
            f"- 财务数据以 {reported_currency} 报告，DCF 原始估值为 {dcf_price_raw:.2f} {reported_currency}\n"
            f"- 股票以 {stock_currency} 交易，已按汇率 {forex_rate:.4f} 换算为 {dcf_price:.2f} {stock_currency}\n"
            f"- 以下所有价格比较和修正估值均以 {stock_currency} 为单位"
        )

    financial_table = summary_df.to_string()
    prompt = GAP_ANALYSIS_PROMPT_TEMPLATE.format(
        company_name=company_name, ticker=ticker, country=country,
        current_price=current_price, currency=stock_currency,
        dcf_price=dcf_price, gap_pct=gap_pct, gap_direction=gap_direction,
        revenue_growth_1=valuation_params['revenue_growth_1'],
        revenue_growth_2=valuation_params['revenue_growth_2'],
        ebit_margin=valuation_params['ebit_margin'],
        wacc=valuation_params['wacc'],
        tax_rate=valuation_params['tax_rate'],
        pv_cf=results['pv_cf_next_10_years'],
        pv_terminal=results['pv_terminal_value'],
        enterprise_value=results['enterprise_value'],
        equity_value=results['equity_value'],
        financial_table=financial_table,
        forecast_year=forecast_year_1 if forecast_year_1 else base_year + 1,
    )
    if currency_note:
        prompt += currency_note

    analysis_text, _ = _run_ai_streaming(prompt, status_label="Gap Analysis")

    # Parse adjusted price
    adjusted_price = None
    price_match = re.search(r'ADJUSTED_PRICE:\s*([\d.,]+)', analysis_text)
    if price_match:
        try:
            adjusted_price = float(price_match.group(1).replace(',', ''))
        except ValueError:
            pass

    return {
        'analysis_text': analysis_text,
        'adjusted_price': adjusted_price,
        'current_price': current_price,
        'dcf_price': dcf_price,
        'dcf_price_raw': dcf_price_raw if currency_converted else None,
        'gap_pct': gap_pct,
        'currency': stock_currency,
        'reported_currency': reported_currency if currency_converted else None,
        'forex_rate': forex_rate if currency_converted else None,
    }


# ────────────────────────────────────────────────────────────────
# Validate empty ticker on button press
# ────────────────────────────────────────────────────────────────
_did_ai_run = False
_empty_ticker_warning = False

if (oneclick_btn or manual_btn) and not ticker_input:
    _empty_ticker_warning = True

# ────────────────────────────────────────────────────────────────
# Action: Button Handlers
# ────────────────────────────────────────────────────────────────
_pending_oneclick = False

# Check if a previous AI run was interrupted (e.g. by a button click)
# and needs to resume. Data is already in session_state from the fetch.
# Only resume if we don't already have AI results (avoid re-running).
if (st.session_state.get('_ai_pending')
        and 'summary_df' in st.session_state
        and 'ai_result' not in st.session_state):
    _pending_oneclick = True

# Effective triggers: button click OR Enter key on ticker
_trigger_ai = (oneclick_btn and ticker_input) or (_ticker_enter and use_ai)
_trigger_manual = (manual_btn and ticker_input) or (_ticker_enter and not use_ai)

# One-click AI: fetch → AI → DCF
if _trigger_ai:
    st.session_state._display_mode = 'valuation'
    st.session_state._show_fin_data = False
    # Clear downstream results but keep summary_df until new fetch succeeds
    for _stale_key in ('results', 'sensitivity_table', 'wacc_results',
                        'wacc_base', 'valuation_params', 'gap_analysis_result',
                        'ai_result', 'user_params_modified'):
        st.session_state.pop(_stale_key, None)
    with st.spinner(f"Fetching data for {ticker_input}..."):
        ok = _fetch_data(ticker_input, apikey)
    if ok:
        _pending_oneclick = True
        st.session_state._ai_pending = True  # Persist across reruns

# Manual Mode: fetch only → then wait for user input
if _trigger_manual and not _trigger_ai:
    st.session_state._display_mode = 'valuation'
    st.session_state._ai_pending = False  # Cancel any pending AI
    st.session_state._show_fin_data = True  # Auto-show historical data in manual mode
    with st.spinner(f"Fetching financial data for {ticker_input}..."):
        _fetch_data(ticker_input, apikey)

# ────────────────────────────────────────────────────────────────
# Display: nothing fetched yet → welcome / warning
# ────────────────────────────────────────────────────────────────
if 'summary_df' not in st.session_state:
    if _empty_ticker_warning:
        st.warning("⚠️ Please enter a stock symbol in the sidebar first, then click a valuation button.")
    st.markdown("""
    <div style="text-align:center; padding:60px 20px; color:#666;">
        <p style="font-size:2.5rem; margin-bottom:4px;">📊</p>
        <p style="font-size:1.1rem;">Enter a stock symbol in the sidebar and click <b>🤖 AI One-Click</b> or <b>📝 Manual Input</b> to begin.</p>
        <p style="font-size:0.85rem; color:#555;">Supports US (e.g. AAPL), HK (e.g. 0700.HK), and A-shares (e.g. 600519.SS)</p>
        <p style="font-size:0.75rem; color:#444; margin-top:16px;">AI-powered DCF valuation for global stocks — HK &amp; A-shares do not require an API key.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ────────────────────────────────────────────────────────────────
# From here on, data is loaded
# ────────────────────────────────────────────────────────────────
ss = st.session_state
_has_results = 'results' in ss
_display_mode = ss.get('_display_mode', 'valuation')  # 'fetch_only' or 'valuation'

# ── Company header bar ──
_company_title = f"{ss.company_name} ({ss.ticker})"

# Build Excel data in advance if results exist (needed for download button)
_excel_buf = None
_excel_filename = None
if _has_results:
    _excel_buf = io.BytesIO()
    write_to_excel(
        _excel_buf, ss.base_year_data, ss.financial_data, ss.valuation_params,
        ss.company_profile, ss.total_equity_risk_premium,
        gap_analysis_result=ss.get('gap_analysis_result'),
        ai_result=ss.get('ai_result'),
        wacc_sensitivity=(ss.wacc_results, ss.wacc_base),
    )
    _excel_buf.seek(0)
    ai_tag = ''
    if use_ai:
        ai_tag = f"_{_ai_engine_display_name().replace(' ', '_')}"
    _excel_filename = f"{ss.company_name}_valuation_{date.today().strftime('%Y%m%d')}{ai_tag}.xlsx"

# ── Render company header bar (consistent across ALL modes) — STICKY ──
gap_btn = False
_show_fin_data = False
_btns_disabled = _pending_oneclick or ss.get('_ai_pending', False)

# ── Sticky header container ──
# We use st.container() + a hidden marker div. The CSS :has() selector
# targets the Streamlit wrapper (stVerticalBlockBorderWrapper) that contains
# our marker and makes it position:sticky. NO JS needed.
_hdr_container = st.container()

with _hdr_container:
    # Invisible marker div — CSS :has(div.valux-sticky-hdr) targets the parent
    st.markdown('<div class="valux-sticky-hdr"></div>', unsafe_allow_html=True)

    if _has_results:
        # Post-DCF: company name + Financials + Gap + Excel (both AI & Manual)
        _hcols = st.columns([3.5, 1, 1, 1])

        with _hcols[0]:
            st.markdown(
                f'<div class="company-header-bar">'
                f'<span class="company-name">{_company_title}</span></div>',
                unsafe_allow_html=True)
        with _hcols[1]:
            if st.button("📋 View Historical\nFinancial Data", use_container_width=True,
                          disabled=_btns_disabled):
                ss._show_fin_data = not ss.get('_show_fin_data', False)
            _show_fin_data = ss.get('_show_fin_data', False)
        with _hcols[2]:
            current_price = ss.company_profile.get('price', 0)
            if current_price and current_price > 0:
                gap_btn = st.button("📊 Analyze DCF\nvs Market Price", use_container_width=True,
                                     disabled=_btns_disabled)
        with _hcols[3]:
            if _excel_buf is not None:
                st.download_button(
                    label="📥 Download\nValuation Report",
                    data=_excel_buf,
                    file_name=_excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    disabled=_btns_disabled,
                )
    else:
        # Pre-DCF: company name + Financials button
        _hcols = st.columns([5, 1])
        with _hcols[0]:
            st.markdown(
                f'<div class="company-header-bar">'
                f'<span class="company-name">{_company_title}</span></div>',
                unsafe_allow_html=True)
        with _hcols[1]:
            if st.button("📋 View Historical\nFinancial Data", use_container_width=True,
                          disabled=_btns_disabled):
                ss._show_fin_data = not ss.get('_show_fin_data', False)
            _show_fin_data = ss.get('_show_fin_data', False)

# TTM info
if ss.is_ttm:
    ttm_date_str = f" (through {ss.ttm_end_date})" if ss.ttm_end_date else ''
    st.caption(f"Using {ss.ttm_label}{ttm_date_str} as base year {ss.base_year}. Forecast Year 1 = {ss.forecast_year_1}.")
else:
    st.caption(f"Base year: {ss.base_year}")
ttm_note = ss.financial_data.get('ttm_note', '')
if ttm_note:
    st.caption(f"TTM: {ttm_note}")

# ════════════════════════════════════════════════════════════════
# MODE: Fetch Only — show ONLY historical financial data
# (Skip if one-click is pending — don't display stale data)
# ════════════════════════════════════════════════════════════════
if _display_mode == 'fetch_only' and not _pending_oneclick:
    st.markdown('<div class="section-hdr">Historical Financial Data (in millions)</div>', unsafe_allow_html=True)
    st.markdown(_render_financial_table(ss.summary_df), unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════════════════════════
# MODE: Valuation — full layout
# ════════════════════════════════════════════════════════════════

# ── Execute One-Click AI + DCF (progress renders here, below header) ──
if _pending_oneclick:
    ai_ok = _run_ai_analysis()
    _did_ai_run = True
    ss._ai_pending = False  # Clear the persistent flag regardless of outcome
    if ai_ok:
        with st.spinner("Calculating DCF..."):
            _run_dcf_from_ai()
        ss._dcf_just_ran = False  # First AI run — no "updated" banner
        ss._scroll_to_results = True
        ss._save_snapshot_on_next_render = True
        st.rerun()
    else:
        st.warning("AI could not produce parameters. Please switch to Manual Input.")

# ── Handle Gap Analysis button ──
if gap_btn:
    results = ss.results
    valuation_params = ss.valuation_params
    current_price = ss.company_profile.get('price', 0)
    forex_rate, forex_msg = _compute_forex_rate_web(results, ss.company_profile, apikey)
    if forex_msg:
        st.caption(forex_msg)
    ss.forex_rate = forex_rate
    try:
        gap_result = _run_gap_analysis_streaming(
            ss.ticker, ss.company_profile, results, valuation_params,
            ss.summary_df, ss.base_year, ss.forecast_year_1, forex_rate)
        ss.gap_analysis_result = gap_result
    except Exception as e:
        st.error(f"Gap analysis failed: {e}")

# Historical data toggled by Financials header button (both AI & Manual modes)
if _show_fin_data:
    with st.expander("Historical Financial Data (in millions)", expanded=True):
        st.markdown(_render_financial_table(ss.summary_df), unsafe_allow_html=True)

# ──────────────────────────────────────────
# § 1  DCF Valuation Results — Hero Card
# ──────────────────────────────────────────
if _has_results:
    results = ss.results
    valuation_params = ss.valuation_params
    reported_currency = results.get('reported_currency', '')
    current_price = ss.company_profile.get('price', 0)

    st.markdown('<div id="dcf-results"></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-hdr">DCF Valuation Results</div>', unsafe_allow_html=True)

    dcf_price_raw = results['price_per_share']
    stock_currency = ss.company_profile.get('currency', '')
    cur_label = reported_currency or stock_currency or ''

    # ── Forex conversion: convert intrinsic value to stock trading currency ──
    _needs_forex = (reported_currency and stock_currency
                    and reported_currency != stock_currency)
    _hero_forex_rate = None
    if _needs_forex:
        # Reuse cached forex_rate if available (must be a positive number), otherwise compute
        _cached = ss.get('forex_rate')
        if _cached and isinstance(_cached, (int, float)) and _cached > 0:
            _hero_forex_rate = _cached
        else:
            _hero_forex_rate, _forex_msg = _compute_forex_rate_web(
                results, ss.company_profile, apikey)
            if _hero_forex_rate:
                ss.forex_rate = _hero_forex_rate

    if _hero_forex_rate and _needs_forex:
        dcf_price_display = dcf_price_raw * _hero_forex_rate
        iv_currency = stock_currency
    else:
        dcf_price_display = dcf_price_raw
        iv_currency = cur_label

    # Show a flash banner when DCF was just (re-)calculated — below the header
    if ss.pop('_dcf_just_ran', False):
        st.success(f"Valuation updated — Intrinsic Value per Share: **{iv_currency} {dcf_price_display:,.2f}**")

    # Intrinsic Value Hero Card
    mos_pct = None
    hero_cls = 'neutral'
    if current_price and current_price > 0:
        mos_pct = (dcf_price_display - current_price) / current_price * 100
        if mos_pct > 15:
            hero_cls = 'positive'
        elif mos_pct < -15:
            hero_cls = 'negative'

    iv_html = f'<div class="iv-hero {hero_cls}"><div class="iv-row">'
    iv_html += (f'<div class="iv-block"><div class="lbl">Intrinsic Value per Share</div>'
                f'<div class="num intrinsic">{iv_currency} {dcf_price_display:,.2f}</div></div>')
    iv_html += '<div class="iv-vs">vs</div>'
    if current_price and current_price > 0:
        iv_html += (f'<div class="iv-block"><div class="lbl">Price per Share</div>'
                    f'<div class="num market">{stock_currency} {current_price:,.2f}</div></div>')
    else:
        iv_html += '<div class="iv-block"><div class="lbl">Price per Share</div><div class="num market">—</div></div>'
    if mos_pct is not None:
        mos_cls = 'positive' if mos_pct >= 0 else 'negative'
        mos_word = 'Undervalued' if mos_pct >= 0 else 'Overvalued'
        iv_html += (f'<div class="iv-mos {mos_cls}">'
                    f'<div class="lbl">Margin of Safety</div>'
                    f'<div class="pct">{mos_pct:+.1f}%</div>'
                    f'<div style="font-size:0.7rem;color:#888;margin-top:2px;">{mos_word}</div>'
                    f'</div>')
    iv_html += '</div></div>'
    st.markdown(iv_html, unsafe_allow_html=True)
    # Forex note below hero card — rendered separately so it's always visible
    if _hero_forex_rate and _needs_forex:
        st.caption(
            f"💱 {reported_currency} {dcf_price_raw:,.2f} × {_hero_forex_rate:.4f} = {stock_currency} {dcf_price_display:,.2f}"
        )

    # EV / Equity / Per-share metric cards — compact row
    ev_html = (f'<div style="display:flex;gap:12px;margin:6px 0;">'
               f'<div class="metric-card" style="flex:1;padding:12px 16px;">'
               f'<div class="label">Enterprise Value (in millions)</div>'
               f'<div class="value" style="font-size:1.35rem;">{cur_label} {results["enterprise_value"]:,.0f}</div></div>'
               f'<div class="metric-card" style="flex:1;padding:12px 16px;">'
               f'<div class="label">Equity Value (in millions)</div>'
               f'<div class="value" style="font-size:1.35rem;">{cur_label} {results["equity_value"]:,.0f}</div></div>'
               f'<div class="metric-card" style="flex:1;padding:12px 16px;">'
               f'<div class="label">Shares Outstanding (in millions)</div>'
               f'<div class="value" style="font-size:1.35rem;">{results.get("outstanding_shares", 0) / 1e6:,.0f}</div></div>'
               f'</div>')
    st.markdown(ev_html, unsafe_allow_html=True)

# ──────────────────────────────────────────
# § 2  Valuation Parameters (between hero and details)
# ──────────────────────────────────────────
st.markdown('<div id="valuation-params"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-hdr">Valuation Parameters</div>', unsafe_allow_html=True)

# Display AI reasoning
has_ai = 'ai_result' in ss and ss.ai_result and ss.ai_result.get('parameters')
if has_ai:
    reasoning_md = _render_ai_reasoning(ss.ai_result['parameters'])
    if reasoning_md:
        # Auto-expand on first render after AI completes so users can read;
        # subsequent renders show it collapsed.
        _expand_reasoning = ss.pop('_reasoning_just_completed', False)
        _hint_action = 'click below to collapse' if _expand_reasoning else 'click below to expand'
        st.markdown(
            f'<div class="expander-hint"><span class="icon">📖</span>'
            f'AI analysis by {_ai_engine_display_name()} — reasoning for each parameter — <b>{_hint_action}</b></div>',
            unsafe_allow_html=True)
        with st.expander("AI Reasoning (per parameter)", expanded=_expand_reasoning):
            st.markdown(reasoning_md)

# Track modified params
_modified_keys = set()

def _param_input(label, ai_key, step, fmt, placeholder, col_key, help_text=None, required=True):
    """Render a number_input. Highlight if modified or missing."""
    ai_val = _get_ai_val(ai_key, ss)
    # Start capturing for the missing state
    val = ss.get(col_key)
    is_missing = required and (val is None)

    # Use a container to apply the CSS class if missing
    with st.container():
        if is_missing:
            st.markdown(f'<div class="param-missing">', unsafe_allow_html=True)

        val = st.number_input(label, value=ai_val, step=step, format=fmt, placeholder=placeholder, key=col_key, help=help_text)

        if is_missing:
            st.markdown('</div>', unsafe_allow_html=True)

    # Compare using display precision to avoid false positives from floating-point drift.
    # Extract decimal places from format string (e.g. "%.1f" → 1, "%.2f" → 2, "%.0f" → 0)
    _decimals = int(fmt.replace('%', '').replace('f', '').replace('.', '')) if '.' in fmt else 0
    _tol = 0.5 * (10 ** -_decimals)  # e.g. 0.05 for %.1f, 0.005 for %.2f
    is_modified = ai_val is not None and val is not None and abs(val - ai_val) > _tol
    if is_modified:
        _modified_keys.add(ai_key)
        st.markdown(
            f'<div class="param-modified-hint">⚡ AI: {ai_val} → You: {val}</div>',
            unsafe_allow_html=True)
    return val

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Growth & Margins**")
    revenue_growth_1 = _param_input(
        "Revenue Growth Year 1 (%)", 'revenue_growth_1', 0.5, "%.1f", "e.g. 12.0", "p_rg1",
        help_text="Projected revenue growth rate for the first forecast year (Year 1).")
    revenue_growth_2 = _param_input(
        "Revenue Growth Years 2-5 CAGR (%)", 'revenue_growth_2', 0.5, "%.1f", "e.g. 8.0", "p_rg2",
        help_text="Annual compounded average growth rate (CAGR) from Year 2 to Year 5.")
    ebit_margin = _param_input(
        "Target EBIT Margin (%)", 'ebit_margin', 0.5, "%.1f", "e.g. 25.0", "p_em",
        help_text="The sustainable operating margin the company is expected to reach by the end of the transition period.")
    convergence = _param_input(
        "Years to Target EBIT Margin", 'convergence', 1.0, "%.0f", "e.g. 5", "p_conv",
        help_text="The number of years it will take for the current margin to reach the target margin.")
    tax_rate = _param_input(
        "Tax Rate (%)", 'tax_rate', 0.5, "%.1f", f"Hist avg: {ss.average_tax_rate*100:.1f}", "p_tax",
        help_text="The expected effective corporate tax rate (typically 15%-25%).")
with col2:
    st.markdown("**Efficiency & Discount Rate**")
    rev_ic_1 = _param_input(
        "Revenue / Invested Capital (Y1-2)", 'revenue_invested_capital_ratio_1', 0.1, "%.2f", "e.g. 2.00", "p_ric1",
        help_text="Capital Efficiency: Amount of revenue generated per unit of invested capital. Higher means less capital intensive.")
    rev_ic_2 = _param_input(
        "Revenue / Invested Capital (Y3-5)", 'revenue_invested_capital_ratio_2', 0.1, "%.2f", "e.g. 2.00", "p_ric2")
    rev_ic_3 = _param_input(
        "Revenue / Invested Capital (Y5-10)", 'revenue_invested_capital_ratio_3', 0.1, "%.2f", "e.g. 1.50", "p_ric3")
    wacc_input = _param_input(
        "WACC (%)", 'wacc', 0.1, "%.1f", f"Calculated: {ss.wacc*100:.1f}", "p_wacc",
        help_text="Weighted Average Cost of Capital (Discount Rate). Higher risk warrants a higher rate (usually 8%-12%).")
    ronic_default = True
    if has_ai:
        ronic_data = ss.ai_result['parameters'].get('ronic_match_wacc', {})
        if isinstance(ronic_data, dict):
            ronic_default = ronic_data.get('value', True)
        elif isinstance(ronic_data, bool):
            ronic_default = ronic_data
    ronic_match = st.checkbox("RONIC matches terminal WACC", value=ronic_default,
                              help="Assume returns on new capital will equal the cost of capital in perpetuity.")

ronic = ss.risk_free_rate + TERMINAL_RISK_PREMIUM + (0 if ronic_match else TERMINAL_RONIC_PREMIUM)

if _modified_keys:
    n = len(_modified_keys)
    st.markdown(
        f'<div style="border-left:3px solid #f0883e;padding:6px 14px;margin:8px 0;font-size:13px;color:#f0883e;'
        f'background:rgba(240,136,62,0.06);border-radius:0 6px 6px 0;">'
        f'⚠ {n} parameter{"s" if n > 1 else ""} modified from AI suggestion</div>',
        unsafe_allow_html=True)

# WACC reference
with st.expander("📊 WACC Calculation Reference", expanded=False):
    wacc_html = '<div class="wacc-mini">'
    for lbl, val in ss.wacc_details:
        wacc_html += f'<div class="item"><span class="k">{lbl}:</span> <span class="v">{val}</span></div>'
    wacc_html += '</div>'
    st.markdown(wacc_html, unsafe_allow_html=True)

# Run / Re-run DCF button
_required_vals = [revenue_growth_1, revenue_growth_2, ebit_margin, convergence,
                  tax_rate, rev_ic_1, rev_ic_2, rev_ic_3, wacc_input]
_all_filled = all(v is not None for v in _required_vals)

# NOTE: We no longer show a pre-emptive missing-params warning here.
# The warning is shown only AFTER the user clicks Run DCF (see below).

# Track whether params changed since last DCF run using a snapshot approach:
# After each DCF run, we save a snapshot of the raw input values.
# On subsequent renders, we compare current inputs against that snapshot.
_current_raw_snapshot = (
    revenue_growth_1, revenue_growth_2, ebit_margin, convergence,
    tax_rate, rev_ic_1, rev_ic_2, rev_ic_3, wacc_input,
)
# After AI One-Click DCF, save the snapshot from the widget values (first render after rerun)
if ss.pop('_save_snapshot_on_next_render', False):
    ss._last_dcf_input_snapshot = _current_raw_snapshot
_params_changed_since_run = False
if _has_results:
    _last_snapshot = ss.get('_last_dcf_input_snapshot')
    if _last_snapshot is not None and _last_snapshot != _current_raw_snapshot:
        _params_changed_since_run = True

# Choose button style: highlight Re-run if params were modified SINCE LAST RUN
if _has_results:
    if _params_changed_since_run:
        _dcf_btn_label = "🔄 Re-run DCF (Parameters Changed)"
        _dcf_btn_type = "primary"
    else:
        _dcf_btn_label = "🔄 Re-run DCF Valuation"
        _dcf_btn_type = "secondary"
else:
    _dcf_btn_label = "▶️ Run DCF Valuation"
    _dcf_btn_type = "primary"

run_dcf = st.button(_dcf_btn_label, type=_dcf_btn_type,
                     use_container_width=True)

if run_dcf and not _all_filled:
    st.warning("Please fill in all required valuation parameters before running DCF.")

if run_dcf and _all_filled and _has_results and not _params_changed_since_run:
    st.info("Parameters unchanged — modify a parameter to re-run the valuation.")

if run_dcf and _all_filled and (not _has_results or _params_changed_since_run):
    raw_params = {
        'revenue_growth_1': revenue_growth_1,
        'revenue_growth_2': revenue_growth_2,
        'ebit_margin': ebit_margin,
        'convergence': convergence,
        'revenue_invested_capital_ratio_1': rev_ic_1,
        'revenue_invested_capital_ratio_2': rev_ic_2,
        'revenue_invested_capital_ratio_3': rev_ic_3,
        'tax_rate': tax_rate,
        'wacc': wacc_input,
        'ronic': ronic,
    }
    valuation_params = _build_valuation_params(
        raw_params, ss.base_year, ss.risk_free_rate,
        ss.is_ttm, ss.ttm_quarter, ss.ttm_label,
    )
    ss.valuation_params = valuation_params
    with st.spinner("Calculating DCF..."):
        results = calculate_dcf(
            ss.base_year_data, valuation_params, ss.financial_data, ss.company_info, ss.company_profile)
        ss.results = results
        ss.sensitivity_table = sensitivity_analysis(
            ss.base_year_data, valuation_params, ss.financial_data, ss.company_info, ss.company_profile)
        wacc_results, wacc_base = wacc_sensitivity_analysis(
            ss.base_year_data, valuation_params, ss.financial_data, ss.company_info, ss.company_profile)
        ss.wacc_results = wacc_results
        ss.wacc_base = wacc_base
    # Save snapshot of raw inputs so Re-run button knows when to dim
    ss._last_dcf_input_snapshot = _current_raw_snapshot
    # Success toast + scroll to results on next rerun
    _toast_cur = results.get('reported_currency', '') or ss.company_profile.get('currency', '')
    st.toast(f"✅ DCF Complete — Per Share: {_toast_cur} {results['price_per_share']:,.2f}", icon="✅")
    ss._dcf_just_ran = True
    ss._scroll_to_results = True
    st.rerun()


# ──────────────────────────────────────────
# § 3  Cash Flow Forecast + Breakdown + Sensitivity (after results)
# ──────────────────────────────────────────
if _has_results:
    results = ss.results
    valuation_params = ss.valuation_params
    reported_currency = results.get('reported_currency', '')
    stock_currency = ss.company_profile.get('currency', '')
    cur_label = reported_currency or stock_currency or ''
    dcf_price = results['price_per_share']

    st.markdown('<div class="section-hdr">Cash Flow Forecast (in millions)</div>', unsafe_allow_html=True)
    st.markdown(_render_dcf_table(results, valuation_params), unsafe_allow_html=True)

    st.markdown('<div class="section-hdr">Valuation Breakdown (in millions)</div>', unsafe_allow_html=True)
    breakdown_items = [
        ("PV of FCFF (10 years)", f"{results['pv_cf_next_10_years']:,.0f}", False, False),
        ("PV of Terminal Value", f"{results['pv_terminal_value']:,.0f}", False, False),
        ("Sum of Present Values", f"{results['pv_cf_next_10_years'] + results['pv_terminal_value']:,.0f}", True, False),
        ("+ Cash & Equivalents", f"{results['cash']:,.0f}", False, False),
        ("+ Total Investments", f"{results['total_investments']:,.0f}", False, False),
        ("Enterprise Value", f"{results['enterprise_value']:,.0f}", True, False),
        ("− Total Debt", f"{results['total_debt']:,.0f}", False, False),
        ("− Minority Interest", f"{results['minority_interest']:,.0f}", False, False),
        ("Equity Value", f"{results['equity_value']:,.0f}", True, False),
        (f"Intrinsic Value per Share",
         f"{cur_label} {dcf_price:,.2f}" if cur_label else f"{dcf_price:,.2f}", False, True),
    ]
    bd_html = '<div class="val-breakdown">'
    for label, val, is_sub, is_hl in breakdown_items:
        cls = 'highlight' if is_hl else ('subtotal' if is_sub else '')
        bd_html += f'<div class="row {cls}"><span>{label}</span><span>{val}</span></div>'
    bd_html += '</div>'
    st.markdown(bd_html, unsafe_allow_html=True)

    # Sensitivity Analysis
    st.markdown('<div class="section-hdr">Sensitivity Analysis</div>', unsafe_allow_html=True)

    st.markdown("**Revenue Growth vs EBIT Margin** (Price / Share)")
    _base_growth = valuation_params.get('revenue_growth_2')
    _base_margin = valuation_params.get('ebit_margin')

    # Build HTML table — terminal / Excel style with crosshair highlighting
    _stbl = ss.sensitivity_table
    _s_html = '<div style="overflow-x:auto;"><table class="sens-table">'
    # Header row: axis label + EBIT Margin column headers
    _s_html += '<tr><th class="sens-axis-label" style="border-bottom:2px solid #333;">EBIT Margin ▸<br><span style="font-style:normal;">Growth ▾</span></th>'
    for col in _stbl.columns:
        _hl = ' sens-hl-col' if col == _base_margin else ''
        _s_html += f'<th class="{_hl}">{int(col)}%</th>'
    _s_html += '</tr>'
    # Data rows
    for idx in _stbl.index:
        _s_html += '<tr>'
        # Row label
        _row_hl = ' sens-hl-row-label' if idx == _base_growth else ''
        _s_html += f'<td class="{_row_hl}">{int(idx)}%</td>'
        for col in _stbl.columns:
            val = _stbl.loc[idx, col]
            formatted = f"{val:,.0f}"
            if idx == _base_growth and col == _base_margin:
                _s_html += f'<td class="sens-hl-center">{formatted}</td>'
            elif idx == _base_growth or col == _base_margin:
                _s_html += f'<td class="sens-hl-cross">{formatted}</td>'
            else:
                _s_html += f'<td>{formatted}</td>'
        _s_html += '</tr>'
    _s_html += '</table></div>'
    st.markdown(_s_html, unsafe_allow_html=True)

    st.markdown("**WACC Sensitivity** (Price / Share)")
    _w_html = '<div style="overflow-x:auto;"><table class="wacc-sens-table">'
    # Header: WACC labels
    _w_html += '<tr><td class="wacc-label">WACC</td>'
    for w in ss.wacc_results.keys():
        _hl = ' sens-hl-col' if w == ss.wacc_base else ''
        _w_html += f'<th class="{_hl}">{w:.1f}%</th>'
    _w_html += '</tr>'
    # Values row
    _w_html += '<tr><td class="wacc-label">Price / Share</td>'
    for w, p in ss.wacc_results.items():
        if w == ss.wacc_base:
            _w_html += f'<td class="sens-hl-center">{p:,.0f}</td>'
        else:
            _w_html += f'<td>{p:,.0f}</td>'
    _w_html += '</tr>'
    _w_html += '</table></div>'
    st.markdown(_w_html, unsafe_allow_html=True)

    # Gap Analysis results
    if 'gap_analysis_result' in ss and ss.gap_analysis_result:
        st.markdown('<div class="section-hdr">DCF vs Market — Gap Analysis</div>', unsafe_allow_html=True)
        gap = ss.gap_analysis_result
        if gap.get('adjusted_price') is not None:
            adj = gap['adjusted_price']
            st.success(f"Adjusted valuation: **{adj:,.2f} {gap['currency']}**")
        display_text = re.sub(r'\n?\s*ADJUSTED_PRICE:.*$', '', gap.get('analysis_text', '')).strip()
        st.markdown('<div class="ai-card">', unsafe_allow_html=True)
        st.markdown(display_text)
        st.markdown('</div>', unsafe_allow_html=True)

# ── Auto-scroll — only after a fresh DCF run or AI run ──
if ss.get('_scroll_to_results'):
    ss._scroll_to_results = False
    _scroll_to("dcf-results")
elif _did_ai_run:
    _scroll_to("valuation-params")

# ── Footer — tagline only ──
st.markdown("""
<div style="margin-top:48px; padding:16px 0 8px 0; border-top:1px solid var(--vx-border-light, #d0d7de); text-align:center; color:var(--vx-text-muted, #8b949e); font-size:0.78rem;">
    <b>ValuX</b> — AI-Powered DCF Valuation
</div>
""", unsafe_allow_html=True)
