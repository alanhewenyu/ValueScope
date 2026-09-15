"""One ticker costs one trial unit, however many tools ask about it.

run_dcf, get_relative_valuation and get_score all go through
_resolve_key_and_quota. A user who values a company, checks its multiples
and reads its score is researching one company, not three — and the engine
fetches the data once and serves the rest from cache, so charging three
units would bill for work that never happened.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

from backend import mcp_server


@pytest.fixture(autouse=True)
def trial_env(monkeypatch):
    monkeypatch.setattr(mcp_server, "_quota_usage", {})
    monkeypatch.setattr(mcp_server, "_quota_tickers", {})
    monkeypatch.setattr(mcp_server, "US_TRIAL_DAILY_LIMIT", 2)
    monkeypatch.setenv("FMP_API_KEY", "server-trial-key")
    # A remote caller: loopback traffic skips the quotas entirely.
    token = mcp_server._request_meta.set({"ip": "203.0.113.7", "fmp_key": ""})
    yield
    mcp_server._request_meta.reset(token)


def test_three_tools_on_one_ticker_cost_one_unit():
    notes = [mcp_server._resolve_key_and_quota("AAPL", "")[1] for _ in range(3)]
    assert all(n is not None for n in notes), "each call should report the trial"
    # Budget of 2 tickers: one is spent on AAPL, so a second name still fits.
    mcp_server._resolve_key_and_quota("MSFT", "")
    with pytest.raises(ValueError, match="额度已用完"):
        mcp_server._resolve_key_and_quota("NVDA", "")


def test_a_paid_ticker_stays_available_after_the_budget_runs_out():
    for t in ("AAPL", "MSFT"):
        mcp_server._resolve_key_and_quota(t, "")
    with pytest.raises(ValueError):
        mcp_server._resolve_key_and_quota("NVDA", "")
    # The user can still switch tools on a company already paid for.
    key, note = mcp_server._resolve_key_and_quota("AAPL", "")
    assert key == "server-trial-key" and note is not None


def test_a_shares_and_hk_never_touch_the_trial():
    for t in ("600519.SS", "0700.HK"):
        key, note = mcp_server._resolve_key_and_quota(t, "")
        assert key == "" and note is None, f"{t} must not need a key"
    # ...so the US budget is untouched.
    for t in ("AAPL", "MSFT"):
        mcp_server._resolve_key_and_quota(t, "")


def test_a_user_key_bypasses_the_trial_entirely():
    for t in ("AAPL", "MSFT", "NVDA", "GOOG"):
        key, note = mcp_server._resolve_key_and_quota(t, "my-own-key")
        assert key == "my-own-key" and note is None
