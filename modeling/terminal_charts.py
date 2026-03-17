# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Terminal chart utilities using plotext for inline CLI visualizations."""

from __future__ import annotations
import sys
from . import style as S

# Lazy-load plotext (not a hard dependency)
_plt = None

def _get_plt():
    global _plt
    if _plt is None:
        try:
            import plotext as plt
            _plt = plt
        except ImportError:
            return None
    return _plt



def _valuation_pct_colored(pct):
    """Color for valuation deviation: above avg = red (expensive), below = green (cheap)."""
    formatted = f"{pct:+.1f}%"
    if pct <= 0:
        return f"{S.BRIGHT_GREEN}{formatted}{S.RESET}"
    else:
        return f"{S.BRIGHT_RED}{formatted}{S.RESET}"


def _fmt_y(val):
    """Format y-axis numbers with commas, no unnecessary decimals."""
    if val == 0:
        return "0"
    abs_val = abs(val)
    if abs_val >= 100:
        return f"{val:,.0f}"
    elif abs_val >= 1:
        return f"{val:.1f}"
    else:
        return f"{val:.2f}"


def _set_yticks(plt, values, n_ticks=5):
    """Set custom formatted y-axis ticks for a list of values."""
    if not values:
        return
    vmin = min(values)
    vmax = max(values)
    if vmin == vmax:
        plt.yticks([vmin], [_fmt_y(vmin)])
        return
    step = (vmax - vmin) / (n_ticks - 1)
    ticks = [vmin + step * i for i in range(n_ticks)]
    plt.yticks(ticks, [_fmt_y(t) for t in ticks])


def _set_date_xticks(plt, dates, n_labels=5):
    """Set evenly-spaced date labels on x-axis from a list of date strings."""
    n = len(dates)
    if n <= n_labels:
        plt.xticks(list(range(n)), [d[:7] for d in dates])
        return
    step = (n - 1) / (n_labels - 1)
    positions = [round(step * i) for i in range(n_labels)]
    # Deduplicate positions
    positions = sorted(set(positions))
    labels = [dates[i][:7] for i in positions]
    plt.xticks(positions, labels)


def _side_by_side(left_str, right_str, gap=3):
    """Merge two chart strings into a side-by-side layout."""
    import re
    ansi_re = re.compile(r'\x1b\[[0-9;]*m')
    left_lines = left_str.rstrip('\n').split('\n')
    right_lines = right_str.rstrip('\n').split('\n')
    max_left = max((len(ansi_re.sub('', l)) for l in left_lines), default=0)
    rows = max(len(left_lines), len(right_lines))
    out = []
    for i in range(rows):
        l = left_lines[i] if i < len(left_lines) else ''
        r = right_lines[i] if i < len(right_lines) else ''
        visible_len = len(ansi_re.sub('', l))
        pad = max_left - visible_len + gap
        out.append(l + ' ' * pad + r)
    return '\n'.join(out)


# ────────────────────────────────────────────────────────────────
# 1. Key Financial Drivers (from summary DataFrame)
# ────────────────────────────────────────────────────────────────

def _extract_series(summary_df, row_name):
    """Extract a row from summary_df as {year: value} in chronological order."""
    if row_name not in summary_df.index:
        return [], []
    row = summary_df.loc[row_name]
    # Columns are newest→oldest, reverse to chronological
    cols = list(reversed(summary_df.columns))
    vals = [row[c] for c in cols]
    # Clean: convert to float, skip None/NaN
    years, values = [], []
    for c, v in zip(cols, vals):
        try:
            fv = float(v)
            if fv != fv:  # NaN check
                continue
            years.append(str(c))
            values.append(fv)
        except (TypeError, ValueError):
            continue
    return years, values


