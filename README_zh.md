## 语言选择
- [English](README.md)
- [中文](README_zh.md)

---

## ValuX 是什么？

ValuX 是一个基于现金流折现模型（DCF）的 AI 股票估值工具。它自动抓取财务数据，借助 AI 实时搜索市场信息生成估值参数建议，并计算公司的内在价值 — 全部在终端中完成。

你可以把它想象成一位坐在身边的股权研究分析师：AI 帮你搜索业绩指引、分析师一致预期和行业数据，然后给出估值参数建议。你来审核和调整，AI 负责繁重的工作。

---

## 核心功能

- **多引擎 AI Copilot** — 支持三种 AI 引擎：[Claude Code](https://docs.anthropic.com/en/docs/claude-code)、[Gemini CLI](https://github.com/google-gemini/gemini-cli)、[Qwen Code](https://github.com/QwenLM/qwen-code)。启动时自动检测已安装的引擎（优先级：Claude > Gemini > Qwen），也可通过 `--engine` 指定。AI 分析公司基本面，搜索分析师预期和业绩指引，为每个 DCF 参数给出建议值和详细分析。你逐项审核，按 Enter 接受或输入新值覆盖。
- **手动模式** — 想完全自己掌控？使用 `--manual` 手动输入所有参数。无需 AI 引擎或 API Key。
- **全自动模式** — 使用 `--auto` 实现全自动流程：AI 分析、自动采纳参数、自动导出 Excel，无需任何交互。
- **估值差异分析** — 估值完成后，AI 对比 DCF 结果与当前股价，搜索分析师目标价，分析差异原因并给出修正估值。
- **敏感性分析** — 生成收入增长率 × EBIT 利润率、WACC 两组敏感性分析表，展示每股价值的可能范围。
- **Excel 导出** — 将估值结果、历史数据、财务报表和 AI 差异分析导出为格式化的 Excel 工作簿。
- **全球覆盖** — 支持美股、A 股、港股等全球市场，根据不同国家的无风险利率和股权风险溢价自动计算 WACC。
- **A 股和港股免费使用** — A 股（akshare）和港股年度数据（yfinance）无需 API Key。配合手动模式，可实现完全免费的估值计算。

---

## 工作流程

```
┌──────────────────────────────────────────────────────────────┐
│  输入股票代码  →  抓取年度历史财务数据                           │
│                    ↓                                         │
│  展示历史数据摘要（含 TTM 数据）                                │
│                    ↓                                         │
│  [可选] 查看季度数据作为参考                                    │
│                    ↓                                         │
│  AI Copilot：搜索市场数据 → 建议参数 → 你来审核                 │
│                    ↓                                         │
│  计算 DCF → 每股内在价值                                       │
│                    ↓                                         │
│  敏感性分析（收入增长 × EBIT 利润率，WACC）                     │
│                    ↓                                         │
│  [可选] AI 估值差异分析：DCF 估值 vs 当前股价                   │
│                    ↓                                         │
│  [可选] 导出 Excel                                            │
└──────────────────────────────────────────────────────────────┘
```

---

## 数据源

ValuX 根据不同市场使用不同数据源，兼顾数据质量和使用成本：

| 市场 | 年度数据 | 季度数据 | API Key |
|------|---------|---------|---------|
| **A 股** | [akshare](https://github.com/akfamily/akshare) | akshare | **不需要**（免费） |
| **港股** | [yfinance](https://github.com/ranaroussi/yfinance) | [FMP](https://financialmodelingprep.com/) | 年度：**免费**；季度：需要 FMP Key |
| **美股及其他** | [FMP](https://financialmodelingprep.com/) | FMP | 需要 FMP Key |

**为什么使用多个数据源？**
- **akshare** 提供中国 GAAP 原始利润表，用于准确计算 EBIT。
- **yfinance** 免费提供可靠的港股年度财务数据。港股季度数据则通过 FMP 获取完整季度明细。
- **FMP** 是美股和国际股票的主要数据源，提供财务报表、市场数据、公司信息和风险溢价等。

> **完全没有 API Key？** 你仍然可以免费查询 A 股和港股年度数据。使用 `--manual` 模式手动输入估值参数，即可获得完全免费的估值方案。

---

## AI 引擎

ValuX 支持三种 AI 引擎。启动时自动检测已安装的 CLI 工具（优先级：Claude > Gemini > Qwen），也可通过 `--engine` 强制指定。

| 引擎 | CLI 工具 | 安装方式 | 说明 |
|------|---------|---------|------|
| **Claude** | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `npm install -g @anthropic-ai/claude-code` | 默认优先。需要 Anthropic 账号。 |
| **Gemini** | [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npm install -g @google/gemini-cli` | Google 账号登录即可免费使用。 |
| **Qwen** | [Qwen Code](https://github.com/QwenLM/qwen-code) | `npm install -g @anthropic-ai/qwen-code` | qwen.ai 账号登录即可免费使用。 |

如果未检测到任何 AI 引擎，ValuX 会自动切换到手动模式。

---

## 运行模式

| 模式 | 命令 | 需要 AI | 说明 |
|------|------|---------|------|
| **Copilot**（默认） | `python main.py` | 是 | AI 逐项给出参数建议和分析，你来审核和调整。 |
| **手动** | `python main.py --manual` | 否 | 自行输入所有估值参数。无需 AI 引擎或 API Key 即可使用。 |
| **全自动** | `python main.py --auto` | 是 | 全自动流程：AI 分析 → 自动采纳参数 → 自动导出 Excel。无需任何交互。 |

额外参数：
- `--engine claude|gemini|qwen` — 强制使用指定 AI 引擎，跳过自动检测。
- `--apikey YOUR_KEY` — 直接传入 FMP API Key（替代 `FMP_API_KEY` 环境变量）。

---

## 安装与使用

### 1. 下载项目

```bash
git clone https://github.com/alanhewenyu/ValuX.git
cd ValuX
```

### 2. 安装依赖

需要 Python 3.8+。

```bash
pip install -r requirements.txt
```

### 3. 设置 FMP API Key（可选）

美股和港股季度数据需要。A 股和港股年度数据不需要。

在 [Financial Modeling Prep](https://financialmodelingprep.com/) 注册账户并设置 API Key：

```bash
export FMP_API_KEY='your_api_key_here'
```

### 4. 安装 AI 引擎（可选）

安装任一支持的 AI CLI 工具：

```bash
# 方式一：Claude Code（推荐）
npm install -g @anthropic-ai/claude-code

# 方式二：Gemini CLI（Google 账号免费使用）
npm install -g @google/gemini-cli

# 方式三：Qwen Code（qwen.ai 账号免费使用）
npm install -g @anthropic-ai/qwen-code
```

如果没有安装任何 AI 引擎，ValuX 会自动切换到手动模式。

### 5. 运行

```bash
python main.py                      # AI copilot 模式（默认）
python main.py --manual             # 手动输入模式
python main.py --auto               # 全自动模式
python main.py --engine gemini      # 强制使用 Gemini 引擎
```

---

## 使用步骤

1. **输入股票代码** — 如 `AAPL`、`600519.SS`（茅台）、`0700.HK`（腾讯）
2. **查看年度历史数据** — 程序抓取并展示年度财务数据摘要（含 TTM 数据）
3. **查看季度数据**（可选） — 在开始估值前，可选择查看季度财务数据作为参考
4. **AI 参数生成**（或手动输入） — AI 逐项给出建议值和分析，按 Enter 接受或输入新值
5. **查看 DCF 结果** — 每股内在价值及完整计算过程
6. **敏感性分析** — 收入增长率 × EBIT 利润率、WACC 两组敏感性表
7. **估值差异分析**（可选） — AI 分析 DCF 估值与市场价差异原因
8. **导出 Excel**（可选） — 保存为格式化的 `.xlsx` 文件

### 输入格式说明

百分比参数（收入增长率、EBIT 利润率、税率、WACC）直接输入数字：输入 `10` 表示 10%，不需要输入 `10%`。

---

## 关键估值参数说明

| 参数 | 说明 |
|------|------|
| **收入增长率（Year 1）** | 未来一年的收入预测。AI 优先参考公司业绩指引，其次参考分析师一致预期。 |
| **收入增长率（Years 2-5）** | 未来 2-5 年的复合年增长率（CAGR）。 |
| **目标 EBIT 利润率** | 公司达到成熟稳定期的 EBIT 利润率。 |
| **收敛年数** | 从当前 EBIT 利润率达到目标利润率所需的年数。 |
| **收入/投资资本比率** | 不同阶段的资本效率比率（Year 1-2、3-5、5-10）。AI 会对照历史再投资数据进行合理性校验。 |
| **税率** | 基于历史数据自动计算，可手动调整。 |
| **WACC** | 基于无风险利率、股权风险溢价和 Beta 自动计算，可手动调整。 |
| **RONIC** | 终值期新投资资本回报率。默认等于 WACC（竞争均衡），对有持续竞争优势的公司可设为 WACC + 5%。 |

> **关于 EBIT**：A 股的 EBIT 基于 akshare 原始数据计算，已剔除投资收益、公允价值变动等非经营性项目。港股直接使用营业利润（Operating Income），部分公司可能包含未剔除的大额非经营性项目，请注意甄别。

---

## DCF 估值对价值投资的意义

价格是你支付的，价值是你得到的。DCF 估值通过折现未来自由现金流来估算公司的内在价值，是价值投资的基石。

本工具聚焦三个核心驱动因素：**收入增长**、**经营效率（EBIT 利润率）** 和 **再投资**。正如巴菲特所说，*"模糊的正确胜过精确的错误。"* 通过敏感性分析，即使假设不完美，也能找到投资的安全垫。

---

## 贡献与反馈

欢迎提交 Issue 或 Pull Request。联系邮箱：[alanhe@icloud.com](mailto:alanhe@icloud.com)

了解更多公司估值内容，欢迎关注微信公众号：**见山笔记**

---

## 许可证

MIT License。详见 [LICENSE](LICENSE)。
