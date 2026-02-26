# Copyright (c) 2026 Alan He. Licensed under MIT.
"""ValuX Streamlit Web App — DCF Stock Valuation."""

import io
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Load environment variables (.env + shell profile fallback) ──
try:
    from dotenv import load_dotenv
    load_dotenv()  # loads from .env if present
except ImportError:
    pass

def _load_env_from_shell():
    """Fallback: parse export lines from user's shell profile to pick up env vars
    that weren't inherited (e.g. when Streamlit is launched from a non-login shell)."""
    for rc in (Path.home() / '.zshrc', Path.home() / '.bash_profile',
               Path.home() / '.bashrc', Path.home() / '.zshenv'):
        if rc.is_file():
            try:
                for line in rc.read_text(errors='ignore').splitlines():
                    line = line.strip()
                    if line.startswith('export ') and '=' in line:
                        kv = line[len('export '):].strip()
                        key, _, val = kv.partition('=')
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key and val and key not in os.environ:
                            os.environ[key] = val
            except Exception:
                pass

_load_env_from_shell()

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
    _fill_profile_from_financial_data,
    _calculate_beta_akshare,
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
    ANALYSIS_PROMPT_TEMPLATE_EN,
    GAP_ANALYSIS_PROMPT_TEMPLATE,
    GAP_ANALYSIS_PROMPT_TEMPLATE_EN,
    _parse_structured_parameters,
    _ENGINE_LABELS,
    _CLAUDE_MODEL_DISPLAY,
    GEMINI_MODEL,
)
import modeling.ai_analyst as _ai_mod
from modeling.excel_export import write_to_excel
from main import _build_valuation_params
from i18n import t, lang, t_fin_row
import subprocess
import json
import shutil
import time

# ────────────────────────────────────────────────────────────────
# Page config & global CSS
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ValuX", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

# ── AI availability flag (False on Streamlit Cloud where no CLI is installed) ──
_has_ai = (_AI_ENGINE is not None)

# ── Google Analytics ──
try:
    _GA_ID = os.environ.get("GA_MEASUREMENT_ID") or st.secrets.get("GA_MEASUREMENT_ID", "")
except Exception:
    _GA_ID = ""
