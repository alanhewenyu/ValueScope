## 语言选择
- [English](README.md)
- [中文](README_zh.md)

---

# ValueScope

**一个能被你的 AI 直接调用的标准化 DCF 估值引擎——确定、可复现,覆盖 A股 / 港股 / 美股 / 日股。**

[![在线体验](https://img.shields.io/badge/🌐_在线体验-valuescope.app-2563eb?style=for-the-badge)](https://valuescope.app)
[![MCP](https://img.shields.io/badge/MCP-mcp.valuescope.app-7c3aed?style=for-the-badge)](https://mcp.valuescope.app/mcp)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)

---

## ValueScope 是什么?

ValueScope 是一个**标准化的 Damodaran FCFF DCF 引擎**——10 年显式预测、终值、WACC、敏感性分析、反向 DCF,全部在一套固定、可复现的框架里完成。

让大模型直接"给这只股票估值",每次对话可能用不同的数据源、报表口径和模型——你分不清估值变化是基本面变了,还是 AI 这次心情不同。ValueScope 用一套清晰的分工解决这个问题:

- **AI 负责判断**——搜索业绩指引、分析师一致预期、行业 benchmark,推理每个假设参数。
- **引擎负责数据和计算**——A股扣非归母口径、剔除非经营项目的 EBIT 调整、10 年 FCFF 折现、敏感性、反向 DCF。**同样的输入永远得到同样的结果。**

AI 提供智能,ValueScope 提供框架和纪律。引擎本身不调用任何大模型。

**支持市场:** 🇨🇳 A股 &nbsp; 🇭🇰 港股 &nbsp; 🇺🇸 美股 &nbsp; 🇯🇵 日股

**三种使用方式:** [MCP 服务](#mcp-服务)(让你自己的 AI 调用)、[网页版](#网页版)(手动操作台)、[终端 CLI](#终端-cli)。

---

## MCP 服务

MCP([Model Context Protocol](https://modelcontextprotocol.io))服务让任何支持 MCP 的 AI 客户端——Claude、ChatGPT、Cherry Studio、Dify 等——都能调用网页版同一套确定性 DCF 引擎。这是**推荐**的使用方式。

**接入地址:** `https://mcp.valuescope.app/mcp`

### 两分钟接入

**Claude Code**(终端和桌面 App 共用同一份配置):

```bash
claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp
```

**Claude 网页版 / 手机 App:** 设置 → Connectors → 添加自定义连接器,粘贴 `https://mcp.valuescope.app/mcp`。

**Cherry Studio 等桌面客户端:** 添加一个 HTTP 类型的 MCP 服务器,填同一个地址。

接入后直接用自然语言提问:*"给贵州茅台做个 DCF 估值"*——无需学任何命令。

### 工作原理——单工具,两相流程

服务只暴露一个 `run_dcf` 工具,模仿股权分析师的工作流,由调用方模型扮演分析师:

1. **基线** —— 不带任何假设调用 `run_dcf(ticker)`,返回按 5 年历史均值计算的基线估值、每个参数的历史区间,以及一份告诉模型如何评估每个假设的分析指南。
2. **最终** —— 模型联网搜索业绩指引与一致预期,推理每个参数,再带上假设调用 `run_dcf(ticker, <参数>)` 得到最终估值:每股内在价值、价值桥、逐年预测表、敏感性矩阵、反向 DCF(市价隐含了什么假设)。

同时暴露一个 `dcf` MCP prompt,在支持 MCP prompt 的客户端里呈现为一键工作流(基线 → 搜索 → 推理 → 三情景)。

ticker 格式:A股 `600519.SS` / `000333.SZ`,港股 `0700.HK`,美股 `AAPL`,日股 `7203.T`。

### 美股 / 日股的 FMP key

A股、港股无需 key。美股 / 日股数据来自 FMP(见[数据源](#数据源与-fmp-api-key))。美股/日股有每日限量的免费体验额度;超出后,用以下两种方式之一提供你自己的 key:

**配置一次(推荐)** —— 作为请求头传入,之后每次对话自动带上。如果你之前接入时没带 key,先删掉再重新加一遍:

```bash
claude mcp remove valuescope
claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp --header "X-FMP-Key: 你的KEY"
```

**按对话临时给** —— 在对话里直接说"我的 FMP key 是 …",模型会在每次调用时带上(仅当前对话有效)。

### 自建 MCP 服务

服务挂载在 FastAPI 后端的 `/mcp`(streamable HTTP)。启动后端(见[安装](#方式-3自建cli--后端--mcp))即可在 `http://localhost:8000/mcp` 访问。设置环境变量 `FMP_API_KEY` 启用美股/日股体验额度;用 `MCP_DAILY_LIMIT`、`MCP_US_TRIAL_DAILY_LIMIT` 调节限流。

---

## 网页版

在线体验 **[valuescope.app](https://valuescope.app)**——无需安装。

网页版是**手动操作台**:亲手调 DCF 参数、实时看估值变化、读敏感性表、看相对估值历史分位和多维评分。如果你喜欢自己驾驭假设,它是一个很好的 DCF 计算器。

### 功能

- **DCF 估值** —— Damodaran FCFF 框架,交互式参数控制、10 年预测表、双敏感性分析(增长×利润率、WACC)、价值桥拆解。
- **相对估值** —— 当前倍数(PE、PB、PS、EV/EBITDA)对比 3/5/10 年历史分位。
- **四维评分** —— 估值、质量、成长、动量,雷达图 + 透明的子因子拆解。
- **财务概览** —— 核心驱动(营收增速、EBIT 利润率、ROIC、FCF)、资产负债表亮点、历史财务表。
- **双语界面** —— 中英文一键切换。

![网页概览](assets/web-overview.png)
![DCF 估值](assets/web-valuation.png)

---

## 终端 CLI

本地使用,接自己的 AI CLI 订阅。需要 Python 3.8+。

- **AI Copilot** —— 本地 AI 引擎(Claude / Gemini / Qwen)建议参数,你交互式审查调整。
- **自定义估值** —— `--manual` 全手动,无需 AI 或 API key。
- **自动模式** —— `--auto` 全自动:AI → 接受 → 导出 Excel。
- **Excel 导出** —— 带估值结果、历史数据、AI 推理的格式化 `.xlsx`。

| 引擎 | 安装 | 说明 |
|--------|---------|-------|
| **Claude** | `npm install -g @anthropic-ai/claude-code` | 检测到即默认使用。 |
| **Gemini** | `npm install -g @google/gemini-cli` | Google 账号免费。 |
| **Qwen** | `npm install -g @anthropic-ai/qwen-code` | qwen.ai 账号免费。 |

自动检测已安装引擎(优先级:Claude > Gemini > Qwen),或用 `--engine` 强制指定。都没有则回退手动模式。

![历史数据](assets/demo-1-historical.png)
![DCF 结果](assets/demo-3-dcf-result.png)

---

## 数据源与 FMP API Key

| 市场 | 数据源 | API Key |
|--------|-----------|---------|
| **A股** | akshare | 无需(免费) |
| **港股** | yfinance(年度) / FMP(季度) | 年度免费;季度需 FMP key |
| **美股** | FMP | 需要 FMP key |
| **日股** | FMP | 需要 FMP key |

> 💡 **[获取 FMP API Key →](https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope)**
>
> FMP(Financial Modeling Prep)为美股、港股、日股提供高质量财务数据。**通过此链接订阅(已含 valuescope 优惠码)价格更优惠**——也是对 ValueScope 持续开发的一点支持。

---

## 安装与使用

### 方式 1:MCP 服务(推荐)

无需安装——把你的 AI 接到 `https://mcp.valuescope.app/mcp`(见上文 [MCP 服务](#mcp-服务))。

### 方式 2:网页版

访问 **[valuescope.app](https://valuescope.app)**——无需安装。

### 方式 3:自建(CLI + 后端 + MCP)

需要 Python 3.8+。

```bash
git clone https://github.com/alanhewenyu/ValueScope.git
cd ValueScope
pip install -r requirements.txt          # CLI
pip install -r requirements-api.txt      # 后端 + MCP 服务
```

设置 FMP API Key(美股/日股必需):

```bash
export FMP_API_KEY='your_api_key_here'
```

运行 CLI:

```bash
python main.py                    # AI copilot(默认)
python main.py --manual           # 手动输入
python main.py --auto             # 全自动
```

或运行后端(同时提供 REST API 和 `/mcp` 上的 MCP 服务):

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 架构

```
valuescope/
├── frontend/              # Next.js(React)—— 网页 UI
├── backend/              # FastAPI —— REST API + MCP 服务
│   └── mcp_server.py     # MCP 工具(run_dcf)+ dcf prompt
├── modeling/             # 核心估值引擎(CLI、后端、MCP 共用)
├── main.py               # 终端 CLI 入口
└── Dockerfile            # 后端容器
```

`modeling/` 引擎是唯一的事实来源——CLI、网页后端、MCP 服务全都调用它,所以无论从哪个入口进来,同一套输入得到的估值完全一致。

---

## 核心估值参数

| 参数 | 说明 |
|-----------|-------------|
| **营收增速(第 1 年)** | 下一年营收预测。优先参考公司业绩指引,其次分析师一致预期。 |
| **营收增速(第 2-5 年)** | 第 2-5 年复合增长率(CAGR)。 |
| **目标 EBIT 利润率** | 成熟期预期 EBIT 利润率。 |
| **营收/投入资本** | 不同阶段的资本效率比率。 |
| **WACC** | 由无风险利率、ERP、beta 自动计算,可调。 |
| **RONIC** | 终值期新增投入资本回报率,默认等于 WACC。 |

---

## 参与贡献

欢迎提交 Issue 或 Pull Request。联系邮箱:[alanhe@icloud.com](mailto:alanhe@icloud.com)

更多公司估值内容,访问 [jianshan.co](https://jianshan.co) 或扫码关注微信公众号:

<img src="https://jianshan.co/images/wechat-qrcode-v2.jpg" alt="见山笔记 微信公众号" width="200">

---

## 许可证

本项目采用 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)。

你可以自由使用、修改、分发本软件,但任何修改版本——包括作为网络服务(SaaS)或托管的 MCP 服务运行——也必须以 AGPL-3.0 开源。

© 2025-2026 Alan He
