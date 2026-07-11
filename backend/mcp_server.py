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

import logging

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

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

logger = logging.getLogger(__name__)

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
数字保留合理精度（价格两位小数、百分比一位）；若做了多情景，用一张情景对比表。"""


def _verdict(diff_pct: float) -> str:
    """One-word verdict, same ±15% thresholds as the web UI."""
    if diff_pct > 0.15:
        return "undervalued (低估)"
    if diff_pct < -0.15:
        return "overvalued (高估)"
    return "fairly valued (接近合理)"


def _friendly_error(exc: Exception, ticker: str, has_key: bool) -> ValueError:
    """Wrap raw upstream failures (e.g. FMP 401) with actionable guidance."""
    msg = str(exc)
    if "401" in msg or "Unauthorized" in msg or "402" in msg:
        return ValueError(
            f"{ticker} 的数据需要 Financial Modeling Prep API key"
            f"（美股/日股必须；A股/港股无需）。"
            + ("当前提供的 fmp_api_key 无效或额度不足。" if has_key
               else "请在调用时传入 fmp_api_key 参数。")
        )
    return ValueError(msg)

mcp = FastMCP(
    "valuescope",
    instructions=(
        "ValueScope 标准化 DCF 估值引擎（A股/港股开箱即用；美股/日股需调用方提供 "
        "fmp_api_key）。用法：先不带假设参数调用 run_dcf 获取基线估值和参数分析指南，"
        "按指南完成参数分析（如可用请先联网搜索），再带上你的参数调用 run_dcf 得到"
        "最终估值。所有计算为确定性模型输出，同样输入永远得到同样结果。不构成投资建议。"
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


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
    fmp_api_key: str = "",
) -> dict:
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

    ticker 格式：A股 600519.SS / 000333.SZ；港股 0700.HK；美股 AAPL；日股 7203.T。
    A股/港股无需 key；美股/日股必须提供 fmp_api_key（Financial Modeling Prep）。
    """
    is_valid, err = validate_ticker(ticker)
    if not is_valid:
        raise ValueError(err)
    normalized = _normalize_ticker(ticker)

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
            defaults = _get_dcf_defaults_endpoint(normalized, fmp_api_key)
        except HTTPException as e:
            raise ValueError(str(e.detail)) from e
        except Exception as e:
            raise _friendly_error(e, normalized, bool(fmp_api_key)) from e
        for key, val in core.items():
            if val is None:
                core[key] = defaults["suggested"][key]
                defaults_used.append(key)

    params = DCFParams(
        ticker=normalized,
        apikey=fmp_api_key,
        tax_rate=tax_rate,
        wacc=wacc,
        ronic_match_wacc=ronic_match_wacc,
        **core,
    )
    try:
        result = _run_dcf_endpoint(params)
    except HTTPException as e:
        raise ValueError(str(e.detail)) from e
    except Exception as e:
        raise _friendly_error(e, normalized, bool(fmp_api_key)) from e

    # US/JP pages need the visitor's own FMP key in browser settings, so the
    # link is only unconditionally useful for A-shares/HK.
    needs_key_on_web = "." not in normalized or normalized.upper().endswith(".T")
    result["web_page_url"] = f"https://valuescope.app/stock/{normalized.upper()}/dcf"
    result["web_page_note"] = (
        "交互式估值页（可自行调参重算），不包含本次计算的参数与结果。"
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
        return result

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
    baseline_note = None
    if (result.get("dcf_price") or 0) <= 0:
        baseline_note = (
            "基线每股价值为负/零：这是用 5 年历史均值机械外推的结果，常见于高再投入、"
            "FCFF 尚为负的成长期公司，不代表公司没有价值——恰恰说明估值高度依赖前瞻"
            "假设，第二步的参数分析才是关键。请勿把该基线数字直接呈现给用户当作结论。"
        )
    return {
        "phase": "baseline",
        "baseline_from_5y_historical_averages": baseline,
        "baseline_note": baseline_note,
        "parameter_history": defaults.get("history"),
        "suggested_parameters": defaults.get("suggested"),
        "parameter_analysis_guide": _build_analysis_guide(normalized, fmp_api_key),
        "next_step": (
            "以上基线直接采用 5 年历史均值，未包含前瞻判断。请按 "
            "parameter_analysis_guide 对每个参数做独立分析（有联网能力请先按指南"
            "搜索最新业绩指引与分析师预期），说明你的推理，然后带上分析得出的参数"
            "再次调用 run_dcf 得到最终估值。也可以用乐观/中性/悲观三组假设分别调用，"
            "生成情景区间。"
        ),
        "disclaimer": DISCLAIMER,
    }
