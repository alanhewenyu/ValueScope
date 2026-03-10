# Copyright (c) 2025 Alan He. Licensed under MIT.

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import date
from . import style as S

# ---------------------------------------------------------------------------
# AI Engine detection: Claude CLI → Gemini CLI → Qwen Code CLI (fallback)
# The actual model name is detected from JSON output on the first call.
# ---------------------------------------------------------------------------

# Supported engines: 'claude', 'gemini', 'qwen'
_ENGINE_LABELS = {'claude': 'Claude CLI', 'gemini': 'Gemini CLI', 'qwen': 'Qwen Code CLI'}

# ---------------------------------------------------------------------------
# Terminal progress display during AI calls
# ---------------------------------------------------------------------------

_SPINNER_CHARS = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
_CLEAR_EOL = '\033[K'

_PROGRESS_MESSAGES = [
    '正在初始化 AI 引擎...',
    '正在搜索最新业绩指引和分析师共识...',
    '正在分析营收增长趋势和行业基准...',
    '正在评估 EBIT 利润率潜力和经营杠杆...',
    '正在评估资本效率和再投资需求...',
    '正在交叉对比多来源 WACC 估算...',
    '正在审查税务结构和有效税率...',
    '正在确定终值假设...',
    '正在将所有数据综合为估值参数...',
]

# Shared mutable state so _call_ai_cli can update engine label / reset
# timer on fallback while the progress thread is running.
_progress_state = {
    'engine_label': '',
    'start_time': 0.0,
    'active': False,   # True while a progress spinner is running
    'paused': False,    # True while a message is being printed over the spinner
}


def _print_progress_safe(msg):
    """Print a message without garbling the progress spinner.

    If the spinner is active, temporarily pause it, clear its line,
    print the message, then resume.
    """
    if _progress_state['active']:
        _progress_state['paused'] = True
        sys.stdout.write(f'\r{_CLEAR_EOL}')
        sys.stdout.flush()
        print(msg)
        _progress_state['paused'] = False
    else:
        print(msg)


def _progress_display(stop_event, failed):
    """Show a live spinner + elapsed time + rotating status message.

    Runs in a background daemon thread. Uses \\r to update in place.
    Reads engine_label and start_time from _progress_state so they
    can be updated on engine fallback.
    """
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return  # skip when output is piped

    idx = 0

    try:
        while not stop_event.is_set():
            if _progress_state['paused']:
                stop_event.wait(0.1)
                continue
            engine_label = _progress_state['engine_label']
            elapsed = time.monotonic() - _progress_state['start_time']
            msg_idx = min(int(elapsed / 12), len(_PROGRESS_MESSAGES) - 1)
            spinner = _SPINNER_CHARS[idx % len(_SPINNER_CHARS)]
            elapsed_str = f'{int(elapsed)}s'
            line = f'\r  {spinner} {_PROGRESS_MESSAGES[msg_idx]}  ({engine_label} · {elapsed_str}){_CLEAR_EOL}'
            sys.stdout.write(line)
            sys.stdout.flush()
            idx += 1
            stop_event.wait(0.1)

        # Clean up: clear line then print final message
        engine_label = _progress_state['engine_label']
        elapsed = time.monotonic() - _progress_state['start_time']
        elapsed_str = f'{int(elapsed)}s'
        sys.stdout.write(f'\r{_CLEAR_EOL}')
        sys.stdout.flush()
        if not failed[0]:
            print(f"  {S.success('✓')} {S.ai_label('AI 分析完成')}  {S.muted(f'({engine_label} · {elapsed_str})')}")
    except (IOError, OSError):
        pass  # stdout closed unexpectedly


@contextmanager
def _with_progress(engine_label):
    """Context manager that shows a live progress spinner during AI calls."""
    _progress_state['engine_label'] = engine_label
    _progress_state['start_time'] = time.monotonic()
    _progress_state['active'] = True
    _progress_state['paused'] = False

    stop_event = threading.Event()
    failed = [False]
    t = threading.Thread(target=_progress_display,
                         args=(stop_event, failed),
                         daemon=True)
    t.start()
    try:
        yield
    except Exception:
        failed[0] = True
        raise
    finally:
        stop_event.set()
        t.join(timeout=2.0)
        _progress_state['active'] = False


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


