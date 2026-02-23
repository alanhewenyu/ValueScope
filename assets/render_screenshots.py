#!/usr/bin/env python3
"""Render terminal-style screenshots for README demo section."""

from PIL import Image, ImageDraw, ImageFont
import os

# --- Config ---
BG_COLOR = (30, 30, 30)       # Dark terminal background
TEXT_COLOR = (204, 204, 204)   # Default text
HEADER_COLOR = (255, 215, 0)  # Gold for headers
MUTED_COLOR = (140, 140, 140) # Muted/info text
GREEN_COLOR = (80, 200, 80)   # Green for positive
CYAN_COLOR = (100, 200, 220)  # Cyan for labels
WHITE_COLOR = (255, 255, 255) # White for emphasis
PADDING = 40
LINE_HEIGHT = 22
CHAR_WIDTH = 9.6   # width per ASCII character in mono font at size 14
CJK_CHAR_WIDTH = 14.0  # CJK characters are roughly 1.5x wider

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

def _load_font(paths, size):
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def get_mono_font(size=14):
    return _load_font([
        "/System/Library/Fonts/SFMono-Regular.otf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.dfont",
    ], size)

def get_cjk_font(size=14):
    return _load_font([
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ], size)

def _is_cjk(ch):
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF or 0x2E80 <= cp <= 0x2EFF or
            0x3000 <= cp <= 0x303F or 0xFF00 <= cp <= 0xFFEF or
            ch in 'ⓘ▸▾△Δ═─────────────────')

def _draw_mixed_text(draw, x, y, text, color, mono_font, cjk_font):
    """Draw text char-by-char, switching fonts for CJK characters."""
    for ch in text:
        if _is_cjk(ch):
            draw.text((x, y), ch, fill=color, font=cjk_font)
            x += CJK_CHAR_WIDTH
        else:
            draw.text((x, y), ch, fill=color, font=mono_font)
            x += CHAR_WIDTH
    return x

def _text_width(text):
    """Calculate pixel width of mixed text."""
    w = 0
    for ch in text:
        w += CJK_CHAR_WIDTH if _is_cjk(ch) else CHAR_WIDTH
    return w

