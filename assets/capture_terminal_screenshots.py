#!/usr/bin/env python3
"""Capture real terminal CLI screenshots using pexpect + ansi2html + Playwright."""

import os
import re
import pexpect
import time
from ansi2html import Ansi2HTMLConverter
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# HTML template mimicking a macOS terminal window
HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<style>
  body {{
    margin: 0; padding: 0;
    background: transparent;
    font-size: 0;
  }}
  .terminal {{
    display: inline-block;
    background: #1e1e1e;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    overflow: hidden;
    max-width: {width}px;
  }}
  .titlebar {{
    background: linear-gradient(#3a3a3a, #303030);
    padding: 8px 12px;
    display: flex;
    align-items: center;
    gap: 7px;
  }}
  .btn {{ width: 12px; height: 12px; border-radius: 50%; }}
  .btn-red {{ background: #ff5f56; }}
  .btn-yellow {{ background: #ffbd2e; }}
  .btn-green {{ background: #27c93f; }}
  .titlebar-text {{
    flex: 1;
    text-align: center;
    color: #999;
    font-family: -apple-system, system-ui, sans-serif;
    font-size: 12px;
    margin-right: 50px;
  }}
  .content {{
    padding: 16px 20px;
    font-family: 'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace;
    font-size: 14px;
    line-height: 1.5;
    color: #ccc;
    white-space: pre;
    overflow: hidden;
  }}
  /* Override ansi2html defaults */
  .content .ansi2html-content {{ white-space: pre; }}
  .content .body_foreground {{ color: #ccc; }}
  .content .body_background {{ background: transparent; }}
  .content span {{ font-family: inherit; font-size: inherit; }}
  .content .ansi1 {{ font-weight: bold; }}
  .content .ansi33 {{ color: #e5c07b; }}  /* Yellow */
  .content .ansi36 {{ color: #56b6c2; }}  /* Cyan */
  .content .ansi32 {{ color: #98c379; }}  /* Green */
  .content .ansi31 {{ color: #e06c75; }}  /* Red */
  .content .ansi35 {{ color: #c678dd; }}  /* Magenta */
  .content .ansi37 {{ color: #ddd; }}     /* White */
  .content .ansi90 {{ color: #888; }}     /* Bright black / muted */
  .content .ansi96 {{ color: #56b6c2; }}  /* Bright cyan */
  .content .ansi93 {{ color: #e5c07b; }}  /* Bright yellow */
  .content .ansi2 {{ opacity: 0.7; }}     /* Dim */
  .content .ansi3 {{ font-style: italic; }}/* Italic */
</style>
</head>
<body>
<div class="terminal">
  <div class="titlebar">
    <div class="btn btn-red"></div>
    <div class="btn btn-yellow"></div>
    <div class="btn btn-green"></div>
    <div class="titlebar-text">{title}</div>
  </div>
  <div class="content">{content}</div>
</div>
</body>
</html>"""


def clean_ansi_output(text):
    """Clean up raw pexpect output: remove progress bars, extra blank lines."""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        # Skip progress bar lines (tqdm)
        if '|' in line and ('it/s' in line or '%|' in line):
            continue
        # Skip carriage return lines
        if '\r' in line and line.strip().startswith('\x1b'):
            line = line.split('\r')[-1]
        # Remove \r
        line = line.replace('\r', '')
        cleaned.append(line)

    # Remove consecutive blank lines (keep max 1)
    result = []
    prev_blank = False
    for line in cleaned:
        stripped = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if not stripped:
            if not prev_blank:
                result.append(line)
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False
    return '\n'.join(result)


def ansi_to_html(ansi_text):
    """Convert ANSI text to HTML spans."""
    conv = Ansi2HTMLConverter(inline=True, dark_bg=True, scheme='osx')
    html = conv.convert(ansi_text, full=False)
    return html


def render_html_to_png(html_content, output_path, pw_browser, vp_width=1400):
    """Render HTML to PNG using Playwright."""
    page = pw_browser.new_page(viewport={"width": vp_width, "height": 900},
                               device_scale_factor=2)
    page.set_content(html_content)
    # Wait for rendering
    time.sleep(0.5)
    # Get the terminal div bounding box
    terminal = page.locator('.terminal')
    box = terminal.bounding_box()
    if box:
        terminal.screenshot(path=output_path)
    else:
        page.screenshot(path=output_path)
    page.close()
    print(f"Saved: {os.path.basename(output_path)}")


def run_cli_session():
    """Run the ValuX CLI session and capture output sections."""
    sections = {}

    child = pexpect.spawn(
        'python3 main.py --manual',
        cwd='/Users/Alan/valux',
        encoding='utf-8',
        timeout=90,
        dimensions=(60, 140),  # rows x cols — wider for tables
        maxread=200000,
    )

    # 1. Ticker input
    child.expect('stock symbol.*:')
    child.sendline('600519.SS')

    # 2. Wait for data fetch + historical data display
    # First: quarterly data prompt
    child.expect('quarterly financial data', timeout=60)
    sections['historical'] = child.before
    child.sendline('')  # Skip quarterly

    # Then: proceed with valuation
    child.expect('Proceed with valuation', timeout=15)
    child.sendline('')  # Enter to proceed

    # 3. Manual inputs
    child.expect('Year 1.*:')
    child.sendline('15')
    child.expect('Years 2-5.*:')
    child.sendline('14.3')
    child.expect('EBIT margin.*:')
    child.sendline('69.5')
    child.expect('years to reach.*:')
    child.sendline('5')
    child.expect('ratio for Year 1.*:')
    child.sendline('2.1')
    child.expect('ratio for Years 3-5.*:')
    child.sendline('3.03')
    child.expect('ratio for Years 5-10.*:')
    child.sendline('3.03')

    # Tax rate (accept default)
    child.expect('Tax Rate.*:')
    child.sendline('')

    # WACC (accept default)
    child.expect('WACC.*:')
    child.sendline('')

    # ROIC
    child.expect('ROIC.*:')
    child.sendline('n')

    # 4. DCF results (up to sensitivity header)
    child.expect('Sensitivity Analysis', timeout=30)
    sections['dcf'] = child.before

    # 5. Sensitivity tables (prepend matched text back)
    child.expect('gap|差异分析|Exit|Exit program|Valuation completed', timeout=30)
    sections['sensitivity'] = 'Sensitivity Analysis' + child.before

    # Exit
    child.sendline('n')
    time.sleep(1)
    child.expect(['Exit|exit|y/n|completed', pexpect.TIMEOUT, pexpect.EOF], timeout=5)
    child.sendline('y')

    try:
        child.expect(pexpect.EOF, timeout=5)
    except:
        child.close()

    return sections


def extract_section(text, start_marker, end_marker=None, max_lines=None):
    """Extract a section from ANSI text by markers."""
    lines = text.split('\n')
    start_idx = None
    end_idx = len(lines)

    for i, line in enumerate(lines):
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
        if start_marker in clean and start_idx is None:
            start_idx = i
        if end_marker and end_marker in clean and start_idx is not None and i > start_idx:
            end_idx = i
            break

    if start_idx is None:
        return text

    result_lines = lines[start_idx:end_idx]
    if max_lines:
        result_lines = result_lines[:max_lines]
    return '\n'.join(result_lines)


def main():
    print("Running CLI session...")
    sections = run_cli_session()

    # Clean up outputs
    hist_raw = clean_ansi_output(sections['historical'])
    dcf_raw = clean_ansi_output(sections['dcf'])
    sens_raw = clean_ansi_output(sections['sensitivity'])

    # Extract specific sections
    hist_section = extract_section(hist_raw, 'Historical Financial Data')
    dcf_section = dcf_raw.strip()
    sens_section = sens_raw.strip()

    # Remove trailing prompt lines from sensitivity
    sens_lines = sens_section.split('\n')
    while sens_lines and ('?' in re.sub(r'\x1b\[[0-9;]*m', '', sens_lines[-1]) or
                           '是否' in re.sub(r'\x1b\[[0-9;]*m', '', sens_lines[-1])):
        sens_lines.pop()
    sens_section = '\n'.join(sens_lines)

    # Debug: save clean sections
    import re as _re
    for label, text in [('hist', hist_section), ('dcf', dcf_section), ('sens', sens_section)]:
        clean = _re.sub(r'\x1b\[[0-9;]*m', '', text)
        with open(os.path.join(OUTPUT_DIR, f'_debug_{label}.txt'), 'w') as f:
            f.write(clean)
        print(f"Debug: {label} = {len(clean)} chars, {clean.count(chr(10))} lines")

    print("\nRendering screenshots...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. Historical data
        html = HTML_TEMPLATE.format(
            width=1100,
            title='python main.py — 贵州茅台 (600519.SS)',
            content=ansi_to_html(hist_section)
        )
        render_html_to_png(html, os.path.join(OUTPUT_DIR, 'demo-1-historical.png'), browser)

        # 3. DCF result
        html = HTML_TEMPLATE.format(
            width=1200,
            title='python main.py — DCF Valuation Result',
            content=ansi_to_html(dcf_section)
        )
        render_html_to_png(html, os.path.join(OUTPUT_DIR, 'demo-3-dcf-result.png'), browser, vp_width=1400)

        # 4. Sensitivity
        html = HTML_TEMPLATE.format(
            width=1400,
            title='python main.py — Sensitivity Analysis',
            content=ansi_to_html(sens_section)
        )
        render_html_to_png(html, os.path.join(OUTPUT_DIR, 'demo-4-sensitivity.png'), browser, vp_width=1600)

        browser.close()

    print("\nAll terminal screenshots captured!")


if __name__ == '__main__':
    main()
