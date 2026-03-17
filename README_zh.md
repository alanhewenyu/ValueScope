## 语言选择
- [English](README.md)
- [中文](README_zh.md)

---

# ValueScope

**AI 驱动的股票估值与分析平台 — DCF 估值、相对估值、多维评分、财务分析。**

[![在线使用](https://img.shields.io/badge/🌐_在线使用-valuescope.app-2563eb?style=for-the-badge)](https://valuescope.app)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)

---

## ValueScope 是什么？

ValueScope 是一个基于 **Damodaran FCFF 标准化 DCF 引擎**的 AI 股票估值平台 — 10 年显性预测期、终值、WACC、敏感性分析，框架固定、结果可复现。与直接让大模型"估个值"不同（每次对话可能用不同的方法和折现框架），ValueScope 产出**一致、可比较的估值结果**，为投资决策提供可靠依据。

你可以把它想象成一位坐在身边的股权研究分析师：AI 帮你搜索业绩指引、分析师一致预期和行业数据，然后给出估值参数建议 — 而底层模型始终是严谨、透明、由你掌控的。

**支持市场：** 🇺🇸 美股 &nbsp; 🇭🇰 港股 &nbsp; 🇨🇳 A 股 &nbsp; 🇯🇵 日股

---

## 在线使用

访问 **[valuescope.app](https://valuescope.app)** — 无需安装，即开即用。

### 网页版 — 首页

![网页版首页](assets/web-landing.png)

### 网页版 — DCF 估值

![网页版估值](assets/web-valuation.png)

---

## 核心功能

### 网页版（[valuescope.app](https://valuescope.app)）

- **DCF 估值** — 基于 Damodaran FCFF 框架，交互式参数调节，含 10 年预测表、双维度敏感性分析（增长率×利润率、WACC）、价值桥分解。
- **AI 一键估值** — Cloud AI（DeepSeek R1 + Serper 联网搜索）分析业绩指引、分析师共识和行业数据，一键生成全部 DCF 参数及详细推理。含免费额度；配置自有密钥可无限使用。
- **DCF 差异分析** — AI 对比 DCF 估值与市场价格，综合分析市场情绪、分析师目标价及风险因素。
- **相对估值** — 当前估值倍数（PE、PB、PS、EV/EBITDA）对比 3/5/10 年历史分位。
- **四维评分** — 估值、质量、成长、动量浓缩为一张雷达图，子因子透明可查。
- **财务概览** — 核心驱动因素（营收增长、EBIT 利润率、ROIC、FCF）、资产负债表要点及历史财务数据表。
- **中英双语** — 一键切换中英文界面。

### 终端 CLI

- **AI Copilot** — 支持三种本地 AI 引擎（Claude、Gemini、Qwen）。AI 逐项给出参数建议，你来审核调整。
- **自定义估值** — `--manual` 模式完全手动调参。无需 AI 或 API Key。
- **全自动模式** — `--auto` 模式全自动：AI 分析 → 采纳参数 → 导出 Excel。
- **Excel 导出** — 格式化 `.xlsx` 工作簿，含估值结果、历史数据和 AI 分析。

### 终端演示

![历史数据](assets/demo-1-historical.png)
![AI 分析](assets/demo-2-ai-params.png)
![DCF 结果](assets/demo-3-dcf-result.png)

---

## 架构

```
valuescope/
├── frontend/          # Next.js 15 (React) — 网页前端
├── backend/           # FastAPI — REST API 服务
├── modeling/          # 核心估值引擎（CLI 和后端共用）
├── main.py            # 终端 CLI 入口
└── Dockerfile         # 后端容器
```

---

## 数据源 & FMP API Key

| 市场 | 数据源 | API Key |
|------|-------|---------|
| **A 股** | akshare | 不需要（免费） |
| **港股** | yfinance（年度）/ FMP（季度） | 年度：免费；季度：需 FMP Key |
| **美股** | FMP | 需要 FMP Key |
| **日股** | FMP | 需要 FMP Key |

> 💡 **[获取 FMP API Key →](https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope)**
>
> FMP（Financial Modeling Prep）提供美股、港股、日股等高质量金融数据。**通过此链接购买可享折扣价**，同时也是对 ValueScope 项目的支持。

---

## AI 引擎

### Cloud AI（网页版）

网页版 [valuescope.app](https://valuescope.app) 内置 Cloud AI，无需安装：

- **DeepSeek R1** — 深度思维链推理，用于财务分析
- **Serper** — Google 搜索 + 网页抓取，获取业绩指引、分析师预期和行业数据
- **含免费额度** — 配置自有 Serper + DeepSeek 密钥可无限使用

### 本地 AI 引擎（终端 CLI）

支持三种 AI CLI 工具，启动时自动检测（优先级：Claude > Gemini > Qwen），也可通过 `--engine` 强制指定。

| 引擎 | 安装方式 | 说明 |
|------|---------|------|
| **Claude** | `npm install -g @anthropic-ai/claude-code` | 默认优先。需要 [Anthropic](https://docs.anthropic.com/en/docs/claude-code) 账号。 |
| **Gemini** | `npm install -g @google/gemini-cli` | [Google](https://github.com/google-gemini/gemini-cli) 账号免费使用。 |
| **Qwen** | `npm install -g @anthropic-ai/qwen-code` | [qwen.ai](https://github.com/QwenLM/qwen-code) 账号免费使用。 |

如果未检测到 AI 引擎，自动切换到自定义估值模式（手动输入）。

---

## 安装与使用

### 方式一：直接使用网页版（推荐）

访问 **[valuescope.app](https://valuescope.app)** — 无需安装。

### 方式二：终端 CLI

需要 Python 3.8+。

```bash
git clone https://github.com/alanhewenyu/ValueScope.git
cd ValueScope
pip install -r requirements.txt
```

设置 FMP API Key（美股/日股需要）：

```bash
export FMP_API_KEY='your_api_key_here'
```

运行：

```bash
python main.py                    # AI copilot（默认）
python main.py --manual           # 手动输入
python main.py --auto             # 全自动
```

额外参数：`--engine claude|gemini|qwen`、`--apikey YOUR_KEY`。

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

本项目采用 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE) 授权。

你可以自由使用、修改和分发本软件，但任何修改版本——包括作为网络服务（SaaS）提供——都必须同样以 AGPL-3.0 开源。

© 2025-2026 Alan He
