# Copyright (c) 2025 Alan He. Licensed under MIT.

import json
import os
import re
import shutil
import subprocess
from . import style as S

# ---------------------------------------------------------------------------
# AI Engine detection: Claude CLI → Gemini CLI → Qwen Code CLI (fallback)
# The actual model name is detected from JSON output on the first call.
# ---------------------------------------------------------------------------

# Supported engines: 'claude', 'gemini', 'qwen'
_ENGINE_LABELS = {'claude': 'Claude CLI', 'gemini': 'Gemini CLI', 'qwen': 'Qwen Code CLI'}

# Claude model ID → human-friendly display name
_CLAUDE_MODEL_DISPLAY = {
    'claude-opus-4-6': 'Claude Opus 4.6',
    'claude-opus-4-5-20251101': 'Claude Opus 4.5',
    'claude-opus-4-5': 'Claude Opus 4.5',
    'claude-opus-4-20250514': 'Claude Opus 4',
    'claude-sonnet-4-5-20250929': 'Claude Sonnet 4.5',
    'claude-sonnet-4-5': 'Claude Sonnet 4.5',
    'claude-sonnet-4-20250514': 'Claude Sonnet 4',
}

# Gemini: 'pro' alias resolves to latest Pro model.
# previewFeatures must be enabled for Gemini 3 — we auto-configure this.
GEMINI_MODEL = 'pro'


def _ensure_gemini_preview():
    """Ensure Gemini CLI has previewFeatures enabled in ~/.gemini/settings.json.

    This is required for the 'pro' alias to resolve to the latest model
    (e.g. Gemini 3 Pro) instead of being stuck on Gemini 2.5 Pro.
    """
    settings_dir = os.path.expanduser('~/.gemini')
    settings_path = os.path.join(settings_dir, 'settings.json')

    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            settings = {}

    general = settings.get('general', {})
    if general.get('previewFeatures') is True:
        return  # already enabled

    general['previewFeatures'] = True
    settings['general'] = general

    os.makedirs(settings_dir, exist_ok=True)
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)


def _detect_ai_engine():
    """Detect available AI CLI engine.

    Returns 'claude', 'gemini', 'qwen', or None.
    Priority: Claude CLI > Gemini CLI > Qwen Code CLI.
    """
    if shutil.which('claude'):
        return 'claude'
    if shutil.which('gemini'):
        _ensure_gemini_preview()
        return 'gemini'
    if shutil.which('qwen'):
        return 'qwen'
    return None

_AI_ENGINE = _detect_ai_engine()

# Actual model name detected at runtime (populated after first AI call)
_detected_model_name = None


def set_ai_engine(engine):
    """Override the auto-detected AI engine (called via --engine flag).

    Args:
        engine: 'claude', 'gemini', or 'qwen'
    Raises:
        RuntimeError: If the requested CLI is not installed.
    """
    global _AI_ENGINE, _detected_model_name
    _install_hints = {
        'claude': "Claude CLI 未安装。请先安装: https://docs.anthropic.com/en/docs/claude-code",
        'gemini': "Gemini CLI 未安装。请先安装: npm install -g @google/gemini-cli",
        'qwen':   "Qwen Code CLI 未安装。请先安装: npm install -g @qwen-code/qwen-code",
    }
    cmd_name = 'qwen' if engine == 'qwen' else engine
    if not shutil.which(cmd_name):
        raise RuntimeError(_install_hints[engine])
    if engine == 'gemini':
        _ensure_gemini_preview()
    _AI_ENGINE = engine
    _detected_model_name = None  # reset so first call re-detects


def _ai_engine_display_name():
    """Return human-friendly display name for the active AI engine."""
    if _detected_model_name:
        return _detected_model_name
    if _AI_ENGINE == 'claude':
        return 'Claude (latest)'
    elif _AI_ENGINE == 'gemini':
        return 'Gemini (latest)'
    elif _AI_ENGINE == 'qwen':
        return 'Qwen (latest)'
    return 'N/A'


def _extract_error_message(raw_error):
    """Extract a concise error message from verbose CLI error output.

    Gemini CLI errors include full stack traces and JSON responses.
    This extracts just the key message (e.g. "No capacity available for model...").
    """
    # Try to find the core error message in JSON
    m = re.search(r'"message"\s*:\s*"([^"]+)"', raw_error)
    if m:
        return m.group(1)
    # Fallback: first non-empty line, capped at 200 chars
    for line in raw_error.split('\n'):
        line = line.strip()
        if line and not line.startswith(('at ', 'Hook ', 'Loaded ')):
            return line[:200]
    return raw_error[:200]


