# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""An aging profile must be served immediately and refreshed in the background.

Blocking a request on a cold upstream fetch is what left crawlers looking at
empty stock pages; serving a stale price forever would be the opposite mistake.
"""

import threading
import time

import pytest

from backend import data_cache


@pytest.fixture(autouse=True)
def clean_caches():
    data_cache._cache.clear()
    data_cache._neg_profiles.clear()
    with data_cache._refreshing_lock:
        data_cache._refreshing.clear()
    yield
    data_cache._cache.clear()
    data_cache._neg_profiles.clear()


def _disk(monkeypatch, value, age):
    monkeypatch.setattr(data_cache.persistent_cache, "get_with_age",
                        lambda key: (value, age))
    monkeypatch.setattr(data_cache.persistent_cache, "get", lambda key: value)
    monkeypatch.setattr(data_cache.persistent_cache, "put",
                        lambda key, v, ttl: None)
    monkeypatch.setattr(data_cache.persistent_cache, "delete", lambda key: None)


def test_fresh_disk_entry_is_not_refreshed(monkeypatch):
    scheduled = []
    monkeypatch.setattr(data_cache, "_schedule_profile_refresh",
                        lambda t, k='': scheduled.append(t))
    _disk(monkeypatch, {"companyName": "X", "price": 10.0}, age=60)

    out = data_cache.get_company_profile("0700.HK")

    assert out["companyName"] == "X"
    assert scheduled == []


def test_aging_disk_entry_is_served_and_refreshed(monkeypatch):
    scheduled = []
    monkeypatch.setattr(data_cache, "_schedule_profile_refresh",
                        lambda t, k='': scheduled.append(t))
    _disk(monkeypatch, {"companyName": "X", "price": 10.0},
          age=data_cache._DISK_PROFILE_FRESH + 1)

    started = time.time()
    out = data_cache.get_company_profile("0700.HK")

    # Served from disk, not from a fetch: must be instant.
    assert time.time() - started < 1
    assert out["companyName"] == "X"
    assert scheduled == ["0700.HK"]


def test_refresh_is_deduped_per_ticker(monkeypatch):
    """A crawler sweep must not spawn one refresh thread per hit."""
    calls = []
    release = threading.Event()

    def slow_fetch(ticker, apikey='', _force=False):
        calls.append(ticker)
        release.wait(timeout=5)
        return {"companyName": "X", "price": 10.0}

    monkeypatch.setattr(data_cache, "get_company_profile", slow_fetch)

    for _ in range(10):
        data_cache._schedule_profile_refresh("0700.HK")

    # Let the single worker reach its fetch before asserting.
    for _ in range(50):
        if calls:
            break
        time.sleep(0.01)
    release.set()

    assert calls == ["0700.HK"]


def test_refresh_fanout_is_capped(monkeypatch):
    """A sweep across many aging tickers must not spawn a thread per ticker."""
    release = threading.Event()
    started = []

    def slow_fetch(ticker, apikey='', _force=False):
        started.append(ticker)
        release.wait(timeout=5)
        return {"companyName": "X", "price": 10.0}

    monkeypatch.setattr(data_cache, "get_company_profile", slow_fetch)

    for i in range(50):
        data_cache._schedule_profile_refresh(f"T{i}.HK")

    for _ in range(100):
        if len(started) >= data_cache._MAX_CONCURRENT_REFRESH:
            break
        time.sleep(0.01)
    in_flight = len(started)
    release.set()

    assert in_flight <= data_cache._MAX_CONCURRENT_REFRESH


def test_failed_refresh_clears_the_inflight_marker(monkeypatch):
    """Otherwise one failure would block refreshes for that ticker forever."""
    def boom(ticker, apikey='', _force=False):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(data_cache, "get_company_profile", boom)

    data_cache._schedule_profile_refresh("0700.HK")

    for _ in range(100):
        with data_cache._refreshing_lock:
            if "0700.HK" not in data_cache._refreshing:
                break
        time.sleep(0.01)

    with data_cache._refreshing_lock:
        assert "0700.HK" not in data_cache._refreshing
