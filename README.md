## Language
- [English](README.md)
- [中文](README_zh.md)

---

## What is ValuX?

ValuX is an AI-powered stock valuation tool built on the Discounted Cash Flow (DCF) model. It automates data collection, leverages AI to generate valuation parameters with real-time market research, and calculates a company's intrinsic value — all from your terminal.

Think of it as having an equity research analyst sitting next to you: AI searches for earnings guidance, analyst consensus, and industry benchmarks, then suggests valuation parameters for your review. You stay in control; AI handles the heavy lifting.

---

## Key Features

- **Multi-Engine AI Copilot** — Supports three AI engines: [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), and [Qwen Code](https://github.com/QwenLM/qwen-code). Auto-detects installed engines (priority: Claude > Gemini > Qwen), or specify one with `--engine`. AI analyzes the company, searches the web for analyst forecasts and earnings guidance, and suggests DCF parameters with detailed reasoning. You review and adjust each parameter interactively.
- **Manual Mode** — Prefer full control? Use `--manual` to input all parameters yourself. No AI engine or API key required.
- **Auto Mode** — Use `--auto` for a fully automated pipeline: AI analysis, parameter acceptance, and Excel export with no interaction.
- **Gap Analysis** — After valuation, AI compares your DCF result against the current stock price, searches for analyst price targets, and explains potential reasons for the discrepancy.
- **Sensitivity Analysis** — Generates sensitivity tables for Revenue Growth vs EBIT Margin and WACC, showing the range of possible per-share valuations.
- **Excel Export** — Exports valuation results, historical data, financial statements, and AI gap analysis to a formatted Excel workbook.
- **Global Coverage** — Supports US, China A-shares, Hong Kong, and other markets, with automatic WACC calculation based on country-specific risk-free rates and equity risk premiums.
- **Free Tier for A-shares & HK Stocks** — A-shares (via akshare) and HK annual data (via yfinance) require no API key. Combined with manual mode, you get a fully free valuation workflow.

---

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│  Enter stock symbol  →  Fetch annual historical financials   │
│                          ↓                                   │
│  Display historical data summary (with TTM if available)     │
│                          ↓                                   │
│  [Optional] View quarterly data as reference                 │
│                          ↓                                   │
│  AI Copilot: search web → suggest parameters → you review    │
│                          ↓                                   │
│  Calculate DCF → intrinsic value per share                   │
│                          ↓                                   │
│  Sensitivity analysis (Revenue Growth × EBIT Margin, WACC)   │
│                          ↓                                   │
│  [Optional] AI gap analysis: DCF vs current stock price      │
│                          ↓                                   │
│  [Optional] Export to Excel                                  │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Sources

ValuX uses different data sources depending on the market, optimizing for data quality and cost:

| Market | Annual Data | Quarterly Data | API Key |
|--------|------------|----------------|---------|
| **China A-shares** | [akshare](https://github.com/akfamily/akshare) | akshare | **Not required** (free) |
| **Hong Kong** | [yfinance](https://github.com/ranaroussi/yfinance) | [FMP](https://financialmodelingprep.com/) | Annual: **free**; Quarterly: FMP key required |
| **US & Others** | [FMP](https://financialmodelingprep.com/) | FMP | FMP key required |

**Why multiple data sources?**
- **akshare** provides original China GAAP profit statements for accurate EBIT calculation.
- **yfinance** provides reliable HK annual financial data without an API key. HK quarterly data routes to FMP for full quarterly breakdown.
- **FMP** is the primary data source for US and international stocks, providing financial statements, market data, company profiles, and risk premiums.

> **No API key at all?** You can still query A-shares and HK annual data for free. Use `--manual` mode to input valuation parameters yourself — a fully free workflow.

---

## AI Engines

ValuX supports three AI engines. On startup, it auto-detects installed CLI tools (priority: Claude > Gemini > Qwen). You can also force a specific engine with `--engine`.

| Engine | CLI Tool | Install | Notes |
|--------|----------|---------|-------|
| **Claude** | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `npm install -g @anthropic-ai/claude-code` | Default if available. Requires Anthropic account. |
| **Gemini** | [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npm install -g @google/gemini-cli` | Free with Google account login. |
| **Qwen** | [Qwen Code](https://github.com/QwenLM/qwen-code) | `npm install -g @anthropic-ai/qwen-code` | Free with qwen.ai account login. |

If no AI engine is detected, ValuX automatically falls back to manual mode.

---

## Running Modes

| Mode | Command | AI Required | Description |
|------|---------|-------------|-------------|
| **Copilot** (default) | `python main.py` | Yes | AI suggests each parameter with reasoning; you review and adjust interactively. |
| **Manual** | `python main.py --manual` | No | You input all valuation parameters yourself. Works without any AI engine or API key. |
| **Auto** | `python main.py --auto` | Yes | Fully automated: AI analysis → auto-accept parameters → auto-export Excel. No user interaction. |

Additional flags:
- `--engine claude|gemini|qwen` — Force a specific AI engine instead of auto-detection.
- `--apikey YOUR_KEY` — Pass FMP API key directly (alternative to `FMP_API_KEY` env variable).

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/alanhewenyu/ValuX.git
cd ValuX
```

### 2. Install Dependencies

Requires Python 3.8+.

```bash
pip install -r requirements.txt
```

### 3. Set Up FMP API Key (Optional)

Required for US stocks and HK quarterly data. Not required for A-shares or HK annual data.

Register at [Financial Modeling Prep](https://financialmodelingprep.com/) and set your API key:

```bash
export FMP_API_KEY='your_api_key_here'
```

### 4. Set Up AI Engine (Optional)

Install any one of the supported AI CLI tools:

```bash
# Option 1: Claude Code (recommended)
npm install -g @anthropic-ai/claude-code

# Option 2: Gemini CLI (free with Google account)
npm install -g @google/gemini-cli

# Option 3: Qwen Code (free with qwen.ai account)
npm install -g @anthropic-ai/qwen-code
```

If no AI engine is available, ValuX falls back to manual mode automatically.

### 5. Run

```bash
python main.py                      # AI copilot mode (default)
python main.py --manual             # Manual input mode
python main.py --auto               # Full auto mode
python main.py --engine gemini      # Force Gemini engine
```

---

## Usage

1. **Enter stock symbol** — e.g., `AAPL`, `600519.SS` (Moutai), `0700.HK` (Tencent)
2. **Review annual historical data** — The program fetches and displays the annual financial summary with TTM data (if available).
3. **View quarterly data** (optional) — Choose to view quarterly financial data as a reference before valuation.
4. **AI parameter generation** (or manual input) — AI suggests each parameter with reasoning; press Enter to accept or type a new value.
5. **View DCF results** — Intrinsic value per share and the full calculation breakdown.
6. **Sensitivity analysis** — Two tables: Revenue Growth vs EBIT Margin, and WACC sensitivity.
7. **Gap analysis** (optional) — AI analyzes why DCF value differs from market price.
8. **Export to Excel** (optional) — Saves everything to a formatted `.xlsx` file.

### Input Format

Percentage parameters (revenue growth, EBIT margin, tax rate, WACC) are entered as plain numbers: enter `10` for 10%, not `10%`.

---

## Key Valuation Parameters

| Parameter | Description |
|-----------|-------------|
| **Revenue Growth (Year 1)** | Next year's revenue forecast. AI prioritizes company earnings guidance, then analyst consensus. |
| **Revenue Growth (Years 2-5)** | Compound annual growth rate (CAGR) for years 2-5. |
| **Target EBIT Margin** | The EBIT margin the company is expected to reach at maturity. |
| **Convergence Years** | Years needed to reach the target EBIT margin from current level. |
| **Revenue/Invested Capital Ratio** | Capital efficiency ratio for different periods (Year 1-2, 3-5, 5-10). AI cross-validates against historical reinvestment data. |
| **Tax Rate** | Auto-calculated from historical data; adjustable. |
| **WACC** | Auto-calculated from risk-free rate, equity risk premium, and beta; adjustable. |
| **RONIC** | Return on new invested capital in the terminal period. Defaults to WACC (competitive equilibrium) or WACC + 5% for companies with durable competitive advantages. |

> **Note on EBIT**: For A-shares, EBIT is calculated from akshare raw data with non-operating items (investment income, fair value changes, etc.) excluded. For HK stocks, operating income is used directly; some companies may include material non-operating items that are not stripped out — review with caution.

---

## Why DCF Valuation Matters

Price is what you pay; value is what you get. DCF valuation estimates a company's intrinsic value by discounting future free cash flows — it's the foundation of value investing.

This tool focuses on three core drivers: **revenue growth**, **operating efficiency (EBIT margin)**, and **reinvestment**. As Buffett said, *"I would rather be vaguely right than precisely wrong."* Through sensitivity analysis, you can find the margin of safety even with imperfect assumptions.

---

## Contributing

Issues and pull requests are welcome. Contact: [alanhe@icloud.com](mailto:alanhe@icloud.com)

For more on company valuation, follow my WeChat Official Account: **见山笔记**

---

## License

MIT License. See [LICENSE](LICENSE) for details.
