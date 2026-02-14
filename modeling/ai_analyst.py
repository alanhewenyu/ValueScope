# Copyright (c) 2025 Alan He. Licensed under MIT.

import json
import os
import re
import subprocess
from . import style as S


ANALYSIS_PROMPT_TEMPLATE = """你是一位资深的股权研究分析师和DCF估值专家。请根据以下历史财务数据和公开市场信息，为 {company_name} ({ticker}) 生成DCF估值参数建议。

**注意：下方历史财务数据的最新年度（最左列）是 {base_year} 年。这是估值的 base year。请基于 {base_year} 年的最新数据进行分析，Year 1 对应 {forecast_year_1} 年。**

**重要：请务必先使用 WebSearch 工具搜索以下信息再开始分析：**
1. 搜索 "{ticker} earnings guidance revenue outlook {forecast_year_1}" — 获取公司管理层业绩指引（最优先参考）
2. 搜索 "{ticker} revenue forecast {forecast_year_1} {forecast_year_2} analyst consensus" — 获取分析师一致预期
3. 搜索 "{ticker} EBIT margin operating margin industry average" — 获取行业 benchmark
4. 搜索 "{ticker} WACC cost of capital" — 获取多源 WACC 数据

## 公司基本信息
- 公司名称: {company_name}
- 股票代码: {ticker}
- 所在国家: {country}
- Beta: {beta}
- 市值: {market_cap}
- 估值 Base Year: {base_year}

## 已计算的参数（供参考）
- 模型计算 WACC: {calculated_wacc}
- 历史平均有效税率: {calculated_tax_rate}

## 历史财务数据（单位：百万，最左列为最新年度 {base_year}）
{financial_table}

---

请对以下每个参数进行**独立、深入**的分析。每个参数的分析必须包含：
- 你的推理逻辑和分析过程
- 引用的数据来源（如搜索到的分析师预期、行业数据等）
- 最终建议数值及理由

**输出格式要求：必须输出严格的 JSON 代码块，每个参数包含 value 和 reasoning 两个字段。reasoning 字段必须是详细的中文分析（不少于2-3句话），包含数据依据和推理过程。**

```json
{{
  "revenue_growth_1": {{
    "value": <数值，如5表示5%>,
    "reasoning": "<详细中文分析：**优先查找公司管理层最新业绩指引（earnings guidance）**，如果有明确的收入指引则以此为最重要参考依据；如果没有业绩指引，则重点参考分析师一致预期（analyst consensus）。请注明数据来源。>"
  }},
  "revenue_growth_2": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：2-5年复合增长率的推理依据，考虑行业天花板、竞争格局、公司护城河等>"
  }},
  "ebit_margin": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：目标EBIT margin的依据，参考行业benchmark、公司历史趋势、运营杠杆等>"
  }},
  "convergence": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：为什么选择这个收敛年数，从当前margin到目标margin需要多久>"
  }},
  "revenue_invested_capital_ratio_1": {{
    "value": <数值，如果建议设为0则填0>,
    "reasoning": "<详细中文分析：Year 1-2阶段的Revenue/Invested Capital比率依据。**重要：必须参考历史Total Reinvestments数据。如果历史Total Reinvestments持续为负数（即公司在回收资本而非投入资本），说明这是轻资产公司，应建议将比率设为0（表示不需要额外净资本投入）。同时验证：按此比率推算出的预期净资本开支（= 预期收入增量 / 比率）与历史Total Reinvestments金额是否在合理范围内，如果差异过大需要调整比率。**>"
  }},
  "revenue_invested_capital_ratio_2": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：Year 3-5阶段的比率依据，同样对照历史reinvestment水平进行合理性校验>"
  }},
  "revenue_invested_capital_ratio_3": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：Year 5-10阶段的比率依据，考虑成熟期资本效率变化，并对照历史数据校验合理性>"
  }},
  "tax_rate": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：税率建议依据，参考历史有效税率、法定税率、税务优惠政策等>"
  }},
  "wacc": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：WACC建议依据，综合模型计算值和第三方数据源>"
  }},
  "ronic_match_wacc": {{
    "value": <true或false>,
    "reasoning": "<详细中文分析：判断ROIC在终值期是否回归WACC的理由，考虑公司竞争优势的持久性>"
  }}
}}
```

**注意：JSON 必须是有效格式，所有字符串用双引号，不要有注释。reasoning 中如有引用数据源请注明。**"""


