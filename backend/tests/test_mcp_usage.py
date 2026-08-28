"""MCP usage log: recording, internal-traffic exclusion, rollup arithmetic.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import sqlite3
import time

import pytest

from backend import analytics, mcp_usage


@pytest.fixture
def usage(tmp_path, monkeypatch):
    """A fresh usage log on disk, with 9.9.9.9 configured as an internal IP."""
    monkeypatch.setattr(analytics, "_INTERNAL_IPS", {"9.9.9.9"})
    monkeypatch.setattr(mcp_usage, "_DB_PATH", str(tmp_path / "mcp_usage.db"))
    monkeypatch.setattr(mcp_usage, "_initialized", False)
    monkeypatch.setattr(mcp_usage, "_disabled", False)
    return mcp_usage


def _seed(mod):
    mod.record("mcp_run_dcf", "1.1.1.1", {"phase": "baseline", "market": "a",
                                          "ticker": "600519.SS", "used_trial": "false"})
    mod.record("mcp_run_dcf", "1.1.1.1", {"phase": "valuation", "market": "a",
                                          "ticker": "600519.SS", "used_trial": "false"})
    mod.record("mcp_run_dcf", "2.2.2.2", {"phase": "baseline", "market": "hk",
                                          "ticker": "0700.HK", "used_trial": "true"})
    mod.record("mcp_run_dcf", "9.9.9.9", {"phase": "baseline", "market": "us",
                                          "ticker": "AAPL"})


def _backdate_first_row(mod, days=1):
    """Move row 1 into an earlier day so repeat-visit logic has something to see."""
    then = time.time() - days * 86400
    with sqlite3.connect(mod._DB_PATH) as c:
        c.execute("UPDATE mcp_calls SET ts=?, day=? WHERE id=1",
                  (then, time.strftime("%Y-%m-%d", time.gmtime(then))))


class TestRecord:
    def test_stores_pseudonymous_caller_not_ip(self, usage):
        usage.record("mcp_run_dcf", "1.1.1.1", {"market": "a"})
        with sqlite3.connect(usage._DB_PATH) as c:
            caller = c.execute("SELECT caller FROM mcp_calls").fetchone()[0]
        assert caller == analytics.caller_id("1.1.1.1")
        assert "1.1.1.1" not in caller

    def test_flags_internal_callers(self, usage):
        usage.record("mcp_run_dcf", "9.9.9.9", {})
        usage.record("mcp_run_dcf", "1.1.1.1", {})
        with sqlite3.connect(usage._DB_PATH) as c:
            rows = dict(c.execute("SELECT caller, internal FROM mcp_calls"))
        assert rows[analytics.caller_id("9.9.9.9")] == 1
        assert rows[analytics.caller_id("1.1.1.1")] == 0

    def test_never_raises_when_disk_unavailable(self, usage, monkeypatch):
        monkeypatch.setattr(usage, "_DB_PATH", "/proc/nope/mcp_usage.db")
        monkeypatch.setattr(usage, "_initialized", False)
        usage.record("mcp_run_dcf", "1.1.1.1", {})  # must not raise
        assert usage.summary()["available"] is False


class TestSummary:
    def test_excludes_internal_traffic_by_default(self, usage):
        _seed(usage)
        assert usage.summary(days=30)["calls"] == 3
        assert usage.summary(days=30, include_internal=True)["calls"] == 4

    def test_counts_unique_callers_not_calls(self, usage):
        _seed(usage)
        s = usage.summary(days=30)
        assert s["unique_callers"] == 2
        assert s["calls_per_caller"] == 1.5

    def test_repeat_caller_needs_two_distinct_days(self, usage):
        _seed(usage)
        # All four rows land on one day, so nobody has come back yet.
        assert usage.summary(days=30)["returning_callers"] == 0
        _backdate_first_row(usage)
        s = usage.summary(days=30)
        assert s["returning_callers"] == 1
        assert s["returning_rate"] == 0.5

    def test_market_split(self, usage):
        _seed(usage)
        assert usage.summary(days=30)["by_market"] == {"a": 2, "hk": 1}

    def test_daily_series_has_one_row_per_active_day(self, usage):
        _seed(usage)
        assert len(usage.summary(days=30)["daily"]) == 1
        _backdate_first_row(usage)
        assert len(usage.summary(days=30)["daily"]) == 2

    def test_window_excludes_older_calls(self, usage):
        _seed(usage)
        _backdate_first_row(usage, days=10)
        # A 2-day window drops the backdated row but keeps the rest.
        assert usage.summary(days=2)["calls"] == 2
        assert usage.summary(days=30)["calls"] == 3

    def test_new_callers_counts_first_ever_call_in_window(self, usage):
        _seed(usage)
        _backdate_first_row(usage, days=10)
        # Caller 1's first call was 10 days ago, so a 2-day window sees only
        # caller 2 as new even though caller 1 is active in it.
        s = usage.summary(days=2)
        assert s["unique_callers"] == 2
        assert s["new_callers"] == 1
