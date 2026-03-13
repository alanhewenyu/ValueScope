# ValueScope Roadmap

Product development roadmap, positioning, and future feature plans.

---

## 🎯 Positioning & Competitive Landscape

### What ValueScope Is

An **open-source, AI-powered stock valuation tool** built on Damodaran's FCFF methodology. It combines rigorous DCF modeling with AI-assisted parameter estimation, targeting individual investors and finance learners who want transparent, reproducible valuations — not black-box outputs.

### Core Differentiators

| vs. | ValueScope Advantage |
|-----|---------------------|
| **Finbox, GuruFocus, Simply Wall St** ($20-50/mo) | Open-source, transparent model logic. User controls every parameter instead of receiving a black-box number. Free to self-host. |
| **Damodaran's Excel templates** (free) | Automated data fetching, real-time parameter tuning, AI-assisted analysis, multi-market support. Lower barrier to entry. |
| **Broker/institutional tools** | Accessible to individual investors. Open-source and auditable. |
| **ChatGPT / AI "value this stock"** | Structured, reproducible model with fixed methodology. Every valuation uses the same framework — consistent and comparable across companies and time periods. |

### Target Users

1. **Individual investors** — want a rigorous yet accessible valuation tool beyond simple screener metrics
2. **Finance students / CFA candidates** — learn DCF valuation through hands-on practice with real data
3. **Content creators / analysts** — produce transparent, shareable valuation analyses

### Market Gap

The **A-share DCF valuation tool** niche is largely empty. Most Chinese stock tools focus on technical analysis or simple screener metrics. A bilingual tool with Damodaran methodology and A-share support has no direct competitor.

---

## ✅ Current Features (v1.0)

- **DCF Absolute Valuation** — Damodaran FCFF methodology, 10-year forecast + terminal value
- **AI-Powered Analysis** — AI searches earnings guidance, analyst consensus, and industry benchmarks, then suggests valuation parameters
- **Multi-Market Support** — US, Hong Kong, A-shares, Japan
- **Sensitivity Analysis** — Revenue growth × EBIT margin grid + WACC sensitivity
- **Gap Analysis** — AI-driven analysis of DCF vs market price discrepancy
- **Excel Export** — Professional multi-sheet valuation report
- **Bilingual UI** — English / 中文
- **Web + CLI** — Streamlit Cloud web app + local terminal interface

---

## 🔜 Planned Features

### Relative Valuation (Multiples & Peer Comparison)

**Goal:** Complement DCF with relative valuation — the most widely used valuation method by practitioners. Makes ValueScope a comprehensive valuation tool rather than DCF-only.

**Scope:**

1. **Company Valuation Multiples**
   - P/E (TTM), P/B, P/S, EV/EBITDA, EV/Revenue, PEG
   - Displayed as metric cards alongside DCF results

2. **Historical Percentile (Valuation Bands)**
   - Show where current multiples sit within their own historical range
   - e.g. "Current P/E of 25x is at the 72nd percentile of its 5-year range (18x–35x)"
   - Visualize as percentile bar or band chart for each multiple
   - Helps answer: "Is this stock expensive relative to its own history?"
   - Data: FMP `key-metrics` (annual/quarterly historical) or `historical-price-eod` + financials

3. **Peer Comparison**
   - Auto-discover comparable companies (same sector + market cap range)
   - Side-by-side multiples comparison table
   - Highlight where the target company sits relative to peers

4. **Industry & Sector Benchmarks**
   - Industry average P/E and sector average P/E as reference points
   - Historical industry P/E trends

5. **Implied Price from Multiples**
   - "If this company traded at the peer median P/E, its price would be X"
   - Calculate implied price from each multiple (P/E, P/B, P/S, EV/EBITDA, EV/Revenue)
   - Composite implied price (weighted average)
   - Three-way comparison: DCF intrinsic value vs multiples implied price vs current market price

**Market Support:**
- US / HK: Full features (FMP API provides peers, multiples, industry data, historical metrics)
- A-shares: Basic multiples + historical percentile (calculated from akshare data), no peer comparison

**Data Sources:** FMP API — `metrics-ratios-ttm`, `key-metrics-ttm`, `key-metrics` (historical), `peers`, `industry-PE-snapshot`, `sector-PE-snapshot`

---

### Additional Future Ideas

| Feature | Description | Priority |
|---------|-------------|----------|
| **PDF Valuation Report** | Export professional PDF report with charts | Medium |
| **Valuation History Tracking** | Track how your valuations change over time | Medium |
| **Price Alert** | Notify when stock price crosses your intrinsic value | Low |
| **Portfolio Valuation** | Batch-valuate a portfolio of stocks | Low |
| **DDM (Dividend Discount Model)** | Alternative valuation for high-dividend stocks | Low |
| **More Markets** | UK, Europe, India, etc. | Low |

---

## 💡 Business Opportunities

### Current
- FMP API affiliate commission (embedded discount link)

### Short-term
- Expand affiliate partnerships (brokers, AI APIs, data platforms)
- Content monetization via jianshan.co (tutorials, case studies)

### Medium-term
- Freemium Pro tier (unlimited AI analysis, batch valuation, PDF reports)
- Valuation API service for developers and institutions

### Long-term
- Valuation community platform (share and discuss valuation models)
- Institutional / education licensing

---

*Last updated: 2026-03-13*
