## Language
- [English](README.md)
- [中文](README_zh.md)

---

# ValueScope

**AI-powered interactive DCF valuation — standardized model, real-time parameter tuning, reproducible results.**

[![Try Online](https://img.shields.io/badge/🌐_Try_Online-valuescope.app-2563eb?style=for-the-badge)](https://valuescope.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)

---

## What is ValueScope?

ValueScope is an AI-powered stock valuation tool built on a **standardized DCF engine** — 10-year FCFF forecast, terminal value, WACC, and sensitivity analysis in a fixed, reproducible framework. Unlike asking an LLM to "value this stock" (where every conversation may use a different method or discount rates), ValueScope produces **consistent, comparable results** across companies and time periods.

Think of it as having an equity research analyst sitting next to you: AI searches for earnings guidance, analyst consensus, and industry benchmarks, then suggests valuation parameters — but the underlying model is always rigorous, transparent, and under your control.

**Supported Markets:** 🇺🇸 US &nbsp; 🇭🇰 Hong Kong &nbsp; 🇨🇳 A-shares &nbsp; 🇯🇵 Japan

---

## Demo

### Cloud Web App — Landing Page

![Cloud Web App](assets/web-landing.png)

### Cloud Web App — Verdict + Interactive Sliders

![Cloud Web App Valuation](assets/web-valuation.png)

### Terminal CLI

![Historical Data](assets/demo-1-historical.png)
![AI Analysis](assets/demo-2-ai-params.png)
![DCF Result](assets/demo-3-dcf-result.png)

---

## Key Features

- **AI Copilot** — AI searches the web for analyst forecasts, earnings guidance, and industry data, then suggests DCF parameters with detailed reasoning. You review and adjust interactively.
- **Cloud Web App** — Try it at [valuescope.app](https://valuescope.app) with built-in Cloud AI (DeepSeek R1 + Serper web search). No installation needed.
- **Terminal CLI** — Supports three local AI engines: [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Gemini CLI](https://github.com/google-gemini/gemini-cli), [Qwen Code](https://github.com/QwenLM/qwen-code). Auto-detects installed engines or specify with `--engine`.
- **Custom Valuation** — Full manual control via sliders (web) or `--manual` (terminal). No AI or API key required.
- **Verdict & Gap Analysis** — BUY/HOLD/SELL verdict with margin of safety. AI compares DCF result against market price and analyst targets.
- **Sensitivity Analysis & Excel Export** — Revenue Growth × EBIT Margin and WACC sensitivity tables. Export everything to a formatted `.xlsx` workbook.

---

## Data Sources & FMP API Key

| Market | Data Source | API Key |
|--------|-----------|---------|
| **A-shares** | [akshare](https://github.com/akfamily/akshare) | Not required (free) |
| **Hong Kong** | [yfinance](https://github.com/ranaroussi/yfinance) (annual) / [FMP](https://site.financialmodelingprep.com/register) (quarterly) | Annual: free; Quarterly: FMP key |
| **US** | [FMP](https://site.financialmodelingprep.com/register) | FMP key required |
| **Japan** | [FMP](https://site.financialmodelingprep.com/register) | FMP key required |

> 💡 **[Get FMP API Key →](https://site.financialmodelingprep.com/register)**
>
> FMP (Financial Modeling Prep) provides high-quality financial data for US, HK, and JP markets. **Buy through this link for a discounted price** — it also supports ValueScope's ongoing development.

---

## Installation

```bash
# 1. Clone and install
git clone https://github.com/alanhewenyu/ValueScope.git
cd ValueScope
pip install -r requirements.txt

# 2. Set FMP API Key (required for US/JP stocks)
export FMP_API_KEY='your_key_here'

# 3. (Optional) Install a local AI engine
npm install -g @anthropic-ai/claude-code    # or @google/gemini-cli or @anthropic-ai/qwen-code

# 4. Run
python main.py                    # Terminal CLI (AI copilot)
python main.py --manual           # Terminal CLI (manual input)
python main.py --auto             # Terminal CLI (fully automated)
streamlit run web_app.py          # Local web GUI
```

> **Don't want to install?** Use the cloud version at [valuescope.app](https://valuescope.app) — Cloud AI (DeepSeek R1) is built in.

---

## Key Valuation Parameters

| Parameter | Description |
|-----------|-------------|
| **Revenue Growth (Year 1)** | Next year's revenue forecast. AI prioritizes company guidance, then analyst consensus. |
| **Revenue Growth (Years 2-5)** | Compound annual growth rate (CAGR) for years 2-5. |
| **Target EBIT Margin** | Expected EBIT margin at maturity. |
| **Revenue/Invested Capital** | Capital efficiency ratio for different periods. |
| **WACC** | Auto-calculated from risk-free rate, ERP, and beta; adjustable. |
| **RONIC** | Return on new invested capital in terminal period. Defaults to WACC. |

---

## Contributing

Issues and pull requests are welcome. Contact: [alanhe@icloud.com](mailto:alanhe@icloud.com)

For more on company valuation, visit [jianshan.co](https://jianshan.co) or scan to follow on WeChat:

<img src="https://jianshan.co/images/wechat-qrcode.jpg" alt="见山笔记 WeChat QR Code" width="200">

---

## License

MIT License. See [LICENSE](LICENSE) for details.
