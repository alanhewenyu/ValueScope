---
name: valuescope-dcf
description: "Value a listed company with a deterministic two-phase DCF. Call run_dcf bare for historical material, research guidance and consensus, then call again with reasoned assumptions for the valuation."
description_zh: "用确定性两相 DCF 给上市公司估值。先裸调 run_dcf 取历史材料和参数分析指南，联网研究业绩指引与一致预期后，带上推理出的假设再调一次得到估值。"
description_en: "Value a listed company with a deterministic two-phase DCF. Call run_dcf bare for historical material, research guidance and consensus, then call again with reasoned assumptions for the valuation."
version: "1.0.0"
author: "ValueScope"
---

# ValueScope（DCF 估值）Connector Skill

## 一、角色定义

当用户的请求涉及**单只股票的估值**——"给 XX 估值"、"XX 值多少钱"、"XX 贵不贵"、"内在价值"、
"DCF"、"安全边际"、"市价隐含了什么预期"——你应调用连接标识为 `valuescope` 的 `run_dcf` 工具。

分工是固定的：**你负责前瞻判断，引擎负责数据和计算。** 引擎不调用任何大模型，同样的输入
永远得到同样的结果，因此估值的变化只来自基本面，而不是模型这次的措辞。

**禁止**：手算 DCF、把网页搜到的目标价或机构评级当作估值结果交付、跳过第一次调用。
这些做法会让结果不可复现，正是这个连接器要消除的问题。

---

## 二、核心能力（工具清单）

### `run_dcf` — 一站式 DCF 估值（10 年两阶段 FCFF 折现）

同一个工具，按**是否传假设参数**分成两个阶段。

#### 第一阶段：取分析材料（不传任何假设参数）

```
run_dcf(ticker="600519.SS")
```

返回 `phase: "context"`，包含：

| 字段 | 内容 |
|---|---|
| `company` | 名称、当前市价、币种、报告币种、基准期、TTM 口径 |
| `engine_computed` | 引擎算出的 WACC 与历史平均税率 |
| `parameter_history` | 每个参数的 5 年取值、均值、区间，含 unicode sparkline |
| `historical_defaults` | 历史均值兜底值（**不是**推荐值，见下） |
| `parameter_analysis_guide` | 资深分析师参数分析指南，告诉你每个假设该看什么、该搜什么 |

**此阶段不返回任何估值。** 返回里的市价是事实，不是估值结论。先给一个数字只会锚定
你接下来的判断。

#### 第二阶段：出估值（带上你推理出的假设）

```
run_dcf(ticker="600519.SS", revenue_growth_1=5, revenue_growth_2=5.5,
        ebit_margin=67, convergence=3,
        revenue_invested_capital_ratio_1=2.0,
        revenue_invested_capital_ratio_2=2.4,
        revenue_invested_capital_ratio_3=2.5,
        ronic_match_wacc=true)
```

返回 `phase: "valuation"`，包含每股内在价值、与市价的差异、价值桥、逐年预测表、
敏感性矩阵、反向 DCF（市价隐含了什么假设），以及 `presentation_guide`（呈现规范）。

---

## 三、参数说明

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ticker` | string | ✅ | — | A股 `600519.SS` / `000333.SZ`，港股 `0700.HK`，美股 `AAPL`，日股 `7203.T` |
| `revenue_growth_1` | number | 否 | 历史兜底 | Year 1 收入增速（百分数，`10` 表示 10%） |
| `revenue_growth_2` | number | 否 | 历史兜底 | Years 2-5 收入增速（百分数） |
| `ebit_margin` | number | 否 | 历史兜底 | 目标 EBIT 利润率（百分数） |
| `convergence` | number | 否 | 历史兜底 | 收敛年数 |
| `revenue_invested_capital_ratio_1` | number | 否 | 历史兜底 | Rev/IC，Year 1（倍数，如 `2.0`） |
| `revenue_invested_capital_ratio_2` | number | 否 | 历史兜底 | Rev/IC，Years 3-5 |
| `revenue_invested_capital_ratio_3` | number | 否 | 历史兜底 | Rev/IC，Years 5-10 |
| `tax_rate` | number | 否 | 引擎计算 | 税率（百分数）。省略即用财报算出的历史平均税率 |
| `wacc` | number | 否 | 引擎计算 | 折现率（百分数）。省略即用引擎按 beta 与资本结构算出的值 |
| `ronic_match_wacc` | boolean | 否 | `false` | 终值期 ROIC 是否回归 WACC。`true` = 终值期无超额回报 |
| `include_history_chart` | boolean | 否 | `false` | 额外返回历史趋势图（PNG，2×2：营收与增速、EBIT 利润率、Rev/IC、再投资额） |
| `fmp_api_key` | string | 否 | — | 美股 / 日股用户自带的 FMP key |

**单位约定**：增长率 / 利润率 / 税率 / WACC 一律为百分数（`10` 表示 10%）；
Rev/IC 为倍数；`convergence` 为年数。数值请传数字而非字符串。

**兜底与披露**：第二阶段省略某个假设时，引擎用历史均值填补，并在返回的
`summary.assumptions_filled_from_historical_defaults` 里如实列出。兜底不是判断——
凡是重要结论，每个参数都应由你给出依据。

---

## 四、典型工作流

1. **裸调** `run_dcf(ticker)` → 读完 `parameter_analysis_guide` 再动手。
2. **联网研究**（若有搜索能力）：公司最近一期业绩指引 > 分析师一致预期 > 行业 benchmark。
   注意区分"卖方目标价"（不用）与"经营预测"（要用）。
3. **逐项推理**：每个参数给出「取值 + 依据 + 与历史均值偏离的理由」。没有理由的偏离不做。
4. **带参数再调** `run_dcf` → 按返回的 `presentation_guide` 呈现。
5. **重要标的补三情景**：乐观 / 中性 / 悲观各调一次，说明每种情景成立的前提。
   同一次分析里三个情景应使用同一个 WACC——情景差异应体现在现金流假设上，
   再调贴现率等于把同一份风险计两遍，也让三个估值不可比。

---

## 五、前置条件与错误恢复

**无需任何凭证**：A股、港股开箱即用。

**美股 / 日股**：数据来自 Financial Modeling Prep。有每日限量的免费体验额度
（按 ticker 计——同一只票当天不限调用次数，可反复调参、跑多情景）。额度用完后：

- 用户自带 key：调用时传 `fmp_api_key` 参数，或在连接配置中加 `X-FMP-Key` 请求头；
- 引擎返回的额度提示与注册链接，**请原样转达给用户**，不要省略或改写链接。

**常见错误**：

| 现象 | 原因与处理 |
|---|---|
| 提示数据获取失败（美股/日股） | key 无效或额度不足；核对 key 状态，或提示用户注册 |
| 提示今日调用次数已达上限 | 单 IP 每日调用配额，次日恢复 |
| 代码找不到 | 核对 ticker 后缀格式（见参数表） |

**不确定时不要换方法。** 引擎连不上就如实告知用户，不要用手算或网页搜到的估值顶替——
静默降级比失败更糟。

---

## 六、输出与免责

呈现时遵循第二阶段返回的 `presentation_guide`：先结论卡（内在价值 vs 市价、上行空间），
再关键假设表（含依据），再价值构成、敏感性区间、反向 DCF 点评。给区间而非单点数字。

所有输出附：**模型计算结果，仅供研究参考，不构成投资建议。**
