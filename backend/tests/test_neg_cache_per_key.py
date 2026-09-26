"""A keyless failure on a US ticker must not block a caller with a key.

US/JP financials come from FMP, where a failed fetch usually means a
missing or rejected key. The failure cache used to be keyed by ticker
alone, so one keyless request for AAPL served "no data" to every keyed
caller for up to six hours.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import pytest

import modeling.data
import modeling.freshness
from backend import data_cache, persistent_cache


@pytest.fixture
def fetches(monkeypatch):
    disk = {}
    monkeypatch.setattr(persistent_cache, "get", lambda k: disk.get(k))
    monkeypatch.setattr(persistent_cache, "put", lambda k, v, ttl: disk.__setitem__(k, v))
    monkeypatch.setattr(data_cache, "_cache", {})
    monkeypatch.setattr(modeling.freshness, "check_data_freshness",
                        lambda t, d, k: (d, {"is_stale": False}))
    calls = []

    def raw(ticker, period, apikey, periods):
        calls.append(apikey)
        return {"rows": 1} if apikey == "good" else None

    monkeypatch.setattr(modeling.data, "get_historical_financials", raw)
    return calls


def test_keyless_failure_does_not_block_a_key(fetches):
    assert data_cache.get_historical_financials("AAPL", "annual", "", 5) is None
    data = data_cache.get_historical_financials("AAPL", "annual", "good", 5)
    assert data is not None and data["rows"] == 1
    assert fetches == ["", "good"]


def test_same_key_failure_is_still_remembered(fetches):
    assert data_cache.get_historical_financials("AAPL", "annual", "", 5) is None
    assert data_cache.get_historical_financials("AAPL", "annual", "", 5) is None
    assert fetches == [""]


def test_a_share_failure_stays_per_ticker(fetches):
    assert data_cache.get_historical_financials("600519.SS", "annual", "", 5) is None
    assert data_cache.get_historical_financials("600519.SS", "annual", "good", 5) is None
    assert fetches == [""]