if _GA_ID:
    import streamlit.components.v1 as _ga_components
    _ga_components.html(f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={_GA_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{_GA_ID}');
    </script>
    """, height=0)

# ── Initialize language early so all t() calls during sidebar rendering work ──
# Language is toggled via EN/CN buttons in the sidebar brand area.
# They set st.session_state._lang directly and call st.rerun().
if '_lang' not in st.session_state:
    st.session_state._lang = 'en'

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

/* ── Sticky mini hero bar (second row, below company header) ── */
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hero),
div[data-testid="stVerticalBlockBorderWrapper"]:has(div.valux-sticky-hero) {
    position: sticky !important; top: 60px !important; z-index: 999990 !important;
    background: var(--vx-bg) !important;
    border-bottom: 1px solid var(--vx-border-light);
    padding: 0 !important;
}
div.valux-sticky-hero { height: 0; overflow: hidden; margin: 0; padding: 0; line-height: 0; font-size: 0; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hero) div[data-testid="stVerticalBlock"] { gap: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hero) div[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hero) div[data-testid="stElementContainer"] { margin: 0 !important; }
.mini-hero-bar {
    display: flex; align-items: center; justify-content: flex-start; gap: 18px;
    padding: 8px 16px 6px 16px; min-height: 48px; flex-wrap: wrap; row-gap: 4px;
}
.mini-hero-bar .mh-title {
    font-size: 0.78rem; font-weight: 700; color: var(--vx-accent); text-transform: uppercase;
    letter-spacing: 0.8px; margin-right: 4px; white-space: nowrap; align-self: center;
}
.mini-hero-bar .mh-item { display: flex; align-items: baseline; gap: 6px; align-self: center; }
.mini-hero-bar .mh-label { font-size: 0.72rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.4px; }
.mini-hero-bar .mh-val { font-size: 1.2rem; font-weight: 700; line-height: 1; }
.mini-hero-bar .mh-val.intrinsic { color: var(--vx-intrinsic); }
.mini-hero-bar .mh-val.market { color: var(--vx-market-num); }
.mini-hero-bar .mh-vs { font-size: 1.0rem; color: var(--vx-text-muted); font-weight: 300; align-self: center; }
.mini-hero-bar .mh-mos { font-weight: 700; font-size: 1.0rem; padding: 3px 10px; border-radius: 5px; align-self: center; }
.mini-hero-bar .mh-mos.positive { color: #2ea043; background: rgba(46,160,67,0.1); }
.mini-hero-bar .mh-mos.negative { color: #cf222e; background: rgba(207,34,46,0.1); }
.mini-hero-bar .mh-mos-label { font-size: 0.68rem; color: var(--vx-text-muted); margin-left: 2px; align-self: center; }
.mini-hero-bar .mh-summary { font-size: 0.88rem; color: var(--vx-text-secondary); margin-left: 6px; line-height: 1.2; align-self: center; width: 100%; }
.mini-hero-bar .mh-forex { font-size: 0.65rem; color: var(--vx-text-muted); opacity: 0.7; }

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
/* Suppress Streamlit's red/primary focus accent on the wrapper divs */
section[data-testid="stSidebar"] div[data-testid="stTextInput"] > div,
section[data-testid="stSidebar"] div[data-testid="stTextInput"] [data-baseweb="base-input"],
section[data-testid="stSidebar"] div[data-testid="stTextInput"] [data-baseweb="input"] {
    border-color: transparent !important; background: transparent !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] div:focus-within {
    border-color: transparent !important; box-shadow: none !important;
}
/* Our own clean blue input style */
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input {
    border: 2px solid var(--vx-accent, #0969da) !important; border-radius: 8px !important;
    font-size: 1.05rem !important; font-weight: 600 !important; padding: 8px 12px !important;
    background: var(--vx-input-bg, #fff) !important;
    color: var(--vx-text, #1f2328) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input:focus {
    border-color: var(--vx-accent, #0969da) !important;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--vx-accent) 20%, transparent) !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input::placeholder {
    color: var(--vx-text-muted, #8b949e) !important; font-weight: 400 !important;
    font-size: 0.88rem !important;
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
/* ── Language switch buttons — styled via JS inline (see _components.html below brand) ── */

/* ── Company header bar ── */
.company-header-bar { background: transparent; padding: 0; margin: 0; display: flex; align-items: center; min-height: 38px; gap: 14px; flex-wrap: wrap; }
.company-header-bar .company-name { font-size: 1.4rem; font-weight: 700; color: var(--vx-text); margin: 0; padding: 0 0 0 8px; line-height: 38px; white-space: nowrap; }
/* Inline intrinsic value badge in sticky header */

/* ── Ensure all inputs have visible text colour ── */
input, textarea, select, [data-baseweb="input"] input, [data-baseweb="select"] div {
    color: var(--vx-text, #1f2328) !important;
}

/* ── Hide zero-height iframes ── */
iframe[height="0"] { display: none !important; }
div[data-testid="stCustomComponentV1"]:has(iframe[height="0"]) { height: 0 !important; margin: 0 !important; padding: 0 !important; overflow: hidden !important; }

/* ── Param input highlights ── */
div[data-testid="stNumberInput"].param-changed > div { border-color: #f0883e !important; background: rgba(240,136,62,0.06) !important; }
div.param-missing div[data-testid="stNumberInput"] > div { border: 1px solid #ff4b4b !important; background: rgba(255,75,75,0.05) !important; }

/* ── Section headers ── */
.section-hdr {
    font-size: 1.2rem; font-weight: 700; color: var(--vx-text);
    border-bottom: 1px solid var(--vx-border-light); padding-bottom: 6px;
    margin: 1.8rem 0 0.8rem 0; letter-spacing: 0.2px;
    position: relative; padding-left: 12px;
}
.section-hdr::before {
    content: ''; position: absolute; left: 0; top: 4px; bottom: 4px; width: 3px;
    background: linear-gradient(180deg, var(--vx-accent) 0%, color-mix(in srgb, var(--vx-accent) 40%, transparent) 100%);
    border-radius: 2px;
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
.ai-card h1 { font-size: 1.1rem !important; font-weight: 700; margin: 0 0 12px 0; }
.ai-card h2 { font-size: 1.0rem !important; font-weight: 700; margin: 16px 0 8px 0; }
.ai-card h3 { font-size: 0.95rem !important; font-weight: 600; margin: 12px 0 6px 0; }
.ai-card p, .ai-card li { font-size: 0.88rem; }
.ai-card a { color: var(--vx-accent, #3a7bd5); text-decoration: none; }
.ai-card a:hover { text-decoration: underline; }
.ai-card ul, .ai-card ol { margin: 6px 0; padding-left: 1.5em; }
.ai-card table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.85rem; }
.ai-card th, .ai-card td { border: 1px solid var(--vx-border, #d0d7de); padding: 6px 10px; text-align: left; }
.ai-card th { background: var(--vx-header-bg, #f6f8fa); font-weight: 600; }
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

/* ── Historical reference label (above slider, clearly associated) ── */
.hist-ref {
    font-size: 13px; color: var(--vx-text-muted); margin-top: 0; margin-bottom: 2px;
    padding: 2px 0 2px 2px; line-height: 1.4;
}
.hist-ref .hist-tag {
    display: inline-block; background: rgba(108,117,125,0.08); color: var(--vx-text-muted);
    border-radius: 3px; padding: 2px 8px; margin-right: 5px; font-size: 12px; letter-spacing: 0.2px;
}
@media (prefers-color-scheme: dark) {
    .hist-ref .hist-tag { background: rgba(255,255,255,0.07); }
}

/* ── Slider parameter row ── */
.slider-param-row { margin-bottom: 4px; }
.slider-param-row .stSlider { margin-top: -8px; margin-bottom: -12px; }

/* ── Larger slider labels for valuation params ── */
div[data-testid="stSlider"] label p { font-size: 0.95rem !important; font-weight: 400 !important; }
div[data-testid="stSlider"] div[data-testid="stTooltipIcon"] { font-size: 0.85rem !important; }

/* ── One-line valuation summary ── */
.val-summary-line {
    font-size: 0.92rem; color: var(--vx-text-muted); text-align: center;
    margin: 4px 0 10px 0; padding: 6px 16px; line-height: 1.5;
    border-radius: 8px; background: rgba(108,117,125,0.04);
}
@media (prefers-color-scheme: dark) {
    .val-summary-line { background: rgba(255,255,255,0.03); }
}

/* ── Slider interaction hint (prominent callout) ── */
.slider-hint {
    font-size: 13px; color: var(--vx-text-secondary); margin: 4px 0 14px 0;
    padding: 10px 16px; border-radius: 8px; line-height: 1.5;
    background: rgba(59,130,246,0.06); border: 1px solid rgba(59,130,246,0.18);
}
.slider-hint .hint-title { font-weight: 700; color: var(--vx-accent); display: block; margin-bottom: 2px; font-size: 13px; }
.slider-hint .hint-body { color: var(--vx-text-muted); font-size: 12px; }
@media (prefers-color-scheme: dark) {
    .slider-hint { background: rgba(59,130,246,0.08); border-color: rgba(59,130,246,0.25); }
}

/* ── UI polish ── */
section[data-testid="stMain"] { scrollbar-width: thin; }
div[data-testid="stAlert"] { border-radius: 8px !important; font-size: 0.95rem; }

/* ── Smooth slider thumb & track ── */
div[data-testid="stSlider"] div[role="slider"] {
    transition: box-shadow 0.15s ease !important;
}
div[data-testid="stSlider"] div[role="slider"]:hover {
    box-shadow: 0 0 0 6px color-mix(in srgb, var(--vx-accent) 18%, transparent) !important;
}

/* ── Metric cards hover lift ── */
.metric-card { transition: transform 0.15s ease, box-shadow 0.15s ease; }
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.1); }

/* ── AI card hover ── */
.ai-card { transition: box-shadow 0.2s ease; }
.ai-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }

/* ── Expander hint hover ── */
.expander-hint { transition: background 0.15s ease; cursor: pointer; }
.expander-hint:hover { background: color-mix(in srgb, var(--vx-accent) 12%, transparent); }

/* ── Sidebar action buttons — equal visual weight, distinct colours ── */
/* Manual button (secondary): solid teal/blue outline, filled on hover */
section[data-testid="stSidebar"] button[kind="secondary"] {
    font-weight: 600 !important; letter-spacing: 0.3px;
    border: 2px solid var(--vx-accent, #0969da) !important;
    color: var(--vx-accent, #0969da) !important;
    background: transparent !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background: var(--vx-accent, #0969da) !important;
    color: #fff !important;
}
/* AI button (primary): solid accent fill */
section[data-testid="stSidebar"] button[kind="primary"] {
    font-weight: 600 !important; letter-spacing: 0.3px;
    border: 2px solid var(--vx-accent, #0969da) !important;
    background: var(--vx-accent, #0969da) !important;
    color: #fff !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] button[kind="primary"]:hover {
    background: color-mix(in srgb, var(--vx-accent, #0969da) 85%, #000) !important;
    border-color: color-mix(in srgb, var(--vx-accent, #0969da) 85%, #000) !important;
}

/* ── Reduce vertical gap between sidebar action buttons (or divider area) ── */
section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(button) {
    margin-bottom: -4px !important;
}

/* ── Hide "press Enter to apply" hint ── */
div[data-testid="InputInstructions"] { display: none !important; }

/* ── Sticky AI progress toast ── */
.ai-progress-toast {
    position: fixed; bottom: 24px; right: 24px; z-index: 99999;
    background: var(--vx-bg, #fff); border: 1px solid var(--vx-border, #d0d7de);
    border-left: 4px solid var(--vx-accent, #3a7bd5);
    border-radius: 10px; padding: 12px 18px; min-width: 280px; max-width: 380px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08);
    font-size: 0.85rem; line-height: 1.4; color: var(--vx-text, #1f2328);
    animation: toast-slide-in 0.3s ease-out;
}
.ai-progress-toast.done {
    border-left-color: var(--vx-green, #1a7f37);
}
@keyframes toast-slide-in {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
}
.ai-progress-toast .toast-title {
    font-weight: 700; font-size: 0.82rem; color: var(--vx-accent, #3a7bd5);
    margin-bottom: 4px; display: flex; align-items: center; gap: 6px;
}
.ai-progress-toast.done .toast-title { color: var(--vx-green, #1a7f37); }
.ai-progress-toast .toast-msg { color: var(--vx-text-secondary, #656d76); font-size: 0.8rem; }
.ai-progress-toast .toast-elapsed { color: var(--vx-text-muted, #8b949e); font-size: 0.75rem; margin-top: 2px; }
.toast-pulse { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--vx-accent); animation: pulse 1.5s ease-in-out infinite; }
.ai-progress-toast.done .toast-pulse { display: none; }

/* ══════════════════════════════════════════════════════════════
   Mobile & Tablet Responsiveness
   ══════════════════════════════════════════════════════════════ */

/* ── Phone (≤768px) ── */
@media (max-width: 768px) {
    /* Reduce overall padding */
    section.main > div.block-container,
    div[data-testid="stMainBlockContainer"] {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }

    /* Sidebar brand smaller */
    .sidebar-brand h1 { font-size: 1.6rem; }
    .sidebar-brand .sub { font-size: 0.78rem; }

    /* Section headers smaller */
    .section-hdr { font-size: 1rem; margin: 1.2rem 0 0.6rem 0; }

    /* Mini hero bar: stack vertically */
    .mini-hero-bar {
        flex-direction: column; align-items: flex-start;
        gap: 6px; padding: 6px 10px; min-height: auto;
    }
    .mini-hero-bar .mh-val { font-size: 1.0rem; }
    .mini-hero-bar .mh-summary { font-size: 0.78rem; }
    .mini-hero-bar .mh-vs { display: none; }
    .mini-hero-bar .mh-title { font-size: 0.7rem; }
    .mini-hero-bar .mh-label { font-size: 0.65rem; }
    .mini-hero-bar .mh-mos { font-size: 0.85rem; padding: 2px 8px; }
    .mini-hero-bar .mh-mos-label { font-size: 0.6rem; }

    /* Sticky header buttons smaller */
    div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] button,
    div[data-testid="stLayoutWrapper"]:has(div.valux-sticky-hdr) div[data-testid="stHorizontalBlock"] a[data-testid="stDownloadButton"] button {
        height: 36px !important; font-size: 0.58rem !important; padding: 2px 4px !important;
    }

    /* Company name smaller */
    .company-header-bar .company-name { font-size: 1.1rem; line-height: 32px; }

    /* Financial tables: smaller text + compact padding */
    .fin-table { font-size: 11px; }
    .fin-table th, .fin-table td { padding: 2px 6px; }
    .dcf-table { font-size: 11px; }
    .dcf-table th, .dcf-table td { padding: 2px 5px; }
    .sens-table { font-size: 11px; }
    .sens-table th, .sens-table td { padding: 3px 5px; }
    .wacc-sens-table { font-size: 11px; }
    .wacc-sens-table th, .wacc-sens-table td { padding: 3px 4px; }

    /* IV hero card compact */
    .iv-row { flex-direction: column; gap: 8px; }
    .iv-block .num { font-size: 1.3rem; }
    .iv-mos .pct { font-size: 1.2rem; }

    /* Metric cards compact */
    .metric-card { padding: 10px 12px; }
    .metric-card .value { font-size: 1.3rem; }
    .metric-card .label { font-size: 0.68rem; }

    /* AI card compact */
    .ai-card { padding: 14px 16px; }
    .ai-card h1 { font-size: 1rem !important; }
    .ai-card h2 { font-size: 0.9rem !important; }
    .ai-card h3 { font-size: 0.85rem !important; }
    .ai-card p, .ai-card li { font-size: 0.82rem; }

    /* AI param grid single column on mobile */
    .ai-param-grid { grid-template-columns: 1fr; gap: 6px; }

    /* Slider labels */
    div[data-testid="stSlider"] label p { font-size: 0.85rem !important; }

    /* Historical reference tags compact */
    .hist-ref { font-size: 11px; }
    .hist-ref .hist-tag { font-size: 10px; padding: 1px 6px; margin-right: 3px; }

    /* Valuation breakdown compact */
    .val-breakdown { font-size: 12px; }
    .val-breakdown .row { padding: 4px 0; }
    .val-breakdown .row.highlight { font-size: 13px; }

    /* AI progress toast repositioned */
    .ai-progress-toast {
        bottom: 12px; right: 12px; left: 12px;
        min-width: auto; max-width: none;
        font-size: 0.78rem; padding: 10px 14px;
    }

    /* Slider touch target larger */
    div[data-testid="stSlider"] div[role="slider"] {
        width: 28px !important; height: 28px !important;
    }

    /* Slider hint compact */
    .slider-hint { padding: 8px 12px; font-size: 12px; }
    .slider-hint .hint-title { font-size: 12px; }
    .slider-hint .hint-body { font-size: 11px; }

    /* Expander hints compact */
    .expander-hint, .expander-hint-warn { padding: 6px 10px; font-size: 12px; }

    /* WACC mini tags wrap tighter */
    .wacc-mini { gap: 4px; }
    .wacc-mini .item { font-size: 11px; padding: 3px 8px; }

    /* Footer compact */
    .val-summary-line { font-size: 0.82rem; padding: 4px 10px; }

    /* AI live reasoning compact */
    .ai-live-reasoning { padding: 14px 16px; max-height: 400px; }
    .ai-live-section { padding: 8px 12px; }
    .ai-live-section .section-label { font-size: 0.82rem; }
    .ai-live-section .section-value { font-size: 0.78rem; }
    .ai-live-section .section-text { font-size: 0.78rem; }
}

/* ── Tablet (769px – 1024px) ── */
@media (min-width: 769px) and (max-width: 1024px) {
    .mini-hero-bar .mh-val { font-size: 1.1rem; }
    .mini-hero-bar .mh-summary { font-size: 0.82rem; }
    .company-header-bar .company-name { font-size: 1.2rem; }
    .section-hdr { font-size: 1.1rem; }
    .ai-param-grid { gap: 6px 16px; }
    .ai-progress-toast { min-width: 240px; max-width: 340px; }
}

/* ══════════════════════════════════════════════════════════════
   Interaction Polish — Animations & Transitions
   ══════════════════════════════════════════════════════════════ */

/* ── Smooth fade+slide for content sections ── */
@keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
.section-hdr { animation: fadeSlideIn 0.3s ease-out; }
div[data-testid="stPlotlyChart"] { animation: fadeSlideIn 0.4s ease-out; }
.sens-table, .wacc-sens-table { animation: fadeSlideIn 0.3s ease-out; }
.val-breakdown { animation: fadeSlideIn 0.3s ease-out; }

/* ── Slider active state (while dragging) ── */
div[data-testid="stSlider"] div[role="slider"]:active {
    box-shadow: 0 0 0 10px color-mix(in srgb, var(--vx-accent) 12%, transparent) !important;
    transform: scale(1.1);
}
/* Slider track glow while adjusting */
div[data-testid="stSlider"]:focus-within {
    background: color-mix(in srgb, var(--vx-accent) 3%, transparent);
    border-radius: 8px;
    transition: background 0.2s ease;
}

/* ── Table row hover effects ── */
.fin-table tbody tr:hover td { background: color-mix(in srgb, var(--vx-accent) 4%, transparent); }
.dcf-table tbody tr:hover td { background: color-mix(in srgb, var(--vx-accent) 4%, transparent); }
.sens-table tbody tr:hover td { background: color-mix(in srgb, var(--vx-accent) 3%, transparent); }
.val-breakdown .row:hover { background: color-mix(in srgb, var(--vx-accent) 3%, transparent); border-radius: 4px; }

/* ── Skeleton loading animation ── */
@keyframes skeletonPulse {
    0%, 100% { opacity: 0.4; }
    50% { opacity: 0.8; }
}
.skeleton-block {
    background: var(--vx-bg-secondary, #f6f8fa);
    border-radius: 8px;
    animation: skeletonPulse 1.5s ease-in-out infinite;
}
</style>
""", unsafe_allow_html=True)

# ── JS: Reposition SIDEBAR-ONLY tooltips to the right of the sidebar ──
# Main-area tooltips (valuation parameter ? icons) are left in their default
# Streamlit position.  Only tooltips triggered from inside the sidebar are
# moved to the right of the sidebar, vertically aligned with their trigger.
import streamlit.components.v1 as _stc
_stc.html("""
<script>
(function() {
    var doc = window.parent.document;
    var win = window.parent;
    if (doc._vxTooltipObserver) return;

    // Track the last-hovered tooltip icon AND whether it's inside the sidebar
    doc._vxLastHoverIcon = null;
    doc._vxLastHoverInSidebar = false;
    doc.addEventListener('mouseover', function(e) {
        var icon = e.target.closest('[data-testid="stTooltipIcon"]');
        if (icon) {
            doc._vxLastHoverIcon = icon;
            doc._vxLastHoverInSidebar = !!icon.closest('section[data-testid="stSidebar"]');
        }
    }, true);

    function repositionTooltip(tt) {
        // Only reposition tooltips triggered from the sidebar
        if (!doc._vxLastHoverInSidebar) return;

        win.requestAnimationFrame(function() {
            win.requestAnimationFrame(function() {
                var sidebar = doc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar) return;
                var sidebarRight = sidebar.getBoundingClientRect().right;
                var cs = win.getComputedStyle(tt);
                if (!cs.transform || cs.transform === 'none') return;
                var m = cs.transform.match(/matrix\\([^,]+,\\s*[^,]+,\\s*[^,]+,\\s*[^,]+,\\s*([\\d.\\-]+),\\s*([\\d.\\-]+)\\)/);
                if (!m) return;

                var newX = sidebarRight + 12;
                var newY = parseFloat(m[2]);

                // Vertically align with the trigger icon
                var icon = doc._vxLastHoverIcon;
                if (icon) {
                    var iconRect = icon.getBoundingClientRect();
                    var ttHeight = tt.offsetHeight || 40;
                    newY = iconRect.top + iconRect.height / 2 - ttHeight / 2;
                    if (newY < 8) newY = 8;
                    if (newY + ttHeight > win.innerHeight - 8) newY = win.innerHeight - ttHeight - 8;
                }

                tt.style.transform = 'matrix(1, 0, 0, 1, ' + newX + ', ' + newY + ')';
            });
        });
    }
    var observer = new MutationObserver(function(mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var added = mutations[i].addedNodes;
            for (var j = 0; j < added.length; j++) {
                var node = added[j];
                if (node.nodeType !== 1) continue;
                var tt = (node.dataset && node.dataset.baseweb === 'tooltip') ? node
                       : (node.querySelector ? node.querySelector('[data-baseweb="tooltip"]') : null);
                if (tt) repositionTooltip(tt);
            }
        }
    });
    observer.observe(doc.body, { childList: true, subtree: true });
    doc._vxTooltipObserver = observer;
})();
</script>
""", height=0)

# ────────────────────────────────────────────────────────────────
# Sidebar — ValuX brand at top, then ticker + buttons
# ────────────────────────────────────────────────────────────────
with st.sidebar:
    _cur = lang()  # 'en' or 'zh'
    st.markdown(f"""
    <div class="sidebar-brand">
        <h1>ValuX</h1>
        <div class="sub">{t('sidebar_brand_sub_web') if not _has_ai else t('sidebar_brand_sub')}</div>
    </div>
    """, unsafe_allow_html=True)
    # ── Language switch: two tiny buttons styled as text ──
    _lc1, _lc2 = st.columns(2)
    with _lc1:
        if st.button("EN", key="_lang_en_btn", use_container_width=True,
                      type="primary" if _cur == 'en' else "secondary"):
            st.session_state._lang = 'en'
            st.rerun()
    with _lc2:
        if st.button("CN", key="_lang_cn_btn", use_container_width=True,
                      type="primary" if _cur == 'zh' else "secondary"):
            st.session_state._lang = 'zh'
            st.rerun()
    # Style EN/CN buttons as minimal inline text via JS (Streamlit emotion CSS is too specific for pure CSS overrides)
    _components.html("""<script>
    (function(){
        var doc = window.parent.document;
        var DIVIDER_ID = '_lang_divider';
        function styleLangBtns() {
            var sidebar = doc.querySelector('[data-testid="stSidebar"]');
            if (!sidebar) return;
            var row = sidebar.querySelector('[data-testid="stHorizontalBlock"]');
            if (!row) return;
            row.style.cssText = 'gap:0!important;margin-top:-8px!important;margin-bottom:-8px!important;justify-content:center!important;align-items:center!important;';
            var cols = row.querySelectorAll('[data-testid="stColumn"]');
            for (var i = 0; i < cols.length; i++)
                cols[i].style.cssText = 'width:auto!important;flex:0 0 auto!important;';
            var btns = row.querySelectorAll('button');
            for (var j = 0; j < btns.length; j++) {
                var b = btns[j], isPri = b.getAttribute('data-testid') === 'stBaseButton-primary';
                b.style.cssText = 'padding:1px 8px!important;min-height:0!important;height:auto!important;line-height:1.3!important;font-size:0.75rem!important;letter-spacing:1px!important;border:none!important;background:transparent!important;box-shadow:none!important;border-radius:3px!important;width:auto!important;color:' + (isPri ? '#2563eb' : '#999') + '!important;font-weight:' + (isPri ? '700' : '400') + '!important;';
            }
            /* Insert a thin vertical line divider between the two columns */
            if (!doc.getElementById(DIVIDER_ID) && cols.length >= 2) {
                var sep = doc.createElement('span');
                sep.id = DIVIDER_ID;
                sep.style.cssText = 'display:inline-block;width:1px;height:12px;background:#bbb;flex:0 0 auto;margin:0 2px;align-self:center;border-radius:0.5px;opacity:0.6;';
                row.insertBefore(sep, cols[1]);
            }
        }
        styleLangBtns();
        new MutationObserver(function(){
            styleLangBtns();
        }).observe(
            doc.querySelector('[data-testid="stSidebar"]') || doc.body,
            {childList: true, subtree: true}
        );
    })();
    </script>""", height=0)

    ticker_input = st.text_input(
        t('sidebar_ticker_label_web') if not _has_ai else t('sidebar_ticker_label'),
        placeholder=t('sidebar_ticker_placeholder_web') if not _has_ai else t('sidebar_ticker_placeholder'),
        label_visibility="visible",
    )

    # ── Action buttons ──
    if 'use_ai' not in st.session_state:
        st.session_state.use_ai = bool(_AI_ENGINE)

    if _has_ai:
        # Local version: show Manual + AI buttons
        st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
        manual_btn = st.button(t('sidebar_manual_btn'), use_container_width=True,
                                help=t('sidebar_manual_help'), key='manual_btn',
                                type="secondary")
    else:
        # Web version: explicit Go button (Enter detection kept as bonus)
        st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
        manual_btn = st.button(t('sidebar_go_btn'), use_container_width=True,
                                key='go_btn', type="primary")

    if _has_ai:
        st.markdown(
            '<div style="display:flex; align-items:center; justify-content:center; gap:8px; '
            'margin:2px 0; padding:0;">'
            '<div style="width:24px; height:1px; background:var(--vx-border, #d0d7de);"></div>'
            f'<span style="color:var(--vx-text-muted, #999); font-size:0.7rem; letter-spacing:0.5px;">{t("sidebar_or")}</span>'
            '<div style="width:24px; height:1px; background:var(--vx-border, #d0d7de);"></div>'
            '</div>',
            unsafe_allow_html=True)

        oneclick_btn = st.button(t('sidebar_oneclick_btn'), type="primary", use_container_width=True,
                                  help=t('sidebar_oneclick_help'), key='oneclick_btn')
    else:
        oneclick_btn = False

    # Determine internal mode based on button clicks
    if oneclick_btn:
        st.session_state.use_ai = True
    elif manual_btn:
        st.session_state.use_ai = False

    # Detect Enter key on ticker input
    _ticker_enter = False
    _show_mode_prompt = False
    if ticker_input and not oneclick_btn and not manual_btn:
        _prev_ticker = st.session_state.get('_prev_ticker_input', '')
        if ticker_input != _prev_ticker:
            if _has_ai:
                _show_mode_prompt = True   # Local: prompt user to pick a mode
            else:
                _ticker_enter = True       # Web: Enter triggers manual valuation
    if ticker_input:
        st.session_state._prev_ticker_input = ticker_input

    # Show mode-selection prompt (local only — web auto-triggers on Enter)
    if _show_mode_prompt and _has_ai:
        st.markdown(
            '<div style="text-align:center; padding:8px 12px; margin:4px 0; '
            'border-radius:8px; background:color-mix(in srgb, var(--vx-accent) 10%, transparent); '
            'border:1px solid color-mix(in srgb, var(--vx-accent) 25%, transparent); '
            'font-size:0.82rem; color:var(--vx-accent, #0969da); line-height:1.4;">'
            f'{t("sidebar_mode_prompt")}'
            '</div>',
            unsafe_allow_html=True)
        # Brief scale-pulse on both buttons to draw attention
        _stc.html("""<script>
        (function(){
            var sidebar = window.parent.document.querySelector('section[data-testid="stSidebar"]');
            if (!sidebar) return;
            var btns = sidebar.querySelectorAll('button');
            btns.forEach(function(b){
                b.style.transition = 'transform 0.15s ease';
                b.style.transform = 'scale(1.03)';
                setTimeout(function(){ b.style.transform = 'scale(1)'; }, 400);
            });
        })();
        </script>""", height=0)

    use_ai = st.session_state.use_ai

    # ── Engine / Settings (only shown when AI CLI is available, i.e. local) ──
    if _AI_ENGINE:
        st.markdown('<hr style="margin:4px 0; border:none; border-top:1px solid var(--vx-border, #d0d7de);">', unsafe_allow_html=True)
        # Show engine options if AI is enabled or being used
        engine_options = ["claude", "gemini", "qwen"]
        engine_labels = {"claude": "Claude CLI", "gemini": "Gemini CLI", "qwen": "Qwen Code CLI"}
        engine_choice = st.selectbox(
            t('sidebar_ai_engine'),
            engine_options,
            format_func=lambda e: engine_labels.get(e, e),
            index=engine_options.index(_AI_ENGINE) if _AI_ENGINE in engine_options else 0,
        )
        try:
            set_ai_engine(engine_choice)
        except RuntimeError:
            _install_cmds = {
                'claude': '`npm install -g @anthropic-ai/claude-code`',
                'gemini': '`npm install -g @google/gemini-cli`',
                'qwen':   '`npm install -g @qwen-code/qwen-code@latest`',
            }
            _auth_notes = {
                'claude': 'Then run `claude` in terminal to sign in.',
                'gemini': 'Then run `gemini` in terminal to sign in with Google.',
                'qwen':   ('Then run `qwen` in terminal → type `/auth` to sign in '
                           '(free: 1,000 req/day).\n\n'
                           'For headless mode (used by this app), you need an API key:\n'
                           '- Get one from [Alibaba Cloud ModelStudio]'
                           '(https://bailian.console.alibabacloud.com/)\n'
                           '- Set `DASHSCOPE_API_KEY` in your environment or `~/.qwen/settings.json`'),
            }
            st.warning(
                f"**{engine_labels[engine_choice]}** is not installed.\n\n"
                f"**Install:** {_install_cmds.get(engine_choice, '')}\n\n"
                f"{_auth_notes.get(engine_choice, '')}"
            )
            # Revert to the previously working (auto-detected) engine
            engine_choice = _AI_ENGINE

        # AI Analysis Speed options
        # NOTE: Streamlit resets radio widget state when *any* of label, help,
        # or format_func output changes between reruns.  To keep the selection
        # stable across language switches we use a collapsed fixed-string label,
        # constant-output format_func, and render the translated label + tooltip
        # via a separate st.markdown.
        if engine_choice == 'claude':
            _speed_options = ['quality', 'balanced']
            _speed_fmt = {'quality': 'Quality (Opus)', 'balanced': 'Balanced (Sonnet)'}
            _state_key = '_claude_speed'
            _cur_speed = st.session_state.get(_state_key, 'quality')
            _speed_idx = _speed_options.index(_cur_speed) if _cur_speed in _speed_options else 0
            st.markdown(f"<p style='font-size:0.875rem;margin:0 0 -12px;'>{t('sidebar_ai_speed')} "
                        f"<span title='{t('sidebar_speed_help_claude')}' "
                        f"style='cursor:help;opacity:0.5;'>ⓘ</span></p>",
                        unsafe_allow_html=True)
            _speed = st.radio(
                'AI Analysis Speed',
                _speed_options,
                index=_speed_idx,
                format_func=lambda s, _f=_speed_fmt: _f[s],
                horizontal=True,
                label_visibility='collapsed',
                key='_claude_speed_radio',
            )
            st.session_state[_state_key] = _speed
        elif engine_choice == 'qwen':
            _speed_options = ['quality', 'fast']
            _speed_fmt = {'quality': '🔍 Quality (+ Web)', 'fast': '⚡ Fast (data only)'}
            _state_key = '_qwen_speed'
            _cur_speed = st.session_state.get(_state_key, 'fast')
            _speed_idx = _speed_options.index(_cur_speed) if _cur_speed in _speed_options else 1
            st.markdown(f"<p style='font-size:0.875rem;margin:0 0 -12px;'>{t('sidebar_ai_speed')} "
                        f"<span title='{t('sidebar_speed_help_qwen')}' "
                        f"style='cursor:help;opacity:0.5;'>ⓘ</span></p>",
                        unsafe_allow_html=True)
            _speed = st.radio(
                'AI Analysis Speed',
                _speed_options,
                index=_speed_idx,
                format_func=lambda s, _f=_speed_fmt: _f[s],
                horizontal=True,
                label_visibility='collapsed',
                key='_qwen_speed_radio',
            )
            st.session_state[_state_key] = _speed
    # ── Language is now controlled by EN|CN buttons in brand area (query params) ──

    # ── API key ──
    _fmp_env = os.environ.get("FMP_API_KEY", "")
    if not _has_ai and _fmp_env:
        # Web with pre-filled key: collapse into expander to declutter sidebar
        with st.expander(t('sidebar_fmp_expander'), expanded=False):
            apikey = st.text_input(
                t('sidebar_fmp_label'),
                type="password",
                value=_fmp_env,
                placeholder=t('sidebar_fmp_placeholder'),
            )
            st.caption(t('sidebar_fmp_hint'))
    else:
        # Local or no pre-filled key: show normally
        apikey = st.text_input(
            t('sidebar_fmp_label'),
            type="password",
            value=_fmp_env,
            placeholder=t('sidebar_fmp_placeholder'),
        )
        st.caption(t('sidebar_fmp_hint'))

    # ── Copyright & contact ──
    st.markdown('<hr style="margin:4px 0; border:none; border-top:1px solid var(--vx-border, #d0d7de);">', unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align:center; font-size:0.72rem; color:#555; line-height:1.7; padding:4px 0;">
        <div>© 2026 Alan He · <a href="https://opensource.org/licenses/MIT" target="_blank" style="color:#58a6ff;text-decoration:none;">MIT License</a></div>
        <div><a href="https://jianshan.co" target="_blank" style="color:#58a6ff;text-decoration:none;">见山笔记</a>
        · <a href="https://github.com/alanhewenyu/ValuX" target="_blank" style="color:#58a6ff;text-decoration:none;">GitHub</a>
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
                    top: scroller.scrollTop + rect.top - scrollerRect.top - 120,
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
            from modeling.data import _is_cloud_mode
            if not _is_cloud_mode():
                from modeling.yfinance_data import fetch_forex_yfinance
                forex_rate = fetch_forex_yfinance(reported_currency, stock_currency)
        if forex_rate is None:
            from modeling.data import fetch_forex_akshare
            forex_rate = fetch_forex_akshare(reported_currency, stock_currency)
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
        html += f'<tr class="currency-row"><td>{t_fin_row("Reported Currency")}</td>'
        for _ in cols:
            html += f'<td>{reported_currency}</td>'
        html += '</tr>'

    for idx in df.index:
        if idx == 'Reported Currency':
            continue
        row_vals = df.loc[idx]

        if idx in SECTION_HEADERS:
            html += f'<tr class="section-row"><td colspan="{len(cols)+1}">{t_fin_row(idx)}</td></tr>'
            continue

        is_amount = idx in AMOUNT_ROWS
        is_ratio = idx in RATIO_ROWS
        row_class = 'amount-row' if is_amount else ('ratio-row' if is_ratio else '')
        html += f'<tr class="{row_class}"><td>{t_fin_row(idx)}</td>'
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
    base_label = t('dcf_base', ttm=ttm_label) if ttm_label else t('dcf_base_plain')
    year_labels = [base_label] + [str(i) for i in range(1, 11)] + [t('dcf_terminal')]

    fields = [
        (t('dcf_rev_growth'), 'Revenue Growth Rate', 'pct'),
        (t('dcf_revenue'), 'Revenue', 'amount'),
        (t('dcf_ebit_margin'), 'EBIT Margin', 'pct'),
        (t('dcf_ebit'), 'EBIT', 'amount'),
        (t('dcf_tax_rate'), 'Tax to EBIT', 'pct'),
        (t('dcf_ebit_1t'), 'EBIT(1-t)', 'amount'),
        (t('dcf_reinvestments'), 'Reinvestments', 'amount'),
        (t('dcf_fcff'), 'FCFF', 'amount'),
        (t('dcf_wacc'), 'WACC', 'pct'),
        (t('dcf_discount_factor'), 'Discount Factor', 'factor'),
        (t('dcf_pv_fcff'), 'PV (FCFF)', 'amount'),
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
        'revenue_growth_1': 'ai_label_rg1',
        'revenue_growth_2': 'ai_label_rg2',
        'ebit_margin': 'ai_label_ebit',
        'convergence': 'ai_label_conv',
        'revenue_invested_capital_ratio_1': 'ai_label_ric1',
        'revenue_invested_capital_ratio_2': 'ai_label_ric2',
        'revenue_invested_capital_ratio_3': 'ai_label_ric3',
        'tax_rate': 'ai_label_tax',
        'wacc': 'ai_label_wacc',
        'ronic_match_wacc': 'ai_label_ronic',
    }
    sections = []
    for key, label_key in PARAM_LABELS.items():
        p = params.get(key)
        if not isinstance(p, dict):
            continue
        reasoning = p.get('reasoning', '')
        if not reasoning:
            continue
        val = p.get('value', '')
        val_str = (t('ai_ronic_yes') if val else t('ai_ronic_no')) if isinstance(val, bool) else str(val)
        sections.append(f"**{t(label_key)}** → `{val_str}`\n\n{reasoning}")
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

    # Fetch financial data and company profile in parallel
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as _pool:
        _f_data = _pool.submit(get_historical_financials, ticker, 'annual', apikey_val, HISTORICAL_DATA_PERIODS_ANNUAL)
        _f_prof = _pool.submit(fetch_company_profile, ticker, apikey_val)
        financial_data = _f_data.result()
        try:
            company_profile = _f_prof.result()
        except Exception:
            company_profile = {'companyName': ticker, 'marketCap': 0, 'beta': 1.0,
                               'country': 'US', 'currency': 'USD', 'exchange': '',
                               'price': 0, 'outstandingShares': 0}

    if financial_data is None:
        if is_hk_stock(ticker):
            st.error(t('err_fetch_failed_hk'))
        elif is_a_share(ticker):
            st.error(t('err_fetch_failed_a'))
        else:
            st.error(t('err_fetch_failed'))
        return False

    company_profile = _fill_profile_from_financial_data(company_profile, financial_data)

    # Beta: calculate AFTER parallel fetch to avoid concurrent connection contention.
    # Only for local Streamlit + A-shares; Cloud uses CHINA_DEFAULT_BETA (Sina blocked).
    if is_a_share(ticker) and company_profile.get('beta', 0) <= 1.0:
        from modeling.data import _is_cloud_mode
        if not _is_cloud_mode():
            company_profile['beta'] = _calculate_beta_akshare(ticker)
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

    # Pre-fetch forex rate once (used by WACC, display, sensitivity, etc.)
    _pre_forex, _pre_forex_msg = _compute_forex_rate_web(
        {'reported_currency': base_year_data.get('Reported Currency', '')},
        company_profile, apikey_val)

    wacc, total_equity_risk_premium, wacc_details = calculate_wacc(
        base_year_data, company_profile, apikey_val, verbose=False,
        forex_rate=_pre_forex)
    risk_free_rate = get_risk_free_rate(company_profile.get('country', 'United States'))

    s = st.session_state
    s.forex_rate = _pre_forex   # cache for display/sensitivity/hero bar
    s.ticker = ticker
    # Language is manually controlled via the sidebar toggle; no auto-detection.
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
    # Clear downstream (results + slider widget keys so new defaults apply)
    for key in ('ai_result', 'results', 'sensitivity_table', 'wacc_results',
                'wacc_base', 'gap_analysis_result', 'forex_rate', 'user_params_modified',
                '_last_dcf_input_snapshot',
                'p_rg1', 'p_rg2', 'p_em', 'p_conv', 'p_tax',
                'p_ric1', 'p_ric2', 'p_ric3', 'p_wacc'):
        s.pop(key, None)
    return True


def _build_ai_cmd(engine, prompt):
    """Build the CLI command for a given AI engine."""
    if engine == 'claude':
        _speed = st.session_state.get('_claude_speed', 'quality')
        cmd = ['claude', '-p', prompt, '--output-format', 'json']
        if _speed == 'balanced':
            # Balanced: Sonnet with web search
            cmd += ['--model', 'sonnet', '--allowedTools', 'WebSearch,WebFetch']
        else:
            # Quality: Opus (default model) with web search
            cmd += ['--allowedTools', 'WebSearch,WebFetch']
        return cmd
    elif engine == 'gemini':
        return ['gemini', '-p', prompt, '--output-format', 'json', '-m', GEMINI_MODEL]
    elif engine == 'qwen':
        _qspeed = st.session_state.get('_qwen_speed', 'fast')
        cmd = ['qwen', '-p', prompt, '--output-format', 'json']
        if _qspeed == 'quality':
            # Quality: enable Tavily web search for research
            _tavily_key = os.environ.get('TAVILY_API_KEY', '')
            if _tavily_key:
                cmd += ['--tavily-api-key', _tavily_key]
        # Fast: data only (no web search)
        return cmd
    return None


def _build_analysis_prompt(s):
    """Build the analysis prompt from session state (mirrors analyze_company logic)."""
    company_name = s.company_profile.get('companyName', s.ticker)
    country = s.company_profile.get('country', 'United States')
    beta = s.company_profile.get('beta', 1.0)
    market_cap = s.company_profile.get('marketCap', 0)
    financial_table = s.summary_df.to_string()
    base_year = s.base_year
    _lang = s.get('_lang', 'en')

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
        if _lang == 'zh':
            ttm_context = f'，数据为 {_ttm_label}（截至 {ttm_end_date} 的最近十二个月）'
            forecast_year_guidance = (
                f'DCF 预测 Year 1 覆盖从 {ttm_end_date} 起的未来12个月（大致对应 {forecast_year_1} 日历年）。'
                f'请以 {forecast_year_1} 年作为 Year 1 的参考年份搜索业绩指引和分析师预期。'
            )
        else:
            ttm_context = f', data is {_ttm_label} (trailing twelve months ending {ttm_end_date})'
            forecast_year_guidance = (
                f'DCF Year 1 covers the next 12 months from {ttm_end_date} (roughly corresponding to calendar year {forecast_year_1}). '
                f'Use {forecast_year_1} as the reference year when searching for earnings guidance and analyst estimates.'
            )
        ttm_base_label = f' ({_ttm_label})'
    else:
        ttm_context = ''
        ttm_base_label = ''
        if _lang == 'zh':
            forecast_year_guidance = f'Year 1 对应 {forecast_year_1} 年。'
        else:
            forecast_year_guidance = f'Year 1 corresponds to fiscal year {forecast_year_1}.'

    search_year = forecast_year_1
    search_year_2 = forecast_year_1 + 1

    _template = ANALYSIS_PROMPT_TEMPLATE if _lang == 'zh' else ANALYSIS_PROMPT_TEMPLATE_EN
    return _template.format(
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


def _render_progress_toast(placeholder, title, msg, elapsed, done=False):
    """Render a fixed-position toast showing AI progress status."""
    cls = 'ai-progress-toast done' if done else 'ai-progress-toast'
    icon = '✅' if done else '<span class="toast-pulse"></span>'
    # Patience reminder — only shown while running (not on completion)
    _patience = ''
    if not done:
        _patience = (f'<div style="font-size:0.72rem; color:var(--vx-text-muted, #8b949e); '
                     f'margin-top:4px; font-style:italic;">'
                     f'{t("ai_patience")}</div>')
    placeholder.markdown(
        f'<div class="{cls}">'
        f'<div class="toast-title">{icon} {title}</div>'
        f'<div class="toast-msg">{msg}</div>'
        f'<div class="toast-elapsed">{t("ai_elapsed", elapsed=elapsed)}</div>'
        f'{_patience}'
        f'</div>', unsafe_allow_html=True)


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
    """Compact streaming: st.status with phase indicators. Used for gap analysis.

    Uses a background thread for stdout reading so the main thread can update
    both the in-status progress AND the fixed-position toast every ~2 seconds.
    Without a thread, Streamlit buffers updates to elements outside the active
    st.status context, causing the toast elapsed time to stay at 0.
    """
    import threading
    import queue as _queue

    phase_icons = {
        'starting': '🚀', 'searching': '🔍',
        'parameters': '📊', 'generating': '📝',
    }
    phase_labels = {
        'starting': t('phase_starting'),
        'searching': t('phase_searching'),
        'parameters': t('phase_parameters'),
        'generating': t('phase_generating'),
    }

    toast_placeholder = st.empty()  # Fixed-position progress toast

    # Shared state between reader thread and main thread
    output_queue = _queue.Queue()
    reader_done = threading.Event()

    def _reader_thread(proc):
        try:
            for line in iter(proc.stdout.readline, ''):
                output_queue.put(line)
            proc.stdout.close()
        except Exception:
            pass
        finally:
            reader_done.set()

    with st.status(f"🤖 {status_label} via {engine_label}", expanded=True) as status:
        current_phase = 'starting'
        st.write(f"{phase_icons['starting']} {t('phase_init_engine', engine=engine_label)}")
        line_count = 0
        progress_placeholder = st.empty()
        output_placeholder = st.empty()

        # Show initial toast immediately
        _render_progress_toast(toast_placeholder,
                                f'🤖 {status_label} — {engine_label}',
                                f'{phase_icons["starting"]} {t("phase_init_engine", engine=engine_label)}',
                                time.time() - start_time)

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, env=current_env,
            )

            # Start background reader
            reader = threading.Thread(target=_reader_thread, args=(proc,), daemon=True)
            reader.start()

            accumulated = []

            # Main thread: poll for output and update UI periodically
            while not reader_done.is_set() or not output_queue.empty():
                # Drain all available lines (non-blocking)
                while not output_queue.empty():
                    try:
                        line = output_queue.get_nowait()
                        accumulated.append(line)
                        line_count += 1
                        new_phase = _detect_ai_phase(line)
                        if new_phase and new_phase != current_phase:
                            current_phase = new_phase
                            st.write(f"{phase_icons.get(current_phase, '⏳')} "
                                     f"{phase_labels.get(current_phase, 'Processing...')}")
                        stripped = line.strip()
                        if stripped and len(stripped) > 5:
                            if stripped.startswith('{') and '"result":' in stripped:
                                try:
                                    peek = json.loads(stripped)
                                    msg = peek.get('result', peek.get('error', stripped))
                                    if isinstance(msg, str):
                                        output_placeholder.code(
                                            msg[:120] + ('...' if len(msg) > 120 else ''), language=None)
                                except Exception:
                                    output_placeholder.code(stripped[:120] + '...', language=None)
                            else:
                                output_placeholder.code(
                                    stripped[:120] + ('...' if len(stripped) > 120 else ''), language=None)
                    except _queue.Empty:
                        break

                elapsed = time.time() - start_time
                _phase_msg = phase_labels.get(current_phase, 'Processing...')
                progress_placeholder.caption(t('ai_lines_received', elapsed=elapsed, lines=line_count))

                # Update sticky toast (visible without scrolling)
                _render_progress_toast(toast_placeholder,
                                        f'🤖 {status_label} — {engine_label}',
                                        _phase_msg, elapsed)

                # Wait before next UI update (or until reader finishes)
                reader_done.wait(timeout=2.0)

            proc.wait(timeout=_timeout)
            stderr_content = proc.stderr.read() if proc.stderr else ''
            proc.stderr.close()
            reader.join(timeout=2)

        except subprocess.TimeoutExpired:
            proc.kill()
            toast_placeholder.empty()
            raise RuntimeError(f"{engine_label} timed out after {_timeout}s")

        raw = ''.join(accumulated).strip()
        elapsed = time.time() - start_time
        if not raw:
            toast_placeholder.empty()
            raise RuntimeError(f"{engine_label} {'failed: ' + stderr_content[:200] if stderr_content else 'returned empty output'}")

        text = _parse_cli_output(raw, engine, engine_label, proc.returncode, stderr_content)
        status.update(label=f"✅ {status_label} ({elapsed:.0f}s)", state="complete", expanded=False)

    # Show completion toast briefly, then clear
    _render_progress_toast(toast_placeholder,
                            t('ai_toast_complete_title', label=status_label),
                            t('ai_toast_complete_msg', engine=engine_label), elapsed, done=True)
    time.sleep(2)
    toast_placeholder.empty()

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
    toast_placeholder = st.empty()  # Fixed-position progress toast (visible without scrolling)
    status_placeholder = st.empty()
    reasoning_placeholder = st.empty()

    # Rotating status messages to keep users engaged during the long wait
    _WAIT_MESSAGES = [
        t('wait_1'), t('wait_2'), t('wait_3'), t('wait_4'),
        t('wait_5'), t('wait_6'), t('wait_7'), t('wait_8'),
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
                f'<h4>{t("ai_live_title")}</h4>'
                f'<div style="padding:16px 0 8px 0; font-size:0.9rem; '
                f'color:var(--vx-text-secondary);">{current_msg}</div>'
                f'<div class="ai-live-status"><div class="pulse"></div> '
                f'{phase_icon} {t("ai_analyzing", engine=engine_label, elapsed=elapsed)}</div>'
                '</div>', unsafe_allow_html=True)

            # Sticky toast (visible from anywhere on page)
            _render_progress_toast(toast_placeholder,
                                    f'🤖 {status_label} — {engine_label}',
                                    current_msg, elapsed)

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
        f'{t("ai_complete", engine=engine_label, elapsed=elapsed)}</div>',
        unsafe_allow_html=True)

    # Show completion toast briefly, then clear it
    _render_progress_toast(toast_placeholder,
                            t('ai_toast_complete_title', label=status_label),
                            t('ai_toast_complete_msg', engine=engine_label), elapsed, done=True)
    time.sleep(2)
    toast_placeholder.empty()

    return text, engine


def _progressive_reveal_reasoning(parameters, reasoning_placeholder, status_placeholder,
                                   engine_label, elapsed):
    """Progressively reveal AI reasoning sections one by one.

    After the AI finishes and we've parsed the structured parameters,
    this function reveals each reasoning section with a brief pause,
    giving users time to start reading before DCF calculation begins.
    """
    PARAM_LABELS = {
        'revenue_growth_1': 'ai_label_rg1_icon',
        'revenue_growth_2': 'ai_label_rg2_icon',
        'ebit_margin': 'ai_label_ebit_icon',
        'convergence': 'ai_label_conv_icon',
        'revenue_invested_capital_ratio_1': 'ai_label_ric1_icon',
        'revenue_invested_capital_ratio_2': 'ai_label_ric2_icon',
        'revenue_invested_capital_ratio_3': 'ai_label_ric3_icon',
        'tax_rate': 'ai_label_tax_icon',
        'wacc': 'ai_label_wacc_icon',
        'ronic_match_wacc': 'ai_label_ronic_icon',
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
        val_str = (t('ai_ronic_yes') if val else t('ai_ronic_no')) if isinstance(val, bool) else str(val)
        _lbl_key = PARAM_LABELS.get(key, key)
        _lbl = t(_lbl_key) if _lbl_key != key else key
        sections_to_show.append((key, _lbl, val_str, reasoning))

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
            f'<h4>{t("ai_live_title")}</h4>'
            + ''.join(revealed_html_parts) +
            f'<div class="ai-live-status" style="color: var(--vx-accent);">'
            f'{t("ai_revealing", idx=idx + 1, total=total)}</div>'
            '</div>'
        )
        reasoning_placeholder.markdown(all_html, unsafe_allow_html=True)

        status_placeholder.markdown(
            f'<div class="ai-live-status"><div class="pulse"></div> '
            f'{t("ai_revealing_status", idx=idx + 1, total=total, elapsed=elapsed)}</div>',
            unsafe_allow_html=True)

        # Brief pause between sections so users can read
        time.sleep(0.35)

    # Final state: all sections revealed
    final_html = (
        '<div class="ai-live-reasoning">'
        f'<h4>{t("ai_live_title")}</h4>'
        + ''.join(revealed_html_parts) +
        f'<div class="ai-live-status" style="color: var(--vx-green);">'
        f'{t("ai_all_done", total=total, elapsed=elapsed)}</div>'
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
        elif engine == 'qwen':
            # Qwen Code CLI JSON format (similar to Gemini — forked from it)
            if data.get('is_error'):
                raise RuntimeError(f"Qwen CLI Error: {data.get('error', 'Unknown')}")
            text = data.get('response', data.get('result', raw))
            if not _ai_mod._detected_model_name:
                # Try to extract model name from stats or modelUsage
                _qstats = data.get('stats', {}).get('models', {})
                if _qstats:
                    _qmodel = next(iter(_qstats))
                    _ai_mod._detected_model_name = _qmodel.replace('qwen', 'Qwen ').replace('-', ' ').strip()
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
            prompt, status_label=t('ai_status_label', company=company_name), live_reasoning=True)

        parameters = _parse_structured_parameters(text)
        if parameters is None:
            st.error(t('err_ai_parse'))
            s._ai_running = False
            return False

        s.ai_result = {
            "parameters": parameters,
            "raw_text": text,
        }
        # Clear user-param-modified flags and old DCF results when AI re-runs
        s.pop('user_params_modified', None)
        for _k in ('results', 'sensitivity_table', 'wacc_results',
                    'wacc_base', 'valuation_params', 'gap_analysis_result',
                    '_last_dcf_input_snapshot',
                    'p_rg1', 'p_rg2', 'p_em', 'p_conv', 'p_tax',
                    'p_ric1', 'p_ric2', 'p_ric3', 'p_wacc'):
            s.pop(_k, None)

        # Flag: show reasoning expander as EXPANDED on first render after AI
        s._reasoning_just_completed = True
        s._ai_running = False
        return True
    except Exception as e:
        s._ai_running = False
        _err_msg = str(e)
        _err_lower = _err_msg.lower()
        st.error(t('err_ai_failed', msg=_err_msg))
        # Engine-specific troubleshooting guidance
        _engine = _ai_mod._AI_ENGINE
        if _engine == 'qwen':
            # Show targeted hint for common errors
            if '401' in _err_msg or 'token expired' in _err_lower or 'access token' in _err_lower:
                st.warning("⚡ **Token 已过期** — 请在终端运行 `qwen` 重新登录，或设置 `DASHSCOPE_API_KEY` 环境变量（API key 不会过期）")
            st.info(
                "**Qwen Code troubleshooting:**\n\n"
                "1. **Install:** `npm install -g @qwen-code/qwen-code@latest` (Node.js ≥ 20)\n"
                "2. **Login (interactive):** Run `qwen` in terminal, then `/auth` → Qwen OAuth (free: 1,000 req/day)\n"
                "3. **Headless mode** (used here) requires API key — OAuth won't work.\n"
                "   - Get an API key from [Alibaba Cloud ModelStudio](https://bailian.console.alibabacloud.com/)\n"
                "   - Set `DASHSCOPE_API_KEY` in your environment or `~/.qwen/settings.json`\n"
                "4. **Alternative:** Switch to Claude or Gemini in the sidebar AI Engine selector."
            )
        elif _engine == 'gemini':
            if 'ineligibletier' in _err_lower:
                st.warning("⚡ **已知问题** — Google 账号资格验证存在 bug，等待 Google 修复中。建议切换到其他 AI 引擎。")
            elif 'consent' in _err_lower or 'authentication' in _err_lower:
                st.warning("⚡ **登录失效** — 请在终端运行 `gemini` 重新登录，或设置 `GEMINI_API_KEY` 环境变量")
            st.info(
                "**Gemini CLI troubleshooting:**\n\n"
                "1. **Install:** `npm install -g @google/gemini-cli`\n"
                "2. **Login:** Run `gemini` in terminal — sign in with Google account (free quota)\n"
                "3. If quota exceeded, try again later or switch to another AI engine."
            )
        elif _engine == 'claude':
            if 'not logged in' in _err_lower or 'login' in _err_lower:
                st.warning("⚡ **未登录** — 请在终端运行 `claude` 完成登录")
            st.info(
                "**Claude CLI troubleshooting:**\n\n"
                "1. **Install:** `npm install -g @anthropic-ai/claude-code`\n"
                "2. **Login:** Run `claude` in terminal — sign in with Anthropic account\n"
                "3. Try switching to **Balanced** or **Fast** speed for lower cost and faster results."
            )
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
        ronic_match = ronic_data.get('value', False)
    elif isinstance(ronic_data, bool):
        ronic_match = ronic_data
    else:
        ronic_match = False
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
        st.warning(t('gap_no_price'))
        return None

    currency_converted = False
    if reported_currency and reported_currency != stock_currency and forex_rate and forex_rate != 1.0:
        dcf_price = dcf_price_raw * forex_rate
        currency_converted = True
    else:
        dcf_price = dcf_price_raw

    gap_pct = (dcf_price - current_price) / current_price * 100
    _lang = st.session_state.get('_lang', 'en')
    if _lang == 'zh':
        gap_direction = 'DCF 估值高于市场价，市场可能低估' if gap_pct > 0 else 'DCF 估值低于市场价，市场可能高估'
    else:
        gap_direction = 'DCF above market price, potentially undervalued' if gap_pct > 0 else 'DCF below market price, potentially overvalued'

    currency_note = ""
    if currency_converted:
        if _lang == 'zh':
            currency_note = (
                f"\n\n**重要：货币换算说明**\n"
                f"- 财务数据以 {reported_currency} 报告，DCF 原始估值为 {dcf_price_raw:.2f} {reported_currency}\n"
                f"- 股票以 {stock_currency} 交易，已按汇率 {forex_rate:.4f} 换算为 {dcf_price:.2f} {stock_currency}\n"
                f"- 以下所有价格比较和修正估值均以 {stock_currency} 为单位"
            )
        else:
            currency_note = (
                f"\n\n**Important: Currency Conversion Note**\n"
                f"- Financial data reported in {reported_currency}, raw DCF valuation is {dcf_price_raw:.2f} {reported_currency}\n"
                f"- Stock trades in {stock_currency}, converted at rate {forex_rate:.4f} to {dcf_price:.2f} {stock_currency}\n"
                f"- All price comparisons and adjusted valuations below are in {stock_currency}"
            )

    financial_table = summary_df.to_string()
    _gap_template = GAP_ANALYSIS_PROMPT_TEMPLATE if _lang == 'zh' else GAP_ANALYSIS_PROMPT_TEMPLATE_EN
    prompt = _gap_template.format(
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

    analysis_text, _ = _run_ai_streaming(prompt, status_label=t('gap_status_label'))

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
_gap_just_done = False
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

# Effective triggers: button click (local) or Enter key (web)
_trigger_ai = oneclick_btn and ticker_input
_trigger_manual = (manual_btn and ticker_input) or (_ticker_enter and ticker_input)

# ── Clean-slate reset: clear ALL previous results so the page starts fresh ──
_ALL_RESULT_KEYS = (
    'results', 'sensitivity_table', 'wacc_results', 'wacc_base',
    'valuation_params', 'gap_analysis_result', 'ai_result',
    'user_params_modified', '_last_dcf_input_snapshot',
    '_ai_reasoning_expanded', '_gap_just_completed',
    'p_rg1', 'p_rg2', 'p_em', 'p_conv', 'p_tax',
    'p_ric1', 'p_ric2', 'p_ric3', 'p_wacc',
    'summary_df', 'company_profile', 'ticker',
    '_fetch_ready', '_fetch_ready_ticker',
)
if _trigger_ai or _trigger_manual:
    # Phase 1: clear everything and schedule the fetch for the next rerun.
    # st.rerun() aborts the current script so Streamlit renders the blank
    # welcome page (because summary_df is gone).  On the NEXT rerun
    # (Phase 2), the blank page is already displayed so the spinner
    # overlays on a clean background rather than the old results.
    for _k in _ALL_RESULT_KEYS:
        st.session_state.pop(_k, None)
    st.session_state._fetch_pending = 'ai' if _trigger_ai else 'manual'
    st.session_state._fetch_ticker = ticker_input
    st.rerun()

# ────────────────────────────────────────────────────────────────
# Display: nothing fetched yet → welcome / loading / warning
# ────────────────────────────────────────────────────────────────
if 'summary_df' not in st.session_state:
    # Clean-slate reset uses a 3-phase approach:
    #   Phase 1 (button click): clear all state, set _fetch_pending, st.rerun()
    #   Phase 2 (this rerun): _fetch_pending is set but we DON'T fetch yet.
    #     Instead we show a clean loading page, move the flag to _fetch_ready,
    #     and call st.rerun() so the browser actually renders this blank page.
    #   Phase 3 (next rerun): _fetch_ready is set — NOW do the actual fetch
    #     with a spinner.  The browser already shows the clean page, so the
    #     spinner overlays on a blank background instead of stale results.
    _fetch_pending = st.session_state.get('_fetch_pending')
    _fetch_ticker = st.session_state.get('_fetch_ticker')
    _fetch_ready = st.session_state.get('_fetch_ready')
    _fetch_ready_ticker = st.session_state.get('_fetch_ready_ticker')

    if _fetch_pending and _fetch_ticker:
        # Phase 2: show clean loading page, schedule actual fetch for next rerun
        st.session_state.pop('_fetch_pending', None)
        st.session_state.pop('_fetch_ticker', None)
        st.session_state._fetch_ready = _fetch_pending  # 'ai' or 'manual'
        st.session_state._fetch_ready_ticker = _fetch_ticker
        st.markdown("""
        <div style="padding:20px 16px; max-width:900px; margin:0 auto;">
            <div class="skeleton-block" style="height:42px; margin-bottom:16px; width:60%;"></div>
            <div style="display:flex; gap:12px; margin-bottom:16px;">
                <div class="skeleton-block" style="flex:1; height:72px;"></div>
                <div class="skeleton-block" style="flex:1; height:72px;"></div>
                <div class="skeleton-block" style="flex:1; height:72px;"></div>
            </div>
            <div class="skeleton-block" style="height:24px; margin-bottom:12px; width:40%;"></div>
            <div class="skeleton-block" style="height:180px; margin-bottom:16px;"></div>
            <div style="display:flex; gap:12px;">
                <div class="skeleton-block" style="flex:1; height:120px;"></div>
                <div class="skeleton-block" style="flex:1; height:120px;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        # End this render so the browser receives the blank page, then rerun
        import time as _t; _t.sleep(0.05)  # tiny yield for Streamlit to flush
        st.rerun()

    elif _fetch_ready and _fetch_ready_ticker:
        # Phase 3: browser now shows clean page — do the actual fetch
        _fr_mode = _fetch_ready
        _fr_ticker = _fetch_ready_ticker
        st.session_state.pop('_fetch_ready', None)
        st.session_state.pop('_fetch_ready_ticker', None)
        st.session_state._display_mode = 'valuation'
        if _fr_mode == 'ai':
            st.session_state._show_fin_data = True
            with st.spinner(t('fetching_data', ticker=_fr_ticker)):
                ok = _fetch_data(_fr_ticker, apikey)
            if ok:
                _pending_oneclick = True
                st.session_state._ai_pending = True
            st.rerun()
        else:
            st.session_state._ai_pending = False
            st.session_state._show_fin_data = True
            with st.spinner(t('fetching_fin_data', ticker=_fr_ticker)):
                ok = _fetch_data(_fr_ticker, apikey)
            if ok:
                st.rerun()
            else:
                st.stop()  # Let the error from _fetch_data stay visible
    else:
        if _empty_ticker_warning:
            st.warning(t('welcome_empty_warning'))
        st.markdown(f"""
        <div style="text-align:center; padding:80px 20px 60px 20px; max-width:560px; margin:0 auto;">
            <p style="font-size:3rem; margin-bottom:8px; line-height:1;">📊</p>
            <p style="font-size:1.5rem; font-weight:700; margin-bottom:6px; color:var(--vx-text, #1f2328);
                       background:linear-gradient(135deg, #00d2ff 0%, #7b2ff7 100%);
                       -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                ValuX
            </p>
            <p style="font-size:1.05rem; color:var(--vx-text-secondary, #656d76); line-height:1.6; margin-bottom:20px;">
                {t('welcome_instruction_web') if not _has_ai else t('welcome_instruction')}
            </p>
            <div style="display:flex; justify-content:center; gap:12px; flex-wrap:wrap; margin-bottom:20px;">
                <span style="font-size:0.8rem; padding:4px 14px; border-radius:20px;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_us')}</span>
                <span style="font-size:0.8rem; padding:4px 14px; border-radius:20px;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_hk')}</span>
                <span style="font-size:0.8rem; padding:4px 14px; border-radius:20px;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_cn')}</span>
            </div>
            <p style="font-size:0.78rem; color:var(--vx-text-muted, #8b949e);">
                {t('welcome_api_note')}
            </p>
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

    # ── Financial data toggle button (shared logic for both pre/post DCF) ──
    _fin_currently_shown = ss.get('_show_fin_data', False)
    _fin_btn_label = t('btn_collapse_fin') if _fin_currently_shown else t('btn_view_fin')

    if _has_results:
        # Post-DCF: company name + Financials + [Gap (AI only)] + Excel
        if _has_ai:
            _hcols = st.columns([3.5, 1, 1, 1])
        else:
            _hcols = st.columns([4.5, 1, 1])
        with _hcols[0]:
            st.markdown(
                f'<div class="company-header-bar">'
                f'<span class="company-name">{_company_title}</span></div>',
                unsafe_allow_html=True)
        with _hcols[1]:
            _fin_toggled = st.button(_fin_btn_label, use_container_width=True,
                                      key="fin_data_toggle")
        if _has_ai:
            with _hcols[2]:
                current_price = ss.company_profile.get('price', 0)
                if current_price and current_price > 0:
                    gap_btn = st.button(t('btn_gap_analysis'), use_container_width=True,
                                         disabled=_btns_disabled)
            _excel_col = _hcols[3]
        else:
            _excel_col = _hcols[2]
        with _excel_col:
            if _excel_buf is not None:
                st.download_button(
                    label=t('btn_download'),
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
            _fin_toggled = st.button(_fin_btn_label, use_container_width=True,
                                      key="fin_data_toggle")

    # Handle toggle action (after both branches so _fin_toggled is always set)
    if _fin_toggled:
        if _fin_currently_shown:
            ss._show_fin_data = False
        else:
            ss._show_fin_data = True
            ss._scroll_to_fin_data = True
        st.rerun()
    _show_fin_data = ss.get('_show_fin_data', False)

# ── Sticky mini hero bar (second row, only after DCF results) ──
if _has_results:
    _hero_bar_container = st.container()
    with _hero_bar_container:
        st.markdown('<div class="valux-sticky-hero"></div>', unsafe_allow_html=True)
        # Compute IV in stock currency for the mini hero bar
        _hdr_res = ss.results
        _hdr_dcf_raw = _hdr_res['price_per_share']
        _hdr_rep_cur = _hdr_res.get('reported_currency', '')
        _hdr_stk_cur = ss.company_profile.get('currency', '')
        _hdr_cur = _hdr_rep_cur or _hdr_stk_cur or ''
        _hdr_forex = ss.get('forex_rate')
        _hdr_needs_forex = (_hdr_rep_cur and _hdr_stk_cur
                            and _hdr_rep_cur != _hdr_stk_cur)
        if _hdr_needs_forex and not _hdr_forex:
            _hdr_forex, _ = _compute_forex_rate_web(
                _hdr_res, ss.company_profile, apikey)
            if _hdr_forex:
                ss.forex_rate = _hdr_forex
        if _hdr_forex and _hdr_needs_forex:
            _hdr_iv = _hdr_dcf_raw * _hdr_forex
            _hdr_iv_cur = _hdr_stk_cur
        else:
            _hdr_iv = _hdr_dcf_raw
            _hdr_iv_cur = _hdr_cur
        _hdr_mkt = ss.company_profile.get('price', 0) or 0

        _hdr_mos = None
        _mh_html = '<div class="mini-hero-bar">'
        _mh_html += f'<span class="mh-title">{t("hero_title")}</span>'
        _mh_html += (f'<div class="mh-item">'
                     f'<span class="mh-label">{t("hero_intrinsic")}</span>'
                     f'<span class="mh-val intrinsic">{_hdr_iv_cur} {_hdr_iv:,.2f}</span>'
                     f'</div>')
        _mh_html += '<span class="mh-vs">vs</span>'
        if _hdr_mkt > 0:
            _mh_html += (f'<div class="mh-item">'
                         f'<span class="mh-label">{t("hero_market")}</span>'
                         f'<span class="mh-val market">{_hdr_stk_cur} {_hdr_mkt:,.2f}</span>'
                         f'</div>')
            _hdr_mos = (_hdr_iv - _hdr_mkt) / _hdr_mkt * 100
            _mos_cls = 'positive' if _hdr_mos >= 0 else 'negative'
            _mos_word = t('hero_undervalued') if _hdr_mos >= 0 else t('hero_overvalued')
            _mh_html += (f'<div class="mh-item">'
                         f'<span class="mh-mos {_mos_cls}">{_hdr_mos:+.1f}%</span>'
                         f'<span class="mh-mos-label">{_mos_word}</span>'
                         f'</div>')
        else:
            _mh_html += '<div class="mh-item"><span class="mh-val market">—</span></div>'
        # One-line summary inline with descriptive param labels
        _mh_vp = ss.get('valuation_params', {})
        if _hdr_mos is not None and _hdr_mkt > 0:
            _mh_abs = abs(_hdr_mos)
            if _hdr_mos > 30:     _mh_verdict = t('verdict_sig_under')
            elif _hdr_mos > 10:   _mh_verdict = t('verdict_mod_under')
            elif _hdr_mos > -10:  _mh_verdict = t('verdict_fair')
            elif _hdr_mos > -30:  _mh_verdict = t('verdict_mod_over')
            else:                 _mh_verdict = t('verdict_sig_over')
            _mh_g1 = _mh_vp.get('revenue_growth_1', 0)
            _mh_g = _mh_vp.get('revenue_growth_2', 0)
            _mh_m = _mh_vp.get('ebit_margin', 0)
            _mh_w = _mh_vp.get('wacc', 0)
            _mh_html += (f'<span class="mh-summary">'
                         f'{t("hero_summary", g1=_mh_g1, g2=_mh_g, m=_mh_m, w=_mh_w, verdict=_mh_verdict)}</span>')
        _mh_html += '</div>'
        st.markdown(_mh_html, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# MODE: Fetch Only — show ONLY historical financial data
# (Skip if one-click is pending — don't display stale data)
# ════════════════════════════════════════════════════════════════
if _display_mode == 'fetch_only' and not _pending_oneclick:
    st.markdown(f'<div class="section-hdr">{t("section_hist_data")}</div>', unsafe_allow_html=True)
    # TTM / base year notes — under historical data title
    if ss.is_ttm:
        _ttm_date_str = f" (through {ss.ttm_end_date})" if ss.ttm_end_date else ''
        st.caption(t('fin_ttm_caption', ttm_label=ss.ttm_label, date_str=_ttm_date_str, base_year=ss.base_year, fy1=ss.forecast_year_1))
    else:
        st.caption(t('fin_base_caption', base_year=ss.base_year))
    _ttm_note = ss.financial_data.get('ttm_note', '')
    if _ttm_note:
        st.caption(t('fin_ttm_note', note=_ttm_note))
    st.markdown(_render_financial_table(ss.summary_df), unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════════════════════════
# MODE: Valuation — full layout
# ════════════════════════════════════════════════════════════════

# ── Historical data (render BEFORE AI so user can review while AI runs) ──
st.markdown('<div id="hist-fin-data"></div>', unsafe_allow_html=True)
if _show_fin_data:
    with st.expander(t('section_hist_data'), expanded=True):
        if ss.is_ttm:
            _ttm_date_str = f" (through {ss.ttm_end_date})" if ss.ttm_end_date else ''
            st.caption(t('fin_ttm_caption', ttm_label=ss.ttm_label, date_str=_ttm_date_str, base_year=ss.base_year, fy1=ss.forecast_year_1))
        else:
            st.caption(t('fin_base_caption', base_year=ss.base_year))
        _ttm_note = ss.financial_data.get('ttm_note', '')
        if _ttm_note:
            st.caption(t('fin_ttm_note', note=_ttm_note))
        st.markdown(_render_financial_table(ss.summary_df), unsafe_allow_html=True)

# Scroll to historical data when toggled ON
if ss.get('_scroll_to_fin_data'):
    ss._scroll_to_fin_data = False
    _scroll_to("hist-fin-data")

# ── Execute One-Click AI + DCF (progress renders here, below header) ──
if _pending_oneclick:
    ai_ok = _run_ai_analysis()
    _did_ai_run = True
    ss._ai_pending = False  # Clear the persistent flag regardless of outcome
    if ai_ok:
        with st.spinner(t('calculating_dcf')):
            _run_dcf_from_ai()
        ss._dcf_just_ran = False  # First AI run — no "updated" banner
        ss._scroll_to_results = True
        ss._save_snapshot_on_next_render = True
        st.rerun()
    else:
        st.warning(t('warn_ai_no_params'))

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
        ss._gap_just_completed = True
    except Exception as e:
        st.error(t('err_gap_failed', msg=str(e)))

# (Historical data is rendered earlier, before AI execution, so user can review during AI analysis)

# ──────────────────────────────────────────
# § 1  DCF Results anchor (all display is now in the sticky mini hero bar)
# ──────────────────────────────────────────
if _has_results:
    st.markdown('<div id="dcf-results"></div>', unsafe_allow_html=True)
    # Consume the flash banner
    if ss.pop('_dcf_just_ran', False):
        pass  # Flash info is now in the sticky bar; no separate banner needed

# ──────────────────────────────────────────
# § 2  Valuation Parameters (between hero and details)
# ──────────────────────────────────────────
st.markdown('<div id="valuation-params"></div>', unsafe_allow_html=True)
st.markdown(f'<div class="section-hdr">{t("section_valuation_params")}</div>', unsafe_allow_html=True)

# Display AI reasoning
has_ai = 'ai_result' in ss and ss.ai_result and ss.ai_result.get('parameters')
if has_ai:
    reasoning_md = _render_ai_reasoning(ss.ai_result['parameters'])
    if reasoning_md:
        # When AI just completed, set persistent expand flag.
        # This keeps reasoning expanded across reruns (e.g. toggling financial data).
        if ss.pop('_reasoning_just_completed', False):
            ss._ai_reasoning_expanded = True
        _expand_reasoning = ss.get('_ai_reasoning_expanded', False)
        _hint_action = t('ai_hint_collapse') if _expand_reasoning else t('ai_hint_expand')
        st.markdown(
            f'<div class="expander-hint"><span class="icon">📖</span>'
            f'{t("ai_reasoning_hint", engine=_ai_engine_display_name(), action=_hint_action)}</div>',
            unsafe_allow_html=True)
        with st.expander(t('ai_reasoning_expander'), expanded=_expand_reasoning):
            st.markdown(reasoning_md)

# ── Slider hint (prominent callout — shown AFTER first DCF run) ──
if _has_results:
    st.markdown(
        f'<div class="slider-hint">'
        f'<span class="hint-title">{t("slider_hint")}</span>'
        f'</div>',
        unsafe_allow_html=True)

# Track modified params
_modified_keys = set()

# ── Historical reference data extraction ──
def _get_hist_refs():
    """Extract historical averages from summary_df for parameter reference labels."""
    refs = {}
    sdf = ss.get('summary_df')
    if sdf is None or sdf.empty:
        return refs
    try:
        n_cols = len(sdf.columns)
        # Build the "latest" label from TTM or base year
        _ttm_lbl = ss.get('ttm_label', '')
        _latest_label = _ttm_lbl if _ttm_lbl else str(sdf.columns[0]) if n_cols > 0 else 'Latest'
        # Number of historical years for avg/range (exclude the TTM/base col)
        _n_hist = max(1, n_cols)

        # Revenue Growth (%) — use all available years
        if 'Revenue Growth (%)' in sdf.index:
            rg = sdf.loc['Revenue Growth (%)'].dropna().values
            rg = [float(v) for v in rg if v != 0 and abs(float(v)) < 200]
            if rg:
                refs['rev_growth'] = {'avg': sum(rg)/len(rg), 'latest': rg[0],
                                      'min': min(rg), 'max': max(rg),
                                      'n': len(rg), 'latest_label': _latest_label}
        # EBIT Margin (%)
        if 'EBIT Margin (%)' in sdf.index:
            em = sdf.loc['EBIT Margin (%)'].dropna().values
            em = [float(v) for v in em if abs(float(v)) < 200]
            if em:
                refs['ebit_margin'] = {'avg': sum(em)/len(em), 'latest': em[0],
                                       'min': min(em), 'max': max(em),
                                       'n': len(em), 'latest_label': _latest_label}
        # Tax Rate (%)
        if 'Tax Rate (%)' in sdf.index:
            tr = sdf.loc['Tax Rate (%)'].dropna().values
            tr = [float(v) for v in tr if 0 < float(v) < 100]
            if tr:
                refs['tax_rate'] = {'avg': sum(tr)/len(tr), 'latest': tr[0],
                                    'n': len(tr), 'latest_label': _latest_label}
        # Revenue / IC
        if 'Revenue / IC' in sdf.index:
            ric = sdf.loc['Revenue / IC'].dropna().values
            ric = [float(v) for v in ric if float(v) > 0]
            if ric:
                refs['rev_ic'] = {'avg': sum(ric)/len(ric), 'latest': ric[0],
                                  'min': min(ric), 'max': max(ric),
                                  'n': len(ric), 'latest_label': _latest_label}
    except Exception:
        pass
    return refs

_hist_refs = _get_hist_refs()

def _render_hist_label(ref_key, fmt="%.1f", suffix="%"):
    """Render a compact historical reference label ABOVE the slider (clearly for the parameter below)."""
    ref = _hist_refs.get(ref_key)
    if not ref:
        return
    # Use the total number of historical data columns (consistent period label)
    _n_data_cols = len(ss.get('summary_df', pd.DataFrame()).columns) if 'summary_df' in ss else 0
    _n_yr = str(_n_data_cols) if _n_data_cols > 0 else ''
    _latest_lbl = ref.get('latest_label', 'Latest')
    parts = []
    if 'latest' in ref:
        parts.append(f'<span class="hist-tag">{t("hist_latest", label=_latest_lbl, val=fmt % ref["latest"], suffix=suffix)}</span>')
    if 'avg' in ref:
        parts.append(f'<span class="hist-tag">{t("hist_avg", n=_n_yr, val=fmt % ref["avg"], suffix=suffix)}</span>')
    if 'min' in ref and 'max' in ref:
        parts.append(f'<span class="hist-tag">{t("hist_range", n=_n_yr, min=fmt % ref["min"], max=fmt % ref["max"], suffix=suffix)}</span>')
    if parts:
        st.markdown(f'<div class="hist-ref">{"".join(parts)}</div>', unsafe_allow_html=True)


def _param_slider(label, ai_key, step, fmt, col_key, min_val, max_val, default_val,
                  help_text=None, hist_key=None, hist_fmt="%.1f", hist_suffix="%"):
    """Render a slider with historical reference label ABOVE it. Returns current value."""
    ai_val = _get_ai_val(ai_key, ss)
    # Determine initial value: AI value > session state > default
    init_val = ai_val if ai_val is not None else default_val
    # Clamp to slider range
    init_val = max(min_val, min(max_val, init_val))
    # Round to step precision
    _decimals = int(fmt.replace('%', '').replace('f', '').replace('.', '')) if '.' in fmt else 0

    # Historical reference label rendered ABOVE the slider so it clearly belongs to this parameter
    if hist_key:
        _render_hist_label(hist_key, hist_fmt, hist_suffix)

    val = st.slider(label, min_value=float(min_val), max_value=float(max_val),
                    value=float(init_val), step=float(step), format=fmt,
                    key=col_key, help=help_text)

    # AI-modified detection
    _tol = 0.5 * (10 ** -_decimals)
    is_modified = ai_val is not None and val is not None and abs(val - ai_val) > _tol
    if is_modified:
        _modified_keys.add(ai_key)
        st.markdown(
            f'<div class="param-modified-hint">{t("param_modified_hint", ai_val=fmt % ai_val, user_val=fmt % val)}</div>',
            unsafe_allow_html=True)
    return val


_rg_ref = _hist_refs.get('rev_growth', {})
_em_ref = _hist_refs.get('ebit_margin', {})
_rg_default = round(_rg_ref.get('avg', 10.0), 1)
_em_default = round(_em_ref.get('avg', 20.0), 1)

# ── Dynamic slider ranges: adapt to historical data so actual values always fit ──
import math as _math
_rg1_max = max(60.0, _math.ceil((_rg_ref.get('max', 30.0)) * 1.5 / 5) * 5)   # round up to nearest 5
_rg2_max = max(40.0, _math.ceil((_rg_ref.get('max', 20.0)) * 1.3 / 5) * 5)
_em_max  = max(60.0, _math.ceil((_em_ref.get('max', 30.0)) * 1.2 / 5) * 5)
_em_min  = min(-10.0, _math.floor((_em_ref.get('min', 0.0)) * 1.2 / 5) * 5) if _em_ref.get('min', 0) < -10 else -10.0

# ── Dynamic year labels for slider parameters ──
_fy1 = ss.forecast_year_1  # e.g. 2026
if ss.is_ttm:
    # TTM: show "Year N" with starting-quarter context on Year 1
    _q_num = int(ss.ttm_quarter.replace('Q', ''))  # e.g. Q2 → 2
    _next_q = _q_num + 1 if _q_num < 4 else 1
    _next_q_year = _fy1 if _q_num < 4 else _fy1
    _ttm_start = f"{_next_q_year}Q{_next_q}"       # e.g. "2025Q3"
    _lbl_rg1 = t('param_rg1_ttm', start=_ttm_start)
    _lbl_rg2 = t('param_rg2_ttm')
    _lbl_ric1 = t('param_ric1_ttm')
    _lbl_ric2 = t('param_ric2_ttm')
    _lbl_ric3 = t('param_ric3_ttm')
    _help_rg1 = t('help_rg1_ttm', start=_ttm_start)
    _help_rg2 = t('help_rg2_ttm')
else:
    # Normal FY: show explicit fiscal years
    _lbl_rg1 = t('param_rg1_fy', fy1=_fy1)
    _lbl_rg2 = t('param_rg2_fy', fy1_1=_fy1+1, fy1_4=_fy1+4)
    _lbl_ric1 = t('param_ric1_fy', fy1=_fy1, fy1_1=_fy1+1)
    _lbl_ric2 = t('param_ric2_fy', fy1_2=_fy1+2, fy1_4=_fy1+4)
    _lbl_ric3 = t('param_ric3_fy', fy1_4=_fy1+4, fy1_9=_fy1+9)
    _help_rg1 = t('help_rg1_fy', fy1=_fy1)
    _help_rg2 = t('help_rg2_fy', fy1_1=_fy1+1, fy1_4=_fy1+4)

col1, col2 = st.columns(2)
with col1:
    st.markdown(t('param_growth_margins'))
    revenue_growth_1 = _param_slider(
        _lbl_rg1, 'revenue_growth_1', 0.5, "%.1f", "p_rg1",
        min_val=-30.0, max_val=_rg1_max, default_val=round(_rg_ref.get('latest', _rg_default), 1),
        help_text=_help_rg1,
        hist_key='rev_growth')
    revenue_growth_2 = _param_slider(
        _lbl_rg2, 'revenue_growth_2', 0.5, "%.1f", "p_rg2",
        min_val=-20.0, max_val=_rg2_max, default_val=_rg_default,
        help_text=_help_rg2,
        hist_key='rev_growth')
    ebit_margin = _param_slider(
        t('param_ebit_margin'), 'ebit_margin', 0.5, "%.1f", "p_em",
        min_val=_em_min, max_val=_em_max, default_val=_em_default,
        help_text=t('help_ebit_margin'),
        hist_key='ebit_margin')
    convergence = _param_slider(
        t('param_convergence'), 'convergence', 1.0, "%.0f", "p_conv",
        min_val=1.0, max_val=10.0, default_val=5.0,
        help_text=t('help_convergence'))
    tax_rate = _param_slider(
        t('param_tax_rate'), 'tax_rate', 0.5, "%.1f", "p_tax",
        min_val=0.0, max_val=45.0, default_val=round(ss.average_tax_rate * 100, 1),
        help_text=t('help_tax_rate'),
        hist_key='tax_rate')
with col2:
    st.markdown(t('param_efficiency'))
    # Determine sensible Rev/IC range from historical data
    _ric_ref = _hist_refs.get('rev_ic', {})
    _ric_max = max(6.0, round((_ric_ref.get('max', 4.0)) * 1.5, 1))
    rev_ic_1 = _param_slider(
        _lbl_ric1, 'revenue_invested_capital_ratio_1', 0.05, "%.2f", "p_ric1",
        min_val=0.10, max_val=_ric_max, default_val=round(_ric_ref.get('latest', 2.0), 2),
        help_text=t('help_ric'),
        hist_key='rev_ic', hist_fmt="%.2f", hist_suffix="x")
    rev_ic_2 = _param_slider(
        _lbl_ric2, 'revenue_invested_capital_ratio_2', 0.05, "%.2f", "p_ric2",
        min_val=0.10, max_val=_ric_max, default_val=round(_ric_ref.get('avg', 2.0), 2),
        hist_key='rev_ic', hist_fmt="%.2f", hist_suffix="x")
    rev_ic_3 = _param_slider(
        _lbl_ric3, 'revenue_invested_capital_ratio_3', 0.05, "%.2f", "p_ric3",
        min_val=0.10, max_val=_ric_max, default_val=round(_ric_ref.get('avg', 1.5), 2),
        hist_key='rev_ic', hist_fmt="%.2f", hist_suffix="x")
    wacc_input = _param_slider(
        t('param_wacc'), 'wacc', 0.1, "%.1f", "p_wacc",
        min_val=4.0, max_val=20.0, default_val=round(ss.wacc * 100, 1),
        help_text=t('help_wacc'))
    # RONIC vs WACC — compact checkbox with explanatory footnote
    ronic_default = False  # Default: ROIC > WACC (assume modest excess returns)
    if has_ai:
        ronic_data = ss.ai_result['parameters'].get('ronic_match_wacc', {})
        if isinstance(ronic_data, dict):
            ronic_default = ronic_data.get('value', False)
        elif isinstance(ronic_data, bool):
            ronic_default = ronic_data
    ronic_match = st.checkbox(
        t('param_ronic_label'),
        value=ronic_default,
        help=t('param_ronic_help'))
    _ronic_note = (
        '<div style="font-size:11px;color:var(--vx-text-muted);margin-top:-8px;margin-bottom:8px;'
        'padding:2px 8px;line-height:1.5;opacity:0.85;">'
        f'{t("param_ronic_note", prem=TERMINAL_RONIC_PREMIUM*100)}'
        '</div>')
    st.markdown(_ronic_note, unsafe_allow_html=True)

ronic = ss.risk_free_rate + TERMINAL_RISK_PREMIUM + (0 if ronic_match else TERMINAL_RONIC_PREMIUM)

if _modified_keys:
    n = len(_modified_keys)
    st.markdown(
        f'<div style="border-left:3px solid #f0883e;padding:6px 14px;margin:8px 0;font-size:13px;color:#f0883e;'
        f'background:rgba(240,136,62,0.06);border-radius:0 6px 6px 0;">'
        f'{t("param_n_modified", n=n, s="s" if n > 1 and lang() == "en" else "")}</div>',
        unsafe_allow_html=True)

# WACC reference
with st.expander(t('wacc_reference'), expanded=False):
    wacc_html = '<div class="wacc-mini">'
    for lbl, val in ss.wacc_details:
        wacc_html += f'<div class="item"><span class="k">{lbl}:</span> <span class="v">{val}</span></div>'
    wacc_html += '</div>'
    st.markdown(wacc_html, unsafe_allow_html=True)

# ── Instant DCF Recalculation ──
# Sliders always have values, so all params are always filled.
# Auto-recalculate whenever parameters change from last snapshot.
_current_raw_snapshot = (
    revenue_growth_1, revenue_growth_2, ebit_margin, convergence,
    tax_rate, rev_ic_1, rev_ic_2, rev_ic_3, wacc_input, ronic_match,
)
# After AI One-Click DCF, save the snapshot from the widget values (first render after rerun)
if ss.pop('_save_snapshot_on_next_render', False):
    ss._last_dcf_input_snapshot = _current_raw_snapshot

_params_changed_since_run = False
_last_snapshot = ss.get('_last_dcf_input_snapshot')
if _last_snapshot is not None and _last_snapshot != _current_raw_snapshot:
    _params_changed_since_run = True

# Auto-recalculate: only when params changed AFTER a first run.
# First run requires explicit action (AI One-Click or user pressing Run DCF).
# This prevents confusing default-value results appearing without user intent.
_should_recalc = _has_results and _params_changed_since_run

def _run_dcf_calc():
    """Execute DCF calculation and store results."""
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
    results = calculate_dcf(
        ss.base_year_data, valuation_params, ss.financial_data, ss.company_info, ss.company_profile)
    ss.results = results
    ss.sensitivity_table = sensitivity_analysis(
        ss.base_year_data, valuation_params, ss.financial_data, ss.company_info, ss.company_profile)
    wacc_results, wacc_base = wacc_sensitivity_analysis(
        ss.base_year_data, valuation_params, ss.financial_data, ss.company_info, ss.company_profile)
    ss.wacc_results = wacc_results
    ss.wacc_base = wacc_base
    ss._last_dcf_input_snapshot = _current_raw_snapshot
    return results

# First-time run: show warning + explicit Run DCF button
if not _has_results:
    st.markdown(
        f'<div class="slider-hint">'
        f'<span class="hint-title">{t("defaults_warning_title")}</span>'
        f'<span class="hint-body">{t("defaults_warning_body")}</span>'
        f'</div>',
        unsafe_allow_html=True)
    if st.button(t('btn_run_dcf'), type="primary", use_container_width=True):
        _run_dcf_calc()
        _has_results = True
        ss._scroll_to_results = True
        st.rerun()

# Auto-recalculate: triggered when sliders change after first run
if _should_recalc:
    _run_dcf_calc()
    _has_results = True
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

    st.markdown(f'<div class="section-hdr">{t("section_cashflow")}</div>', unsafe_allow_html=True)
    st.markdown(_render_dcf_table(results, valuation_params), unsafe_allow_html=True)

    # Forex rate for converting IV to stock trading currency
    _bd_forex = ss.get('forex_rate')
    _bd_needs_forex = (reported_currency and stock_currency
                       and reported_currency != stock_currency)
    if _bd_needs_forex and not _bd_forex:
        _bd_forex, _ = _compute_forex_rate_web(results, ss.company_profile, apikey)
        if _bd_forex:
            ss.forex_rate = _bd_forex

    st.markdown(f'<div class="section-hdr">{t("section_breakdown")}</div>', unsafe_allow_html=True)
    _shares_m = results.get('outstanding_shares', 0) / 1e6  # Convert to millions display
    breakdown_items = [
        (t('bd_pv_fcff'), f"{results['pv_cf_next_10_years']:,.0f}", False, False),
        (t('bd_pv_terminal'), f"{results['pv_terminal_value']:,.0f}", False, False),
        (t('bd_sum_pv'), f"{results['pv_cf_next_10_years'] + results['pv_terminal_value']:,.0f}", True, False),
        (t('bd_cash'), f"{results['cash']:,.0f}", False, False),
        (t('bd_investments'), f"{results['total_investments']:,.0f}", False, False),
        (t('bd_ev'), f"{results['enterprise_value']:,.0f}", True, False),
        (t('bd_debt'), f"{results['total_debt']:,.0f}", False, False),
        (t('bd_minority'), f"{results['minority_interest']:,.0f}", False, False),
        (t('bd_equity'), f"{results['equity_value']:,.0f}", True, False),
        (t('bd_shares'), f"{_shares_m:,.0f}", False, False),
        (t('bd_iv_per_share_cur', cur=reported_currency) if reported_currency else t('bd_iv_per_share'),
         f"{dcf_price:,.2f}", False, True),
    ]
    # Add forex-converted IV line if currencies differ
    if _bd_needs_forex and _bd_forex:
        _bd_iv_converted = dcf_price * _bd_forex
        breakdown_items.append(
            (t('bd_iv_per_share_cur', cur=stock_currency),
             f"{_bd_iv_converted:,.2f}  (× {_bd_forex:.4f})", False, True))
    elif not reported_currency and stock_currency:
        # No conversion needed but show currency
        breakdown_items[-1] = (
            t('bd_iv_per_share_cur', cur=stock_currency),
            f"{dcf_price:,.2f}", False, True)
    bd_html = '<div class="val-breakdown">'
    for label, val, is_sub, is_hl in breakdown_items:
        cls = 'highlight' if is_hl else ('subtotal' if is_sub else '')
        bd_html += f'<div class="row {cls}"><span>{label}</span><span>{val}</span></div>'
    bd_html += '</div>'
    st.markdown(bd_html, unsafe_allow_html=True)

    # Sensitivity Analysis — values converted to stock trading currency if forex needed
    _sens_forex = _bd_forex if (_bd_needs_forex and _bd_forex) else None
    _sens_cur = stock_currency if _sens_forex else (reported_currency or stock_currency or '')

    st.markdown(f'<div class="section-hdr">{t("section_sensitivity")}</div>', unsafe_allow_html=True)

    st.markdown(t('sens_rev_vs_ebit', cur=_sens_cur))
    _base_growth = valuation_params.get('revenue_growth_2')
    _base_margin = valuation_params.get('ebit_margin')

    # Build HTML table — terminal / Excel style with crosshair highlighting
    _stbl = ss.sensitivity_table
    _s_html = '<div style="overflow-x:auto;"><table class="sens-table">'
    # Header row: axis label + EBIT Margin column headers
    _s_html += f'<tr><th class="sens-axis-label" style="border-bottom:2px solid #333;">{t("sens_ebit_axis")}<br><span style="font-style:normal;">{t("sens_growth_axis")}</span></th>'
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
            _display_val = val * _sens_forex if _sens_forex else val
            formatted = f"{_display_val:,.0f}"
            if idx == _base_growth and col == _base_margin:
                _s_html += f'<td class="sens-hl-center">{formatted}</td>'
            elif idx == _base_growth or col == _base_margin:
                _s_html += f'<td class="sens-hl-cross">{formatted}</td>'
            else:
                _s_html += f'<td>{formatted}</td>'
        _s_html += '</tr>'
    _s_html += '</table></div>'
    st.markdown(_s_html, unsafe_allow_html=True)

    st.markdown(t('sens_wacc_title', cur=_sens_cur))
    _w_html = '<div style="overflow-x:auto;"><table class="wacc-sens-table">'
    # Header: WACC labels
    _w_html += f'<tr><td class="wacc-label">{t("sens_wacc_label")}</td>'
    for w in ss.wacc_results.keys():
        _hl = ' sens-hl-col' if w == ss.wacc_base else ''
        _w_html += f'<th class="{_hl}">{w:.1f}%</th>'
    _w_html += '</tr>'
    # Values row
    _w_html += f'<tr><td class="wacc-label">{t("sens_price_share")}</td>'
    for w, p in ss.wacc_results.items():
        _display_p = p * _sens_forex if _sens_forex else p
        if w == ss.wacc_base:
            _w_html += f'<td class="sens-hl-center">{_display_p:,.0f}</td>'
        else:
            _w_html += f'<td>{_display_p:,.0f}</td>'
    _w_html += '</tr>'
    _w_html += '</table></div>'
    st.markdown(_w_html, unsafe_allow_html=True)

    # Gap Analysis results
    if 'gap_analysis_result' in ss and ss.gap_analysis_result:
        gap = ss.gap_analysis_result
        _gap_just_done = ss.pop('_gap_just_completed', False)
        _gap_adj_str = ''
        if gap.get('adjusted_price') is not None:
            _gap_adj_str = f" · Adjusted: <b>{gap['adjusted_price']:,.2f} {gap['currency']}</b>"
        st.markdown('<div id="gap-analysis-anchor"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="expander-hint"><span class="icon">📊</span>'
            f'{t("gap_hint", adj=_gap_adj_str)}</div>',
            unsafe_allow_html=True)
        with st.expander(t('gap_expander'), expanded=_gap_just_done):
            if gap.get('adjusted_price') is not None:
                adj = gap['adjusted_price']
                st.success(t('gap_adjusted', val=adj, cur=gap['currency']))
            display_text = re.sub(r'\n?\s*ADJUSTED_PRICE:.*$', '', gap.get('analysis_text', '')).strip()
            # Convert markdown → HTML so we can wrap everything inside a
            # single <div class="ai-card">.  Streamlit wraps each
            # st.markdown() call in its own DOM node, so a separate opening
            # tag + content + closing tag would NOT create a parent-child
            # relationship.  Using Python-markdown ensures headings end up
            # *inside* .ai-card, where the CSS size constraints apply.
            try:
                import markdown as _md_lib
                _gap_html = _md_lib.markdown(display_text, extensions=['tables'])
            except ImportError:
                # Fallback: let Streamlit render markdown normally (headings
                # won't be size-constrained but content is still readable).
                st.markdown(display_text)
                _gap_html = None
            if _gap_html is not None:
                st.markdown(f'<div class="ai-card">{_gap_html}</div>', unsafe_allow_html=True)

# ── Auto-scroll — only after a fresh DCF run, AI run, or gap analysis ──
if ss.get('_scroll_to_results'):
    ss._scroll_to_results = False
    _scroll_to("dcf-results")
elif _did_ai_run:
    _scroll_to("valuation-params")
elif _gap_just_done:
    _scroll_to("gap-analysis-anchor")

# ── Footer — tagline only ──
st.markdown(f"""
<div style="margin-top:48px; padding:16px 0 8px 0; border-top:1px solid var(--vx-border-light, #d0d7de); text-align:center; color:var(--vx-text-muted, #8b949e); font-size:0.78rem;">
    {t('footer_tagline_web') if not _has_ai else t('footer_tagline')}
</div>
""", unsafe_allow_html=True)
