"""Errors say whether the caller's key arrived, and final valuations run.

A US ticker failing with "needs a key" while the user has configured one
leaves them nowhere to look. The error names where the key came from when
one was received (so a rejected key reads differently from a missing one),
and phase 2 of run_dcf must not trip over its own bookkeeping.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

from backend import mcp_server


@pytest.fixture
def request_meta():
    def _set(**meta):
        token = mcp_server._request_meta.set({"ip": "127.0.0.1", **meta})
        tokens.append(token)
    tokens = []
    yield _set
    for token in reversed(tokens):
        mcp_server._request_meta.reset(token)


def test_param_beats_request_key(request_meta):
    request_meta(fmp_key="hdr", fmp_key_source="authorization")
    assert mcp_server._caller_key("p") == ("p", "param")
    assert mcp_server._caller_key("") == ("hdr", "authorization")


def test_no_key_anywhere(request_meta):
    request_meta(fmp_key="", fmp_key_source="")
    assert mcp_server._caller_key("") == ("", "")


def test_rejected_key_names_its_source():
    msg = str(mcp_server._friendly_error(ValueError("401"), "AAPL", "authorization"))
    assert "Authorization 请求头" in msg
    assert "拒绝" in msg


def test_missing_key_says_none_was_sent():
    msg = str(mcp_server._friendly_error(ValueError("401"), "AAPL", ""))
    assert "没有带 key" in msg


def test_phase_2_returns_a_valuation(monkeypatch, request_meta):
    request_meta(fmp_key="", fmp_key_source="")
    monkeypatch.setattr(mcp_server, "_track", lambda *a, **k: None)
    monkeypatch.setattr(mcp_server, "_run_dcf_endpoint", lambda params: {
        "company_name": "Test Co", "dcf_price": 120.0, "market_price": 100.0,
        "currency": "HKD", "diff_pct": 0.2,
    })
    result = mcp_server.run_dcf(
        "0700.HK", revenue_growth_1=10, revenue_growth_2=8, ebit_margin=35,
        convergence=3, revenue_invested_capital_ratio_1=2,
        revenue_invested_capital_ratio_2=2, revenue_invested_capital_ratio_3=2,
    )
    assert result["phase"] == "valuation"
    assert result["summary"]["intrinsic_value_per_share"] == 120.0
