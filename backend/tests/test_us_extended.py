import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.services import portfolio_prices as prices

NY = ZoneInfo("America/New_York")


def _ms(y, m, d, hh, mm=0):
    """Epoch milliseconds for a New York wall-clock time."""
    return int(datetime.datetime(y, m, d, hh, mm, tzinfo=NY).timestamp() * 1000)


def _quote(**over):
    """A Monday quote: Friday close 312.41, Monday regular close 313.33."""
    q = {
        "symbol": "AAPL",
        "last_close": 312.41,
        "current": 313.33,
        "timestamp": _ms(2026, 8, 10, 16, 0),
        "current_ext": None,
        "timestamp_ext": None,
        "current_night_session": None,
        "timestamp_night_session": None,
    }
    q.update(over)
    return q


@pytest.mark.parametrize("ticker,expected", [
    ("AAPL", "AAPL"),
    ("brk-b", "BRK.B"),
    ("0700.HK", None),
    ("600415.SS", None),
    ("7203.T", None),
    ("001071", None),
])
def test_us_symbol_only_matches_us_tickers(ticker, expected):
    assert prices._xueqiu_us_symbol(ticker) == expected


def test_regular_session_measures_from_previous_close():
    now = datetime.datetime(2026, 8, 10, 11, 0, tzinfo=NY)
    q = _quote(current=315.0, timestamp=_ms(2026, 8, 10, 11, 0))
    assert prices._xueqiu_pick_quote(q, now) == (315.0, 312.41, "regular")


def test_after_hours_keeps_the_previous_close_as_the_days_base():
    # 18:00 NY: the regular session's move is still part of today, so the
    # reference must stay Friday's close (not today's 16:00 close).
    now = datetime.datetime(2026, 8, 10, 18, 0, tzinfo=NY)
    q = _quote(current_ext=310.0, timestamp_ext=_ms(2026, 8, 10, 18, 0))
    assert prices._xueqiu_pick_quote(q, now) == (310.0, 312.41, "extended")


def test_overnight_session_rolls_the_day_at_2000_ny():
    # 22:00 NY Monday: past the roll, so the base is Monday's regular close.
    now = datetime.datetime(2026, 8, 10, 22, 0, tzinfo=NY)
    q = _quote(current_night_session=316.0, timestamp_night_session=_ms(2026, 8, 10, 22, 0))
    assert prices._xueqiu_pick_quote(q, now) == (316.0, 313.33, "night")


def test_overnight_session_after_midnight_still_bases_on_yesterdays_close():
    # 03:00 NY Tuesday — the live overnight print, the window where Yahoo has
    # nothing and the tracker used to sit frozen on the 20:00 price.
    now = datetime.datetime(2026, 8, 11, 3, 0, tzinfo=NY)
    q = _quote(
        current_ext=313.25, timestamp_ext=_ms(2026, 8, 10, 19, 59),
        current_night_session=313.0, timestamp_night_session=_ms(2026, 8, 11, 3, 0),
    )
    assert prices._xueqiu_pick_quote(q, now) == (313.0, 313.33, "night")


def test_pre_market_measures_from_yesterdays_close():
    now = datetime.datetime(2026, 8, 11, 7, 0, tzinfo=NY)
    q = _quote(current_ext=318.0, timestamp_ext=_ms(2026, 8, 11, 7, 0))
    assert prices._xueqiu_pick_quote(q, now) == (318.0, 313.33, "extended")


def test_no_session_today_zeroes_the_daily_move():
    # Saturday: newest print is Friday's after-hours, and pairing it with any
    # earlier close would replay Friday's move as today's.
    now = datetime.datetime(2026, 8, 15, 10, 0, tzinfo=NY)
    q = _quote(
        current=313.33, timestamp=_ms(2026, 8, 14, 16, 0),
        current_ext=313.25, timestamp_ext=_ms(2026, 8, 14, 19, 59),
    )
    price, prev, session = prices._xueqiu_pick_quote(q, now)
    assert (price, prev) == (313.25, 313.25)


def test_absurd_overnight_print_falls_back_to_the_regular_close():
    now = datetime.datetime(2026, 8, 10, 22, 0, tzinfo=NY)
    q = _quote(current_night_session=31.33, timestamp_night_session=_ms(2026, 8, 10, 22, 0))
    assert prices._xueqiu_pick_quote(q, now) == (313.33, 312.41, "regular")


def test_batch_maps_symbols_back_to_tickers(monkeypatch):
    captured = {}

    def fake_raw(symbols):
        captured["symbols"] = symbols
        return [
            {"quote": _quote(symbol="AAPL", current_night_session=316.0,
                             timestamp_night_session=_ms(2026, 8, 10, 22, 0))},
            {"quote": _quote(symbol="BRK.B", current=520.0, last_close=515.0)},
        ]

    monkeypatch.setattr(prices, "_fetch_xueqiu_raw", fake_raw)
    out = prices._fetch_xueqiu_us_batch(["AAPL", "BRK-B", "0700.HK"])

    assert "0700.HK" not in captured["symbols"]
    assert set(out) == {"AAPL", "BRK-B"}
    assert out["BRK-B"] == (520.0, "USD", 515.0)
    assert prices.get_price_session  # session tags recorded per ticker
    assert prices._us_session_tag["BRK-B"] == "regular"


def test_batch_regular_only_ignores_the_extended_book(monkeypatch):
    monkeypatch.setattr(prices, "_fetch_xueqiu_raw", lambda symbols: [
        {"quote": _quote(current_night_session=316.0,
                         timestamp_night_session=_ms(2026, 8, 10, 22, 0))},
    ])
    out = prices._fetch_xueqiu_us_batch(["AAPL"], regular_only=True)
    assert out["AAPL"] == (313.33, "USD", 312.41)


def test_batch_survives_a_dead_feed(monkeypatch):
    def boom(symbols):
        raise RuntimeError("400016")

    monkeypatch.setattr(prices, "_fetch_xueqiu_raw", boom)
    assert prices._fetch_xueqiu_us_batch(["AAPL"]) == {}