def _auth_error_hint(engine, raw_err):
    """Return a user-friendly fix hint for common authentication errors."""
    err_lower = raw_err.lower()
    if engine == 'qwen':
        if '401' in raw_err or 'token expired' in err_lower or 'access token' in err_lower:
            return "💡 修复: 终端运行 qwen 重新登录, 或设置环境变量 DASHSCOPE_API_KEY"
        if 'not found' in err_lower or 'not installed' in err_lower:
            return "💡 修复: npm install -g @qwen-code/qwen-code@latest"
    elif engine == 'claude':
        if 'not logged in' in err_lower or 'login' in err_lower:
            return "💡 修复: 终端运行 claude 并完成登录"
        if 'api error' in err_lower or 'rate limit' in err_lower:
            return "💡 提示: Claude API 限流或 token 过期, 稍后重试"
    elif engine == 'gemini':
        if 'ineligibletier' in err_lower:
            return "💡 已知问题: Google 账号资格验证 bug, 等待 Google 修复中"
        if 'consent' in err_lower or 'authentication' in err_lower:
            return "💡 修复: 终端运行 gemini 重新登录, 或设置环境变量 GEMINI_API_KEY"
    return ""


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
        cmd = ['qwen', '-p', prompt, '--output-format', 'json']
    else:
        _print_progress_safe(f"  {S.error(f'未知引擎: {engine}')}")
        return None

    _timeout = 600  # 10 minutes for search + analysis
    # Build a clean env without CLAUDE* markers to avoid
    # "nested session" error when launched from Claude Code.
    clean_env = {k: v for k, v in os.environ.items()
                 if not k.startswith('CLAUDE')}
    for _ek in ('PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'TERM',
                'FMP_API_KEY', 'GEMINI_API_KEY', 'OPENAI_API_KEY',
                'DASHSCOPE_API_KEY',
                # Windows-required env vars
                'SYSTEMROOT', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
                'APPDATA', 'LOCALAPPDATA', 'USERPROFILE', 'HOMEDRIVE',
                'HOMEPATH', 'SYSTEMDRIVE', 'WINDIR'):
        if _ek in os.environ:
            clean_env[_ek] = os.environ[_ek]
    # On Windows, npm global installs create .cmd wrappers (e.g. qwen.cmd).
    # subprocess.run() won't find .cmd files without shell=True,
    # so resolve the full path via shutil.which() first.
    _is_windows = sys.platform == 'win32'
    if _is_windows:
        resolved = shutil.which(cmd[0])
        if resolved:
            cmd[0] = resolved
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=_timeout, env=clean_env,
                                shell=_is_windows, encoding='utf-8',
                                errors='replace')
    except subprocess.TimeoutExpired:
        _print_progress_safe(f"  {S.warning(f'{engine_label} 调用超时 ({_timeout}s)')}")
        return None

    if result.returncode != 0:
        raw_err = result.stderr.strip() or result.stdout.strip() or "Unknown error"
        error_msg = _extract_error_message(raw_err)
        _print_progress_safe(f"  {S.warning(f'{engine_label} 调用失败: {error_msg}')}")
        # Show actionable fix hints for common auth errors
        _hints = _auth_error_hint(engine, raw_err)
        if _hints:
            _print_progress_safe(f"  {S.muted(_hints)}")
        return None

    raw = result.stdout.strip()
    if not raw:
        _print_progress_safe(f"  {S.warning(f'{engine_label} 返回空内容')}")
        return None

    # Claude CLI may return exit code 0 but with is_error:true in JSON
    # (e.g. rate limit hit). Detect this and treat as failure so fallback kicks in.
    if engine == 'claude':
        try:
            _parsed = json.loads(raw)
            if isinstance(_parsed, dict) and _parsed.get('is_error'):
                error_msg = _parsed.get('result', '') or 'Unknown error'
                _print_progress_safe(f"  {S.warning(f'{engine_label} 调用失败: {error_msg}')}")
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
            _print_progress_safe(f"  {S.info(f'自动切换到 {fallback_label} 继续分析...')}")
            if fallback == 'gemini':
                _ensure_gemini_preview()
            _AI_ENGINE = fallback
            _detected_model_name = None
            # Reset progress display for the new engine
            _progress_state['engine_label'] = _ENGINE_LABELS.get(fallback, fallback)
            _progress_state['start_time'] = time.monotonic()
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
        elif engine_used == 'qwen':
            data = json.loads(raw)
            text = data.get('result', raw)
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