def analyze_company(ticker, summary_df, base_year_data, company_profile, calculated_wacc, calculated_tax_rate, base_year):
    """
    Call Claude via CLI (using Max subscription) to analyze a company and generate DCF valuation parameters.

    Returns:
        dict with keys: parameters (dict), raw_text (str)
    """
    company_name = company_profile.get('companyName', ticker)
    country = company_profile.get('country', 'United States')
    beta = company_profile.get('beta', 1.0)
    market_cap = company_profile.get('marketCap', 0)

    financial_table = summary_df.to_string()

    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        ticker=ticker,
        company_name=company_name,
        country=country,
        beta=beta,
        market_cap=f"{market_cap:,.0f}",
        calculated_wacc=f"{calculated_wacc:.2%}",
        calculated_tax_rate=f"{calculated_tax_rate:.2%}",
        financial_table=financial_table,
        base_year=base_year,
        forecast_year_1=base_year + 1,
        forecast_year_2=base_year + 2,
    )

    print(f"\n{S.ai_label(f'正在使用 AI 分析 {company_name} ({ticker})...')}")
    print(S.info("（AI 正在搜索最新市场数据和分析师预期，请稍候...）\n"))

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    result = subprocess.run(
        ['claude', '-p', prompt, '--allowedTools', 'WebSearch,WebFetch'],
        capture_output=True, text=True, timeout=300, env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or "Unknown error"
        raise RuntimeError(S.error(f"Claude CLI 调用失败: {error_msg}"))

    all_text = result.stdout.strip()

    if not all_text:
        raise RuntimeError(S.error("Claude CLI 返回空内容"))

    parameters = _parse_structured_parameters(all_text)

    return {
        "parameters": parameters,
        "raw_text": all_text,
    }


def _parse_structured_parameters(text):
    """Parse structured JSON with value+reasoning per parameter."""
    # Try ```json ... ``` block
    json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find a large JSON object
    json_match = re.search(r'\{[\s\S]*"revenue_growth_1"[\s\S]*"ronic_match_wacc"[\s\S]*\}', text)
    if json_match:
        # Find the balanced braces
        raw = json_match.group(0)
        depth = 0
        for i, c in enumerate(raw):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[:i+1])
                    except json.JSONDecodeError:
                        break

    return None


def interactive_review(ai_result, calculated_wacc, calculated_tax_rate, company_profile, wacc_details):
    """
    Interactive review of AI-suggested parameters.
    Each parameter shows ONLY its own reasoning from the structured AI output.

    Returns:
        dict of final valuation parameters, or None if parsing failed
    """
    params = ai_result["parameters"]

    if params is None:
        print(f"\n{S.warning('无法解析 AI 返回的参数。以下是 AI 的完整分析：')}")
        print(S.divider())
        print(ai_result.get("raw_text", "（无内容）"))
        print(S.divider())
        return None

    print(f"\n{S.header('AI 估值参数建议 — 逐项确认')}")
    print(S.info("按 Enter 接受建议值，或输入新值覆盖"))

    # Define review sections — each parameter reviewed independently
    param_configs = [
        ("revenue_growth_1", "Year 1 收入增长率 (%)", "%"),
        ("revenue_growth_2", "Years 2-5 复合年增长率 CAGR (%)", "%"),
        ("ebit_margin", "目标 EBIT Margin (%)", "%"),
        ("convergence", "收敛到目标 EBIT margin 的年数", "年"),
        ("revenue_invested_capital_ratio_1", "Revenue/Invested Capital 比率 (Year 1-2)", ""),
        ("revenue_invested_capital_ratio_2", "Revenue/Invested Capital 比率 (Year 3-5)", ""),
        ("revenue_invested_capital_ratio_3", "Revenue/Invested Capital 比率 (Year 5-10)", ""),
        ("tax_rate", "税率 (%)", "%"),
        ("wacc", "WACC (%)", "%"),
    ]

    final_params = {}

    for key, label, unit in param_configs:
        param_data = params.get(key, {})

        # Support both structured {value, reasoning} and flat value format
        if isinstance(param_data, dict):
            ai_value = param_data.get("value")
            reasoning = param_data.get("reasoning", "")
        else:
            ai_value = param_data
            reasoning = ""

        print(f"\n{S.subheader(label)}")

        # Show AI reasoning for THIS parameter only
        if reasoning:
            print(f"\n  {S.ai_label('AI 分析:')}")
            _print_wrapped(reasoning, indent="    ", width=70)

        # For WACC: show the model calculation details
        if key == "wacc" and wacc_details:
            from .dcf import print_wacc_details
            print_wacc_details(wacc_details)

        # For tax_rate: show calculated reference
        if key == "tax_rate":
            print(f"\n  {S.muted(f'历史平均有效税率: {calculated_tax_rate * 100:.1f}%')}")

        if ai_value is not None:
            print(f"\n  {S.label('AI 建议值:')} {S.value(f'{ai_value}{unit}')}")
            _warn_if_out_of_range(key, ai_value)
            user_input = input(f"  {S.prompt(f'输入新值或按 Enter 接受 [{ai_value}]: ')}").strip()
        else:
            print(f"\n  {S.warning('AI 未提供建议值')}")
            user_input = input(f"  {S.prompt('请输入值: ')}").strip()

        if user_input == "":
            final_params[key] = float(ai_value) if ai_value is not None else 0.0
        else:
            try:
                final_params[key] = float(user_input)
            except ValueError:
                print(f"  {S.warning(f'输入无效，使用 AI 建议值: {ai_value}')}")
                final_params[key] = float(ai_value) if ai_value is not None else 0.0

    # Handle RONIC separately
    ronic_data = params.get("ronic_match_wacc", {})
    if isinstance(ronic_data, dict):
        ronic_match = ronic_data.get("value", True)
        ronic_reasoning = ronic_data.get("reasoning", "")
    else:
        ronic_match = ronic_data if isinstance(ronic_data, bool) else True
        ronic_reasoning = ""

    print(f"\n{S.subheader('RONIC (终值期再投资收益率)')}")

    if ronic_reasoning:
        print(f"\n  {S.ai_label('AI 分析:')}")
        _print_wrapped(ronic_reasoning, indent="    ", width=70)

    if ronic_match:
        print(f"\n  {S.label('AI 建议:')} {S.value('ROIC 在终值期回归 WACC（保守假设）')}")
    else:
        print(f"\n  {S.label('AI 建议:')} {S.value('ROIC 在终值期高于 WACC（公司有持续竞争优势）')}")

    default_ronic = 'y' if ronic_match else 'n'
    ronic_input = input(f"  {S.prompt(f'ROIC 是否在终值期回归 WACC? (y/n) [{default_ronic}]: ')}").strip().lower()
    if ronic_input == "":
        final_params["ronic_match_wacc"] = ronic_match
    else:
        final_params["ronic_match_wacc"] = (ronic_input == "y")

    print(f"\n{S.header('参数确认完成')}")

    return final_params


