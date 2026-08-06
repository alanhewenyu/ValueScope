import datetime

from backend.services import portfolio_prices as prices


def test_fund_nav_pair_keeps_yesterdays_nav_as_daily_base(monkeypatch):
    class FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 6)  # Thursday

    monkeypatch.setattr(prices.datetime, "date", FakeDate)
    monkeypatch.setattr("backend.persistent_cache.put", lambda *a, **k: None)
    nav, currency, previous = prices._fund_nav_pair([
        {"FSRQ": "2026-08-05", "DWJZ": "4.0520"},
        {"FSRQ": "2026-08-04", "DWJZ": "3.9710"},
    ], "001071", "test")

    assert (nav, currency, previous) == (4.052, "CNY", 3.971)
    assert prices._fund_nav_meta["001071"]["nav_date"] == "2026-08-05"


def test_fund_nav_pair_zeroes_genuinely_stale_feed(monkeypatch):
    class FakeDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 8, 6)

    monkeypatch.setattr(prices.datetime, "date", FakeDate)
    monkeypatch.setattr("backend.persistent_cache.put", lambda *a, **k: None)
    nav, _, previous = prices._fund_nav_pair([
        {"FSRQ": "2026-08-03", "DWJZ": "3.7970"},
        {"FSRQ": "2026-07-31", "DWJZ": "3.9200"},
    ], "001071", "test")

    assert nav == previous == 3.797