**关于 EBIT（Operating Profit）的重要说明：**
上表中的 EBIT 是为 DCF 估值目的而调整后的经营利润，**不等同于 GAAP 标准的营业利润或 Operating Income**：
- **A 股**：EBIT = 营业利润 − 投资收益 − 公允价值变动收益 − 其他收益 − 资产处置收益 − 信用减值损失 − 资产减值损失 + 财务费用。即从营业利润中剔除了非经营性项目（投资收益、一次性损益等），加回了财务费用。
- **港股**：直接使用 Operating Income，部分公司可能仍包含未剔除的非经营性项目。
- **美股及其他**：使用数据源（FMP）提供的调整后 Operating Income，已剔除非经常性项目。
因此，设定目标 EBIT Margin 时，**必须以上表中的历史 EBIT Margin 作为首要参考基准**，而不是外部搜索到的 GAAP operating margin（口径不同，直接对比会产生误导）。

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
    "reasoning": "<详细中文分析：**首要参考上方历史数据表中的 EBIT Margin 趋势和水平**（注意：该 EBIT 是为估值目的调整后的经营利润，口径与 GAAP 标准不同，不要直接与外部搜索到的 GAAP operating margin 对比）。在此基础上，结合行业长期趋势、公司运营杠杆、规模效应等因素，判断公司成熟期能达到的目标 EBIT margin。>"
  }},
  "convergence": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：为什么选择这个收敛年数，从当前margin到目标margin需要多久>"
  }},
  "revenue_invested_capital_ratio_1": {{
    "value": <数值，如果建议设为0则填0>,
    "reasoning": "<详细中文分析：**分析步骤（必须严格按顺序执行）：**\n1. **首先**检查历史 Revenue / IC 比率（在 Key Ratios 部分）是否各年稳定（波动幅度在±20%以内）。如果稳定，则**优先使用历史平均值**作为基准，并根据未来收入增速预测适当调整（增速加快→比率可略高，增速放缓→比率可略低）。\n2. **其次**，如果 Revenue / IC 波动较大或不适用，则检查历史 Total Reinvestments 数据：如果持续为负数（公司在回收资本），说明是轻资产公司，应设为0；如果为正，则反算合理比率（= 收入增量 / Total Reinvestments），并验证推算出的预期净资本开支与历史水平是否匹配。\n请明确说明采用了哪种方法及原因。\n3. **必须给出再投资金额校验**：根据建议的比率和前面的收入增长率假设，计算 Year 1-2 预期再投资金额（= ΔRevenue × EBIT Margin / Revenue/IC），与最近一年的 Total Reinvestment 对比，说明是否合理。例如：'建议设为3.0，对应 Year 1 预期再投资约 $X B，高于/低于最近一年的 $Y B，符合/需要关注增长趋势。'>"
  }},
  "revenue_invested_capital_ratio_2": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：Year 3-5阶段的比率依据。同样优先参考历史 Revenue / IC 稳定性，其次对照历史 reinvestment 水平校验。**必须给出再投资金额校验**：根据建议的比率和 Year 3-5 的收入增长率假设，估算该阶段年均预期再投资金额，与最近一年的 Total Reinvestment 对比，说明是否合理。>"
  }},
  "revenue_invested_capital_ratio_3": {{
    "value": <数值>,
    "reasoning": "<详细中文分析：Year 5-10阶段的比率依据。考虑成熟期资本效率变化，参考历史 Revenue / IC 趋势和 reinvestment 水平。**必须给出再投资金额校验**：根据建议的比率和 Year 5-10 的收入增长率假设，估算该阶段年均预期再投资金额，与最近一年的 Total Reinvestment 对比，说明是否与公司规模扩大后的资本需求相匹配。>"
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


ANALYSIS_PROMPT_TEMPLATE_EN = """You are a senior equity research analyst and DCF valuation expert. Based on the following historical financial data and publicly available market information, generate DCF valuation parameter recommendations for {company_name} ({ticker}).

**Note: The most recent year in the historical data below (leftmost column) is {base_year}{ttm_context}. Please base your analysis on the latest {base_year} data. {forecast_year_guidance}**

**Important: You MUST use WebSearch to search for the following information before starting your analysis:**
1. Search "{ticker} earnings guidance revenue outlook {search_year}" — find management earnings guidance (highest priority)
2. Search "{ticker} revenue forecast {search_year} {search_year_2} analyst consensus" — find analyst consensus estimates
3. Search "{ticker} EBIT margin operating margin industry average" — find industry benchmarks
4. Search "{ticker} WACC cost of capital" — find WACC data from multiple sources

## Company Information
- Company Name: {company_name}
- Ticker: {ticker}
- Country: {country}
- Beta: {beta}
- Market Cap: {market_cap}
- Valuation Base Year: {base_year}{ttm_base_label}

## Pre-calculated Parameters (for reference)
- Model-calculated WACC: {calculated_wacc}
- Historical average effective tax rate: {calculated_tax_rate}

## Historical Financial Data (in millions, leftmost column is most recent year {base_year})
{financial_table}

**Important note about EBIT (Operating Profit):**
The EBIT figures in the table above are adjusted operating profit for DCF valuation purposes and **may differ from standard GAAP Operating Income**:
- **China A-shares**: EBIT = Operating Profit − Investment Income − Fair Value Changes − Other Income − Asset Disposal Gains − Credit Impairment Losses − Asset Impairment Losses + Interest Expense. Non-operating items (investment income, one-time gains/losses, etc.) have been stripped out, and interest expense has been added back.
- **HK stocks**: Uses GAAP Operating Income directly; some companies may still include non-operating items.
- **US stocks and others**: Uses adjusted Operating Income from the data provider (FMP), with non-recurring items already excluded.
Therefore, when setting the target EBIT Margin, you **must use the historical EBIT Margin shown in the table above as the primary benchmark**, rather than externally searched GAAP operating margins (which use a different definition and direct comparison would be misleading).

---

Please conduct **independent, in-depth** analysis for each parameter below. Each analysis must include:
- Your reasoning logic and analytical process
- Cited data sources (e.g., analyst estimates, industry data found via search)
- Final recommended value with justification

**Output format: Must output a strict JSON code block with value and reasoning fields for each parameter. The reasoning field must contain detailed English analysis (at least 2-3 sentences) with supporting data and reasoning process.**

```json
{{
  "revenue_growth_1": {{
    "value": <number, e.g. 5 means 5%>,
    "reasoning": "<Detailed analysis: **Prioritize finding management's latest earnings guidance.** If explicit revenue guidance exists, use it as the primary reference; otherwise, focus on analyst consensus estimates. Cite data sources.>"
  }},
  "revenue_growth_2": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: Reasoning for 2-5 year CAGR, considering industry ceiling, competitive landscape, company moat, etc.>"
  }},
  "ebit_margin": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: **Primarily reference the historical EBIT Margin trends and levels shown in the data table above** (note: this EBIT is adjusted for valuation purposes and differs from standard GAAP — do not directly compare with externally searched GAAP operating margins). Based on this, consider long-term industry trends, operating leverage, scale effects, etc. to determine the target EBIT margin the company can achieve at maturity.>"
  }},
  "convergence": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: Why this convergence period — how long to move from current margin to target margin.>"
  }},
  "revenue_invested_capital_ratio_1": {{
    "value": <number, use 0 if recommending zero>,
    "reasoning": "<Detailed analysis: **Analysis steps (must follow in order):**\n1. **First**, check if historical Revenue / IC ratios (in Key Ratios section) are stable across years (fluctuation within ±20%). If stable, **prioritize using the historical average** as baseline, with adjustments based on projected revenue growth (faster growth → slightly higher ratio, slower growth → slightly lower).\n2. **Second**, if Revenue / IC is volatile or not applicable, check historical Total Reinvestments: if consistently negative (company is returning capital), it's asset-light — set to 0; if positive, back-calculate a reasonable ratio (= revenue increment / Total Reinvestments) and verify that implied capex aligns with historical levels.\nClearly state which method you used and why.\n3. **Must include reinvestment sanity check**: Using the recommended ratio and the revenue growth rates assumed above, calculate the implied Year 1-2 reinvestment amount (= ΔRevenue × EBIT Margin / Revenue/IC) and compare it against the most recent year's Total Reinvestment. State whether the level is reasonable. Example: 'Recommend 3.0, consistent with recent 2-year levels. Implied Year 1 reinvestment ≈ $X B, above the most recent $Y B but consistent with accelerating growth.'>"
  }},
  "revenue_invested_capital_ratio_2": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: Basis for Year 3-5 ratio. Similarly prioritize historical Revenue / IC stability, then cross-check against historical reinvestment levels. **Must include reinvestment sanity check**: Using the recommended ratio and Year 3-5 revenue growth assumptions, estimate average annual reinvestment for this period and compare against the most recent year's Total Reinvestment. State whether the level is reasonable.>"
  }},
  "revenue_invested_capital_ratio_3": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: Basis for Year 5-10 ratio. Consider mature-stage capital efficiency changes, historical Revenue / IC trends and reinvestment levels. **Must include reinvestment sanity check**: Using the recommended ratio and Year 5-10 revenue growth assumptions, estimate average annual reinvestment for this period and compare against the most recent year's Total Reinvestment. State whether the implied capital needs are consistent with the company's expanding scale.>"
  }},
  "tax_rate": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: Tax rate recommendation basis, referencing historical effective rates, statutory rates, tax incentives, etc.>"
  }},
  "wacc": {{
    "value": <number>,
    "reasoning": "<Detailed analysis: WACC recommendation basis, synthesizing model-calculated value and third-party data sources.>"
  }},
  "ronic_match_wacc": {{
    "value": <true or false>,
    "reasoning": "<Detailed analysis: Whether ROIC should converge to WACC in terminal period, considering durability of competitive advantages.>"
  }}
}}
```

**Note: JSON must be valid format, all strings in double quotes, no comments. Cite data sources in reasoning where applicable.**"""


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

    with _with_progress(engine_name):
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
            _format_ai_text(reasoning)

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
        _format_ai_text(ronic_reasoning)

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

**请使用 WebSearch 搜索以下信息来辅助分析（当前日期：{current_date}）：**

**重要：必须搜索最近 3-6 个月的最新信息。忽略超过 1 年的旧新闻，搜索时优先使用 {current_year} 年的关键词。**

建议搜索（可根据需要追加更多搜索）：
1. "{company_name} {forecast_year} 分析师目标价" 或 "{ticker} analyst price target {forecast_year}" — 获取分析师目标价
2. "{company_name} {current_year} 最新消息" 或 "{ticker} latest news {current_year}" — 获取最近的重大新闻和事件
3. "{company_name} {current_year} 风险 挑战" 或 "{ticker} risks headwinds {current_year}" — 获取当前面临的风险和挑战
4. "{company_name} {current_year} 增长 前景" 或 "{ticker} growth catalysts outlook {current_year}" — 获取增长驱动因素和前景

如果公司属于特定行业（如科技、消费、金融、医药等），请额外搜索该行业最新的趋势和政策变化，例如 "{company_name} 行业 竞争格局 {current_year}"。

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
- 修正的目的是：通过搜索发现**之前设定 DCF 参数时可能未考虑到的新信息**，据此判断是否需要调整
- **"新信息"的严格定义——必须同时满足以下条件：**
  1. **时效性**：必须是最近 6 个月内发生的事件或趋势变化。超过 6 个月的旧新闻，市场早已消化定价，不构成增量信息
  2. **增量性**：该信息尚未反映在当前股价或 DCF 参数中。如果事件发生后股价已充分调整，说明市场已定价，不应重复计入
  3. **实质性**：对公司未来现金流有可量化的实质影响，而非仅停留在情绪或叙事层面
  - 反面示例：某公司一年前被列入某政府清单 → 已是旧闻，股价早已反映，**不属于新信息，不应据此调整估值**
  - 正面示例：本月刚发布的新监管政策、最近一个季度的业绩大幅偏离预期、近期突发的重大诉讼等
- 修正后估值必须与你的分析逻辑**自洽**：
  - 如果搜索发现了**符合上述定义的真正新信息且为负面**，则应向下修正
  - 如果搜索未发现符合上述定义的重大新信息，说明 DCF 估值参数已合理反映公司基本面，**不需要调整**——DCF 高于股价可能意味着市场定价偏低或受短期情绪影响，这恰恰是价值投资的买入机会
  - **绝对禁止**：分析中列出负面因素后反而把估值调得比 DCF 更高
- 不要仅仅因为 DCF 估值与市场价有差异就自动向市场价靠拢。市场价格可能是错误的

请在分析最后一行，严格按以下格式输出（仅数字，不含货币符号）：
   ADJUSTED_PRICE: <数值>

请直接输出分析内容，不需要 JSON 格式（仅最后一行的 ADJUSTED_PRICE 需要严格格式）。"""


GAP_ANALYSIS_PROMPT_TEMPLATE_EN = """You are a senior equity research analyst. Analyze the gap between the following DCF valuation result and the current market stock price, and provide possible explanations for the discrepancy.

## Company Information
- Company Name: {company_name}
- Ticker: {ticker}
- Country: {country}
- Current Stock Price: {current_price} {currency}
- DCF Valuation Per Share: {dcf_price:.2f} {currency}
- Gap: {gap_pct:+.1f}% ({gap_direction})

## Key DCF Assumptions
- Year 1 Revenue Growth: {revenue_growth_1}%
- Years 2-5 CAGR: {revenue_growth_2}%
- Target EBIT Margin: {ebit_margin}%
- WACC: {wacc}%
- Tax Rate: {tax_rate}%

## Valuation Summary (in millions)
- PV of Next 10 Years Cash Flows: {pv_cf:,.0f}
- PV of Terminal Value: {pv_terminal:,.0f}
- Enterprise Value: {enterprise_value:,.0f}
- Equity Value: {equity_value:,.0f}

## Historical Financial Data (in millions)
{financial_table}

---

**Please use WebSearch to search for the following information (Current date: {current_date}):**

**Important: Focus on the most recent 3-6 months of information. Ignore news older than 1 year. Prefer search keywords with {current_year}.**

Suggested searches (add more as needed):
1. "{company_name} analyst price target {forecast_year}" or "{ticker} price target {forecast_year}" — find analyst price targets
2. "{company_name} latest news {current_year}" or "{ticker} recent developments {current_year}" — find recent major news and events
3. "{company_name} risks challenges {current_year}" or "{ticker} risks headwinds {current_year}" — find current risks and challenges
4. "{company_name} growth catalysts outlook {current_year}" — find growth drivers and outlook

If the company belongs to a specific sector (e.g., technology, consumer, finance, healthcare), please also search for the latest trends and policy changes in that sector, e.g. "{company_name} industry competition {current_year}".

Please conduct your analysis in **English**, covering the following:

1. **Valuation Gap Summary**: Briefly describe the magnitude and direction of the gap between DCF valuation and market price
2. **DCF Key Assumptions vs Market/Analyst Expectations** (present in table format):
   Compare each DCF assumption against searched data, noting data sources and applicable time periods.
   **Strictly distinguish short-term vs long-term data applicability:**
   - Analyst forecasts for a specific year's revenue/EPS → only supports the corresponding year's assumption (usually Year 1)
   - Historical growth rates → reference only, cannot be directly extrapolated as future 5-year CAGR
   - Years 2-5 CAGR assessment should be based on: long-term industry growth potential, competitive moats, Total Addressable Market (TAM) ceiling, sustainability analysis of historical growth
   - Do not use 1-2 year analyst estimates as basis for 5-year CAGR
3. **Possible Overvaluation/Undervaluation Reasons** (list at least 3-5 factors):
   - Market sentiment / macro factors
   - Industry trends / competitive landscape changes
   - Company-specific risks or catalysts
   - Areas where DCF model assumptions may be too conservative/aggressive
4. **Analyst Consensus Comparison**: Compare DCF results with analyst price targets found via search
5. **Recommendations**: Based on the above analysis, provide a confidence assessment of the valuation result and key risks to monitor
6. **Adjusted Valuation**: Considering all the above factors, provide what you believe is a more reasonable intrinsic value per share.

**Key Principles for Adjusted Valuation (must strictly follow):**
- The purpose of adjustment is: to incorporate **new information discovered through search that may not have been considered when setting DCF parameters**, and decide whether adjustments are needed
- **Strict definition of "new information" — ALL of the following conditions must be met:**
  1. **Recency**: Must be an event or trend change from the last 6 months. News older than 6 months has already been digested and priced in by the market, and does NOT constitute incremental information
  2. **Incrementality**: The information is not yet reflected in the current stock price or DCF parameters. If the stock price has already fully adjusted after the event, the market has priced it in — do NOT double-count it
  3. **Materiality**: Must have a quantifiable, substantive impact on the company's future cash flows, not just narrative or sentiment-level concerns
  - Counter-example: A company was added to a government list over a year ago → this is old news, the stock price has long reflected it, **this is NOT new information and should NOT be used to adjust valuation**
  - Valid example: A new regulatory policy announced this month, a major earnings miss in the most recent quarter, a significant lawsuit filed recently, etc.
- The adjusted valuation must be **logically consistent** with your analysis:
  - If search reveals **genuinely new negative information meeting the above criteria**, adjust downward
  - If search reveals no major new information meeting the above criteria, the DCF parameters reasonably reflect company fundamentals and **no adjustment is needed** — DCF above stock price may indicate market mispricing or short-term sentiment, which is precisely a value investing buy opportunity
  - **Absolutely forbidden**: listing negative factors in analysis but then adjusting valuation higher than DCF
- Do not automatically gravitate toward market price just because DCF valuation differs from it. Market prices can be wrong

On the very last line of your analysis, output strictly in this format (number only, no currency symbol):
   ADJUSTED_PRICE: <number>

Output analysis content directly, no JSON format needed (only the final ADJUSTED_PRICE line requires strict format)."""


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

    today = date.today()
    current_date_str = today.strftime('%Y-%m-%d')
    current_year = today.year

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
        current_date=current_date_str,
        current_year=current_year,
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

        with _with_progress(engine_name):
            analysis_text = _call_ai_cli(prompt)

        # Parse adjusted price from the last line
        adjusted_price = None
        price_match = re.search(r'ADJUSTED_PRICE:\s*([\d.,]+)', analysis_text)
        if price_match:
            try:
                adjusted_price = float(price_match.group(1).replace(',', ''))
            except ValueError:
                pass

        # Compute adjusted price in reporting currency (reverse forex conversion)
        adjusted_price_reporting = None
        if adjusted_price is not None and currency_converted and forex_rate and forex_rate > 0:
            adjusted_price_reporting = adjusted_price / forex_rate

        # Display analysis (strip the ADJUSTED_PRICE line from display)
        display_text = re.sub(r'\n?\s*ADJUSTED_PRICE:.*$', '', analysis_text).strip()
        print(f"\n{S.divider()}")
        _format_ai_text(display_text, indent='  ')
        print(S.divider())

        if adjusted_price is not None:
            adj_gap_pct = (adjusted_price - current_price) / current_price * 100
            print(f"\n  {S.label('综合差异分析后修正估值:')} {S.price_colored(adjusted_price, current_price)} {stock_currency}（相对当前股价 {S.pct_colored(adj_gap_pct)}）")
            if adjusted_price_reporting is not None:
                print(f"  {S.label('修正估值（列报币种）:')} {adjusted_price_reporting:,.2f} {reported_currency}  {S.muted(f'(÷ {forex_rate:.4f})')}")

        return {
            'analysis_text': analysis_text,
            'adjusted_price': adjusted_price,
            'adjusted_price_reporting': adjusted_price_reporting,
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


def _display_width(s):
    """Return the visual display width of *s* in a terminal.

    CJK / full-width characters count as 2 columns; all others as 1.
    ANSI escape sequences are excluded from the count.
    """
    # Strip ANSI escape codes before measuring
    plain = re.sub(r'\033\[[0-9;]*m', '', s)
    w = 0
    for ch in plain:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ('F', 'W') else 1
    return w


def _wrap_line(text, width, indent=''):
    """Wrap a single line of text to *width* display columns.

    Handles mixed CJK / Latin text correctly.  Returns a list of
    indented output lines (strings).
    """
    if not text:
        return [indent]

    indent_w = _display_width(indent)
    avail = width - indent_w
    if avail < 20:
        avail = 20  # safety floor

    result = []
    buf = ''
    buf_w = 0

    for ch in text:
        ch_w = 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
        if buf_w + ch_w > avail:
            result.append(f'{indent}{buf}')
            buf = ''
            buf_w = 0
            if ch == ' ':
                continue  # skip leading space on new line
        buf += ch
        buf_w += ch_w

    if buf:
        result.append(f'{indent}{buf}')

    return result or [indent]


def _render_bold(text):
    """Convert markdown **bold** to ANSI bold."""
    if not S._COLOR:
        return text.replace('**', '')
    return re.sub(r'\*\*(.+?)\*\*', f'{S.BOLD}\\1{S.RESET}', text)


def _render_table(table_lines, indent='    '):
    """Render markdown table lines as a box-drawn terminal table.

    Parses ``| col | col |`` rows, computes column widths using
    display-width-aware measurement, wraps long cell content, and
    outputs with box-drawing characters (─ │ ┌ ┐ └ ┘ ├ ┤ ┬ ┴ ┼).
    """
    # Parse rows into cells, skipping separator lines (|---|---|)
    rows = []
    for line in table_lines:
        stripped = line.strip().strip('|')
        if re.match(r'^[\s:|-]+$', stripped):
            continue  # skip separator rows like |---|---|
        # Strip **bold** markers — bold is handled via header styling
        cells = [c.strip().replace('**', '') for c in stripped.split('|')]
        rows.append(cells)

    if not rows:
        return

    # Normalise column count
    n_cols = max(len(r) for r in rows)
    for r in rows:
        while len(r) < n_cols:
            r.append('')

    # Compute natural column widths
    nat_widths = [0] * n_cols
    for r in rows:
        for i, cell in enumerate(r):
            w = _display_width(cell)
            if w > nat_widths[i]:
                nat_widths[i] = w

    # Fit table to terminal width — shrink columns if needed
    term_w = shutil.get_terminal_size((80, 24)).columns
    indent_w = _display_width(indent)
    # border overhead: indent + outer │ + per-column " cell │"
    border_overhead = indent_w + 1 + n_cols * 3
    avail = term_w - border_overhead
    total_nat = sum(nat_widths)

    if total_nat <= avail:
        col_widths = nat_widths
    else:
        # Smart shrink: keep narrow columns at natural width,
        # only shrink columns wider than the fair share.
        col_widths = list(nat_widths)
        fair_share = avail // n_cols
        locked = 0       # total width of narrow columns (not shrunk)
        shrinkable = 0   # total natural width of wide columns
        for i, w in enumerate(nat_widths):
            if w <= fair_share:
                locked += w
            else:
                shrinkable += w
        remaining = avail - locked
        if remaining > 0 and shrinkable > 0:
            for i, w in enumerate(nat_widths):
                if w <= fair_share:
                    col_widths[i] = w  # keep natural
                else:
                    col_widths[i] = max(6, int(w / shrinkable * remaining))

    # ── helpers ──

    def _wrap_cell(text, max_w):
        """Wrap cell text to fit within *max_w* display columns."""
        if _display_width(text) <= max_w:
            return [text]
        lines = []
        buf = ''
        buf_w = 0
        for ch in text:
            ch_w = 2 if unicodedata.east_asian_width(ch) in ('F', 'W') else 1
            if buf_w + ch_w > max_w:
                lines.append(buf)
                buf = ''
                buf_w = 0
                if ch == ' ':
                    continue  # skip leading space on new line
            buf += ch
            buf_w += ch_w
        if buf:
            lines.append(buf)
        return lines or ['']

    def _pad(text, target_w):
        """Pad *text* to *target_w* display columns with trailing spaces."""
        return text + ' ' * max(0, target_w - _display_width(text))

    def _hline(left, mid, right):
        segs = ['─' * (w + 2) for w in col_widths]
        return f'{indent}{left}{mid.join(segs)}{right}'

    # ── render ──

    print(_hline('┌', '┬', '┐'))

    for row_idx, cells in enumerate(rows):
        # Wrap each cell to its column width
        wrapped = [_wrap_cell(cells[i], col_widths[i]) for i in range(n_cols)]
        max_lines = max(len(w) for w in wrapped)

        for line_idx in range(max_lines):
            parts = []
            for i in range(n_cols):
                cell_line = wrapped[i][line_idx] if line_idx < len(wrapped[i]) else ''
                padded = _pad(cell_line, col_widths[i])
                # Bold styling for header row
                if row_idx == 0 and S._COLOR:
                    padded = f'{S.BOLD}{padded}{S.RESET}'
                parts.append(f' {padded} ')
            print(f'{indent}│{"│".join(parts)}│')

        # After header row, print a separator
        if row_idx == 0:
            print(_hline('├', '┼', '┤'))

    # Print bottom border
    print(_hline('└', '┴', '┘'))


def _format_ai_text(text, indent='    ', width=None):
    """Pretty-print AI-generated markdown text to the terminal.

    Handles:
      - ``## headers``  → coloured with S.ai_label()
      - ``**bold**``    → ANSI bold
      - numbered / bullet lists → preserved with hanging indent
      - ``| tables |``  → box-drawn tables with aligned columns
      - long paragraphs → auto-wrapped at terminal width
      - blank lines     → kept as paragraph separators
    """
    if width is None:
        width = shutil.get_terminal_size((80, 24)).columns - 2  # small margin
    if width < 40:
        width = 40

    lines = text.split('\n')
    prev_blank = False
    table_buf = []  # accumulate consecutive table rows

    def _flush_table():
        """Render accumulated table rows and clear the buffer."""
        if table_buf:
            _render_table(table_buf, indent=indent)
            table_buf.clear()

    for raw_line in lines:
        line = raw_line.rstrip()

        # --- blank line → paragraph break (max one) ---
        if not line.strip():
            _flush_table()
            if not prev_blank:
                print()
                prev_blank = True
            continue
        prev_blank = False

        # --- table row (starts with |) → collect into buffer ---
        if line.lstrip().startswith('|'):
            table_buf.append(line)
            continue

        # Flush any pending table before processing other line types
        _flush_table()

        # --- markdown header ---
        hdr_match = re.match(r'^(#{1,4})\s+(.*)', line)
        if hdr_match:
            title = hdr_match.group(2).strip()
            title = title.replace('**', '')  # strip bold markers in headers
            print(f"\n{indent}{S.ai_label(title)}")
            continue

        # --- divider line (--- or ===) ---
        if re.match(r'^[-=]{3,}\s*$', line.strip()):
            continue  # skip markdown horizontal rules

        # --- numbered list item (e.g. "1. xxx", "  2. xxx") ---
        num_match = re.match(r'^(\s*)(\d+\.\s+)(.*)', line)
        if num_match:
            pre_indent = num_match.group(1)
            marker = num_match.group(2)
            content = _render_bold(num_match.group(3))
            first_indent = f'{indent}{pre_indent}{marker}'
            cont_indent = f'{indent}{pre_indent}{" " * len(marker)}'
            wrapped = _wrap_line(content, width, cont_indent)
            if wrapped:
                wrapped[0] = first_indent + wrapped[0][len(cont_indent):]
            for wl in wrapped:
                print(wl)
            continue

        # --- bullet list item (- or *) ---
        bullet_match = re.match(r'^(\s*)([-*]\s+)(.*)', line)
        if bullet_match:
            pre_indent = bullet_match.group(1)
            marker = bullet_match.group(2)
            content = _render_bold(bullet_match.group(3))
            first_indent = f'{indent}{pre_indent}{marker}'
            cont_indent = f'{indent}{pre_indent}{" " * len(marker)}'
            wrapped = _wrap_line(content, width, cont_indent)
            if wrapped:
                wrapped[0] = first_indent + wrapped[0][len(cont_indent):]
            for wl in wrapped:
                print(wl)
            continue

        # --- regular paragraph line ---
        content = _render_bold(line.strip())
        for wl in _wrap_line(content, width, indent):
            print(wl)

    # Flush any trailing table at end of text
    _flush_table()


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


# ---------------------------------------------------------------------------
# Cloud AI: Serper.dev (Google search) + DeepSeek API (reasoning)
# Used on Streamlit Cloud where no CLI is installed.
# ---------------------------------------------------------------------------

import requests as _requests


def _serper_search(query, api_key, num_results=5):
    """Run a Google search via Serper.dev API. Returns list of {title, snippet, link}."""
    resp = _requests.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": num_results},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    # Include answer box if present
    if "answerBox" in data:
        ab = data["answerBox"]
        snippet = ab.get("answer", ab.get("snippet", ""))
        if snippet:
            results.append({"title": ab.get("title", "Answer Box"), "snippet": snippet, "link": ""})
    for item in data.get("organic", []):
        results.append({
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "link": item.get("link", ""),
        })
    return results[:num_results]


def _serper_scrape(url, api_key, max_chars=6000):
    """Scrape a webpage via Serper.dev Scrape API. Returns markdown/text content.

    Args:
        url: URL to scrape
        api_key: Serper.dev API key
        max_chars: Maximum characters to return (to keep prompt size reasonable)

    Returns:
        str: Scraped page content (markdown), or empty string on failure
    """
    try:
        resp = _requests.post(
            "https://scrape.serper.dev",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"url": url, "includeMarkdown": True},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        # Prefer markdown content, fall back to text
        content = data.get("markdown", data.get("text", ""))
        if content and len(content) > max_chars:
            content = content[:max_chars] + "\n...(truncated)"
        return content
    except Exception:
        return ""


def _deepseek_chat(prompt, api_key, model="deepseek-reasoner"):
    """Call DeepSeek API (OpenAI-compatible) and return response text.

    Supports both deepseek-chat and deepseek-reasoner models.
    For deepseek-reasoner: temperature/top_p are ignored (no error), response
    includes reasoning_content field alongside content.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 16384,
    }
    # Only set temperature for non-reasoner models (reasoner ignores it)
    if model != "deepseek-reasoner":
        payload["temperature"] = 0.3

    resp = _requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,  # reasoner needs more time for CoT
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _format_search_results(queries, all_results, scraped_pages=None):
    """Format search results into a readable text block for prompt injection.

    Args:
        queries: list of search query strings
        all_results: dict mapping query index -> list of search result dicts
        scraped_pages: optional dict mapping URL -> scraped content string
    """
    sections = []
    for i, query in enumerate(queries):
        results = all_results.get(i, [])
        lines = [f"### Search {i+1}: {query}"]
        if not results:
            lines.append("（No results found）")
        else:
            for r in results:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                link = r.get("link", "")
                lines.append(f"- **{title}**")
                if snippet:
                    lines.append(f"  {snippet}")
                if link:
                    lines.append(f"  Source: {link}")
                # Append full page content if scraped
                if scraped_pages and link and link in scraped_pages:
                    page_content = scraped_pages[link]
                    if page_content:
                        lines.append(f"\n  <page_content source=\"{link}\">\n{page_content}\n  </page_content>")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def _build_cloud_analysis_prompt(template_args, search_context, lang='zh'):
    """Build analysis prompt with search results injected (no WebSearch tool needed).

    Uses the same ANALYSIS_PROMPT_TEMPLATE but replaces the WebSearch instructions
    with pre-fetched search results.
    """
    _template = ANALYSIS_PROMPT_TEMPLATE if lang == 'zh' else ANALYSIS_PROMPT_TEMPLATE_EN
    prompt = _template.format(**template_args)

    # Replace the WebSearch instructions block with search results
    if lang == 'zh':
        search_instruction_marker = "**重要：请务必先使用 WebSearch 工具搜索以下信息再开始分析：**"
        replacement_header = "**以下是通过 Google 搜索获取的最新市场数据，请基于这些数据进行分析（你没有 WebSearch 工具，请直接使用下面的搜索结果）：**"
    else:
        search_instruction_marker = "**Important: You MUST use WebSearch to search for the following information before starting your analysis:**"
        replacement_header = "**The following market data has been retrieved via Google Search. Analyze based on these results (you do NOT have WebSearch — use the search results below directly):**"

    # Find and replace the search instructions block
    marker_pos = prompt.find(search_instruction_marker)
    if marker_pos >= 0:
        # Find the end of the search instructions (before the next ## section)
        next_section = prompt.find("\n## ", marker_pos + len(search_instruction_marker))
        if next_section < 0:
            # Try finding the --- separator
            next_section = prompt.find("\n---", marker_pos + len(search_instruction_marker))
        if next_section >= 0:
            prompt = (
                prompt[:marker_pos]
                + replacement_header + "\n\n"
                + search_context + "\n\n"
                + prompt[next_section:]
            )

    return prompt


def _build_cloud_gap_prompt(template_args, search_context, lang='zh'):
    """Build gap analysis prompt with search results injected."""
    _template = GAP_ANALYSIS_PROMPT_TEMPLATE if lang == 'zh' else GAP_ANALYSIS_PROMPT_TEMPLATE_EN
    prompt = _template.format(**template_args)

    # Replace the WebSearch instructions block with search results
    if lang == 'zh':
        search_instruction_marker = "**请使用 WebSearch 搜索以下信息来辅助分析"
    else:
        search_instruction_marker = "**Please use WebSearch to search for the following information"

    marker_pos = prompt.find(search_instruction_marker)
    if marker_pos >= 0:
        # Find the end of the search instructions block (before the analysis instructions)
        if lang == 'zh':
            next_section_marker = "\n请用**中文**进行分析"
        else:
            next_section_marker = "\nPlease conduct your analysis in **English**"
        next_section = prompt.find(next_section_marker, marker_pos)
        if next_section >= 0:
            if lang == 'zh':
                replacement = (
                    "**以下是通过 Google 搜索获取的最新市场数据，请基于这些数据进行分析"
                    "（你没有 WebSearch 工具，请直接使用下面的搜索结果）：**\n\n"
                    + search_context + "\n"
                )
            else:
                replacement = (
                    "**The following market data has been retrieved via Google Search. "
                    "Analyze based on these results (you do NOT have WebSearch):**\n\n"
                    + search_context + "\n"
                )
            prompt = prompt[:marker_pos] + replacement + prompt[next_section:]

    return prompt


def _collect_top_links(all_results, max_links=3):
    """Collect unique top links from search results for scraping."""
    seen = set()
    links = []
    for i in sorted(all_results.keys()):
        for r in all_results[i]:
            link = r.get("link", "")
            if link and link not in seen and not link.endswith(".pdf"):
                seen.add(link)
                links.append(link)
                if len(links) >= max_links:
                    return links
    return links


def _call_deepseek_with_live_progress(prompt, api_key, model, progress_callback):
    """Call DeepSeek in a background thread, firing progress_callback every 3s.

    This prevents the UI timer from freezing during long blocking API calls
    (DeepSeek R1 can take 60-180s for chain-of-thought reasoning).
    """
    import threading as _threading

    if progress_callback:
        progress_callback('generating', None)

    _result = [None]
    _error = [None]

    def _api_call():
        try:
            _result[0] = _deepseek_chat(prompt, api_key, model=model)
        except Exception as e:
            _error[0] = e

    _t = _threading.Thread(target=_api_call, daemon=True)
    _t.start()

    # Poll every 3s, re-firing callback so the UI elapsed timer stays alive
    while _t.is_alive():
        _t.join(timeout=3)
        if _t.is_alive() and progress_callback:
            progress_callback('generating', None)

    if _error[0]:
        raise _error[0]
    return _result[0]


def cloud_ai_analyze(template_args, serper_key, deepseek_key, lang='zh',
                     progress_callback=None):
    """Cloud AI analysis: run Serper searches, scrape top pages, call DeepSeek Reasoner.

    Args:
        template_args: dict of format parameters for ANALYSIS_PROMPT_TEMPLATE
        serper_key: Serper.dev API key
        deepseek_key: DeepSeek API key
        lang: 'zh' or 'en'
        progress_callback: optional callable(phase, message) for UI updates

    Returns:
        str: AI response text containing JSON parameters
    """
    ticker = template_args['ticker']
    company_name = template_args.get('company_name', ticker)
    search_year = template_args['search_year']
    search_year_2 = template_args['search_year_2']

    # Step 1: Run 6 Serper searches (expanded from 4)
    queries = [
        f"{ticker} earnings guidance revenue outlook {search_year}",
        f"{ticker} revenue forecast analyst consensus {search_year} {search_year_2}",
        f"{ticker} EBIT margin operating margin trend",
        f"{ticker} WACC cost of capital discount rate",
        f"{company_name} latest quarterly earnings results analysis",
        f"{company_name} industry competitive landscape growth drivers {search_year}",
    ]

    all_results = {}
    for i, query in enumerate(queries):
        if progress_callback:
            progress_callback('searching', query)
        try:
            all_results[i] = _serper_search(query, serper_key)
        except Exception as e:
            all_results[i] = [{"title": "Search Error", "snippet": str(e), "link": ""}]

    # Step 2: Scrape top 3 search result pages for full content
    scraped_pages = {}
    top_links = _collect_top_links(all_results, max_links=3)
    for link in top_links:
        if progress_callback:
            progress_callback('scraping', link)
        content = _serper_scrape(link, serper_key, max_chars=6000)
        if content:
            scraped_pages[link] = content

    search_context = _format_search_results(queries, all_results, scraped_pages)

    # Step 3: Build prompt with search results + scraped content
    if progress_callback:
        progress_callback('analyzing', None)
    prompt = _build_cloud_analysis_prompt(template_args, search_context, lang)

    # Step 4: Call DeepSeek Reasoner (R1 with chain-of-thought)
    # Run in background thread so progress_callback keeps firing → live timer
    text = _call_deepseek_with_live_progress(
        prompt, deepseek_key, "deepseek-reasoner", progress_callback)

    return text


def cloud_gap_analyze(template_args, serper_key, deepseek_key, lang='zh',
                      progress_callback=None):
    """Cloud AI gap analysis: run Serper searches, scrape pages, call DeepSeek Reasoner.

    Args:
        template_args: dict of format parameters for GAP_ANALYSIS_PROMPT_TEMPLATE
        serper_key: Serper.dev API key
        deepseek_key: DeepSeek API key
        lang: 'zh' or 'en'
        progress_callback: optional callable(phase, message)

    Returns:
        str: AI analysis text with ADJUSTED_PRICE line
    """
    ticker = template_args['ticker']
    company_name = template_args['company_name']
    forecast_year = template_args.get('forecast_year', '')
    current_year = template_args.get('current_year', '')

    # Gap analysis searches (expanded from 4 to 6)
    queries = [
        f"{ticker} analyst price target consensus {forecast_year}",
        f"{ticker} latest news earnings {current_year}",
        f"{ticker} risks headwinds challenges {current_year}",
        f"{company_name} growth catalysts outlook {current_year}",
        f"{ticker} valuation analysis fair value {current_year}",
        f"{ticker} competitive position market share {current_year}",
    ]

    all_results = {}
    for i, query in enumerate(queries):
        if progress_callback:
            progress_callback('searching', query)
        try:
            all_results[i] = _serper_search(query, serper_key)
        except Exception as e:
            all_results[i] = [{"title": "Search Error", "snippet": str(e), "link": ""}]

    # Scrape top 3 search result pages for full content
    scraped_pages = {}
    top_links = _collect_top_links(all_results, max_links=3)
    for link in top_links:
        if progress_callback:
            progress_callback('scraping', link)
        content = _serper_scrape(link, serper_key, max_chars=6000)
        if content:
            scraped_pages[link] = content

    search_context = _format_search_results(queries, all_results, scraped_pages)

    if progress_callback:
        progress_callback('analyzing', None)
    prompt = _build_cloud_gap_prompt(template_args, search_context, lang)

    text = _call_deepseek_with_live_progress(
        prompt, deepseek_key, "deepseek-reasoner", progress_callback)

    return text
