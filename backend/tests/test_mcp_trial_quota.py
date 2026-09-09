"""US/JP trial quota is charged per ticker per day, not per call.

One valuation is at least two run_dcf calls (baseline, then final
assumptions) and a three-scenario run is more, but only the first reaches
FMP — so a user must never be cut off mid-flow on a ticker already paid for.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

from backend import mcp_server


@pytest.fixture(autouse=True)
def clean_quotas(monkeypatch):
    monkeypatch.setattr(mcp_server, "_quota_usage", {})
    monkeypatch.setattr(mcp_server, "_quota_tickers", {})


def consume(ticker, ip="1.2.3.4", limit=5):
    return mcp_server._consume_quota("us_trial", ip, limit, ticker)


def test_repeat_calls_on_one_ticker_cost_one_unit():
    for _ in range(6):  # baseline + final + three scenarios + a re-run
        remaining = consume("AAPL")
    assert remaining == 4


def test_distinct_tickers_each_cost_one_unit():
    for i, t in enumerate(["AAPL", "MSFT", "NVDA", "7203.T", "GOOG"], start=1):
        assert consume(t) == 5 - i
    with pytest.raises(ValueError):
        consume("AMZN")


def test_exhausted_budget_still_serves_an_already_paid_ticker():
    """The cutoff must never land between a user's baseline and valuation."""
    for t in ["AAPL", "MSFT", "NVDA", "7203.T", "GOOG"]:
        consume(t)
    with pytest.raises(ValueError):
        consume("AMZN")
    assert consume("AAPL") == 0  # second phase on a paid ticker goes through


def test_budgets_are_per_ip():
    consume("AAPL", ip="1.1.1.1", limit=1)
    with pytest.raises(ValueError):
        consume("MSFT", ip="1.1.1.1", limit=1)
    assert consume("MSFT", ip="2.2.2.2", limit=1) == 0


def test_without_a_ticker_it_still_counts_per_call():
    """The all-calls budget (MCP_DAILY_LIMIT) passes no ticker."""
    assert mcp_server._consume_quota("all", "1.2.3.4", 2) == 1
    assert mcp_server._consume_quota("all", "1.2.3.4", 2) == 0
    with pytest.raises(ValueError):
        mcp_server._consume_quota("all", "1.2.3.4", 2)