def _run_engine(engine, prompt):
    """Run a single AI engine and return (raw_stdout, engine_name) or None on failure.

    This is a low-level helper — it does NOT do fallback. The caller (_call_ai_cli)
    handles fallback logic.
    """
    engine_label = _ENGINE_LABELS.get(engine, engine)

    if engine == 'claude':
        cmd = ['claude', '-p', prompt, '--output-format', 'json',
               '--allowedTools', 'WebSearch,WebFetch']
    elif engine == 'gemini':
        cmd = ['gemini', '-p', prompt, '--output-format', 'json', '-m', GEMINI_MODEL]
    elif engine == 'qwen':
        cmd = ['qwen', '-p', prompt]
    else:
        print(f"  {S.error(f'未知引擎: {engine}')}")
        return None

    _timeout = 600  # 10 minutes for search + analysis
    # Build a clean env without CLAUDE* markers to avoid
    # "nested session" error when launched from Claude Code.
    clean_env = {k: v for k, v in os.environ.items()
                 if not k.startswith('CLAUDE')}
    for _ek in ('PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM',
                'FMP_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY'):
        if _ek in os.environ:
            clean_env[_ek] = os.environ[_ek]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=_timeout, env=clean_env)
    except subprocess.TimeoutExpired:
        print(f"  {S.warning(f'{engine_label} 调用超时 ({_timeout}s)')}")
        return None

    if result.returncode != 0:
        error_msg = _extract_error_message(result.stderr.strip() or result.stdout.strip() or "Unknown error")
        print(f"  {S.warning(f'{engine_label} 调用失败: {error_msg}')}")
        return None

    raw = result.stdout.strip()
    if not raw:
        print(f"  {S.warning(f'{engine_label} 返回空内容')}")
        return None

    # Claude CLI may return exit code 0 but with is_error:true in JSON
    # (e.g. rate limit hit). Detect this and treat as failure so fallback kicks in.
    if engine == 'claude':
        try:
            _parsed = json.loads(raw)
            if isinstance(_parsed, dict) and _parsed.get('is_error'):
                error_msg = _parsed.get('result', '') or 'Unknown error'
                print(f"  {S.warning(f'{engine_label} 调用失败: {error_msg}')}")
                return None
        except (json.JSONDecodeError, KeyError):
            pass  # not JSON or unexpected structure — continue normally

    return (raw, engine)


def _call_ai_cli(prompt):
    """Call the detected AI CLI with a prompt and return the response text.

    Claude: uses CLI default (latest model), --output-format json.
    Gemini: uses -m pro (latest Pro), --output-format json.
    Qwen:   uses CLI default (qwen3-coder), plain text output.

    If Gemini/Qwen fails and Claude CLI is available, automatically falls back
    to Claude so the analysis can continue.

    Returns:
        str: The AI response text (stdout).
    Raises:
        RuntimeError: If no AI engine is available or all engines fail.
    """
    global _detected_model_name, _AI_ENGINE

    if _AI_ENGINE is None:
        raise RuntimeError(
            "未检测到可用的 AI 引擎。请安装以下任一工具：\n"
            "  1. Claude CLI: https://docs.anthropic.com/en/docs/claude-code\n"
            "  2. Gemini CLI: npm install -g @google/gemini-cli\n"
            "     （只需 Google 账号登录，免费使用）\n"
            "  3. Qwen Code:  npm install -g @qwen-code/qwen-code\n"
            "     （只需 qwen.ai 账号登录，免费使用）"
        )

    engine = _AI_ENGINE
    result = _run_engine(engine, prompt)

    # Fallback chain: try other available engines if the primary one fails.
    # Priority order: claude → gemini → qwen
    if result is None:
        _all_engines = ['claude', 'gemini', 'qwen']
        for fallback in _all_engines:
            if fallback == engine:
                continue  # skip the engine that already failed
            cmd_name = 'qwen' if fallback == 'qwen' else fallback
            if not shutil.which(cmd_name):
                continue  # not installed
            fallback_label = _ENGINE_LABELS.get(fallback, fallback)
            print(f"  {S.info(f'自动切换到 {fallback_label} 继续分析...')}")
            if fallback == 'gemini':
                _ensure_gemini_preview()
            _AI_ENGINE = fallback
            _detected_model_name = None
            result = _run_engine(fallback, prompt)
            if result is not None:
                break  # success

    if result is None:
        raise RuntimeError(f"{_ENGINE_LABELS.get(_AI_ENGINE, _AI_ENGINE)} 调用失败")

    raw, engine_used = result

    # Parse output — Claude and Gemini use JSON; Qwen uses plain text
    text = raw
    try:
        if engine_used == 'claude':
            data = json.loads(raw)
            text = data.get('result', raw)
            if not _detected_model_name and 'modelUsage' in data:
                models = data['modelUsage']
                primary = max(models, key=lambda m: models[m].get('costUSD', 0))
                _detected_model_name = _CLAUDE_MODEL_DISPLAY.get(primary, primary)
        elif engine_used == 'gemini':
            data = json.loads(raw)
            text = data.get('response', raw)
            if not _detected_model_name and 'stats' in data:
                model_stats = data['stats'].get('models', {})
                if model_stats:
                    model_id = next(iter(model_stats))
                    pretty = model_id.replace('gemini-', 'Gemini ').replace('-', ' ').title()
                    _detected_model_name = pretty
        else:  # qwen — plain text, no JSON output to detect model
            text = raw
    except (json.JSONDecodeError, KeyError, StopIteration):
        pass

    if not text:
        raise RuntimeError(f"{_ENGINE_LABELS.get(engine_used, engine_used)} 返回空内容")

    return text