def render_text_image(lines, filename, width=1200):
    """Render lines of (text, color) tuples to a PNG image."""
    mono_font = get_mono_font(14)
    cjk_font = get_cjk_font(14)
    height = PADDING * 2 + len(lines) * LINE_HEIGHT + 10
    img = Image.new('RGB', (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = PADDING
    for line_parts in lines:
        x = PADDING
        if isinstance(line_parts, str):
            line_parts = [(line_parts, TEXT_COLOR)]
        for text, color in line_parts:
            x = _draw_mixed_text(draw, x, y, text, color, mono_font, cjk_font)
        y += LINE_HEIGHT

    filepath = os.path.join(OUTPUT_DIR, filename)
    img.save(filepath, "PNG")
    print(f"Saved: {filepath}")


# ─── Screenshot 1: Historical Financial Data ───
lines1 = [
    [("════════════════════════════════════════════════════════════", HEADER_COLOR)],
    [("  贵州茅台 Historical Financial Data (Summary, in millions)", HEADER_COLOR)],
    [("════════════════════════════════════════════════════════════", HEADER_COLOR)],
    [("Calendar Year                   2025        2024        2023        2022        2021        2020", WHITE_COLOR)],
    [("Date                      2025-09-30  2024-12-31  2023-12-31  2022-12-31  2021-12-31  2020-12-31", MUTED_COLOR)],
    [("Period                   2025Q3(TTM)          FY          FY          FY          FY          FY", MUTED_COLOR)],
    [("Reported Currency                CNY         CNY         CNY         CNY         CNY         CNY", MUTED_COLOR)],
    [("▸ Profitability", CYAN_COLOR)],
    "Revenue                      178,576     170,899     147,693     124,099     106,190      94,915",
    "EBIT                         124,225     118,149     101,809      86,413      73,752      66,453",
    "Revenue Growth (%)               8.1        15.7        19.0        16.9        11.9         0.0",
    "EBIT Growth (%)                 10.1        16.0        17.8        17.2        11.0         0.0",
    "EBIT Margin (%)                 69.6        69.1        68.9        69.6        69.5        70.0",
    "Tax Rate (%)                    25.4        25.3        25.2        25.5        25.2        25.2",
    [("▸ Reinvestment", CYAN_COLOR)],
    "(+) Capital Expenditure        4,087       4,678       2,619       5,306       3,408       2,089",
    "(-) D&A                        2,085       2,085       1,937       1,688       1,581       1,316",
    "(+) ΔWorking Capital          -1,919      -1,919      11,667      29,126      -7,859        -857",
    "Total Reinvestment                83         674      12,349      32,744      -6,032         -84",
    [("▸ Capital Structure", CYAN_COLOR)],
    "(+) Total Debt                   262         425         323         443         400           0",
    "(+) Total Equity             265,705     242,011     223,656     204,938     196,957     167,720",
    "(-) Cash & Equivalents       175,407     165,761     164,720     165,707     168,539     143,001",
    "(-) Total Investments          5,542       5,792       9,726         380         170          29",
    "Invested Capital              85,017      70,883      49,533      39,293      28,648      24,688",
    "Minority Interest              8,635       8,905       7,987       7,458       7,418       6,397",
    [("▸ Key Ratios", CYAN_COLOR)],
    "Revenue / IC                     2.1         2.4         3.0         3.2         3.7         3.8",
    "ROIC (%)                       118.8        35.0        33.3        29.2        27.3        29.4",
    "ROE (%)                         36.7        36.0        34.2        30.3        29.9        31.4",
    "Debt to Assets (%)               0.1         0.1         0.1         0.2         0.2         0.0",
    "Cost of Debt (%)                 0.0         0.0         0.0         0.0         0.0         0.0",
    "",
    [("  ⓘ TTM Note: D&A and WC use FY2024 annual data; Capex is TTM", MUTED_COLOR)],
]

# ─── Screenshot 2: AI Copilot Parameter Suggestions (simulated) ───
lines2 = [
    [("════════════════════════════════════════════════════════════", HEADER_COLOR)],
    [("  AI 估值参数建议 — 逐项确认 (Claude Sonnet 4)", HEADER_COLOR)],
    [("════════════════════════════════════════════════════════════", HEADER_COLOR)],
    "",
    [("──── Revenue Growth Rate - Year 1 ────────────────────────", CYAN_COLOR)],
    "",
    [("  AI Suggestion: ", MUTED_COLOR), ("15.0%", GREEN_COLOR)],
    "",
    [("  Analysis:", WHITE_COLOR)],
    [("  Based on management guidance from Moutai's 2024 annual report,", TEXT_COLOR)],
    [("  the company targets ~15% revenue growth for 2025. Key drivers:", TEXT_COLOR)],
    [("  • Direct sales channel expansion (+20% YoY)", TEXT_COLOR)],
    [("  • Price increase on non-core products", TEXT_COLOR)],
    [("  • Analyst consensus: 14.5-16.2% (Wind, Bloomberg)", TEXT_COLOR)],
    "",
    [("  Sources: Moutai 2024 Annual Report, Wind consensus estimates", MUTED_COLOR)],
    "",
    [("  Accept 15.0%? (Enter to accept, or type new value): ", MUTED_COLOR), ("█", WHITE_COLOR)],
    "",
    "",
    [("──── Target EBIT Margin ─────────────────────────────────", CYAN_COLOR)],
    "",
    [("  AI Suggestion: ", MUTED_COLOR), ("70.0%", GREEN_COLOR)],
    "",
    [("  Analysis:", WHITE_COLOR)],
    [("  Moutai's EBIT margin has been stable at 69-70% over the past", TEXT_COLOR)],
    [("  5 years. As China's premium baijiu leader with 90%+ gross", TEXT_COLOR)],
    [("  margin, 70% target EBIT margin reflects operating leverage", TEXT_COLOR)],
    [("  at scale with minimal compression risk.", TEXT_COLOR)],
]

# ─── Screenshot 3: DCF Result ───
lines3 = [
    [("═══════════════════════════════════════════════════════════════", HEADER_COLOR)],
    [("  贵州茅台 Free Cashflow Forecast Results - 10 years, in millions", HEADER_COLOR)],
    [("═══════════════════════════════════════════════════════════════", HEADER_COLOR)],
    [("                    Base (2025Q3 TTM)     1      2      3      4      5    ...   10  Terminal", WHITE_COLOR)],
    [("Year                             2025  2026   2027   2028   2029   2030    ...  2035      2036", MUTED_COLOR)],
    "Revenue Growth Rate              8.1%  15.0%  12.0%  12.0%  12.0%  12.0%   ...   2.5%      2.5%",
    "Revenue                       178,577  205K   230K   258K   289K   323K    ...   438K      449K",
    "EBIT Margin                     69.6%  69.7%  69.9%  70.0%  70.0%  70.0%   ...  70.0%     70.0%",
    "EBIT(1-t)                      93,169  107K   121K   135K   151K   170K    ...   230K      236K",
    "FCFF                           93,086   94K   108K   124K   139K   156K    ...   226K      189K",
    "",
    [("────────────────────────────────────────────────────────────", CYAN_COLOR)],
    [("  Valuation Calculation - in millions", CYAN_COLOR)],
    [("────────────────────────────────────────────────────────────", CYAN_COLOR)],
    "  PV (FCFF over next 10 years) :     1,048,761",
    "  PV (Terminal value)          :     1,829,302",
    "  Sum of PV                    :     2,878,063",
    "  + Cash & Cash Equivalents    :       175,407",
    "  + Total Investments          :         5,543",
    "  Enterprise Value             :     3,059,013",
    "  - Total Debt                 :           263",
    "  - Minority Interest          :         8,635",
    "  Equity Value                 :     3,050,116",
    "  Outstanding Shares           : 1,252,270,215",
    "",
    [("  Equity Price per Share (CNY) :      ", TEXT_COLOR), ("2,435.67", GREEN_COLOR)],
]

# ─── Screenshot 4: Sensitivity Analysis ───
lines4 = [
    [("──────────────────────────────────────────────────────────────────────────", HEADER_COLOR)],
    [("  Sensitivity Analysis - Revenue Growth vs EBIT Margin (Price per Share)", HEADER_COLOR)],
    [("──────────────────────────────────────────────────────────────────────────", HEADER_COLOR)],
    [("  EBIT ▸         65%       66%       67%       68%       69%       70%       71%       72%       73%       74%       75%", WHITE_COLOR)],
    [("Growth ▾  ────────────────────────────────────────────────────────────────────────────────────────────────────────", MUTED_COLOR)],
    "      7% |     1,834     1,859     1,885     1,910     1,936     1,961     1,986     2,012     2,037     2,063     2,088",
    "      8% |     1,914     1,941     1,967     1,994     2,021     2,048     2,074     2,101     2,128     2,155     2,181",
    "      9% |     1,998     2,026     2,054     2,082     2,110     2,138     2,166     2,194     2,223     2,251     2,279",
    "     10% |     2,086     2,115     2,145     2,174     2,204     2,233     2,263     2,292     2,322     2,351     2,381",
    "     11% |     2,177     2,208     2,239     2,270     2,301     2,332     2,363     2,394     2,425     2,456     2,487",
    [("     12% |     2,273     2,306     2,338     2,371     2,403     ", TEXT_COLOR), ("2,436", GREEN_COLOR), ("     2,468     2,501     2,533     2,566     2,598", TEXT_COLOR)],
    "     13% |     2,373     2,407     2,441     2,476     2,510     2,544     2,578     2,612     2,646     2,680     2,714",
    "     14% |     2,478     2,514     2,549     2,585     2,621     2,657     2,693     2,728     2,764     2,800     2,836",
    "     15% |     2,587     2,625     2,662     2,700     2,737     2,775     2,812     2,850     2,887     2,925     2,963",
    "     16% |     2,701     2,740     2,780     2,819     2,859     2,898     2,937     2,977     3,016     3,056     3,095",
    "     17% |     2,820     2,861     2,903     2,944     2,985     3,026     3,068     3,109     3,150     3,192     3,233",
    "",
    [("────────────────────────────────────────────────────────────", HEADER_COLOR)],
    [("  Sensitivity Analysis - WACC (Price per Share)", HEADER_COLOR)],
    [("────────────────────────────────────────────────────────────", HEADER_COLOR)],
    [("            5.5%        6.0%        6.5%        7.0%        7.5%        8.0%        8.5%        9.0%        9.5%       10.0%       10.5%", WHITE_COLOR)],
    [("           2,496       2,483       2,471       2,459       2,447       ", TEXT_COLOR), ("2,436", GREEN_COLOR), ("       2,424       2,413       2,402       2,392       2,381", TEXT_COLOR)],
]


if __name__ == '__main__':
    render_text_image(lines1, "demo-1-historical.png", width=1060)
    render_text_image(lines2, "demo-2-ai-params.png", width=780)
    render_text_image(lines3, "demo-3-dcf-result.png", width=860)
    render_text_image(lines4, "demo-4-sensitivity.png", width=1200)
    print("\nAll screenshots rendered!")