def print_key_drivers(summary_df, company_name=""):
    """Print 4 key driver charts in full-width single-column layout."""
    plt = _get_plt()
    if plt is None:
        print(S.muted("  ⓘ Install plotext for terminal charts: pip install plotext"))
        return

    title = f"Key Financial Drivers — {company_name}" if company_name else "Key Financial Drivers"
    print(f"\n{S.header(title)}")

    _chart_width = 72
    _chart_height = 12

    def _init_chart(height=_chart_height):
        plt.clear_figure()
        plt.theme("clear")
        plt.plotsize(_chart_width, height)
        plt.grid(False, False)

    # Extract all data upfront
    years_r, revenues = _extract_series(summary_df, "Revenue")
    years_g, growth = _extract_series(summary_df, "Revenue Growth (%)")
    years_m, margins = _extract_series(summary_df, "EBIT Margin (%)")
    years_roic, roic = _extract_series(summary_df, "ROIC (%)")
    years_roe, roe = _extract_series(summary_df, "ROE (%)")
    years_ebit, ebit_vals = _extract_series(summary_df, "EBIT")
    years_tax, tax_vals = _extract_series(summary_df, "Tax Rate (%)")
    years_reinv, reinv_vals = _extract_series(summary_df, "Total Reinvestment")

    # --- 1. Revenue Growth Rate line chart (skip first year — no prior year) ---
    if len(growth) > 1:
        g_vals = growth[1:]
        g_years = years_g[1:]
        _init_chart(height=8)
        plt.title("Revenue Growth (%)")
        x_idx = list(range(len(g_vals)))
        plt.plot(x_idx, g_vals, marker="braille", color="cyan")
        plt.horizontal_line(0, color="gray")
        avg_g = sum(g_vals) / len(g_vals)
        plt.horizontal_line(avg_g, color="gray")
        plt.xticks(x_idx, g_years)
        _set_yticks(plt, g_vals + [0], n_ticks=4)
        plt.show()
        print(f"  Avg Growth: {avg_g:.1f}%")
        print()

    # --- 2. EBIT Margin ---
    if margins:
        _init_chart()
        plt.title("EBIT Margin (%)")
        avg_margin = sum(margins) / len(margins)
        x_idx = list(range(len(margins)))
        plt.plot(x_idx, margins, marker="braille", color="green")
        plt.horizontal_line(avg_margin, color="gray")
        plt.xticks(x_idx, years_m)
        _set_yticks(plt, margins + [avg_margin])
        plt.show()
        print(f"  Avg: {avg_margin:.1f}%")
        print()

    # --- 3. ROIC & ROE ---
    if roic or roe:
        _init_chart()
        plt.title("ROIC & ROE (%)")
        x_idx = list(range(len(roic or roe)))
        labels = years_roic or years_roe
        all_vals = []
        if roic:
            plt.plot(x_idx, roic, marker="braille", color="magenta", label="ROIC")
            all_vals.extend(roic)
        if roe and len(roe) == len(x_idx):
            plt.plot(x_idx, roe, marker="braille", color="cyan", label="ROE")
            all_vals.extend(roe)
        plt.xticks(x_idx, labels)
        _set_yticks(plt, all_vals)
        plt.show()
        print()

    # --- 4. FCFF (bar chart — minimal yticks) ---
    if ebit_vals and tax_vals and reinv_vals and len(ebit_vals) == len(tax_vals) == len(reinv_vals):
        fcff = []
        for e, t, r in zip(ebit_vals, tax_vals, reinv_vals):
            nopat = e * (1 - t / 100)
            fcff.append(nopat - r)
        _init_chart()
        plt.title("Free Cash Flow to Firm (in M)")
        x_idx = list(range(len(fcff)))
        colors = ["green" if v >= 0 else "red" for v in fcff]
        plt.bar(x_idx, fcff, color=colors, width=0.6)
        avg_fcff = sum(fcff) / len(fcff)
        plt.horizontal_line(avg_fcff, color="gray")
        plt.xticks(x_idx, years_ebit)
        plt.yticks([min(fcff), max(fcff)],
                   [_fmt_y(min(fcff)), _fmt_y(max(fcff))])
        plt.show()
        print(f"  Avg FCFF: {avg_fcff:,.0f}M")
        print()


# ────────────────────────────────────────────────────────────────
# 2. Relative Valuation — Current Metrics + Historical Percentile
# ────────────────────────────────────────────────────────────────

def _percentile_bar(label, percentile, current, stats, width=40):
    """Render a text-based percentile bar: [░░░░▓▓████████░░░░░░░░░░░░]."""
    if percentile is None:
        return f"  {label:>12s}:  N/A"

    pct = max(0, min(100, percentile))
    filled = round(pct / 100 * width)
    bar = "█" * filled + "░" * (width - filled)

    # Color: green if low percentile (cheap), red if high (expensive)
    if pct <= 30:
        color = S.BRIGHT_GREEN
    elif pct <= 70:
        color = S.YELLOW
    else:
        color = S.BRIGHT_RED

    current_str = f"{current:.1f}x" if current is not None else "N/A"
    stats_str = ""
    if stats:
        stats_str = f"  (min {stats.get('min',0):.1f} | avg {stats.get('mean',0):.1f} | max {stats.get('max',0):.1f})"

    return f"  {label:>12s}: {color}[{bar}]{S.RESET} {pct:.0f}th  {S.BOLD}{current_str}{S.RESET}{S.DIM}{stats_str}{S.RESET}"