ANALYSIS_PROMPT_TEMPLATE = """你是一位资深的股权研究分析师和DCF估值专家。请根据以下历史财务数据和公开市场信息，为 {company_name} ({ticker}) 生成DCF估值参数建议。

**注意：下方历史财务数据的最新年度（最左列）是 {base_year} 年{ttm_context}。请基于 {base_year} 年的最新数据进行分析。{forecast_year_guidance}**

**重要：请务必先使用 WebSearch 工具搜索以下信息再开始分析：**
1. 搜索 "{ticker} earnings guidance revenue outlook {search_year}" — 获取公司管理层业绩指引（最优先参考）
2. 搜索 "{ticker} revenue forecast {search_year} {search_year_2} analyst consensus" — 获取分析师一致预期
3. 搜索 "{ticker} EBIT margin operating margin industry average" — 获取行业 benchmark
4. 搜索 "{ticker} WACC cost of capital" — 获取多源 WACC 数据

## 公司基本信息
- 公司名称: {company_name}
- 股票代码: {ticker}
- 所在国家: {country}
- Beta: {beta}
- 市值: {market_cap}
- 估值 Base Year: {base_year}{ttm_base_label}

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
    "reasoning": "<详细中文分析：**分析步骤（必须严格按顺序执行）：**\n1. **首先**检查历史 Revenue / IC 比率（在 Key Ratios 部分）是否各年稳定（波动幅度在±20%以内）。如果稳定，则**优先使用历史平均值**作为基准，并根据未来收入增速预测适当调整（增速加快→比率可略高，增速放缓→比率可略低）。\n2. **其次**，如果 Revenue / IC 波动较大或不适用，则检查历史 Total Reinvestments 数据：如果持续为负数（公司在回收资本），说明是轻资产公司，应设为0；如果为正，则反算合理比率（= 收入增量 / Total Reinvestments），并验证推算出的预期净资本开支与历史水平是否匹配。\n请明确说明采用了哪种方法及原因。>"
  }},
  "revenue_invested_capital_ratio_2": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：Year 3-5阶段的比率依据。同样优先参考历史 Revenue / IC 稳定性，其次对照历史 reinvestment 水平校验。>"
  }},
  "revenue_invested_capital_ratio_3": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：Year 5-10阶段的比率依据。考虑成熟期资本效率变化，参考历史 Revenue / IC 趋势和 reinvestment 水平。>"
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


def analyze_company(ticker, summary_df, base_year_data, company_profile, calculated_wacc, calculated_tax_rate, base_year, ttm_quarter='', ttm_end_date=''):
    """
    Call AI CLI (Claude or Gemini) to analyze a company and generate DCF valuation parameters.

    Returns:
        dict with keys: parameters (dict), raw_text (str)
    """
    company_name = company_profile.get('companyName', ticker)
    country = company_profile.get('country', 'United States')
    beta = company_profile.get('beta', 1.0)
    market_cap = company_profile.get('marketCap', 0)

    financial_table = summary_df.to_string()

    # Calculate forecast_year_1 using the same logic as main.py
    if ttm_end_date and ttm_quarter:
        _end_month = int(ttm_end_date[5:7])
        _end_year = int(ttm_end_date[:4])
        forecast_year_1 = _end_year if _end_month <= 6 else _end_year + 1
    else:
        forecast_year_1 = base_year + 1

    # Build TTM context strings for the prompt
    # TTM label format: "2026Q1 TTM" (year = base_year+1)
    _ttm_year_label = str(base_year + 1) if ttm_quarter else ''
    if ttm_quarter:
        _ttm_label = f'{_ttm_year_label}{ttm_quarter} TTM'
        ttm_context = f'，数据为 {_ttm_label}（截至 {ttm_end_date} 的最近十二个月）'
        ttm_base_label = f' ({_ttm_label})'
        # Year 1 guidance: tell AI precisely what period Year 1 covers
        forecast_year_guidance = (
            f'DCF 预测 Year 1 覆盖从 {ttm_end_date} 起的未来12个月（大致对应 {forecast_year_1} 日历年）。'
            f'请以 {forecast_year_1} 年作为 Year 1 的参考年份搜索业绩指引和分析师预期。'
        )
    else:
        ttm_context = ''
        ttm_base_label = ''
        forecast_year_guidance = f'Year 1 对应 {forecast_year_1} 年。'

    # Search year: use forecast_year_1 for search keywords
    search_year = forecast_year_1
    search_year_2 = forecast_year_1 + 1

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
        forecast_year_guidance=forecast_year_guidance,
        search_year=search_year,
        search_year_2=search_year_2,
        ttm_context=ttm_context,
        ttm_base_label=ttm_base_label,
    )

    engine_name = _ai_engine_display_name()
    print(f"\n{S.ai_label(f'正在使用 AI 分析 {company_name} ({ticker})...')}  {S.muted(f'({engine_name})')}")
    print(S.info("（AI 正在搜索最新市场数据和分析师预期，请稍候...）\n"))

    all_text = _call_ai_cli(prompt)

    # Show actual model name if detected during the call
    if _detected_model_name and _detected_model_name != engine_name:
        print(S.muted(f"  模型: {_detected_model_name}"))

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

    print(f"\n{S.header(f'AI 估值参数建议 — 逐项确认 ({_ai_engine_display_name()})')}")
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
2. **DCF 关键假设 vs 市场/分析师预期对比**（用表格展示）：
   逐项对比 DCF 的每个关键假设与搜索到的数据，并标注数据来源和适用期限。
   **严格区分短期 vs 长期数据的适用范围：**
   - 分析师对某一具体年度的收入/EPS 预测 → 只能佐证对应年度的假设（通常是 Year 1）
   - 历史增长率 → 只是参考，不能直接外推为未来 5 年复合增长率
   - Years 2-5 复合增长率的评估需要基于：行业长期增长空间、公司竞争壁垒和护城河、可寻址市场（TAM）天花板、历史增长的可持续性分析
   - 不要把 1-2 年期的分析师预期当作 5 年复合增长率的依据
3. **可能的高估/低估原因**（至少列出3-5个因素）：
   - 市场情绪/宏观因素
   - 行业趋势/竞争格局变化
   - 公司特有风险或催化剂
   - DCF 模型假设可能过于保守/激进的地方
4. **分析师共识对比**：将 DCF 结果与搜索到的分析师目标价进行对比
5. **建议**：基于以上分析，给出对估值结果的信心评价和需要关注的关键风险
6. **修正后估值**：综合以上分析因素，给出你认为更合理的每股内在价值。

**修正估值的关键原则（必须严格遵守）：**
- 修正的目的是：通过搜索发现**之前设定 DCF 参数时可能未考虑到的新信息**（如最新的行业政策变化、重大风险事件、市场情绪转变等），据此判断是否需要调整
- 修正后估值必须与你的分析逻辑**自洽**：
  - 如果搜索发现了**显著影响估值的负面新信息**（如行业监管政策收紧、重大诉讼风险、竞争格局恶化等，且这些信息在 DCF 参数设定时未被充分考虑），则应向下修正
  - 如果搜索未发现超出 DCF 假设范围的重大新信息，说明 DCF 估值参数已合理反映公司基本面，**不需要调整**——DCF 高于股价可能意味着市场定价偏低或受短期情绪影响，这恰恰是价值投资的买入机会
  - **绝对禁止**：分析中列出负面因素后反而把估值调得比 DCF 更高
- 不要仅仅因为 DCF 估值与市场价有差异就自动向市场价靠拢。市场价格可能是错误的

请在分析最后一行，严格按以下格式输出（仅数字，不含货币符号）：
   ADJUSTED_PRICE: <数值>

请直接输出分析内容，不需要 JSON 格式（仅最后一行的 ADJUSTED_PRICE 需要严格格式）。"""


