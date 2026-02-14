## Language
- [English](README.md)
- [中文](README_zh.md)

---

## What is ValuX?

ValuX is an AI-powered stock valuation tool built on the Discounted Cash Flow (DCF) model. It automates data collection, leverages AI to generate valuation parameters with real-time market research, and calculates a company's intrinsic value — all from your terminal.

Think of it as having an equity research analyst sitting next to you: AI searches for earnings guidance, analyst consensus, and industry benchmarks, then suggests valuation parameters for your review. You stay in control; AI handles the heavy lifting.

---

## Key Features

- **AI Copilot Mode** — Powered by [Claude Code](https://docs.anthropic.com/en/docs/claude-code), an AI coding tool developed by Anthropic. The AI analyzes the company, searches the web for analyst forecasts and earnings guidance, and suggests DCF parameters with detailed reasoning. You review and adjust each parameter interactively. See [Set Up AI Copilot](#4-set-up-ai-copilot-optional) for details.
- **Manual Mode** — Prefer full control? Use `--manual` to input all parameters yourself.
- **Gap Analysis** — After valuation, AI compares your DCF result against the current stock price, searches for analyst price targets, and explains potential reasons for the discrepancy.
- **Sensitivity Analysis** — Generates sensitivity tables for Revenue Growth vs EBIT Margin and WACC, showing the range of possible per-share valuations.
- **Excel Export** — Exports valuation results, historical data, financial statements, and AI gap analysis to a formatted Excel workbook.
- **Global Coverage** — Supports US, China A-shares, Hong Kong, and other markets, with automatic WACC calculation based on country-specific risk-free rates and equity risk premiums.

---

## How It Works

```
┌──────────────────────────────────────────────────────────────┐
│  Enter stock symbol  →  Fetch historical financials          │
│                          ↓                                   │
│  Display historical data summary                             │
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

| Source | Coverage | API Key | Description |
|--------|----------|---------|-------------|
| [**FMP**](https://financialmodelingprep.com/) | Global (US, China A-shares, HK, etc.) | Required | Financial statements, market data, valuation metrics, company profiles, risk premiums. Primary data source for all markets. |
| [**akshare**](https://github.com/akfamily/akshare) | China A-shares | Not required | Used to fetch original China GAAP profit statements and calculate EBIT accurately. FMP's operating income for Chinese stocks includes non-operating items (investment income, fair value changes, etc.); akshare provides the raw data needed to compute a clean EBIT. |

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

### 3. Get an FMP API Key

Register at [Financial Modeling Prep](https://financialmodelingprep.com/) and set your API key:

```bash
export FMP_API_KEY='your_api_key_here'
```

### 4. Set Up AI Copilot (Optional)

The AI features require [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated. ValuX calls Claude via CLI to perform web search and generate analysis. The model used depends on your Claude Code configuration (defaults to Claude Sonnet). You can switch models via `claude config set model` if you have access to other models (e.g., Claude Opus).

If Claude CLI is not available, ValuX automatically falls back to manual mode.

```bash
claude --version
```

### 5. Run

```bash
python main.py              # AI copilot mode (default)
python main.py --manual     # Manual input mode
```

---

## Usage

1. **Enter stock symbol** — e.g., `AAPL`, `600519.SS` (Moutai), `000333.SZ` (Midea)
2. **Select period** — `annual` or `quarter`
3. **Review historical data** — The program displays a financial summary table.
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