GAP_ANALYSIS_PROMPT_TEMPLATE = """你是一位资深的股权研究分析师。请分析以下 DCF 估值结果与当前市场股价之间的差异，并给出可能的原因分析。

## 公司信息
- 公司名称: {company_name}
- 股票代码: {ticker}
- 所在国家: {country}
- 当前股价: {current_price} {currency}
- DCF 估值每股价格: {dcf_price:.2f} {currency}
- 差异: {gap_pct:+.1f}% （{gap_direction}）

## DCF 估值关键假设
- Year 1 收入增长率: {revenue_growth_1}%
- Years 2-5 复合增长率: {revenue_growth_2}%
- 目标 EBIT Margin: {ebit_margin}%
- WACC: {wacc}%
- 税率: {tax_rate}%

## 估值摘要（单位：百万）
- 未来10年现金流现值: {pv_cf:,.0f}
- 终值现值: {pv_terminal:,.0f}
- 企业价值: {enterprise_value:,.0f}
- 股权价值: {equity_value:,.0f}

## 历史财务数据（单位：百万）
{financial_table}

---

**请使用 WebSearch 搜索以下信息来辅助分析：**
1. 搜索 "{ticker} stock price target analyst {forecast_year}" — 获取分析师目标价
2. 搜索 "{ticker} risks challenges {forecast_year}" — 获取公司面临的风险
3. 搜索 "{ticker} growth catalysts outlook" — 获取增长催化剂

请用**中文**进行分析，包含以下内容：

1. **估值差异总结**：简要说明 DCF 估值与市场价的差异幅度和方向
2. **可能的高估/低估原因**（至少列出3-5个因素）：
   - 市场情绪/宏观因素
   - 行业趋势/竞争格局变化
   - 公司特有风险或催化剂
   - DCF 模型假设可能过于保守/激进的地方
   - 市场对未来增长预期的共识与 DCF 假设的对比
3. **分析师共识对比**：将 DCF 结果与搜索到的分析师目标价进行对比
4. **建议**：基于以上分析，给出对估值结果的信心评价和需要关注的关键风险
5. **修正后估值**：综合以上分析因素（市场预期差异、风险溢价调整、增长假设修正等），给出你认为更合理的每股内在价值。请在分析最后一行，严格按以下格式输出（仅数字，不含货币符号）：
   ADJUSTED_PRICE: <数值>

请直接输出分析内容，不需要 JSON 格式（仅最后一行的 ADJUSTED_PRICE 需要严格格式）。"""


