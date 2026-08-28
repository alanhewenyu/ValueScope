"""MCP server exposing ValueScope's deterministic valuation engine.

Mounted at /mcp on the main FastAPI app (streamable HTTP transport), so any
MCP client — Claude, ChatGPT, Cherry Studio, Dify, etc. — can call the same
DCF engine the website uses.

Single tool, two phases — mirrors the `vs --auto` CLI flow, except the
analyst role is played by the calling model itself (which, unlike an
MCP sampling request, can search the web for guidance/consensus):

1. run_dcf(ticker) with no assumptions → baseline valuation from 5Y
   historical averages + historical context + the analyst prompt that
   `vs --auto` uses, for the calling model to evaluate each parameter.
2. run_dcf(ticker, <adjusted assumptions>) → final deterministic valuation.

This server never calls an LLM itself.
"""

import contextvars
import io
import logging
import os
import threading
import time

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.transport_security import TransportSecuritySettings

from backend.routers.valuation import (
    DCFParams,
    HISTORICAL_DATA_PERIODS_ANNUAL,
    _ensure_profile_complete,
    _normalize_ticker,
    calculate_wacc,
    cached_get_profile,
    get_dcf_defaults as _get_dcf_defaults_endpoint,
    get_historical_financials,
    run_dcf as _run_dcf_endpoint,
    validate_ticker,
)
from modeling.ai_analyst import build_analysis_prompt
from backend import analytics, mcp_usage

logger = logging.getLogger(__name__)


def _track(event: str, ip: str, params: dict) -> None:
    """Report a tool call to GA and to the local usage log.

    Both are fire-and-forget and swallow their own errors — a tool call
    must never fail because a metric could not be written.
    """
    analytics.track(event, ip, params)
    mcp_usage.record(event, ip, params)


def _market(ticker: str) -> str:
    """Coarse market bucket for analytics."""
    t = ticker.upper()
    if t.endswith(".SS") or t.endswith(".SZ"):
        return "a"
    if t.endswith(".HK"):
        return "hk"
    if t.endswith(".T"):
        return "jp"
    if "." not in t:
        return "us"
    return "other"

# ── Per-request metadata (client IP + key header) ────────────────────────
# Captured by a pure-ASGI middleware in main.py; contextvars propagate into
# the tool call (FastMCP runs tools inside the request's task context).

_request_meta: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "vs_mcp_request_meta", default={}
)