def fetch_relative_valuation_data(ticker, apikey=""):
    """Fetch relative valuation data (can run in background thread).

    Returns (current_dict, historical_dict) or None on error.
    """
    from .relative_valuation import get_current_valuation, get_historical_valuations
    from .data import _normalize_ticker

    normalized = _normalize_ticker(ticker)
    current = get_current_valuation(normalized, apikey)
    if "error" in current:
        return None
    hist = get_historical_valuations(normalized, years=5, apikey=apikey)
    return (current, hist)


def print_relative_valuation(ticker, apikey="", prefetched=None):
    """Display relative valuation metrics + historical percentiles.

    If *prefetched* is provided (from fetch_relative_valuation_data), skip fetching.
    """
    if prefetched is not None:
        current, hist = prefetched
    else:
        data = fetch_relative_valuation_data(ticker, apikey)
        if data is None:
            return
        current, hist = data

    print(f"\n{S.header('Relative Valuation')}")

    # --- Current Metrics ---
    print(f"\n{S.subheader('Current Valuation Metrics')}")
    if "error" in current:
        print(f"  {S.error(current['error'])}")
        return

    metrics = [
        ("Trailing PE", current.get("trailing_pe")),
        ("Forward PE", current.get("forward_pe")),
        ("P/B", current.get("price_to_book")),
        ("P/S", current.get("price_to_sales")),
        ("EV/EBITDA", current.get("ev_to_ebitda")),
    ]
    for name, val in metrics:
        if val is not None:
            formatted = f"{val:.1f}x" if val > 0.1 else f"{val:.2f}x"
            print(f"  {name:>15s}: {S.value(formatted)}")
        else:
            print(f"  {name:>15s}: {S.muted('N/A')}")
    currency = current.get("currency", "USD")
    print(f"\n  {S.muted(f'Data source: yfinance · Currency: {currency}')}")

    # --- Historical Percentiles (5Y) ---
    print(f"\n{S.subheader('Historical Percentiles (5 Year)')}")

    pe_pctl = hist.get("pe_percentile")
    pb_pctl = hist.get("pb_percentile")
    pe_stats = hist.get("pe_stats")
    pb_stats = hist.get("pb_stats")

    print(_percentile_bar("PE (TTM)", pe_pctl,
                          pe_stats.get("current") if pe_stats else None, pe_stats))
    print(_percentile_bar("P/B", pb_pctl,
                          pb_stats.get("current") if pb_stats else None, pb_stats))

    ds = hist.get("data_source", "")
    if ds:
        print(f"\n  {S.muted(f'Data source: {ds}')}")

    # --- PE/PB History Charts (full width) ---
    plt = _get_plt()
    if plt is None:
        return

    pe_history = hist.get("pe_history", [])
    pb_history = hist.get("pb_history", [])

    _chart_width = 72
    _chart_height = 12

    def _init_rv_chart():
        plt.clear_figure()
        plt.theme("clear")
        plt.plotsize(_chart_width, _chart_height)
        plt.grid(False, False)

    if pe_history and len(pe_history) > 5:
        dates = [p["date"] for p in pe_history]
        values = [p["value"] for p in pe_history]
        x_idx = list(range(len(values)))
        _init_rv_chart()
        plt.title("PE (TTM) — 5 Year History")
        plt.plot(x_idx, values, marker="braille", color="blue")
        if pe_stats:
            plt.horizontal_line(pe_stats["mean"], color="gray")
            plt.horizontal_line(pe_stats["current"], color="yellow")
        _set_date_xticks(plt, dates)
        _set_yticks(plt, values)
        plt.show()
        if pe_stats:
            cur = pe_stats["current"]
            avg = pe_stats["mean"]
            diff = ((cur - avg) / avg * 100) if avg else 0
            print(f"  Current: {S.BOLD}{cur:.1f}x{S.RESET}  Avg: {avg:.1f}x  ({_valuation_pct_colored(diff)} vs avg)")
        print()

    if pb_history and len(pb_history) > 5:
        dates = [p["date"] for p in pb_history]
        values = [p["value"] for p in pb_history]
        x_idx = list(range(len(values)))
        _init_rv_chart()
        plt.title("P/B — 5 Year History")
        plt.plot(x_idx, values, marker="braille", color="magenta")
        if pb_stats:
            plt.horizontal_line(pb_stats["mean"], color="gray")
            plt.horizontal_line(pb_stats["current"], color="yellow")
        _set_date_xticks(plt, dates)
        _set_yticks(plt, values)
        plt.show()
        if pb_stats:
            cur = pb_stats["current"]
            avg = pb_stats["mean"]
            diff = ((cur - avg) / avg * 100) if avg else 0
            print(f"  Current: {S.BOLD}{cur:.1f}x{S.RESET}  Avg: {avg:.1f}x  ({_valuation_pct_colored(diff)} vs avg)")
        print()
    print()