def analyze_valuation_gap(ticker, company_profile, results, valuation_params, summary_df, base_year):
    """
    Call Claude via CLI to analyze the gap between DCF valuation and current stock price.

    Returns:
        dict with 'analysis_text' (str) and 'adjusted_price' (float or None), or None on failure.
    """
    company_name = company_profile.get('companyName', ticker)
    country = company_profile.get('country', 'United States')
    currency = company_profile.get('currency', 'USD')
    current_price = company_profile.get('price', 0)
    dcf_price = results['price_per_share']

    if current_price == 0:
        print(f"\n{S.warning('无法获取当前股价，跳过估值差异分析。')}")
        return None

    gap_pct = (dcf_price - current_price) / current_price * 100
    gap_direction = 'DCF 估值高于市场价，市场可能低估' if gap_pct > 0 else 'DCF 估值低于市场价，市场可能高估'

    financial_table = summary_df.to_string()

    prompt = GAP_ANALYSIS_PROMPT_TEMPLATE.format(
        company_name=company_name,
        ticker=ticker,
        country=country,
        current_price=current_price,
        currency=currency,
        dcf_price=dcf_price,
        gap_pct=gap_pct,
        gap_direction=gap_direction,
        revenue_growth_1=valuation_params['revenue_growth_1'],
        revenue_growth_2=valuation_params['revenue_growth_2'],
        ebit_margin=valuation_params['ebit_margin'],
        wacc=valuation_params['wacc'],
        tax_rate=valuation_params['tax_rate'],
        pv_cf=results['pv_cf_next_10_years'],
        pv_terminal=results['pv_terminal_value'],
        enterprise_value=results['enterprise_value'],
        equity_value=results['equity_value'],
        financial_table=financial_table,
        forecast_year=base_year + 1,
    )

    print(f"\n{S.header('DCF 估值 vs 当前股价 差异分析')}")
    print(f"  {S.label('当前股价:')}     {current_price:.2f} {currency}")
    print(f"  {S.label('DCF 估值:')}     {S.price_colored(dcf_price, current_price)} {currency}")
    print(f"  {S.label('差异:')}         {S.pct_colored(gap_pct)}")
    print(f"\n{S.ai_label('正在使用 AI 分析估值差异原因...')}")

    env = os.environ.copy()
    env.pop('CLAUDECODE', None)

    try:
        result = subprocess.run(
            ['claude', '-p', prompt, '--allowedTools', 'WebSearch,WebFetch'],
            capture_output=True, text=True, timeout=300, env=env,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Unknown error"
            print(f"\n{S.error(f'AI 分析调用失败: {error_msg}')}")
            return None

        analysis_text = result.stdout.strip()
        if not analysis_text:
            print(f"\n{S.warning('AI 返回空内容，跳过差异分析。')}")
            return None

        # Parse adjusted price from the last line
        adjusted_price = None
        price_match = re.search(r'ADJUSTED_PRICE:\s*([\d.,]+)', analysis_text)
        if price_match:
            try:
                adjusted_price = float(price_match.group(1).replace(',', ''))
            except ValueError:
                pass

        # Display analysis (strip the ADJUSTED_PRICE line from display)
        display_text = re.sub(r'\n?\s*ADJUSTED_PRICE:.*$', '', analysis_text).strip()
        print(f"\n{S.divider()}")
        print(display_text)
        print(S.divider())

        if adjusted_price is not None:
            adj_gap_pct = (adjusted_price - current_price) / current_price * 100
            print(f"\n  {S.label('综合差异分析后修正估值:')} {S.price_colored(adjusted_price, current_price)} {currency}（相对当前股价 {S.pct_colored(adj_gap_pct)}）")

        return {
            'analysis_text': analysis_text,
            'adjusted_price': adjusted_price,
            'current_price': current_price,
            'dcf_price': dcf_price,
            'gap_pct': gap_pct,
            'currency': currency,
        }

    except subprocess.TimeoutExpired:
        print(f"\n{S.warning('AI 分析超时，跳过差异分析。')}")
        return None
    except Exception as e:
        print(f"\n{S.error(f'AI 差异分析出错: {e}')}")
        return None


def _print_wrapped(text, indent="    ", width=70):
    """Print text with word wrapping and indent."""
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        while len(line) > width:
            # Find a good break point
            break_at = line.rfind(' ', 0, width)
            if break_at == -1:
                break_at = width
            print(f"{indent}{line[:break_at]}")
            line = line[break_at:].lstrip()
        if line:
            print(f"{indent}{line}")


def _warn_if_out_of_range(key, value):
    """Print a warning if a parameter value seems unreasonable."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return

    ranges = {
        "revenue_growth_1": (-50, 100),
        "revenue_growth_2": (-20, 50),
        "ebit_margin": (-20, 60),
        "convergence": (1, 10),
        "revenue_invested_capital_ratio_1": (0, 10),
        "revenue_invested_capital_ratio_2": (0, 10),
        "revenue_invested_capital_ratio_3": (0, 10),
        "tax_rate": (0, 50),
        "wacc": (3, 25),
    }

    if key in ranges:
        low, high = ranges[key]
        if v < low or v > high:
            print(f"  {S.warning(f'⚠ 警告: 该值 ({v}) 超出通常范围 ({low} ~ {high})，请仔细确认')}")