class MCPRequestMetaMiddleware:
    """Stash client IP and X-FMP-Key header for /mcp requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            # Railway terminates TLS at the edge and forwards plain HTTP, so
            # the app's scheme is "http" and the trailing-slash redirect
            # (/mcp → /mcp/) would downgrade to http:// — which MCP clients
            # refuse to follow. Honor X-Forwarded-Proto so the redirect (and
            # any generated URL) stays https.
            if headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
                scope = dict(scope, scheme="https")
            fwd = headers.get("x-forwarded-for", "")
            client = scope.get("client") or ("", 0)
            ip = (fwd.split(",")[0].strip() if fwd else "") or client[0] or "unknown"
            token = _request_meta.set({"ip": ip, "fmp_key": headers.get("x-fmp-key", "").strip()})
            try:
                await self.app(scope, receive, send)
            finally:
                _request_meta.reset(token)
        else:
            await self.app(scope, receive, send)


# ── Quotas (in-memory, per IP, rolling 24h — same pattern as the AI quota) ──

MCP_DAILY_LIMIT = int(os.environ.get("MCP_DAILY_LIMIT", "60"))
US_TRIAL_DAILY_LIMIT = int(os.environ.get("MCP_US_TRIAL_DAILY_LIMIT", "3"))
# Global cap on trial calls served by the SERVER's FMP key across all IPs.
# The per-IP trial limit alone doesn't bound cost — a public endpoint can be
# hit from rotating IPs — so this is the hard ceiling on how much of the
# owner's FMP quota the free trial can burn per day.
MCP_US_TRIAL_GLOBAL_DAILY = int(os.environ.get("MCP_US_TRIAL_GLOBAL_DAILY", "200"))
_LOOPBACK_IPS = {"127.0.0.1", "::1", "localhost", "unknown", ""}
_GLOBAL_QUOTA_KEY = "__global__"

_quota_lock = threading.Lock()
_quota_usage: dict[str, list[float]] = {}


def _consume_quota(kind: str, ip: str, limit: int) -> int:
    """Consume one unit; return remaining. Raise ValueError when exhausted."""
    now = time.time()
    key = f"{kind}:{ip}"
    with _quota_lock:
        stamps = [t for t in _quota_usage.get(key, []) if t > now - 86400]
        if len(stamps) >= limit:
            _quota_usage[key] = stamps
            raise ValueError("quota_exhausted")
        stamps.append(now)
        _quota_usage[key] = stamps
        return limit - len(stamps)


DISCLAIMER = (
    "模型计算结果，仅供研究参考，不构成投资建议。"
    "Model output for research reference only; not investment advice."
)

# How the calling model should present final results to the user. Returned
# with every phase-2 response so output stays consistent across clients.
PRESENTATION_GUIDE = """向用户呈现估值结果时，请遵循以下结构（用 Markdown，不要直接倾倒原始 JSON）：
1. 结论卡：公司名（代码）｜每股内在价值 vs 当前市价｜上行/下行空间百分比｜一句话结论（|差异|>15% 才说"低估/高估"，否则说"接近合理区间"）。
2. 关键假设表：每个参数一行——你采用的值、5年历史均值（来自第一步的历史区间）、一句话依据（引用你搜索到的指引/预期时注明来源）。标注哪些参数沿用了历史默认值。
3. 价值构成（bridge）：PV(现金流) + PV(终值) + 现金及投资 − 债务及少数股东权益 → 每股价值，简短列出；提及终值占比（PV终值/企业价值），占比高说明估值主要押在远期。
4. 敏感性：从 sensitivity 表提取估值对增长率/利润率/WACC 的敏感区间，给出一个"合理价值区间"而非单点数字。
5. 反向 DCF：市价隐含的增长率/利润率 vs 你的假设，一句话点评市场定价了什么。
6. 结尾：附 web_page_url（如有）并注明它是交互式估值页可自行调参，最后附免责声明。
数字保留合理精度（价格两位小数、百分比一位）；若做了多情景，用一张情景对比表。
关键假设表建议带趋势列（parameter_history 里每个指标有现成的 sparkline 字段），例如：
| 假设 | 采用值 | 5Y均值 | 历史区间 | 趋势 |。用户想看图表时，
带 include_history_chart=true 重新调用本工具即可返回历史趋势图（PNG）。"""


_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values_by_year: dict) -> str:
    """Unicode sparkline over chronologically-sorted yearly values."""
    try:
        pairs = sorted(values_by_year.items())
        nums = [float(v) for _, v in pairs if v is not None]
        if len(nums) < 2:
            return ""
        lo, hi = min(nums), max(nums)
        span = (hi - lo) or 1.0
        return "".join(_SPARK_CHARS[int((v - lo) / span * (len(_SPARK_CHARS) - 1))] for v in nums)
    except Exception:
        return ""


def _verdict(diff_pct: float) -> str:
    """One-word verdict, same ±15% thresholds as the web UI."""
    if diff_pct > 0.15:
        return "undervalued (低估)"
    if diff_pct < -0.15:
        return "overvalued (高估)"
    return "fairly valued (接近合理)"


FMP_SIGNUP_URL = (
    "https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope"
)


def _friendly_error(exc: Exception, ticker: str, has_key: bool) -> ValueError:
    """Wrap raw upstream failures (e.g. FMP 401) with actionable guidance."""
    msg = str(exc)
    # A US/JP ticker failing with "data not found" usually means a key
    # problem (the FMP fetch just returns nothing), not missing data
    needs_key = "." not in ticker or ticker.upper().endswith(".T")
    if needs_key and "not found" in msg.lower():
        if not has_key:
            msg = "401"
        else:
            return ValueError(
                f"未能获取 {ticker} 的数据：可能是 fmp_api_key 无效/额度不足，"
                f"也可能该代码不存在。请核对代码拼写，并检查 key 状态"
                f"（FMP 注册/升级，含 valuescope 优惠码：{FMP_SIGNUP_URL}）。"
                f"—— 请把该链接原样告知用户。"
            )
    if "401" in msg or "Unauthorized" in msg or "402" in msg:
        return ValueError(
            f"{ticker} 的数据需要 Financial Modeling Prep (FMP) API key"
            f"（美股/日股必须；A股/港股无需 key，可直接估值）。"
            + ("当前提供的 fmp_api_key 无效或额度不足，请检查 key 或升级套餐："
               if has_key
               else "获取方式：注册 FMP 订阅后，把 key 通过 fmp_api_key 参数传入"
                    "即可。注册链接（使用 valuescope 优惠码有折扣）：")
            + FMP_SIGNUP_URL
            + " —— 请把该链接原样告知用户。"
        )
    return ValueError(msg)

mcp = FastMCP(
    "valuescope",
    instructions=(
        "ValueScope 标准化 DCF 估值引擎。A股/港股开箱即用；美股/日股可先用每日限量"
        "的免费体验额度，注册 FMP key 后不限次（fmp_api_key 参数或 X-FMP-Key 请求头）。"
        "用法：先不带假设参数调用 run_dcf 获取基线估值和参数分析指南，按指南完成参数"
        "分析（如可用请先联网搜索），再带上你的参数调用 run_dcf 得到最终估值。所有计算"
        "为确定性模型输出，同样输入永远得到同样结果。不构成投资建议。"
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    # Public remote server: the SDK's DNS-rebinding protection defaults to
    # localhost-only Host headers and rejects the Railway/custom domains.
    # Rebinding attacks target localhost servers with ambient credentials;
    # this endpoint is public, unauthenticated, and IP-rate-limited, so the
    # protection does not apply.
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    ),
)


@mcp.prompt(name="dcf", description="对指定股票执行完整两相 DCF 估值：搜索业绩指引 → 推理参数 → 三情景估值")
def dcf_prompt(ticker: str) -> str:
    """One-command valuation workflow (shows up as a slash command in
    clients that surface MCP prompts, e.g. /mcp__valuescope__dcf)."""
    return f"""用 valuescope 的 run_dcf 工具给 {ticker} 做完整 DCF 估值，严格执行：

