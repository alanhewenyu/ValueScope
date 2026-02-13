# Copyright (c) 2025 Alan He. Licensed under MIT.

import json
import os
import re
import subprocess


ANALYSIS_PROMPT_TEMPLATE = """你是一位资深的股权研究分析师和DCF估值专家。你的任务是根据提供的历史财务数据和公开市场信息，为一家公司生成合理的DCF估值参数建议。

请按照以下8个步骤进行分析，每一步都要用中文详细说明推理依据：

1. **Year 1 收入增长率**：基于最新业绩指引、分析师一致预期、行业趋势判断下一年收入增长率
2. **Years 2-5 复合年增长率(CAGR)**：考虑行业天花板、竞争格局、公司护城河，预测中期增长
3. **目标 EBIT Margin**：参考行业 benchmark、公司运营杠杆、管理层指引
4. **收敛年数**：从当前 EBIT margin 收敛到目标值需要的年数
5. **再投资比率（Revenue/Invested Capital）**：分 Year 1-2、Year 3-5、Year 5-10 三个阶段
6. **税率**：参考历史有效税率和法定税率
7. **WACC**：综合考虑已计算的 WACC 和市场数据
8. **RONIC（终值再投资收益率）**：判断 ROIC 在终值期是否会回归 WACC

请先使用 WebSearch 工具搜索以下信息（重要！请务必搜索）：
- 该公司最新业绩指引和分析师一致预期（搜索 "{ticker} revenue forecast 2025 2026 analyst consensus"）
- 行业平均 EBIT margin 和增长率 benchmark
- 多源 WACC 估算数据（搜索 "{ticker} WACC"）

以下是公司信息和历史财务数据：

## 公司基本信息
- 公司名称: {company_name}
- 股票代码: {ticker}
- 所在国家: {country}
- Beta: {beta}
- 市值: {market_cap}

## 已计算的参数（供参考）
- 计算得到的 WACC: {calculated_wacc}
- 历史平均有效税率: {calculated_tax_rate}

## 历史财务数据（单位：百万）
{financial_table}

完成分析后，**必须**在最后输出一个 JSON 代码块，格式严格如下：
```json
{{
  "revenue_growth_1": <Year1收入增长率，百分比数值，如15表示15%>,
  "revenue_growth_2": <Years2-5 CAGR，百分比数值>,
  "ebit_margin": <目标EBIT margin，百分比数值>,
  "convergence": <收敛年数>,
  "revenue_invested_capital_ratio_1": <Year1-2 Revenue/IC比率>,
  "revenue_invested_capital_ratio_2": <Year3-5 Revenue/IC比率>,
  "revenue_invested_capital_ratio_3": <Year5-10 Revenue/IC比率>,
  "tax_rate": <税率，百分比数值>,
  "wacc": <WACC，百分比数值>,
  "ronic_match_wacc": <true或false, ROIC是否在终值期回归WACC>
}}
```"""


