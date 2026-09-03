"""/portfolio/benchmarks caching contract.

The chart froze on 2026-08-28 for five days: Yahoo throttled the concurrent
downloads a page load fires, every series was quietly backfilled from
`lastgood`, and the backfilled response was then treated as complete —
cached for the full TTL and written back to lastgood with a fresh 7-day
expiry. These tests pin the three rules that broke the ratchet.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import datetime as dt
import sys
import types

import pandas as pd
import pytest

from backend.routers import portfolio as P

NAMES = ["CSI 300", "S&P 500", "Nasdaq 100", "Hang Seng"]


class FakeCache:
    """Stand-in for persistent_cache: records the TTL each key was put with."""

    def __init__(self):
        self.data: dict[str, tuple] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value, ttl):
        self.data[key] = value
        self.ttls[key] = ttl

    def delete(self, key):
        self.data.pop(key, None)


def _closes(ticker, last_date, n=5):
    """A MultiIndex close frame shaped like yf.download's output."""
    idx = pd.bdate_range(end=pd.Timestamp(last_date), periods=n)
    return pd.DataFrame({("Close", ticker): range(100, 100 + n)}, index=idx)


def _series(last_date, n=5):
    """A benchmark series as the endpoint returns it (CNY rows)."""
    idx = pd.bdate_range(end=pd.Timestamp(last_date), periods=n)
    return [{"date": d.strftime("%Y-%m-%d"), "close": 100.0} for d in idx]


@pytest.fixture
def env(monkeypatch):
    """Fake yfinance + fake cache; FX conversion stubbed to 1:1."""
    cache = FakeCache()
    # The endpoint does `from backend import persistent_cache as pc` inside the
    # function body, which resolves via the package attribute when the module
    # has already been imported and via sys.modules when it has not — another
    # test importing it first would otherwise silently hand the real on-disk
    # cache to these tests. Cover both paths.
    import backend
    monkeypatch.setattr(backend, "persistent_cache", cache, raising=False)
    monkeypatch.setitem(sys.modules, "backend.persistent_cache", cache)
    monkeypatch.setattr(P, "_fx_history", lambda ccy, start: [("1970-01-01", 1.0)])
    fail: set[str] = set()
    today = dt.date.today().isoformat()

    def download(ticker, **kw):
        if ticker in fail:
            return pd.DataFrame()
        return _closes(ticker, today)

    monkeypatch.setitem(sys.modules, "yfinance",
                        types.SimpleNamespace(download=download))
    return types.SimpleNamespace(cache=cache, fail=fail, today=today)


def test_all_series_fresh_cached_for_full_ttl(env):
    out = P.get_benchmarks(start="2026-03-07")
    assert sorted(out) == sorted(NAMES)
    assert env.cache.ttls["benchmarks_cny:2026-03-07"] == 600


def test_backfilled_response_is_not_treated_as_complete(env):
    """A stale fill must shorten the TTL so the next request retries."""
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    env.cache.put("benchmarks_cny_lastgood:2026-03-07",
                  {"Nasdaq 100": _series(yesterday)}, ttl=7 * 86400)
    env.fail.update({"^NDX", "QQQ"})

    out = P.get_benchmarks(start="2026-03-07")

    assert out["Nasdaq 100"][-1]["date"] == yesterday  # gap filled
    assert env.cache.ttls["benchmarks_cny:2026-03-07"] == 120  # but not "complete"
    # lastgood keeps the fallback and gains the series we did fetch
    lastgood = env.cache.data["benchmarks_cny_lastgood:2026-03-07"]
    assert lastgood["Nasdaq 100"][-1]["date"] == yesterday
    assert lastgood["Hang Seng"][-1]["date"] == env.today


def test_lastgood_older_than_the_cap_is_dropped_not_drawn(env):
    """Past the cap the copy is a wrong answer, not a gap-filler.

    The frontend truncates the portfolio line to the benchmark's last close,
    so a frozen index freezes the whole comparison — a missing line is the
    honest failure mode.
    """
    ancient = (dt.date.today()
               - dt.timedelta(days=P._LASTGOOD_MAX_AGE_DAYS + 2)).isoformat()
    env.cache.put("benchmarks_cny_lastgood:2026-03-07",
                  {"Nasdaq 100": _series(ancient)}, ttl=7 * 86400)
    env.fail.update({"^NDX", "QQQ"})

    out = P.get_benchmarks(start="2026-03-07")

    assert "Nasdaq 100" not in out
    assert sorted(out) == sorted(n for n in NAMES if n != "Nasdaq 100")


def test_concurrent_callers_fetch_once(env, monkeypatch):
    """The single-flight lock is what keeps Yahoo from throttling us."""
    import threading

    calls = []
    real = sys.modules["yfinance"].download

    def counting(ticker, **kw):
        calls.append(ticker)
        return real(ticker, **kw)

    monkeypatch.setitem(sys.modules, "yfinance",
                        types.SimpleNamespace(download=counting))
    threads = [threading.Thread(target=P.get_benchmarks, args=("2026-03-07",))
               for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 4 indices downloaded once, plus the 510300 staleness probe at most
    assert len(calls) <= 5