1. 确定 ticker 格式（A股 600519.SS / 000333.SZ，港股 0700.HK，美股 AAPL，日股 7203.T；给的是公司名先推断代码）。
2. 裸调 run_dcf(ticker) 获取基线估值、参数历史区间和 parameter_analysis_guide。
3. 按 guide 联网搜索最新业绩指引、分析师一致预期、行业 benchmark（无联网能力则基于历史数据和你的知识推理，并说明局限）。
4. 对每个参数独立推理并给出依据，然后按乐观/中性/悲观三组假设分别调用 run_dcf。
5. 按返回的 presentation_guide 呈现：以中性情景为主结论，附三情景对比表、关键假设表（含趋势列）、反向 DCF 点评。
6. 结尾附免责声明：模型计算结果，仅供研究参考，不构成投资建议。"""


def _render_history_chart(ticker: str, apikey: str) -> bytes:
    """Render the four valuation-driver charts (same set as the website's
    overview page) as one 2×2 PNG. Data comes from the backend cache, so
    this is cheap after any prior call for the ticker."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    financial_data = get_historical_financials(
        ticker, "annual", apikey, HISTORICAL_DATA_PERIODS_ANNUAL
    )
    if financial_data is None:
        raise ValueError(f"Financial data not found: {ticker}")
    df = financial_data["summary"]
    years = list(df.columns)[::-1]  # chronological

    def series(name):
        if name not in df.index:
            return [None] * len(years)
        row = pd.to_numeric(df.loc[name][::-1], errors="coerce")
        return [None if pd.isna(v) else float(v) for v in row]

    revenue = series("Revenue")
    growth = series("Revenue Growth (%)")
    margin = series("EBIT Margin (%)")
    rev_ic = series("Revenue / IC")
    reinvest = series("Total Reinvestment")
    currency = ""
    if "Reported Currency" in df.index:
        currency = str(df.loc["Reported Currency"].iloc[0])

    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5), dpi=110)
    fig.suptitle(f"{ticker} — Valuation Drivers (5Y)", fontsize=12, fontweight="bold")

    ax = axes[0][0]
    ax.bar(years, [v or 0 for v in revenue], color="#3b82f6", alpha=0.85)
    ax.set_title(f"Revenue ({currency} M) & Growth", fontsize=10)
    ax2 = ax.twinx()
    ax2.plot(years, growth, color="#f59e0b", marker="o", linewidth=1.5)
    ax2.axhline(0, color="#9ca3af", linewidth=0.6, linestyle="--")
    ax2.set_ylabel("Growth %", fontsize=8)

    ax = axes[0][1]
    ax.plot(years, margin, color="#10b981", marker="o", linewidth=1.8)
    ax.set_title("EBIT Margin %", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1][0]
    ax.plot(years, rev_ic, color="#8b5cf6", marker="o", linewidth=1.8)
    ax.set_title("Revenue / Invested Capital (x)", fontsize=10)
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1][1]
    colors = ["#ef4444" if (v or 0) < 0 else "#3b82f6" for v in reinvest]
    ax.bar(years, [v or 0 for v in reinvest], color=colors, alpha=0.85)
    ax.axhline(0, color="#9ca3af", linewidth=0.6)
    ax.set_title(f"Total Reinvestment ({currency} M)", fontsize=10)

    for row_axes in axes:
        for a in row_axes:
            a.tick_params(labelsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _build_analysis_guide(ticker: str, apikey: str) -> str:
    """Assemble the same analyst prompt `vs --auto` uses (data fetches are
    backend-cached, so this is cheap after the baseline run)."""
    financial_data = get_historical_financials(
        ticker, "annual", apikey, HISTORICAL_DATA_PERIODS_ANNUAL
    )
    if financial_data is None:
        raise ValueError(f"Financial data not found: {ticker}")

    profile = cached_get_profile(ticker, apikey)
    profile = _ensure_profile_complete(profile, financial_data, ticker)

    summary_df = financial_data["summary"]
    base_year_col = summary_df.columns[0]
    base_year_data = summary_df.iloc[:, 0].copy()
    base_year_data.name = base_year_col
    base_year_data["Average Tax Rate"] = financial_data["average_tax_rate"]

    wacc_calc, _total_erp, _details = calculate_wacc(
        base_year_data, profile, apikey, verbose=False
    )

    ttm_quarter = financial_data.get("ttm_latest_quarter", "")
    ttm_end_date = financial_data.get("ttm_end_date", "")
    is_ttm = bool(ttm_quarter and ttm_end_date)

    return build_analysis_prompt(
        ticker=ticker,
        summary_df=summary_df,
        company_profile=profile,
        calculated_wacc=wacc_calc,
        calculated_tax_rate=financial_data["average_tax_rate"],
        base_year=int(str(base_year_col).replace("FY", "")),
        ttm_quarter=ttm_quarter if is_ttm else "",
        ttm_end_date=ttm_end_date if is_ttm else "",
        fy_end_month=financial_data.get("fy_end_month", 12),
        freshness_info=financial_data.get("freshness"),
    )


@mcp.tool()
def run_dcf(
    ticker: str,
    revenue_growth_1: float | None = None,
    revenue_growth_2: float | None = None,
    ebit_margin: float | None = None,
    convergence: float | None = None,
    revenue_invested_capital_ratio_1: float | None = None,
    revenue_invested_capital_ratio_2: float | None = None,
    revenue_invested_capital_ratio_3: float | None = None,
    tax_rate: float | None = None,
    wacc: float | None = None,
    ronic_match_wacc: bool = False,
    include_history_chart: bool = False,
    fmp_api_key: str = "",
):
    """一站式 DCF 估值（10 年两阶段 FCFF 折现），分两步使用：

    第一步——不带任何假设参数调用：返回按 5 年历史均值计算的基线估值、每个参数的
    历史区间，以及 parameter_analysis_guide（资深分析师参数分析指南）。收到后请
    按指南对每个参数做独立分析（若有联网搜索能力，务必先按指南搜索业绩指引与
    分析师预期），然后进入第二步。

    第二步——带上你分析得出的假设参数再次调用：返回最终估值，含每股内在价值、
    与市价差异、价值桥、逐年预测表、敏感性矩阵、反向 DCF（市价隐含假设）。

    参数单位：增长率/利润率/税率/WACC 为百分数（10 表示 10%）；
    revenue_invested_capital_ratio 为倍数（如 2.0）；convergence 为收敛年数。
    省略 tax_rate/wacc 时由引擎按财报与市场数据自动计算。

    include_history_chart=true 时额外返回一张历史趋势图（PNG，2×2：营收与增速、
    EBIT 利润率、Rev/IC、再投资额）——用户想看关键假设的历史数据可视化时使用。

    ticker 格式：A股 600519.SS / 000333.SZ；港股 0700.HK；美股 AAPL；日股 7203.T。
    A股/港股无需 key。美股/日股需要 FMP key：可通过 fmp_api_key 参数传入，或在
    MCP 连接配置中设置 X-FMP-Key 请求头；未提供时可使用每日限量的免费体验额度。
    FMP 注册（valuescope 优惠码有折扣）：
    https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope
    """
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise ValueError(err)
    normalized = _normalize_ticker(ticker)

    # ── Quotas & key resolution: param > X-FMP-Key header > server trial ──
    meta = _request_meta.get()
    ip = meta.get("ip", "")
    is_remote = ip not in _LOOPBACK_IPS
    user_key = (fmp_api_key or "").strip() or meta.get("fmp_key", "")

    if is_remote:
        try:
            _consume_quota("all", ip, MCP_DAILY_LIMIT)
        except ValueError:
            raise ValueError(
                f"今日调用次数已达上限（{MCP_DAILY_LIMIT} 次/日），请明天再试。"
            ) from None

    needs_key = "." not in normalized or normalized.upper().endswith(".T")
    effective_key = user_key
    trial_note = None
    if needs_key and not user_key:
        server_key = os.environ.get("FMP_API_KEY", "")
        if server_key:
            if is_remote:
                _trial_exhausted = (
                    "美股/日股的免费体验额度已用完（A股/港股无需 key、不限体验额度）。"
                    "注册自己的 FMP key 即可继续："
                    "调用时传 fmp_api_key 参数，或在 MCP 连接配置中加 X-FMP-Key 请求头。"
                    f"注册链接（使用 valuescope 优惠码有折扣）：{FMP_SIGNUP_URL} "
                    "—— 请把以上说明和链接原样告知用户。"
                )
                # Per-IP limit first (so a single IP hitting its own cap
                # doesn't consume a global slot), then the global ceiling on
                # the owner's FMP key (bounds total cost under IP rotation).
                try:
                    remaining = _consume_quota("us_trial", ip, US_TRIAL_DAILY_LIMIT)
                except ValueError:
                    raise ValueError(_trial_exhausted) from None
                try:
                    _consume_quota("us_trial_global", _GLOBAL_QUOTA_KEY,
                                   MCP_US_TRIAL_GLOBAL_DAILY)
                except ValueError:
                    raise ValueError(_trial_exhausted) from None
                trial_note = (
                    f"本次美股/日股估值使用了免费体验额度（今日剩余 {remaining} 次）。"
                    f"注册自己的 FMP key 可不限次使用（使用 valuescope 优惠码有折扣）："
                    f"{FMP_SIGNUP_URL} —— 请在呈现结果末尾将此信息连同链接告知用户。"
                )
            effective_key = server_key

    core = {
        "revenue_growth_1": revenue_growth_1,
        "revenue_growth_2": revenue_growth_2,
        "ebit_margin": ebit_margin,
        "convergence": convergence,
        "revenue_invested_capital_ratio_1": revenue_invested_capital_ratio_1,
        "revenue_invested_capital_ratio_2": revenue_invested_capital_ratio_2,
        "revenue_invested_capital_ratio_3": revenue_invested_capital_ratio_3,
    }
    analysis_phase = all(v is None for v in core.values())

    # Fill omitted assumptions from 5Y-historical suggestions
    defaults_used = []
    if any(v is None for v in core.values()):
        try:
            defaults = _get_dcf_defaults_endpoint(normalized, effective_key)
        except HTTPException as e:
            raise _friendly_error(ValueError(str(e.detail)), normalized, bool(user_key)) from e
        except Exception as e:
            raise _friendly_error(e, normalized, bool(user_key)) from e
        for key, val in core.items():
            if val is None:
                core[key] = defaults["suggested"][key]
                defaults_used.append(key)

    params = DCFParams(
        ticker=normalized,
        apikey=effective_key,
        tax_rate=tax_rate,
        wacc=wacc,
        ronic_match_wacc=ronic_match_wacc,
        **core,
    )
    try:
        result = _run_dcf_endpoint(params)
    except HTTPException as e:
        raise _friendly_error(ValueError(str(e.detail)), normalized, bool(user_key)) from e
    except Exception as e:
        raise _friendly_error(e, normalized, bool(user_key)) from e

    # US/JP pages need the visitor's own FMP key in browser settings, so the
    # link is only unconditionally useful for A-shares/HK.
    needs_key_on_web = needs_key
    if trial_note:
        result["fmp_trial_note"] = trial_note
    result["web_page_url"] = f"https://valuescope.app/stock/{normalized.upper()}/dcf"
    result["web_page_note"] = (
        "交互式估值页（可自行调参重算），不包含本次计算的参数与结果；"
        f"历史财务趋势交互图表见概览页 https://valuescope.app/stock/{normalized.upper()}。"
        + ("该美股/日股页面需访问者在网页设置中配置自己的 FMP key 才能加载数据。"
           if needs_key_on_web else "")
    )
    result["disclaimer"] = DISCLAIMER

    if not analysis_phase:
        diff = result.get("diff_pct") or 0
        result["summary"] = {
            "company": result.get("company_name"),
            "ticker": normalized.upper(),
            "intrinsic_value_per_share": result.get("dcf_price_converted", result.get("dcf_price")),
            "market_price": result.get("market_price"),
            "currency": result.get("currency"),
            "upside_pct": round(diff * 100, 1),
            "verdict": _verdict(diff),
            "assumptions_filled_from_historical_defaults": defaults_used or None,
        }
        result["presentation_guide"] = PRESENTATION_GUIDE
        _track("mcp_run_dcf", ip, {
            "phase": "valuation",
            "market": _market(normalized),
            "ticker": normalized.upper(),
            "verdict": result["summary"]["verdict"].split(" ")[0],
            "used_trial": "true" if trial_note else "false",
        })
        return _with_optional_chart(result, normalized, effective_key, include_history_chart)

    # ── Phase 1: baseline + analyst guide ──
    # Trim the heavy tables — full detail comes with the phase-2 run.
    baseline = {
        k: result.get(k)
        for k in (
            "company_name", "dcf_price", "dcf_price_converted", "market_price",
            "diff_pct", "currency", "reported_currency", "bridge",
            "valuation_params", "ttm",
        )
    }
    # Enrich per-parameter history with unicode sparklines (chronological)
    history = defaults.get("history") or {}
    for metric in history.values():
        if isinstance(metric, dict) and isinstance(metric.get("values"), dict):
            metric["sparkline"] = _sparkline(metric["values"])

    baseline_note = None
    if (result.get("dcf_price") or 0) <= 0:
        baseline_note = (
            "基线每股价值为负/零：这是用 5 年历史均值机械外推的结果，常见于高再投入、"
            "FCFF 尚为负的成长期公司，不代表公司没有价值——恰恰说明估值高度依赖前瞻"
            "假设，第二步的参数分析才是关键。请勿把该基线数字直接呈现给用户当作结论。"
        )
    payload = {
        "phase": "baseline",
        "baseline_from_5y_historical_averages": baseline,
        "baseline_note": baseline_note,
        "parameter_history": history,
        "suggested_parameters": defaults.get("suggested"),
        "fmp_trial_note": trial_note,
        "parameter_analysis_guide": _build_analysis_guide(normalized, effective_key),
        "next_step": (
            "以上基线直接采用 5 年历史均值，未包含前瞻判断。请按 "
            "parameter_analysis_guide 对每个参数做独立分析（有联网能力请先按指南"
            "搜索最新业绩指引与分析师预期），说明你的推理，然后带上分析得出的参数"
            "再次调用 run_dcf 得到最终估值。也可以用乐观/中性/悲观三组假设分别调用，"
            "生成情景区间。"
        ),
        "disclaimer": DISCLAIMER,
    }
    _track("mcp_run_dcf", ip, {
        "phase": "baseline",
        "market": _market(normalized),
        "ticker": normalized.upper(),
        "used_trial": "true" if trial_note else "false",
    })
    return _with_optional_chart(payload, normalized, effective_key, include_history_chart)


def _with_optional_chart(payload: dict, ticker: str, apikey: str, include_chart: bool):
    """Append the history chart as an MCP image content block when asked."""
    if not include_chart:
        return payload
    try:
        chart = Image(data=_render_history_chart(ticker, apikey), format="png")
    except Exception as e:
        logger.warning("history chart render failed for %s: %s", ticker, e)
        payload["history_chart_error"] = str(e)
        return payload
    return [payload, chart]