def analyze_valuation_gap(ticker, company_profile, results, valuation_params, summary_df, base_year, forecast_year_1=None, forex_rate=None):
    """
    Call AI CLI (Claude or Gemini) to analyze the gap between DCF valuation and current stock price.

    Args:
        forex_rate: Exchange rate from reporting currency to stock trading currency.
                    Required when they differ (e.g. CNY→HKD for HK-listed Chinese companies).
                    If None and currencies match, no conversion is needed.

    Returns:
        dict with 'analysis_text' (str) and 'adjusted_price' (float or None), or None on failure.
    """
    company_name = company_profile.get('companyName', ticker)
    country = company_profile.get('country', 'United States')
    stock_currency = company_profile.get('currency', 'USD')
    current_price = company_profile.get('price', 0)
    dcf_price_raw = results['price_per_share']
    reported_currency = results.get('reported_currency', stock_currency)

    if current_price == 0:
        print(f"\n{S.warning('无法获取当前股价，跳过估值差异分析。')}")
        return None

    # Convert DCF price to stock trading currency if they differ
    currency_converted = False
    if reported_currency and reported_currency != stock_currency and forex_rate and forex_rate != 1.0:
        dcf_price = dcf_price_raw * forex_rate
        currency_converted = True
    else:
        dcf_price = dcf_price_raw

    gap_pct = (dcf_price - current_price) / current_price * 100
    gap_direction = 'DCF 估值高于市场价，市场可能低估' if gap_pct > 0 else 'DCF 估值低于市场价，市场可能高估'

    # Build currency context for prompt
    if currency_converted:
        currency_note = (
            f"\n\n**重要：货币换算说明**\n"
            f"- 财务数据以 {reported_currency} 报告，DCF 原始估值为 {dcf_price_raw:.2f} {reported_currency}\n"
            f"- 股票以 {stock_currency} 交易，已按汇率 {forex_rate:.4f} 换算为 {dcf_price:.2f} {stock_currency}\n"
            f"- 以下所有价格比较和修正估值均以 {stock_currency} 为单位"
        )
    else:
        currency_note = ""

    financial_table = summary_df.to_string()

    prompt = GAP_ANALYSIS_PROMPT_TEMPLATE.format(
        company_name=company_name,
        ticker=ticker,
        country=country,
        current_price=current_price,
        currency=stock_currency,
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
        forecast_year=forecast_year_1 if forecast_year_1 else base_year + 1,
    )
    if currency_note:
        prompt += currency_note

    print(f"\n{S.header('DCF 估值 vs 当前股价 差异分析')}")
    if currency_converted:
        print(f"  {S.label('当前股价:')}     {current_price:.2f} {stock_currency}")
        print(f"  {S.label('DCF 估值:')}     {S.price_colored(dcf_price, current_price)} {stock_currency}  {S.muted(f'({dcf_price_raw:.2f} {reported_currency} × {forex_rate:.4f})')}")
        print(f"  {S.label('差异:')}         {S.pct_colored(gap_pct)}")
    else:
        print(f"  {S.label('当前股价:')}     {current_price:.2f} {stock_currency}")
        print(f"  {S.label('DCF 估值:')}     {S.price_colored(dcf_price, current_price)} {stock_currency}")
        print(f"  {S.label('差异:')}         {S.pct_colored(gap_pct)}")

    try:
        engine_name = _ai_engine_display_name()
        print(f"\n{S.ai_label('正在使用 AI 分析估值差异原因...')}  {S.muted(f'({engine_name})')}")
        analysis_text = _call_ai_cli(prompt)

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
            print(f"\n  {S.label('综合差异分析后修正估值:')} {S.price_colored(adjusted_price, current_price)} {stock_currency}（相对当前股价 {S.pct_colored(adj_gap_pct)}）")

        return {
            'analysis_text': analysis_text,
            'adjusted_price': adjusted_price,
            'current_price': current_price,
            'dcf_price': dcf_price,
            'dcf_price_raw': dcf_price_raw if currency_converted else None,
            'gap_pct': gap_pct,
            'currency': stock_currency,
            'reported_currency': reported_currency if currency_converted else None,
            'forex_rate': forex_rate if currency_converted else None,
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
