# Copyright (c) 2026 Alan He. Licensed under MIT.
"""ValueScope Streamlit Web App — DCF Stock Valuation."""

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
    cloud_ai_analyze,
    cloud_gap_analyze,
    SerperCreditError,
    DeepSeekCreditError,
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
st.set_page_config(page_title="ValueScope", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

# ── AI availability flags ──
# _has_ai: local CLI (Claude/Gemini/Qwen) is installed
# _has_cloud_ai: Serper + DeepSeek API keys are available (for Streamlit Cloud)
_has_ai = (_AI_ENGINE is not None)

def _get_secret(key):
    """Get a secret from environment or Streamlit secrets."""
    val = os.environ.get(key, "")
    if not val:
        try:
            val = st.secrets[key]
        except (KeyError, FileNotFoundError, Exception):
            val = ""
    return val or ""

_ADMIN_SERPER_KEY = _get_secret("SERPER_API_KEY")
_ADMIN_DEEPSEEK_KEY = _get_secret("DEEPSEEK_API_KEY")
_has_cloud_ai = bool(_ADMIN_SERPER_KEY and _ADMIN_DEEPSEEK_KEY)


def _get_effective_cloud_keys():
    """Return (serper_key, deepseek_key, is_user_keys).

    User-provided keys (from sidebar) take priority over admin secrets.
    """
    user_serper = st.session_state.get('user_serper_key', '').strip()
    user_deepseek = st.session_state.get('user_deepseek_key', '').strip()
    if user_serper and user_deepseek:
        return user_serper, user_deepseek, True
    return _ADMIN_SERPER_KEY, _ADMIN_DEEPSEEK_KEY, False


def _cloud_ai_available():
    """Check if cloud AI is available (admin keys OR user-provided keys)."""
    serper, deepseek, _ = _get_effective_cloud_keys()
    return bool(serper and deepseek)


# ── Ticker autocomplete: static JSON served via Streamlit static files ──
# .streamlit/static/tickers.json contains ~10K tickers (symbol, name, exchange)
# JS loads it once, then searches client-side — no API key needed.


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

# ── SEO meta tags & structured data ──
import streamlit.components.v1 as _seo_components
_seo_components.html("""
<script>
(function() {
    var doc = window.parent.document;
    if (doc.querySelector('meta[name="description"]')) return;  // already injected
    var head = doc.head;
    var m = function(name, content) {
        var el = doc.createElement('meta');
        el.setAttribute('name', name);
        el.setAttribute('content', content);
        head.appendChild(el);
    };
    var p = function(prop, content) {
        var el = doc.createElement('meta');
        el.setAttribute('property', prop);
        el.setAttribute('content', content);
        head.appendChild(el);
    };
    // Basic meta
    m('description', 'ValueScope — 免费 AI 驱动的 DCF 股票估值工具。支持 A 股、港股、美股，一键 AI 估值，实时参数调节，敏感性分析，Excel 导出。Free AI-powered DCF stock valuation for A-shares, HK & US stocks.');
    m('keywords', 'DCF估值,股票估值,内在价值,现金流折现,AI估值,一键估值,A股估值,港股估值,美股估值,WACC,免费估值工具,DCF计算器,stock valuation,intrinsic value,free cash flow,AI valuation');
    // Open Graph
    p('og:title', 'ValueScope — AI 智能 DCF 股票估值工具');
    p('og:description', '免费 AI 驱动的 DCF 估值工具。支持 A 股、港股、美股，一键 AI 估值 + 实时参数调节 + 敏感性分析 + Excel 导出。');
    p('og:type', 'website');
    p('og:url', 'https://valuescope.app');
    p('og:image', 'https://valuescope.app/og-image.png');
    p('og:image:width', '1200');
    p('og:image:height', '630');
    p('og:locale', 'zh_CN');
    // Twitter Card
    m('twitter:card', 'summary_large_image');
    m('twitter:title', 'ValueScope — AI 智能 DCF 股票估值工具');
    m('twitter:description', '免费 AI 驱动的 DCF 估值工具。支持 A 股、港股、美股，一键估值 + 敏感性分析 + Excel 导出。');
    m('twitter:image', 'https://valuescope.app/og-image.png');
    // Canonical URL
    var link = doc.createElement('link');
    link.setAttribute('rel', 'canonical');
    link.setAttribute('href', 'https://valuescope.app');
    head.appendChild(link);
    // JSON-LD structured data
    var ld = doc.createElement('script');
    ld.setAttribute('type', 'application/ld+json');
    ld.textContent = JSON.stringify({
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "ValueScope",
        "alternateName": "ValueScope AI 估值工具",
        "description": "免费 AI 驱动的 DCF 股票估值工具，支持 A 股、港股、美股。提供一键 AI 估值、实时参数调节、敏感性分析和 Excel 导出。",
        "url": "https://valuescope.app",
        "applicationCategory": "FinanceApplication",
        "operatingSystem": "Web",
        "inLanguage": ["zh-CN", "en"],
        "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
        "author": { "@type": "Person", "name": "Alan He" }
    });
    head.appendChild(ld);
})();
</script>
""", height=0)

# ── Initialize language early so all t() calls during sidebar rendering work ──
# Language is toggled via EN/CN buttons in the sidebar brand area.
# They set st.session_state._lang directly and call st.rerun().
if '_lang' not in st.session_state:
    st.session_state._lang = 'en'

# ── Force sidebar open on first load ──
import streamlit.components.v1 as _components
_components.html("""
<script>
(function() {
    var doc = window.parent.document;
    // Clear cached collapsed state so sidebar always starts expanded
    Object.keys(window.parent.localStorage).forEach(function(key) {
        if (key.indexOf('stSidebarCollapsed') === 0) {
            window.parent.localStorage.removeItem(key);
        }
    });
    var sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (sidebar && sidebar.getAttribute('aria-expanded') === 'false') {
        var btn = doc.querySelector('[data-testid="stSidebarCollapsedControl"] button')
                || doc.querySelector('[data-testid="collapsedControl"] button');
        if (btn) btn.click();
    }
})();
</script>
""", height=0)

st.markdown("""
<style>
/* ══════════════════════════════════════════════════════════════
   ValueScope CSS — System theme–aware (light/dark)
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
/* Hide Streamlit chrome but keep sidebar expand button visible */
header[data-testid="stHeader"] {
    background: transparent !important;
    height: auto !important;
}
#MainMenu,
[data-testid="stStatusWidget"],
[data-testid="stHeader"] [data-testid="stDecoration"],
[data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"] { display: none !important; }

/* ── Sticky header ── */
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr),
div[data-testid="stVerticalBlockBorderWrapper"]:has(div.vs-sticky-hdr) {
    position: sticky !important; top: 0 !important; z-index: 999991 !important;
    background: var(--vx-bg) !important;
    border-bottom: 1px solid var(--vx-border-light);
    box-shadow: var(--vx-shadow);
    padding: 6px 0 !important;
}
div.vs-sticky-hdr { height: 0; overflow: hidden; margin: 0; padding: 0; line-height: 0; font-size: 0; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stVerticalBlock"] { gap: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stElementContainer"] { margin: 0 !important; }

/* ── Header action buttons & company name ── */
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] { align-items: center !important; min-height: 48px; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"] { display: flex !important; align-items: center !important; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"] > div { width: 100%; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stMarkdownContainer"] p { margin-bottom: 0 !important; padding: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] button,
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] a[data-testid="stDownloadButton"] button {
    height: 42px !important; padding: 2px 6px !important; font-size: 0.66rem !important;
    white-space: pre-line !important; display: flex !important; align-items: center !important;
    justify-content: center !important; text-align: center !important; line-height: 1.2 !important;
    background: var(--vx-accent-light) !important;
    border: 1px solid color-mix(in srgb, var(--vx-accent) 30%, transparent) !important;
    color: var(--vx-accent) !important;
    border-radius: 6px !important; transition: all 0.15s ease !important;
}
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] button:hover,
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] a[data-testid="stDownloadButton"] button:hover {
    background: color-mix(in srgb, var(--vx-accent) 18%, transparent) !important;
    border-color: color-mix(in srgb, var(--vx-accent) 50%, transparent) !important;
}

/* ── Sticky verdict bar (second row, below company header) ── */
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hero),
div[data-testid="stVerticalBlockBorderWrapper"]:has(div.vs-sticky-hero) {
    position: sticky !important; top: 60px !important; z-index: 999990 !important;
    background: var(--vx-bg) !important;
    border-bottom: 1px solid var(--vx-border-light);
    padding: 0 !important;
}
div.vs-sticky-hero { height: 0; overflow: hidden; margin: 0; padding: 0; line-height: 0; font-size: 0; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hero) div[data-testid="stVerticalBlock"] { gap: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hero) div[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hero) div[data-testid="stElementContainer"] { margin: 0 !important; }

/* ── Verdict card ── */
.verdict-card {
    border-radius: 12px; padding: 16px 24px; margin: 8px 0;
    display: flex; align-items: center; justify-content: space-between; gap: 28px; flex-wrap: wrap;
}
.verdict-card.buy  { background: var(--vx-hero-positive); border: 1px solid rgba(46,204,113,0.3); }
.verdict-card.hold { background: var(--vx-hero-neutral); border: 1px solid var(--vx-border); }
.verdict-card.sell { background: var(--vx-hero-negative); border: 1px solid rgba(231,76,60,0.3); }
.verdict-badge {
    display: inline-flex; flex-direction: column; align-items: center; gap: 2px; min-width: 100px;
}
.verdict-badge .badge-label {
    font-size: 1.4rem; font-weight: 900; letter-spacing: 1.5px; text-transform: uppercase; line-height: 1;
}
.verdict-card.buy .badge-label  { color: var(--vx-green); }
.verdict-card.hold .badge-label { color: var(--vx-text-muted); }
.verdict-card.sell .badge-label { color: var(--vx-red); }
.verdict-badge .badge-sub {
    font-size: 0.72rem; color: var(--vx-text-secondary); text-align: center; line-height: 1.2;
}
.verdict-metrics {
    display: flex; align-items: center; gap: 28px; flex-wrap: wrap; flex: 1; justify-content: flex-end;
}
.verdict-metric { text-align: right; }
.verdict-metric .vm-label {
    font-size: 0.68rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;
}
.verdict-metric .vm-val { font-size: 1.5rem; font-weight: 800; line-height: 1; }
.verdict-metric .vm-val.intrinsic { color: var(--vx-intrinsic); }
.verdict-metric .vm-val.market   { color: var(--vx-market-num); }
.verdict-vs { font-size: 1.1rem; color: var(--vx-text-muted); font-weight: 300; align-self: center; }
.verdict-mos { text-align: right; min-width: 100px; padding-left: 8px; border-left: 1px solid rgba(128,128,128,0.2); }
.verdict-mos .vm-label { font-size: 0.68rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
.verdict-mos .vm-pct { font-size: 1.5rem; font-weight: 800; line-height: 1; }
.verdict-card.buy  .verdict-mos .vm-pct { color: var(--vx-green); }
.verdict-card.hold .verdict-mos .vm-pct { color: var(--vx-text-secondary); }
.verdict-card.sell .verdict-mos .vm-pct { color: var(--vx-red); }

/* ── Summary cards (4 metric cards below verdict) ── */
.summary-cards {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 4px 0 8px 0;
}
.summary-card {
    background: var(--vx-card-bg); border: 1px solid var(--vx-card-border);
    border-radius: 8px; padding: 10px 14px; text-align: center;
}
.summary-card .sc-label { font-size: 0.68rem; color: var(--vx-text-muted); text-transform: uppercase; letter-spacing: 0.4px; }
.summary-card .sc-val { font-size: 1.3rem; font-weight: 700; color: var(--vx-text); margin-top: 2px; }

/* ── Global backgrounds — follow system theme ── */
section[data-testid="stSidebar"] > div { padding-top: 0 !important; }
[data-testid="stSidebarContent"] { padding-top: 0 !important; }
[data-testid="stSidebarUserContent"] { padding-top: 0 !important; }
/* Compact sidebar vertical spacing */
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 0.75rem !important; }
/* Auto-push footer to bottom of sidebar */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div[data-testid="stVerticalBlock"] { min-height: 100%; display: flex; flex-direction: column; }
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]:has(> div[data-testid="stVerticalBlock-vs_sidebar_footer"]) > div:last-child { margin-top: auto; }
[data-testid="stSidebarHeader"] {
    display: flex !important; min-height: 28px; justify-content: flex-end;
    padding: 2px 4px 0 0 !important;
}
[data-testid="stSidebarCollapseButton"] { visibility: visible !important; }
[data-testid="stSidebarCollapseButton"] button { visibility: visible !important; }
[data-testid="stLogoSpacer"] { display: none !important; }
@media (max-width: 768px) {
    [data-testid="stSidebarHeader"] { min-height: 44px; padding: 4px 8px 0 0 !important; }
}

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

/* ── Ticker input — Google-style pill with soft shadow ── */
/* Suppress Streamlit's default input wrapper styling */
section[data-testid="stSidebar"] div[data-testid="stTextInput"] > div,
section[data-testid="stSidebar"] div[data-testid="stTextInput"] [data-baseweb="base-input"],
section[data-testid="stSidebar"] div[data-testid="stTextInput"] [data-baseweb="input"] {
    border-color: transparent !important; background: transparent !important;
    overflow: visible !important; border-radius: 22px !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] div:focus-within {
    border-color: transparent !important; box-shadow: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input {
    border: 1px solid var(--vx-border-light, #e0e0e0) !important;
    border-radius: 22px !important;
    font-size: 1.1rem !important; font-weight: 600 !important;
    padding: 12px 14px 12px 40px !important;
    min-height: 48px !important;
    background: var(--vx-input-bg, #fff) !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='%239aa0a6' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: 14px center !important;
    background-size: 18px 18px !important;
    color: var(--vx-text, #1f2328) !important;
    transition: box-shadow 0.2s ease, border-color 0.2s ease !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input:hover {
    box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important;
    border-color: #ccc !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input:focus {
    border-color: transparent !important;
    box-shadow: 0 1px 6px rgba(0,0,0,0.12) !important;
}
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input::placeholder {
    color: var(--vx-text-muted, #8b949e) !important; font-weight: 400 !important;
    font-size: 0.92rem !important;
}
/* ── Expander text inputs — reset to normal rectangular style ── */
section[data-testid="stSidebar"] details[data-testid="stExpander"] div[data-testid="stTextInput"] input {
    padding: 6px 10px !important; padding-left: 10px !important;
    border-radius: 6px !important;
    border: 1.5px solid var(--vx-border, #d0d7de) !important;
    font-size: 0.85rem !important; min-height: auto !important;
    background-image: none !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] div[data-testid="stTextInput"] input:hover {
    box-shadow: none !important; border-color: var(--vx-border, #d0d7de) !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] div[data-testid="stTextInput"] input:focus {
    border-color: var(--vx-accent, #0969da) !important;
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--vx-accent) 15%, transparent) !important;
}
div[data-testid="stSidebarCollapsedControl"] {
    z-index: 999999 !important;
}
/* Mobile: make sidebar expand button larger and more visible */
@media (max-width: 768px) {
    div[data-testid="stSidebarCollapsedControl"] {
        top: 0.5rem !important;
        left: 0.5rem !important;
    }
    div[data-testid="stSidebarCollapsedControl"] button {
        width: 44px !important;
        height: 44px !important;
        background: var(--vx-bg, #fff) !important;
        border: 1px solid var(--vx-border, #d0d7de) !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
    }
    div[data-testid="stSidebarCollapsedControl"] button svg {
        width: 20px !important;
        height: 20px !important;
    }
}

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

/* ── Sidebar action buttons — distinct colours for Custom vs AI ── */
/* Custom button (secondary): deep navy outline, filled on hover */
section[data-testid="stSidebar"] button[kind="secondary"] {
    font-weight: 600 !important; letter-spacing: 0.3px;
    border: 2px solid #1a3a5c !important;
    color: #1a3a5c !important;
    background: transparent !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background: #1a3a5c !important;
    color: #fff !important;
}
/* Dark mode: brighten Custom button for visibility */
@media (prefers-color-scheme: dark) {
  section[data-testid="stSidebar"] button[kind="secondary"] {
    border-color: #5b9bd5 !important; color: #5b9bd5 !important;
  }
  section[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background: #5b9bd5 !important; color: #fff !important;
  }
}
[data-testid="stAppViewContainer"][data-theme="dark"] ~ * section[data-testid="stSidebar"] button[kind="secondary"],
html[data-theme="dark"] section[data-testid="stSidebar"] button[kind="secondary"],
:root[data-theme="dark"] section[data-testid="stSidebar"] button[kind="secondary"] {
    border-color: #5b9bd5 !important; color: #5b9bd5 !important;
}
[data-testid="stAppViewContainer"][data-theme="dark"] ~ * section[data-testid="stSidebar"] button[kind="secondary"]:hover,
html[data-theme="dark"] section[data-testid="stSidebar"] button[kind="secondary"]:hover,
:root[data-theme="dark"] section[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background: #5b9bd5 !important; color: #fff !important;
}
/* AI button (primary): bright blue fill */
section[data-testid="stSidebar"] button[kind="primary"] {
    font-weight: 600 !important; letter-spacing: 0.3px;
    border: 2px solid #2b8be8 !important;
    background: #2b8be8 !important;
    color: #fff !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] button[kind="primary"]:hover {
    background: transparent !important;
    color: #2b8be8 !important;
    border-color: #2b8be8 !important;
}

/* ── Reduce vertical gap between sidebar action buttons (or divider area) ── */
section[data-testid="stSidebar"] div[data-testid="stElementContainer"]:has(button) {
    margin-bottom: -4px !important;
}

/* ── Sidebar expanders — subdued card style ── */
section[data-testid="stSidebar"] details[data-testid="stExpander"] {
    border: 1px solid var(--vx-border-light, #e8e8e8) !important;
    border-radius: 8px !important;
    background: color-mix(in srgb, var(--vx-bg, #fff) 97%, var(--vx-border, #d0d7de)) !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] summary {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    padding: 6px 12px !important;
    color: var(--vx-text-muted, #666) !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] summary:hover {
    color: var(--vx-text, #1f2328) !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] label {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] input {
    font-size: 0.85rem !important;
    padding: 6px 10px !important;
    border-width: 1.5px !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] .stCaption p {
    font-size: 0.78rem !important;
    font-weight: 400 !important;
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

    /* Verdict card: stack on mobile */
    .verdict-card {
        flex-direction: column; align-items: stretch; gap: 10px; padding: 12px 14px;
    }
    .verdict-badge .badge-label { font-size: 1.1rem; }
    .verdict-metrics { gap: 12px; justify-content: center; }
    .verdict-metric { text-align: center; }
    .verdict-metric .vm-val { font-size: 1.2rem; }
    .verdict-mos { text-align: center; border-left: none; padding-left: 0; border-top: 1px solid rgba(128,128,128,0.15); padding-top: 8px; }
    .verdict-mos .vm-pct { font-size: 1.2rem; }
    .verdict-vs { display: none; }
    .summary-cards { grid-template-columns: repeat(2, 1fr); gap: 8px; }
    .summary-card .sc-val { font-size: 1.1rem; }

    /* Hide sticky header action buttons on mobile — only show company name */
    div[data-testid="stLayoutWrapper"]:has(div.vs-sticky-hdr) div[data-testid="stHorizontalBlock"] div[data-testid="stColumn"]:not(:first-child) {
        display: none !important;
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

    /* Force single-column layout on mobile — main content only (not sidebar) */
    [data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
    }
    [data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* ── Sidebar: keep language buttons in a row ── */
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        justify-content: center !important;
        gap: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
        width: 5rem !important;
        max-width: 5rem !important;
        min-width: 0 !important;
        flex: 0 0 auto !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] button {
        width: auto !important;
        min-width: 0 !important;
    }

    /* ── Sidebar: full-width overlay on mobile ── */
    section[data-testid="stSidebar"] {
        width: 100vw !important;
        min-width: 100vw !important;
        max-width: 100vw !important;
    }
    /* Fully hide sidebar when collapsed (Streamlit uses translateX(-300px) by default) */
    section[data-testid="stSidebar"][aria-expanded="false"] {
        transform: translateX(-100vw) !important;
    }

    /* ── Sidebar collapse button (✕): replace Material Symbols icon ── */
    [data-testid="stSidebarCollapseButton"] button {
        width: 44px !important;
        height: 44px !important;
        overflow: hidden !important;
        font-size: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [data-testid="stSidebarCollapseButton"] button * {
        display: none !important;
    }
    [data-testid="stSidebarCollapseButton"] button::after {
        content: "✕";
        display: block !important;
        font-size: 1.3rem;
        font-family: system-ui, -apple-system, sans-serif;
        color: var(--vx-text-secondary, #666);
    }

    /* ── Sidebar expand button (☰): large & visible when collapsed ── */
    [data-testid="stExpandSidebarButton"] {
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        z-index: 999999 !important;
        width: 44px !important;
        height: 44px !important;
        border-radius: 10px !important;
        background: var(--vx-accent, #0969da) !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2) !important;
        overflow: hidden !important;
        font-size: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [data-testid="stExpandSidebarButton"] * {
        display: none !important;
    }
    [data-testid="stExpandSidebarButton"]::after {
        content: "☰";
        display: block !important;
        font-size: 1.3rem;
        font-family: system-ui, -apple-system, sans-serif;
        color: #fff;
    }

    /* Touch targets — Apple HIG minimum 44px */
    .stButton > button,
    a[data-testid="stDownloadButton"] > button {
        min-height: 44px !important;
    }

    /* Disable sticky header on mobile (saves vertical space) */
    .vs-sticky-hdr {
        position: static !important;
    }

    /* Welcome page compact on mobile */
    .vx-welcome {
        padding: 20px 12px 20px 12px !important;
    }
    .vx-welcome p:first-child { font-size: 2.4rem !important; }
    .vx-welcome p:nth-child(3) { font-size: 0.92rem !important; }  /* instruction text */
}

/* ── Tablet (769px – 1024px) ── */
@media (min-width: 769px) and (max-width: 1024px) {
    .verdict-metric .vm-val { font-size: 1.3rem; }
    .verdict-badge .badge-label { font-size: 1.2rem; }
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
# AI quota helpers (must be defined before sidebar uses them)
# ────────────────────────────────────────────────────────────────
def _get_client_id():
    """Get client IP from Streamlit Cloud headers, fallback to 'local'."""
    try:
        headers = st.context.headers  # Streamlit 1.37+
        forwarded = headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
    except Exception:
        pass
    return 'local'


def _is_admin():
    """Check if current user is admin via ?admin=<key> query param."""
    admin_key = _get_secret('VS_ADMIN_KEY')
    if not admin_key:
        return False
    try:
        params = st.query_params
        return params.get('admin', '') == admin_key
    except Exception:
        return False


def _check_ai_quota():
    """Returns (allowed: bool, used: int, limit: int).

    Admin users (via ?admin=<key>) bypass the limit entirely.
    Users providing their own API keys bypass the limit entirely.
    Uses DB-backed tracking when VS_DB_PATH is set, otherwise falls back
    to session-state tracking (per-session, per-IP).
    The effective limit = base limit + any extra quota granted by admin.
    """
    if _is_admin():
        return True, 0, 0  # Admin = unlimited
    # User-provided keys bypass quota
    _, _, is_user_keys = _get_effective_cloud_keys()
    if is_user_keys:
        return True, 0, 0
    base_limit = int(_get_secret('VS_AI_DAILY_LIMIT') or '5')
    if base_limit <= 0:  # 0 or negative = unlimited
        return True, 0, 0
    db_path = _get_secret('VS_DB_PATH')
    if db_path:
        from modeling.db_export import get_ai_usage_today, get_extra_quota_today
        client_id = _get_client_id()
        used = get_ai_usage_today(db_path, client_id)
        extra = get_extra_quota_today(db_path, client_id)
        effective_limit = base_limit + extra
    else:
        # Fallback: session-state tracking (resets on redeploy / new session)
        _key = '_ai_usage_count'
        used = st.session_state.get(_key, 0)
        effective_limit = base_limit
    return used < effective_limit, used, effective_limit


def _record_ai_usage(ticker=None):
    """Record an AI usage event (DB + session-state fallback). Admin and user-key users skip recording."""
    if _is_admin():
        return
    _, _, is_user_keys = _get_effective_cloud_keys()
    if is_user_keys:
        return
    # Always bump session counter
    _key = '_ai_usage_count'
    st.session_state[_key] = st.session_state.get(_key, 0) + 1
    # DB tracking if available
    db_path = _get_secret('VS_DB_PATH')
    if not db_path:
        return
    from modeling.db_export import record_ai_usage
    client_id = _get_client_id()
    record_ai_usage(db_path, client_id, ticker)


# ────────────────────────────────────────────────────────────────
# Sidebar — ValueScope brand at top, then ticker + buttons
# ────────────────────────────────────────────────────────────────
with st.sidebar:
    _cur = lang()  # 'en' or 'zh'
    st.markdown(f"""
    <div class="sidebar-brand">
        <h1>ValueScope</h1>
        <div class="sub">{t('sidebar_brand_sub_web') if not (_has_ai or _has_cloud_ai) else t('sidebar_brand_sub')}</div>
    </div>
    """, unsafe_allow_html=True)
    # ── Language switch: two tiny buttons styled as text ──
    _lc1, _lc2 = st.columns(2)
    with _lc1:
        if st.button("English", key="_lang_en_btn", use_container_width=True,
                      type="primary" if _cur == 'en' else "secondary"):
            st.session_state._lang = 'en'
            st.rerun()
    with _lc2:
        if st.button("\u4e2d\u6587", key="_lang_cn_btn", use_container_width=True,
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
                cols[i].style.cssText = 'width:5rem!important;max-width:5rem!important;min-width:0!important;flex:0 0 auto!important;display:inline-flex!important;';
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

    # Pre-fill ticker from URL query param (?ticker=XXX)
    _url_ticker = ''
    if '_url_ticker_consumed' not in st.session_state:
        try:
            _url_ticker = st.query_params.get('ticker', '')
            if _url_ticker:
                st.session_state._url_ticker_consumed = True
        except Exception:
            pass

    _ticker_label = t('sidebar_ticker_label_web') if not (_has_ai or _has_cloud_ai) else t('sidebar_ticker_label')
    _ticker_ph = t('sidebar_ticker_placeholder_web') if not (_has_ai or _has_cloud_ai) else t('sidebar_ticker_placeholder')

    # Use session state to support suggestion-click → pre-fill
    if '_selected_ticker' in st.session_state:
        _url_ticker = st.session_state.pop('_selected_ticker')

    ticker_input = st.text_input(
        _ticker_label, value=_url_ticker, placeholder=_ticker_ph,
        label_visibility="visible", key="ticker_input_main",
    )

    # ── Real-time autocomplete via static tickers.json (no API key needed) ──
    _stc.html(
        r"""<script>
(function(){
var D=200,M=8;
var P=window.parent.document;
var sb=P.querySelector('section[data-testid="stSidebar"]');
if(!sb) return;
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

// Load ticker data once, cache in window
var tickerData=window._vsTickers;
if(!tickerData){
  tickerData=[];
  window._vsTickers=tickerData;
  fetch('/app/static/tickers.json').then(function(r){return r.json();}).then(function(d){
    tickerData.push.apply(tickerData,d);
    window._vsTickers=tickerData;
  }).catch(function(){});
}

function search(q){
  if(!tickerData.length) return [];
  var ql=q.toLowerCase(),results=[],exact=[],starts=[],contains=[];
  for(var i=0;i<tickerData.length;i++){
    var t=tickerData[i],sl=t.s.toLowerCase(),nl=t.n.toLowerCase();
    if(sl===ql){exact.push(t);}
    else if(sl.indexOf(ql)===0){starts.push(t);}
    else if(nl.indexOf(ql)!==-1||sl.indexOf(ql)!==-1){contains.push(t);}
    if(exact.length+starts.length+contains.length>50) break;
  }
  return exact.concat(starts,contains).slice(0,M);
}

function tryInit(){
  var inp=sb.querySelector('div[data-testid="stTextInput"] input');
  if(!inp){setTimeout(tryInit,100);return;}
  if(inp._acInit) return;
  inp._acInit=true;
  var dd=P.createElement('div');
  dd.style.cssText='position:absolute;top:100%;left:0;right:0;background:#ffffff;border:1px solid #e0e0e0;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.12);z-index:999999;display:none;max-height:300px;overflow-y:auto;margin-top:4px;';
  var wrap=inp.closest('div[data-testid="stTextInput"]');
  if(wrap){wrap.style.position='relative';wrap.style.overflow='visible';wrap.appendChild(dd);}
  var timer=null,ai=-1,picking=false;
  function doSearch(q){
    if(!q||q.length<1){dd.style.display='none';return;}
    var data=search(q);
    if(!data.length){dd.style.display='none';return;}
    dd.innerHTML='';ai=-1;
    data.forEach(function(it,i){
      var o=P.createElement('div');
      o.innerHTML='<strong style="color:#1f2328;">'+esc(it.s)+'</strong>'
        +'<span style="color:#666;margin-left:8px;font-size:0.82em;">'+esc(it.n)+'</span>'
        +(it.x?'<span style="color:#999;margin-left:4px;font-size:0.75em;">('+esc(it.x)+')</span>':'');
      o.style.cssText='padding:9px 14px;cursor:pointer;font-size:0.88rem;border-bottom:1px solid #f0f0f0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background 0.1s;background:#fff;';
      o.dataset.sym=it.s;
      o.addEventListener('mouseenter',function(){o.style.background='#eef3ff';ai=i;});
      o.addEventListener('mouseleave',function(){o.style.background='#fff';});
      o.addEventListener('mousedown',function(e){e.preventDefault();pick(it.s);});
      dd.appendChild(o);
    });
    if(dd.firstChild) dd.firstChild.style.borderRadius='12px 12px 0 0';
    if(dd.lastChild){dd.lastChild.style.borderRadius='0 0 12px 12px';dd.lastChild.style.borderBottom='none';}
    if(dd.childNodes.length===1) dd.firstChild.style.borderRadius='12px';
    dd.style.display='block';
  }
  function pick(sym){
    picking=true;clearTimeout(timer);
    var setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    setter.call(inp,sym);
    inp.dispatchEvent(new Event('input',{bubbles:true}));
    inp.dispatchEvent(new Event('change',{bubbles:true}));
    dd.style.display='none';dd.innerHTML='';
    setTimeout(function(){
      inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
      inp.blur();
    },80);
    setTimeout(function(){picking=false;},400);
  }
  inp.addEventListener('input',function(e){
    if(picking) return;
    clearTimeout(timer);
    var v=e.target.value;
    if(!v||v.length<1){dd.style.display='none';return;}
    timer=setTimeout(function(){doSearch(v);},D);
  });
  inp.addEventListener('keydown',function(e){
    var items=dd.querySelectorAll('div[data-sym]');
    if(!items.length||dd.style.display==='none') return;
    if(e.key==='ArrowDown'){e.preventDefault();ai=Math.min(ai+1,items.length-1);items.forEach(function(it,i){it.style.background=i===ai?'#eef3ff':'#fff';});items[ai].scrollIntoView({block:'nearest'});}
    else if(e.key==='ArrowUp'){e.preventDefault();ai=Math.max(ai-1,0);items.forEach(function(it,i){it.style.background=i===ai?'#eef3ff':'#fff';});items[ai].scrollIntoView({block:'nearest'});}
    else if(e.key==='Enter'&&ai>=0){e.preventDefault();e.stopPropagation();pick(items[ai].dataset.sym);}
    else if(e.key==='Enter'){dd.style.display='none';}
    else if(e.key==='Escape'){dd.style.display='none';}
  });
  P.addEventListener('click',function(e){
    if(!inp.contains(e.target)&&!dd.contains(e.target)) dd.style.display='none';
  });
}
tryInit();
})();
</script>""",
        height=0,
    )

    # ── Action buttons ──
    _any_ai = _has_ai or _cloud_ai_available()
    if 'use_ai' not in st.session_state:
        st.session_state.use_ai = bool(_AI_ENGINE)

    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
    manual_btn = st.button(t('sidebar_manual_btn'), use_container_width=True,
                            help=t('sidebar_manual_help'), key='manual_btn',
                            type="secondary" if _any_ai else "primary")

    if _any_ai:
        st.markdown(
            '<div style="display:flex; align-items:center; justify-content:center; gap:8px; '
            'margin:2px 0; padding:0;">'
            '<div style="width:24px; height:1px; background:var(--vx-border, #d0d7de);"></div>'
            f'<span style="color:var(--vx-text-muted, #999); font-size:0.7rem; letter-spacing:0.5px;">{t("sidebar_or")}</span>'
            '<div style="width:24px; height:1px; background:var(--vx-border, #d0d7de);"></div>'
            '</div>',
            unsafe_allow_html=True)

        # Check AI quota for button state
        _sb_allowed, _sb_used, _sb_limit = _check_ai_quota()
        oneclick_btn = st.button(t('sidebar_oneclick_btn'), type="primary", use_container_width=True,
                                  help=t('sidebar_oneclick_help'), key='oneclick_btn',
                                  disabled=not _sb_allowed)
        if _sb_limit > 0:
            _sb_remaining = _sb_limit - _sb_used
            st.caption(t('ai_quota_remaining', n=_sb_remaining, limit=_sb_limit))
            if not _sb_allowed:
                st.warning(t('ai_quota_exceeded', limit=_sb_limit))
                _contact_email = _get_secret('VS_CONTACT_EMAIL') or 'alanhe@icloud.com'
                st.caption(t('ai_quota_exceeded_contact', email=f'mailto:{_contact_email}'))
                # ── Invite code redemption ──
                _invite_db = _get_secret('VS_DB_PATH')
                if _invite_db:
                    _code_input = st.text_input(
                        t('invite_code_label'), placeholder=t('invite_code_placeholder'),
                        key='invite_code_input', label_visibility='collapsed',
                    )
                    if _code_input:
                        from modeling.db_export import redeem_invite_code
                        _ok, _granted, _err = redeem_invite_code(
                            _invite_db, _code_input.strip(), _get_client_id())
                        if _ok:
                            st.success(t('invite_code_success', n=_granted))
                            st.rerun()
                        elif _err == 'already_used':
                            st.error(t('invite_code_used'))
                        else:
                            st.error(t('invite_code_invalid'))
    else:
        oneclick_btn = False

    # Latch button clicks into session state so they survive concurrent reruns.
    # Streamlit buttons are ephemeral (True only during the click-triggered
    # rerun).  If the text-input focus-loss also fires a rerun at the same
    # time, the button True can be lost.  Storing in session_state makes the
    # click "sticky" until it's consumed by the trigger logic further down.
    if oneclick_btn:
        st.session_state.use_ai = True
        st.session_state['_btn_action'] = 'ai'
    elif manual_btn:
        st.session_state.use_ai = False
        st.session_state['_btn_action'] = 'manual'

    # Detect Enter key on ticker input
    _ticker_enter = False
    _has_latched_btn = '_btn_action' in st.session_state
    if ticker_input and not oneclick_btn and not manual_btn and not _has_latched_btn:
        _prev_ticker = st.session_state.get('_prev_ticker_input', '')
        if ticker_input != _prev_ticker:
            if _any_ai:
                st.session_state['_needs_mode_select'] = True   # persist until button clicked
            else:
                _ticker_enter = True       # No AI available: Enter triggers manual valuation
    if ticker_input:
        st.session_state._prev_ticker_input = ticker_input

    # Clear mode-selection prompt when a button is clicked
    if oneclick_btn or manual_btn or _has_latched_btn:
        st.session_state.pop('_needs_mode_select', None)

    _show_mode_prompt = st.session_state.get('_needs_mode_select', False)

    # Show mode-selection prompt when AI is available (local or cloud)
    if _show_mode_prompt and _any_ai:
        st.markdown(
            '<div style="text-align:center; padding:10px 12px; margin:6px 0; '
            'border-radius:8px; background:linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%); '
            'border:1px solid #ffc107; '
            'font-size:0.88rem; color:#856404; font-weight:600; line-height:1.4; '
            'animation:pulse-prompt 1.5s ease-in-out 2;">'
            f'{t("sidebar_mode_prompt")}'
            '</div>'
            '<style>@keyframes pulse-prompt{0%,100%{transform:scale(1)}50%{transform:scale(1.02)}}</style>',
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

    # ── Spacer between action buttons and settings ──
    st.markdown('<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
    st.markdown('<hr style="margin:0 0 12px 0; border:none; border-top:1px solid var(--vx-border, #d0d7de); opacity:0.5;">', unsafe_allow_html=True)

    # ── Admin panel (visible only with ?admin=<key>) ──
    if _is_admin():
        with st.expander("🔧 Admin", expanded=False):
            _adm_limit = int(_get_secret('VS_AI_DAILY_LIMIT') or '5')
            _db_path = _get_secret('VS_DB_PATH')
            if not _db_path:
                st.caption("⚠️ Set `VS_DB_PATH` in Secrets to enable admin features.")
            else:
                from modeling.db_export import (
                    get_ai_usage_stats, grant_extra_quota, reset_usage_today,
                    get_extra_quota_today, generate_invite_code, list_invite_codes,
                )

                # ── Tab layout: Usage | Invite Codes ──
                _adm_tab1, _adm_tab2 = st.tabs(["📊 Usage", "🎟️ Invite Codes"])

                with _adm_tab1:
                    st.markdown(f"**Base limit:** `{_adm_limit}` / user / day")
                    _stats = get_ai_usage_stats(_db_path)
                    if _stats:
                        _total = sum(r[1] for r in _stats)
                        st.markdown(f"**Today:** {_total} calls · {len(_stats)} users")
                        for _idx, (_ip, _cnt, _last_tk) in enumerate(_stats):
                            _extra = get_extra_quota_today(_db_path, _ip)
                            _eff_limit = _adm_limit + _extra
                            _tk_label = f" · {_last_tk}" if _last_tk else ""
                            _ip_short = _ip[:15] + '…' if len(_ip) > 15 else _ip
                            st.markdown(f"`{_ip_short}` — **{_cnt}/{_eff_limit}**{_tk_label}")
                            _col_g, _col_r = st.columns(2)
                            with _col_g:
                                if st.button("➕ +10", key=f"grant_{_idx}"):
                                    grant_extra_quota(_db_path, _ip, 10, note="admin grant")
                                    st.rerun()
                            with _col_r:
                                if st.button("🔄 Reset", key=f"reset_{_idx}"):
                                    reset_usage_today(_db_path, _ip)
                                    st.rerun()
                    else:
                        st.caption("No AI usage today.")

                with _adm_tab2:
                    # Generate new invite code
                    _code_quota = st.number_input("Quota per code", min_value=1, max_value=999,
                                                   value=10, step=5, key="adm_code_quota")
                    _code_count = st.number_input("How many codes", min_value=1, max_value=20,
                                                   value=1, step=1, key="adm_code_count")
                    if st.button("🎟️ Generate", key="gen_codes"):
                        _new_codes = []
                        for _ in range(int(_code_count)):
                            _c = generate_invite_code(_db_path, quota=int(_code_quota))
                            if _c:
                                _new_codes.append(_c)
                        if _new_codes:
                            st.success(f"Generated {len(_new_codes)} code(s)")
                            st.code('\n'.join(_new_codes), language=None)
                        else:
                            st.error("Failed to generate codes")

                    # List existing codes
                    _codes = list_invite_codes(_db_path, limit=20)
                    if _codes:
                        st.markdown("**Recent codes:**")
                        for _ci in _codes:
                            _status = f"✅ {_ci['redeemed_by'][:12]}…" if _ci['redeemed_by'] else "🟡 unused"
                            st.caption(f"`{_ci['code']}` · {_ci['quota']}x · {_status}")

    # ── API keys section (no divider — expanders provide visual separation) ──

    # ── User Cloud AI API keys (optional override) ──
    # Show only in web/cloud mode — lets users bring their own Serper + DeepSeek keys
    if not _has_ai:
        with st.expander(t('sidebar_cloud_ai_expander'), expanded=False):
            _user_serper = st.text_input(
                t('sidebar_serper_label'),
                type="password",
                placeholder=t('sidebar_serper_placeholder'),
                key='user_serper_key',
            )
            _user_deepseek = st.text_input(
                t('sidebar_deepseek_label'),
                type="password",
                placeholder=t('sidebar_deepseek_placeholder'),
                key='user_deepseek_key',
            )
            st.caption(t('sidebar_cloud_ai_hint'))
            if _user_serper and _user_deepseek:
                st.success(t('sidebar_cloud_ai_active'))
            elif _user_serper or _user_deepseek:
                st.warning(t('sidebar_cloud_ai_partial'))

    # ── Financial data API key ──
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

    # Store FMP key in session state so ticker search can access it
    st.session_state['_fmp_key_val'] = apikey

    # ── Copyright & contact (keyed container prevents duplication on rapid reruns) ──
    with st.container(key="vs_sidebar_footer"):
        st.markdown('<hr style="margin:16px 0 10px 0; border:none; border-top:1px solid var(--vx-border, #d0d7de);">',
                    unsafe_allow_html=True)
        with st.expander(t('sidebar_sponsor'), expanded=False):
            st.image('assets/wechat-reward.jpg', width="stretch")
            st.caption(t('sponsor_guide'))
        st.markdown(
            '<div style="text-align:center; font-size:0.72rem; color:#555; line-height:1.7; padding:4px 0;">'
            '    <div>© 2026 Alan He · <a href="https://opensource.org/licenses/MIT" target="_blank" style="color:#58a6ff;text-decoration:none;">MIT License</a></div>'
            '    <div><a href="https://jianshan.co" target="_blank" style="color:#58a6ff;text-decoration:none;">见山笔记</a>'
            '    · <a href="https://github.com/alanhewenyu/ValueScope" target="_blank" style="color:#58a6ff;text-decoration:none;">GitHub</a>'
            '    · <a href="https://jianshan.co/wechat/" target="_blank" style="color:#58a6ff;text-decoration:none;">公众号</a>'
            '    · <a href="mailto:alanhe@icloud.com" style="color:#58a6ff;text-decoration:none;">alanhe@icloud.com</a></div>'
            '</div>',
            unsafe_allow_html=True)


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


def _render_verdict_section(results, company_profile, valuation_params, forex_rate):
    """Render verdict card + 4 summary metric cards as HTML."""
    # ── Compute IV in stock currency ──
    dcf_raw = results['price_per_share']
    rep_cur = results.get('reported_currency', '')
    stk_cur = company_profile.get('currency', '')
    cur = rep_cur or stk_cur or ''
    needs_forex = (rep_cur and stk_cur and rep_cur != stk_cur)
    if forex_rate and needs_forex:
        iv = dcf_raw * forex_rate
        iv_cur = stk_cur
    else:
        iv = dcf_raw
        iv_cur = cur
    mkt = company_profile.get('price', 0) or 0

    # ── Determine verdict ──
    mos = None
    if mkt > 0:
        mos = (iv - mkt) / mkt * 100
    # 3-tier badge
    if mos is None:
        badge_cls, badge_label = 'hold', t('verdict_hold')
    elif mos > 10:
        badge_cls, badge_label = 'buy', t('verdict_buy')
    elif mos < -10:
        badge_cls, badge_label = 'sell', t('verdict_sell')
    else:
        badge_cls, badge_label = 'hold', t('verdict_hold')
    # 5-tier sub-text
    if mos is not None:
        if mos > 30:     sub_text = t('verdict_sig_under')
        elif mos > 10:   sub_text = t('verdict_mod_under')
        elif mos > -10:  sub_text = t('verdict_fair')
        elif mos > -30:  sub_text = t('verdict_mod_over')
        else:            sub_text = t('verdict_sig_over')
    else:
        sub_text = ''

    # ── Build verdict card HTML ──
    html = f'<div class="verdict-card {badge_cls}">'
    # Badge
    html += (f'<div class="verdict-badge">'
             f'<span class="badge-label">{badge_label}</span>'
             f'<span class="badge-sub">{sub_text}</span>'
             f'</div>')
    # IV vs Market metrics
    html += '<div class="verdict-metrics">'
    html += (f'<div class="verdict-metric">'
             f'<div class="vm-label">{t("verdict_iv_label")}</div>'
             f'<div class="vm-val intrinsic">{iv_cur} {iv:,.2f}</div>'
             f'</div>')
    html += '<span class="verdict-vs">vs</span>'
    if mkt > 0:
        html += (f'<div class="verdict-metric">'
                 f'<div class="vm-label">{t("verdict_mkt_label")}</div>'
                 f'<div class="vm-val market">{stk_cur} {mkt:,.2f}</div>'
                 f'</div>')
    else:
        html += '<div class="verdict-metric"><div class="vm-val market">\u2014</div></div>'
    # MOS%
    if mos is not None:
        html += (f'<div class="verdict-mos">'
                 f'<div class="vm-label">{t("verdict_mos_label")}</div>'
                 f'<div class="vm-pct">{mos:+.1f}%</div>'
                 f'</div>')
    html += '</div>'  # verdict-metrics
    html += '</div>'  # verdict-card

    # ── Build 4 summary cards ──
    vp = valuation_params or {}
    g1 = vp.get('revenue_growth_1', 0)
    g2 = vp.get('revenue_growth_2', 0)
    m = vp.get('ebit_margin', 0)
    w = vp.get('wacc', 0)
    html += '<div class="summary-cards">'
    html += (f'<div class="summary-card">'
             f'<div class="sc-label">{t("summary_y1_growth")}</div>'
             f'<div class="sc-val">{g1:.1f}%</div>'
             f'</div>')
    html += (f'<div class="summary-card">'
             f'<div class="sc-label">{t("summary_y25_cagr")}</div>'
             f'<div class="sc-val">{g2:.1f}%</div>'
             f'</div>')
    html += (f'<div class="summary-card">'
             f'<div class="sc-label">{t("summary_ebit_margin")}</div>'
             f'<div class="sc-val">{m:.1f}%</div>'
             f'</div>')
    html += (f'<div class="summary-card">'
             f'<div class="sc-label">{t("summary_wacc")}</div>'
             f'<div class="sc-val">{w:.1f}%</div>'
             f'</div>')
    html += '</div>'  # summary-cards

    return html


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

    # ── Early check: US/Japan stocks require FMP API key ──
    if not is_a_share(ticker) and not is_hk_stock(ticker) and not apikey_val.strip():
        st.warning(t('err_no_fmp_key'))
        return False

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


def _run_cloud_ai_analysis():
    """Run cloud AI analysis (Serper + DeepSeek). Returns True on success."""
    s = st.session_state
    s._ai_running = True
    _eff_serper, _eff_deepseek, _is_user_keys = _get_effective_cloud_keys()
    try:
        company_name = s.company_profile.get('companyName', s.ticker)
        _lang = s.get('_lang', 'en')

        # Build template args (same as _build_analysis_prompt but as dict)
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
            if _lang == 'zh':
                ttm_context = f'，数据为 {_ttm_label}（截至 {ttm_end_date} 的最近十二个月）'
                forecast_year_guidance = (
                    f'DCF 预测 Year 1 覆盖从 {ttm_end_date} 起的未来12个月（大致对应 {forecast_year_1} 日历年）。'
                    f'请以 {forecast_year_1} 年作为 Year 1 的参考年份搜索业绩指引和分析师预期。'
                )
            else:
                ttm_context = f', data is {_ttm_label} (trailing twelve months ending {ttm_end_date})'
                forecast_year_guidance = (
                    f'DCF Year 1 covers the next 12 months from {ttm_end_date} '
                    f'(roughly corresponding to calendar year {forecast_year_1}). '
                    f'Use {forecast_year_1} as the reference year when searching for earnings guidance.'
                )
            ttm_base_label = f' ({_ttm_label})'
        else:
            ttm_context = ''
            ttm_base_label = ''
            if _lang == 'zh':
                forecast_year_guidance = f'Year 1 对应 {forecast_year_1} 年。'
            else:
                forecast_year_guidance = f'Year 1 corresponds to fiscal year {forecast_year_1}.'

        template_args = dict(
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
            search_year=forecast_year_1,
            search_year_2=forecast_year_1 + 1,
            ttm_context=ttm_context,
            ttm_base_label=ttm_base_label,
        )

        # Run cloud AI with st.status progress
        start_time = time.time()
        status_label = t('ai_status_label', company=company_name)

        toast_placeholder = st.empty()

        with st.status(f"🤖 {status_label} via DeepSeek R1", expanded=True) as status:
            progress_ph = st.empty()

            def _progress(phase, message):
                elapsed = time.time() - start_time
                if phase == 'searching':
                    progress_ph.write(t('cloud_searching', query=message))
                    _render_progress_toast(toast_placeholder,
                                            f'🤖 {status_label} — DeepSeek R1',
                                            t('cloud_searching', query=(message or '')[:60]),
                                            elapsed)
                elif phase == 'scraping':
                    _url_short = (message or '')[:50]
                    progress_ph.write(t('cloud_scraping', url=_url_short))
                    _render_progress_toast(toast_placeholder,
                                            f'🤖 {status_label} — DeepSeek R1',
                                            t('cloud_scraping', url=_url_short),
                                            elapsed)
                elif phase == 'analyzing':
                    progress_ph.write(t('cloud_analyzing'))
                    _render_progress_toast(toast_placeholder,
                                            f'🤖 {status_label} — DeepSeek R1',
                                            t('cloud_analyzing'), elapsed)
                elif phase == 'generating':
                    progress_ph.write(t('cloud_generating'))
                    _render_progress_toast(toast_placeholder,
                                            f'🤖 {status_label} — DeepSeek R1',
                                            t('cloud_generating'), elapsed)

            text = cloud_ai_analyze(
                template_args, _eff_serper, _eff_deepseek,
                lang=_lang, progress_callback=_progress)

            elapsed = time.time() - start_time
            status.update(
                label=t('cloud_ai_complete', elapsed=elapsed),
                state="complete", expanded=False)

        # Show completion toast briefly, then clear
        _render_progress_toast(toast_placeholder,
                                t('ai_toast_complete_title', label=status_label),
                                t('ai_toast_complete_msg', engine='DeepSeek R1'),
                                elapsed, done=True)
        time.sleep(2)
        toast_placeholder.empty()

        # Set detected model name for display
        _ai_mod._detected_model_name = 'DeepSeek'

        parameters = _parse_structured_parameters(text)
        if parameters is None:
            st.error(t('err_ai_parse'))
            s._ai_running = False
            return False

        s.ai_result = {
            "parameters": parameters,
            "raw_text": text,
        }
        s.pop('user_params_modified', None)
        for _k in ('results', 'sensitivity_table', 'wacc_results',
                    'wacc_base', 'valuation_params', 'gap_analysis_result',
                    '_last_dcf_input_snapshot',
                    'p_rg1', 'p_rg2', 'p_em', 'p_conv', 'p_tax',
                    'p_ric1', 'p_ric2', 'p_ric3', 'p_wacc'):
            s.pop(_k, None)

        s._reasoning_just_completed = True
        s._ai_running = False
        return True
    except SerperCreditError:
        s._ai_running = False
        st.error(t('err_serper_credits_user') if _is_user_keys else t('err_serper_credits'))
        return False
    except DeepSeekCreditError:
        s._ai_running = False
        st.error(t('err_deepseek_credits_user') if _is_user_keys else t('err_deepseek_credits'))
        return False
    except Exception as e:
        s._ai_running = False
        st.error(t('err_ai_failed', msg=str(e)))
        return False


def _run_ai_analysis():
    """Run AI analysis; routes to cloud or CLI based on availability. Returns True on success."""
    # Cloud AI path (Serper + DeepSeek) — used on Streamlit Cloud or with user-provided keys
    if _cloud_ai_available() and not _has_ai:
        return _run_cloud_ai_analysis()

    # Local CLI path (Claude/Gemini/Qwen)
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
    from datetime import date as _date
    _today = _date.today()
    current_date_str = _today.strftime('%Y-%m-%d')
    current_year = _today.year
    _forecast_year = forecast_year_1 if forecast_year_1 else base_year + 1

    _gap_template_args = dict(
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
        forecast_year=_forecast_year,
        current_date=current_date_str,
        current_year=current_year,
    )

    # ── Cloud AI path for gap analysis ──
    _eff_serper, _eff_deepseek, _is_user_keys = _get_effective_cloud_keys()
    if _cloud_ai_available() and not _has_ai:
        import time as _time
        _t0 = _time.time()
        with st.status(t('gap_status_label'), expanded=True) as status:
            def _gap_progress(phase, msg):
                if phase == 'searching':
                    status.update(label=t('cloud_searching').format(query=msg))
                elif phase == 'scraping':
                    _url_short = (msg or '')[:50]
                    status.update(label=t('cloud_scraping').format(url=_url_short))
                elif phase == 'analyzing':
                    status.update(label=t('cloud_analyzing'))
                elif phase == 'generating':
                    status.update(label=t('cloud_generating'))

            try:
                analysis_text = cloud_gap_analyze(
                    _gap_template_args, _eff_serper, _eff_deepseek,
                    lang=_lang, progress_callback=_gap_progress,
                )
                _elapsed = _time.time() - _t0
                status.update(label=t('cloud_ai_complete').format(elapsed=_elapsed), state="complete")
            except SerperCreditError:
                status.update(label="Error", state="error")
                st.error(t('err_serper_credits_user') if _is_user_keys else t('err_serper_credits'))
            except DeepSeekCreditError:
                status.update(label="Error", state="error")
                st.error(t('err_deepseek_credits_user') if _is_user_keys else t('err_deepseek_credits'))
            except Exception as e:
                status.update(label=f"Error: {e}", state="error")
                return None
    else:
        _gap_template = GAP_ANALYSIS_PROMPT_TEMPLATE if _lang == 'zh' else GAP_ANALYSIS_PROMPT_TEMPLATE_EN
        prompt = _gap_template.format(**_gap_template_args)
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

    # Compute adjusted price in reporting currency (reverse forex conversion)
    adjusted_price_reporting = None
    if adjusted_price is not None and currency_converted and forex_rate and forex_rate > 0:
        adjusted_price_reporting = adjusted_price / forex_rate

    return {
        'analysis_text': analysis_text,
        'adjusted_price': adjusted_price,
        'adjusted_price_reporting': adjusted_price_reporting,
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

# Effective triggers: consume latched button action from session state.
# This is robust against concurrent reruns where the ephemeral button
# value (oneclick_btn / manual_btn) may have already gone back to False.
_btn_action = st.session_state.pop('_btn_action', None)
_trigger_ai = (oneclick_btn or _btn_action == 'ai') and ticker_input
_trigger_manual = ((manual_btn or _btn_action == 'manual') and ticker_input) or (_ticker_enter and ticker_input)

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
        # Collapse sidebar on mobile so user sees the loading/results area
        _components.html("""<script>
        (function(){
            if (window.parent.innerWidth > 768) return;
            var sb = window.parent.document.querySelector('[data-testid="stSidebar"]');
            if (sb && sb.getAttribute('aria-expanded') !== 'false') {
                sb.setAttribute('aria-expanded', 'false');
            }
        })();
        </script>""", height=0)
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
        st.markdown(f"""
        <div class="vx-welcome" style="text-align:center; padding:20px 20px 24px 20px; max-width:720px; margin:0 auto;">
            <p style="font-size:3rem; margin-bottom:8px; line-height:1;">📊</p>
            <p style="font-size:1.5rem; font-weight:700; margin-bottom:6px; color:var(--vx-text, #1f2328);
                       background:linear-gradient(135deg, #00d2ff 0%, #7b2ff7 100%);
                       -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                ValueScope
            </p>
            <p style="font-size:1.05rem; color:var(--vx-text-secondary, #656d76); line-height:1.6; margin-bottom:14px;">
                {t('welcome_instruction_web') if not (_has_ai or _has_cloud_ai) else t('welcome_instruction')}
            </p>
            <div style="display:flex; justify-content:center; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
                <span style="font-size:0.78rem; padding:4px 10px; border-radius:20px; white-space:nowrap;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_us')}</span>
                <span style="font-size:0.78rem; padding:4px 10px; border-radius:20px; white-space:nowrap;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_hk')}</span>
                <span style="font-size:0.78rem; padding:4px 10px; border-radius:20px; white-space:nowrap;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_cn')}</span>
                <span style="font-size:0.78rem; padding:4px 10px; border-radius:20px; white-space:nowrap;
                             background:color-mix(in srgb, var(--vx-accent, #0969da) 8%, transparent);
                             color:var(--vx-accent, #0969da); border:1px solid color-mix(in srgb, var(--vx-accent) 20%, transparent);">
                    {t('welcome_jp')}</span>
            </div>
            <p style="font-size:0.78rem; color:var(--vx-text-muted, #8b949e);">
                {t('welcome_api_note')}
            </p>
            <!-- Mission / Philosophy -->
            <hr style="border:none; border-top:1px solid color-mix(in srgb, var(--vx-text-muted, #8b949e) 25%, transparent); margin:18px 0 14px 0;">
            <p style="font-size:0.88rem; font-weight:600; color:var(--vx-text-secondary, #656d76); margin-bottom:14px; letter-spacing:0.03em;">
                {t('mission_heading')}</p>
            <div style="display:flex; gap:16px; flex-wrap:wrap; justify-content:center; max-width:660px; margin:0 auto;">
                <div style="flex:1; min-width:170px; max-width:210px; padding:14px 14px; border-radius:12px; text-align:center;
                            background:color-mix(in srgb, var(--vx-accent, #0969da) 4%, transparent);
                            border:1px solid color-mix(in srgb, var(--vx-accent, #0969da) 12%, transparent);">
                    <p style="font-size:1.6rem; margin-bottom:8px; line-height:1;">🌐</p>
                    <p style="font-size:0.9rem; font-weight:600; color:var(--vx-text, #1f2328); margin-bottom:8px;">
                        {t('mission_pillar1_title')}</p>
                    <p style="font-size:0.8rem; color:var(--vx-text-secondary, #656d76); line-height:1.6;">
                        {t('mission_pillar1_desc')}</p>
                </div>
                <div style="flex:1; min-width:170px; max-width:210px; padding:14px 14px; border-radius:12px; text-align:center;
                            background:color-mix(in srgb, var(--vx-accent, #0969da) 4%, transparent);
                            border:1px solid color-mix(in srgb, var(--vx-accent, #0969da) 12%, transparent);">
                    <p style="font-size:1.6rem; margin-bottom:8px; line-height:1;">🧱</p>
                    <p style="font-size:0.9rem; font-weight:600; color:var(--vx-text, #1f2328); margin-bottom:8px;">
                        {t('mission_pillar2_title')}</p>
                    <p style="font-size:0.8rem; color:var(--vx-text-secondary, #656d76); line-height:1.6;">
                        {t('mission_pillar2_desc')}</p>
                </div>
                <div style="flex:1; min-width:170px; max-width:210px; padding:14px 14px; border-radius:12px; text-align:center;
                            background:color-mix(in srgb, var(--vx-accent, #0969da) 4%, transparent);
                            border:1px solid color-mix(in srgb, var(--vx-accent, #0969da) 12%, transparent);">
                    <p style="font-size:1.6rem; margin-bottom:8px; line-height:1;">🎯</p>
                    <p style="font-size:0.9rem; font-weight:600; color:var(--vx-text, #1f2328); margin-bottom:8px;">
                        {t('mission_pillar3_title')}</p>
                    <p style="font-size:0.8rem; color:var(--vx-text-secondary, #656d76); line-height:1.6;">
                        {t('mission_pillar3_desc')}</p>
                </div>
            </div>
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

# ── Dynamic page title for SEO & better browser tab readability ──
_escaped_title = _company_title.replace("'", "\\'").replace('"', '\\"')
_components.html(f"""<script>
window.parent.document.title = '{_escaped_title} — ValueScope DCF';
</script>""", height=0)

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
    # Invisible marker div — CSS :has(div.vs-sticky-hdr) targets the parent
    st.markdown('<div class="vs-sticky-hdr"></div>', unsafe_allow_html=True)

    # ── Financial data toggle button (shared logic for both pre/post DCF) ──
    _fin_currently_shown = ss.get('_show_fin_data', False)
    _fin_btn_label = t('btn_collapse_fin') if _fin_currently_shown else t('btn_view_fin')

    if _has_results:
        # Post-DCF: company name + Financials + [Gap (AI only)] + Excel
        _gap_avail = _has_ai or _cloud_ai_available()
        if _gap_avail:
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
        if _gap_avail:
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

# ── Sticky verdict bar (second row, only after DCF results) ──
if _has_results:
    _hero_bar_container = st.container()
    with _hero_bar_container:
        st.markdown('<div class="vs-sticky-hero"></div>', unsafe_allow_html=True)
        # Ensure forex rate is available for cross-currency valuations
        _hdr_forex = ss.get('forex_rate')
        _hdr_rep_cur = ss.results.get('reported_currency', '')
        _hdr_stk_cur = ss.company_profile.get('currency', '')
        if (_hdr_rep_cur and _hdr_stk_cur and _hdr_rep_cur != _hdr_stk_cur
                and not _hdr_forex):
            _hdr_forex, _ = _compute_forex_rate_web(
                ss.results, ss.company_profile, apikey)
            if _hdr_forex:
                ss.forex_rate = _hdr_forex
        _verdict_html = _render_verdict_section(
            ss.results, ss.company_profile,
            ss.get('valuation_params', {}), _hdr_forex)
        st.markdown(_verdict_html, unsafe_allow_html=True)

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
    # Check AI quota before running
    _ai_allowed, _ai_used, _ai_limit = _check_ai_quota()
    if not _ai_allowed:
        st.warning(t('ai_quota_exceeded', used=_ai_used, limit=_ai_limit))
        ss._ai_pending = False
    else:
        _record_ai_usage(ss.get('ticker'))
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
        # Update DB record with gap analysis
        if ss.get('_db_row_id'):
            from modeling.db_export import update_gap_analysis
            update_gap_analysis(
                _get_secret('VS_DB_PATH'), ss._db_row_id, gap_result)
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

    # ── Optional DB export ──
    from modeling.db_export import maybe_save_to_db
    row_id = maybe_save_to_db(
        ticker=ss.ticker, company_name=ss.company_name,
        mode='copilot' if use_ai else 'manual',
        ai_engine=_ai_engine_display_name() if use_ai else None,
        valuation_params=valuation_params, results=results,
        company_profile=ss.company_profile,
        gap_analysis_result=ss.get('gap_analysis_result'),
        ai_result=ss.get('ai_result'),
        sensitivity_table=ss.sensitivity_table,
        wacc_sensitivity=(wacc_results, wacc_base),
        financial_data=ss.financial_data,
        forex_rate=ss.get('forex_rate'),
    )
    ss._db_row_id = row_id

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
            if gap.get('adjusted_price_reporting') is not None and gap.get('reported_currency'):
                _gap_adj_str += f" ({gap['adjusted_price_reporting']:,.2f} {gap['reported_currency']})"
        st.markdown('<div id="gap-analysis-anchor"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="expander-hint"><span class="icon">📊</span>'
            f'{t("gap_hint", adj=_gap_adj_str)}</div>',
            unsafe_allow_html=True)
        with st.expander(t('gap_expander'), expanded=_gap_just_done):
            if gap.get('adjusted_price') is not None:
                adj = gap['adjusted_price']
                _adj_msg = t('gap_adjusted', val=adj, cur=gap['currency'])
                if gap.get('adjusted_price_reporting') is not None and gap.get('reported_currency'):
                    _adj_msg += f"  ({gap['adjusted_price_reporting']:,.2f} {gap['reported_currency']})"
                st.success(_adj_msg)
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
    {t('footer_tagline_web') if not (_has_ai or _has_cloud_ai) else t('footer_tagline')}
</div>
""", unsafe_allow_html=True)

# ── Signal parent iframe wrapper that Streamlit has finished rendering ──
_stc.html('<script>try{window.top.postMessage("streamlit-ready","*")}catch(e){}</script>', height=0)
