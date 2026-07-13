## Language
- [English](README.md)
- [中文](README_zh.md)

---

# ValueScope

**A standardized DCF valuation engine your AI can call — deterministic, reproducible, and built for A-shares / HK / US / JP.**

[![Try Online](https://img.shields.io/badge/🌐_Try_Online-valuescope.app-2563eb?style=for-the-badge)](https://valuescope.app)
[![MCP](https://img.shields.io/badge/MCP-mcp.valuescope.app-7c3aed?style=for-the-badge)](https://mcp.valuescope.app/mcp)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)

---

## What is ValueScope?

ValueScope is a **standardized Damodaran FCFF DCF engine** — 10-year explicit forecast, terminal value, WACC, sensitivity analysis, and reverse DCF in a fixed, reproducible framework.

Ask an LLM to "value this stock" and every conversation may use a different data source, accounting convention, and model — you can't tell whether a changed valuation means the fundamentals moved or the AI just felt different this time. ValueScope solves that with a clean division of labor:

- **Your AI does the judgment** — searches earnings guidance, analyst consensus, and industry benchmarks, then reasons about each assumption.
- **The engine does the data and the math** — A-share deducted-NI convention, non-operating-item EBIT adjustment, 10-year FCFF discounting, sensitivity, reverse DCF. **Same inputs always yield the same output.**

Your AI brings the intelligence; ValueScope brings the framework and the discipline. The engine itself never calls an LLM.

**Supported Markets:** 🇨🇳 A-shares &nbsp; 🇭🇰 Hong Kong &nbsp; 🇺🇸 US &nbsp; 🇯🇵 Japan

**Three ways to use it:** the [MCP server](#mcp-server) (call it from your own AI), the [web app](#web-app) (manual operator console), and the [terminal CLI](#terminal-cli).

---

## MCP Server

The MCP ([Model Context Protocol](https://modelcontextprotocol.io)) server lets any MCP-capable AI client — Claude, ChatGPT, Cherry Studio, Dify, and others — call the same deterministic DCF engine the web app uses. This is the recommended way to use ValueScope.

**Endpoint:** `https://mcp.valuescope.app/mcp`

### Connect in two minutes

**Claude Code** (terminal and desktop app share one config):

```bash
claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp
```

**Claude web / mobile app:** Settings → Connectors → add a custom connector, paste `https://mcp.valuescope.app/mcp`.

**Cherry Studio and other desktop clients:** add an MCP server of type HTTP with the same URL.

Then just ask in natural language: *"Value Kweichow Moutai with a DCF"* — no commands to learn.

### How it works — one tool, two phases

The server exposes a single `run_dcf` tool that mirrors an equity analyst's workflow, with the calling model playing the analyst:

1. **Baseline** — call `run_dcf(ticker)` with no assumptions. Returns a baseline valuation from 5-year historical averages, each parameter's historical range, and an analyst guide telling the model how to evaluate every assumption.
2. **Final** — the model searches the web for guidance and consensus, reasons about each parameter, then calls `run_dcf(ticker, <assumptions>)` for the final valuation: intrinsic value, value bridge, forecast table, sensitivity matrix, and reverse DCF (what the market price implies).

A `dcf` MCP prompt is also exposed, surfacing a one-command workflow (baseline → search → reason → three scenarios) in clients that support MCP prompts.

Ticker format: A-shares `600519.SS` / `000333.SZ`, HK `0700.HK`, US `AAPL`, JP `7203.T`.

### FMP key for US / JP

A-shares and HK need no key. US / JP data comes from FMP (see [Data Sources](#data-sources--fmp-api-key)). US/JP tickers get a small daily free trial served by the server; beyond that, provide your own key one of two ways:

**Configure once (recommended)** — pass it as a request header so every conversation uses it automatically. If you already added the server without a key, remove and re-add it:

```bash
claude mcp remove valuescope
claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp --header "X-FMP-Key: YOUR_KEY"
```

**Per-conversation** — just say *"my FMP key is …"* in the chat; the model passes it on each call (only valid for that conversation).

### Self-hosting the MCP server

The server is mounted on the FastAPI backend at `/mcp` (streamable HTTP). Run the backend (see [Installation](#option-3-self-host-the-backend--mcp)) and it's available at `http://localhost:8000/mcp`. Set `FMP_API_KEY` in the environment to enable the US/JP trial; tune `MCP_DAILY_LIMIT` and `MCP_US_TRIAL_DAILY_LIMIT` for rate limits.

---

## Web App

Try it at **[valuescope.app](https://valuescope.app)** — no installation required.

The web app is the **manual operator console**: dial in DCF parameters by hand, watch the valuation update live, read sensitivity tables, and eyeball relative-valuation percentiles and multi-factor scores. If you like driving the assumptions yourself, it's a solid DCF calculator.

### Features

- **DCF Valuation** — Damodaran FCFF framework with interactive parameter controls, 10-year forecast table, dual sensitivity analysis (Growth×Margin, WACC), and bridge-to-value breakdown.
- **Relative Valuation** — Current multiples (PE, PB, PS, EV/EBITDA) vs historical percentiles across 3/5/10-year windows.
- **4-Dimension Scoring** — Valuation, Quality, Growth, and Momentum in a radar chart with transparent sub-factor breakdown.
- **Financial Overview** — Key drivers (revenue growth, EBIT margin, ROIC, FCF), balance sheet highlights, and historical financial table.
- **Bilingual UI** — English and Chinese with one-click toggle.

![Web App Overview](assets/web-overview.png)
![Web App Valuation](assets/web-valuation.png)

---

## Terminal CLI

For local use with your own AI CLI subscription. Requires Python 3.8+.

- **AI Copilot** — local AI engine (Claude / Gemini / Qwen) suggests parameters; you review and adjust interactively.
- **Custom Valuation** — full manual control with `--manual`. No AI or API key required.
- **Auto Mode** — fully automated with `--auto`: AI → accept → export Excel.
- **Excel Export** — formatted `.xlsx` with valuation results, historical data, and AI reasoning.

| Engine | Install | Notes |
|--------|---------|-------|
| **Claude** | `npm install -g @anthropic-ai/claude-code` | Default if available. |
| **Gemini** | `npm install -g @google/gemini-cli` | Free with a Google account. |
| **Qwen** | `npm install -g @anthropic-ai/qwen-code` | Free with a qwen.ai account. |

Auto-detects installed engines (priority: Claude > Gemini > Qwen), or force one with `--engine`. If none is found, falls back to manual mode.

![Historical Data](assets/demo-1-historical.png)
![DCF Result](assets/demo-3-dcf-result.png)

---

## Data Sources & FMP API Key

| Market | Data Source | API Key |
|--------|-----------|---------|
| **A-shares** | akshare | Not required (free) |
| **Hong Kong** | yfinance (annual) / FMP (quarterly) | Annual: free; Quarterly: FMP key |
| **US** | FMP | FMP key required |
| **Japan** | FMP | FMP key required |

> 💡 **[Get an FMP API Key →](https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope)**
>
> FMP (Financial Modeling Prep) provides high-quality financial data for US, HK, and JP markets. **Subscribing through this link (coupon `valuescope` included) is discounted** — and supports ValueScope's ongoing development.

---

## Installation & Usage

### Option 1: MCP Server (Recommended)

No installation — connect your AI to `https://mcp.valuescope.app/mcp` (see [MCP Server](#mcp-server) above).

### Option 2: Web App

Visit **[valuescope.app](https://valuescope.app)** — no installation needed.

### Option 3: Self-host (CLI + backend + MCP)

Requires Python 3.8+.

```bash
git clone https://github.com/alanhewenyu/ValueScope.git
cd ValueScope
pip install -r requirements.txt          # CLI
pip install -r requirements-api.txt      # backend + MCP server
```

Set your FMP API key (required for US/Japan):

```bash
export FMP_API_KEY='your_api_key_here'
```

Run the CLI:

```bash
python main.py                    # AI copilot (default)
python main.py --manual           # Manual input
python main.py --auto             # Fully automated
```

Or run the backend (serves the REST API and the MCP server at `/mcp`):

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## Architecture

```
valuescope/
├── frontend/              # Next.js (React) — web UI
├── backend/              # FastAPI — REST API + MCP server
│   └── mcp_server.py     # MCP tool (run_dcf) + dcf prompt
├── modeling/             # Core valuation engine (shared by CLI, backend, MCP)
├── main.py               # Terminal CLI entry point
└── Dockerfile            # Backend container
```

The `modeling/` engine is the single source of truth — the CLI, the web backend, and the MCP server all call it, so a valuation is identical no matter how you reach it.

---

## Key Valuation Parameters

| Parameter | Description |
|-----------|-------------|
| **Revenue Growth (Year 1)** | Next year's revenue forecast. Prioritize company guidance, then analyst consensus. |
| **Revenue Growth (Years 2-5)** | Compound annual growth rate (CAGR) for years 2-5. |
| **Target EBIT Margin** | Expected EBIT margin at maturity. |
| **Revenue/Invested Capital** | Capital efficiency ratio for different periods. |
| **WACC** | Auto-calculated from risk-free rate, ERP, and beta; adjustable. |
| **RONIC** | Return on new invested capital in terminal period. Defaults to WACC. |

---

## Contributing

Issues and pull requests are welcome. Contact: [alanhe@icloud.com](mailto:alanhe@icloud.com)

For more on company valuation, visit [jianshan.co](https://jianshan.co) or scan to follow on WeChat:

<img src="https://jianshan.co/images/wechat-qrcode-v2.jpg" alt="见山笔记 WeChat QR Code" width="200">

---

## License

This project is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).

You are free to use, modify, and distribute this software, but any modified version — including use as a network service (SaaS) or a hosted MCP server — must also be open-sourced under AGPL-3.0.

© 2025-2026 Alan He