def analyze_company(ticker, summary_df, base_year_data, company_profile, calculated_wacc, calculated_tax_rate):
    """
    Call Claude via CLI (using Max subscription) to analyze a company and generate DCF valuation parameters.

    Returns:
        dict with keys: parameters (dict), reasoning (dict), raw_text (str)
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
    )

    print(f"\n正在使用 AI 分析 {company_name} ({ticker})...")
    print("（AI 正在搜索最新市场数据和分析师预期，请稍候...）\n")

    # Call claude CLI using Max subscription
    env = os.environ.copy()
    env.pop('CLAUDECODE', None)  # Allow nested invocation

    result = subprocess.run(
        ['claude', '-p', prompt, '--allowedTools', 'WebSearch,WebFetch'],
        capture_output=True, text=True, timeout=300, env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or "Unknown error"
        raise RuntimeError(f"Claude CLI 调用失败: {error_msg}")

    all_text = result.stdout.strip()

    if not all_text:
        raise RuntimeError("Claude CLI 返回空内容")

    # Parse the JSON parameters from the response
    parameters = _parse_parameters(all_text)
    reasoning = _parse_reasoning(all_text)

    return {
        "parameters": parameters,
        "reasoning": reasoning,
        "raw_text": all_text,
    }


def _parse_parameters(text):
    """Parse JSON parameter block from AI response text."""
    # Try to find ```json ... ``` block
    json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object with expected keys
    json_match = re.search(r'\{[^{}]*"revenue_growth_1"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _parse_reasoning(text):
    """Extract per-parameter reasoning from AI response text."""
    reasoning = {}
    params_labels = {
        "revenue_growth_1": "Year 1 收入增长率",
        "revenue_growth_2": "Years 2-5 CAGR",
        "ebit_margin": "目标 EBIT Margin",
        "convergence": "收敛年数",
        "revenue_invested_capital_ratio_1": "Year 1-2 Revenue/IC",
        "revenue_invested_capital_ratio_2": "Year 3-5 Revenue/IC",
        "revenue_invested_capital_ratio_3": "Year 5-10 Revenue/IC",
        "tax_rate": "税率",
        "wacc": "WACC",
        "ronic_match_wacc": "RONIC",
    }

    # Try to extract reasoning sections from the text
    for key, label in params_labels.items():
        patterns = [
            rf'(?:\d+\.?\s*\**\s*{re.escape(label)}[^*]*\**[：:]\s*)(.*?)(?=\n\d+\.|\n\*\*|```json|$)',
            rf'(?:{re.escape(label)}[^：:]*[：:]\s*)(.*?)(?=\n\d+\.|\n\*\*|```json|$)',
            rf'(?:"{re.escape(key)}"[^：:]*[：:]\s*)(.*?)(?=\n"|```|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                reasoning[key] = match.group(1).strip()[:500]
                break

    return reasoning


def interactive_review(ai_result, calculated_wacc, calculated_tax_rate, company_profile):
    """
    Interactive review of AI-suggested parameters.
    User can press Enter to accept or type a new value to override.

    Returns:
        dict of final valuation parameters, or None if parsing failed
    """
    params = ai_result["parameters"]
    reasoning = ai_result.get("reasoning", {})

    if params is None:
        print("\n无法解析 AI 返回的参数。以下是 AI 的完整分析：")
        print("-" * 60)
        print(ai_result.get("raw_text", "（无内容）"))
        print("-" * 60)
        return None

    print("\n" + "=" * 60)
    print("AI 估值参数建议 — 逐项确认")
    print("按 Enter 接受建议值，或输入新值覆盖")
    print("=" * 60)

    param_configs = [
        ("revenue_growth_1", "Year 1 收入增长率 (%)", "%", None),
        ("revenue_growth_2", "Years 2-5 复合年增长率 CAGR (%)", "%", None),
        ("ebit_margin", "目标 EBIT Margin (%)", "%", None),
        ("convergence", "收敛到目标 EBIT margin 的年数", "年", None),
        ("revenue_invested_capital_ratio_1", "Revenue/Invested Capital 比率 (Year 1-2)", "", None),
        ("revenue_invested_capital_ratio_2", "Revenue/Invested Capital 比率 (Year 3-5)", "", None),
        ("revenue_invested_capital_ratio_3", "Revenue/Invested Capital 比率 (Year 5-10)", "", None),
        ("tax_rate", "税率 (%)", "%", calculated_tax_rate * 100),
        ("wacc", "WACC (%)", "%", calculated_wacc * 100),
    ]

    final_params = {}

    for key, label, unit, reference_value in param_configs:
        ai_value = params.get(key)
        reason = reasoning.get(key, "")

        print(f"\n--- {label} ---")
        if reason:
            display_reason = reason[:200] + ("..." if len(reason) > 200 else "")
            print(f"  AI 分析: {display_reason}")

        if reference_value is not None and ai_value is not None:
            print(f"  模型计算值: {reference_value:.1f}{unit}  |  AI 建议值: {ai_value}{unit}")
        elif ai_value is not None:
            print(f"  AI 建议值: {ai_value}{unit}")
        else:
            print(f"  AI 未提供建议值")

        if ai_value is not None:
            _warn_if_out_of_range(key, ai_value)

        if ai_value is not None:
            user_input = input(f"  输入新值或按 Enter 接受 [{ai_value}]: ").strip()
        else:
            default = reference_value if reference_value is not None else ""
            user_input = input(f"  请输入值 [{default}]: ").strip()
            if user_input == "" and reference_value is not None:
                ai_value = reference_value

        if user_input == "":
            final_params[key] = float(ai_value) if ai_value is not None else 0.0
        else:
            try:
                final_params[key] = float(user_input)
            except ValueError:
                print(f"  输入无效，使用 AI 建议值: {ai_value}")
                final_params[key] = float(ai_value) if ai_value is not None else 0.0

    # Handle RONIC
    ronic_match = params.get("ronic_match_wacc", True)
    ronic_reason = reasoning.get("ronic_match_wacc", "")
    print(f"\n--- RONIC (终值期再投资收益率) ---")
    if ronic_reason:
        display_reason = ronic_reason[:200] + ("..." if len(ronic_reason) > 200 else "")
        print(f"  AI 分析: {display_reason}")

    if ronic_match:
        print("  AI 建议: ROIC 在终值期回归 WACC（保守假设）")
    else:
        print("  AI 建议: ROIC 在终值期高于 WACC（公司有持续竞争优势）")

    ronic_input = input(f"  ROIC 是否在终值期回归 WACC? (y/n) [{'y' if ronic_match else 'n'}]: ").strip().lower()
    if ronic_input == "":
        final_params["ronic_match_wacc"] = ronic_match
    else:
        final_params["ronic_match_wacc"] = (ronic_input == "y")

    print("\n" + "=" * 60)
    print("参数确认完成")
    print("=" * 60)

    return final_params


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
        "revenue_invested_capital_ratio_1": (0.1, 10),
        "revenue_invested_capital_ratio_2": (0.1, 10),
        "revenue_invested_capital_ratio_3": (0.1, 10),
        "tax_rate": (0, 50),
        "wacc": (3, 25),
    }

    if key in ranges:
        low, high = ranges[key]
        if v < low or v > high:
            print(f"  ⚠ 警告: 该值 ({v}) 超出通常范围 ({low} ~ {high})，请仔细确认")
