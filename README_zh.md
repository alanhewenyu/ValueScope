## 语言选择
- [English](README.md)
- [中文](README_zh.md)

---

# ValueScope

**AI 驱动的交互式 DCF 股票估值工具 — 标准化模型、实时调参、可复现结果。**

[![在线使用](https://img.shields.io/badge/🌐_在线使用-valuescope.app-2563eb?style=for-the-badge)](https://valuescope.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)

---

## ValueScope 是什么？

ValueScope 是一个基于**标准化 DCF 引擎**的 AI 股票估值工具 — 10 年 FCFF 显性预测期、终值、WACC、敏感性分析，框架固定、结果可复现。与直接让大模型"估个值"不同（每次对话可能用不同的方法和折现框架），ValueScope 产出**一致、可比较的估值结果**，为投资决策提供可靠依据。

你可以把它想象成一位坐在身边的股权研究分析师：AI 帮你搜索业绩指引、分析师一致预期和行业数据，然后给出估值参数建议 — 而底层模型始终是严谨、透明、由你掌控的。

**支持市场：** 🇺🇸 美股 &nbsp; 🇭🇰 港股 &nbsp; 🇨🇳 A 股 &nbsp; 🇯🇵 日股

---

## 演示

### 在线网页版 — 首页

![在线网页版](assets/web-landing.png)

### 在线网页版 — 估值判定 + 滑块调参

![在线网页版估值](assets/web-valuation.png)

### 终端 CLI

![历史数据](assets/demo-1-historical.png)
![AI 分析](assets/demo-2-ai-params.png)
![DCF 结果](assets/demo-3-dcf-result.png)

---

## 核心功能

- **AI Copilot** — AI 联网搜索分析师预期、业绩指引和行业数据，为每个 DCF 参数给出建议值和详细分析。你逐项审核调整。
- **在线网页版** — 访问 [valuescope.app](https://valuescope.app)，内置 Cloud AI（DeepSeek R1 + Serper 联网搜索），无需安装。
- **终端 CLI** — 支持三种本地 AI 引擎，启动时自动检测，也可通过 `--engine` 指定。
- **自定义估值** — 通过滑块（网页版）或 `--manual`（终端）完全手动调参。无需 AI 引擎或 API Key。
- **估值判定与差异分析** — 买入/持有/卖出判定及安全边际。AI 对比 DCF 估值与市场价格和分析师目标价。
- **敏感性分析 & Excel 导出** — 收入增长率 × EBIT 利润率、WACC 敏感性分析表。一键导出格式化 `.xlsx` 工作簿。

---

## 数据源 & FMP API Key

| 市场 | 数据源 | API Key |
|------|-------|---------|
| **A 股** | [akshare](https://github.com/akfamily/akshare) | 不需要（免费） |
| **港股** | [yfinance](https://github.com/ranaroussi/yfinance)（年度）/ [FMP](https://site.financialmodelingprep.com/register)（季度） | 年度：免费；季度：需 FMP Key |
| **美股** | [FMP](https://site.financialmodelingprep.com/register) | 需要 FMP Key |
| **日股** | [FMP](https://site.financialmodelingprep.com/register) | 需要 FMP Key |

> 💡 **[获取 FMP API Key →](https://site.financialmodelingprep.com/register)**
>
> FMP（Financial Modeling Prep）提供美股、港股、日股等高质量金融数据。**通过此链接购买可享折扣价**，同时也是对 ValueScope 项目的支持。

---

## AI 引擎

### Cloud AI（在线网页版）

在线网页版 [valuescope.app](https://valuescope.app) 内置 Cloud AI，无需安装：

- **DeepSeek R1** — 深度思维链推理，用于财务分析
- **Serper** — Google 搜索 + 网页抓取，获取业绩指引、分析师预期和行业数据

### 本地 AI 引擎（终端 CLI 和本地网页版）

支持三种 AI CLI 工具，启动时自动检测（优先级：Claude > Gemini > Qwen），也可通过 `--engine` 强制指定。

| 引擎 | 安装方式 | 说明 |
|------|---------|------|
| **Claude** | `npm install -g @anthropic-ai/claude-code` | 默认优先。需要 [Anthropic](https://docs.anthropic.com/en/docs/claude-code) 账号。 |
| **Gemini** | `npm install -g @google/gemini-cli` | [Google](https://github.com/google-gemini/gemini-cli) 账号免费使用。 |
| **Qwen** | `npm install -g @anthropic-ai/qwen-code` | [qwen.ai](https://github.com/QwenLM/qwen-code) 账号免费使用。 |

如果未检测到 AI 引擎，自动切换到自定义估值模式（手动输入）。

---

## 运行模式

### 终端 CLI

| 模式 | 命令 | 需要 AI | 说明 |
|------|------|---------|------|
| **Copilot**（默认） | `python main.py` | 是 | AI 逐项给出参数建议，你来审核调整。 |
| **自定义** | `python main.py --manual` | 否 | 自行输入所有参数。无需 AI 或 API Key。 |
| **全自动** | `python main.py --auto` | 是 | 全自动：AI 分析 → 采纳参数 → 导出 Excel。 |

额外参数：`--engine claude|gemini|qwen` 强制指定引擎，`--apikey YOUR_KEY` 直接传入 FMP Key。

### 网页版

| 模式 | 说明 |
|------|------|
| **AI 一键估值** | AI 联网搜索，一键生成所有 DCF 参数建议。 |
| **自定义估值** | 滑块手动调参，实时图表动态更新。 |

---

## 安装与使用

### 1. 下载并安装依赖

需要 Python 3.8+。

```bash
git clone https://github.com/alanhewenyu/ValueScope.git
cd ValueScope
pip install -r requirements.txt
```

### 2. 设置 FMP API Key

美股、日股需要 FMP API Key。A 股使用免费数据源，港股年度数据也免费。

> 💡 **[获取 FMP API Key →](https://site.financialmodelingprep.com/register)** — 通过此链接购买可享折扣价，同时支持 ValueScope 的发展。

```bash
# macOS / Linux
export FMP_API_KEY='your_api_key_here'

# Windows CMD
set FMP_API_KEY=your_api_key_here

# Windows PowerShell
$env:FMP_API_KEY="your_api_key_here"
```

### 3. 安装 AI 引擎（可选 — 仅本地使用）

> **使用在线版？** 跳过此步骤 — Cloud AI 已内置于 [valuescope.app](https://valuescope.app)。

安装任一支持的 AI CLI 工具：

```bash
npm install -g @anthropic-ai/claude-code    # 方式一：Claude Code（推荐）
npm install -g @google/gemini-cli           # 方式二：Gemini CLI（Google 账号免费）
npm install -g @anthropic-ai/qwen-code      # 方式三：Qwen Code（qwen.ai 账号免费）
```

如果没有安装 AI 引擎，自动切换到自定义估值模式。

### 4. 运行

```bash
python main.py                    # 终端 CLI — AI copilot（默认）
python main.py --manual           # 终端 CLI — 手动输入
python main.py --auto             # 终端 CLI — 全自动
streamlit run web_app.py          # 本地网页版（打开 http://localhost:8501）
```

---

## 关键估值参数

| 参数 | 说明 |
|------|------|
| **收入增长率（Year 1）** | 未来一年收入预测。AI 优先参考公司业绩指引，其次参考分析师预期。 |
| **收入增长率（Years 2-5）** | 未来 2-5 年复合年增长率（CAGR）。 |
| **目标 EBIT 利润率** | 公司达到成熟稳定期的 EBIT 利润率。 |
| **收入/投资资本比率** | 不同阶段的资本效率比率。 |
| **WACC** | 基于无风险利率、股权风险溢价和 Beta 自动计算，可手动调整。 |
| **RONIC** | 终值期新投资资本回报率。默认等于 WACC。 |

---

## 贡献与反馈

欢迎提交 Issue 或 Pull Request。联系邮箱：[alanhe@icloud.com](mailto:alanhe@icloud.com)

了解更多公司估值内容，欢迎访问 [jianshan.co](https://jianshan.co) 或扫码关注微信公众号：**见山笔记**

<img src="https://jianshan.co/images/wechat-qrcode.jpg" alt="见山笔记 微信公众号二维码" width="200">

---

## 许可证

MIT License。详见 [LICENSE](LICENSE)。
