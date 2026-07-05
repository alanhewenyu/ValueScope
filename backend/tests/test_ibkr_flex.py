"""IBKR Flex reconciliation: ticker mapping, tolerances, diff kinds."""
import pytest

from backend.services import ibkr_flex
from backend.services.portfolio_db import init_db, get_conn, upsert_position, upsert_cash


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "flex_test.db")
    init_db(path)
    conn = get_conn(path)
    yield conn
    conn.close()


class TestMapTicker:
    def test_sehk_zero_pads(self):
        assert ibkr_flex.map_ticker("700", "SEHK", "HKD") == "0700.HK"
        assert ibkr_flex.map_ticker("5", "SEHK", "HKD") == "0005.HK"

    def test_us_passthrough(self):
        assert ibkr_flex.map_ticker("AAPL", "NASDAQ", "USD") == "AAPL"

    def test_jpy_suffix(self):
        assert ibkr_flex.map_ticker("7203", "TSEJ", "JPY") == "7203.T"


def _stub(monkeypatch, positions, cash):
    stmt = {"report_date": "2026-07-03", "account": "U1", "trade_count": 0,
            "positions": positions, "cash": cash}
    monkeypatch.setattr(ibkr_flex, "fetch_statement", lambda force=False: stmt)


def _pos(ticker, qty, cost):
    return {"ticker": ticker, "symbol": ticker, "currency": "USD",
            "quantity": qty, "cost_price": cost, "mark_price": 0}


class TestReconcile:
    def test_clean_match_and_cost_tolerance(self, db, monkeypatch):
        upsert_position(db, "AAPL", "Apple", "美股", "盈透U1", "USD", 150, 196.033, user_id="u1")
        db.commit()
        # cost differs by 0.0004 — inside tolerance
        _stub(monkeypatch, [_pos("AAPL", 150, 196.0334)], {})
        r = ibkr_flex.reconcile(db, "u1")
        assert r["diffs"] == []

    def test_qty_and_cost_diffs(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("NVDA", 170, 105.0)], {})
        kinds = {d["kind"] for d in ibkr_flex.reconcile(db, "u1")["diffs"]}
        assert kinds == {"qty", "cost"}

    def test_missing_both_ways(self, db, monkeypatch):
        upsert_position(db, "GOOGL", "Alphabet", "美股", "盈透U1", "USD", 60, 158.79, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("GOOG", 60, 158.79)], {})
        kinds = sorted(d["kind"] for d in ibkr_flex.reconcile(db, "u1")["diffs"])
        assert kinds == ["missing_ibkr", "missing_tracker"]

    def test_cash_diff_and_tolerance(self, db, monkeypatch):
        upsert_cash(db, "盈透U1", "USD", -6214.0, user_id="u1")
        upsert_cash(db, "盈透U1", "HKD", -114130.38, user_id="u1")
        db.commit()
        _stub(monkeypatch, [], {"USD": -6217.42, "HKD": -114130.383})
        diffs = ibkr_flex.reconcile(db, "u1")["diffs"]
        assert len(diffs) == 1 and diffs[0]["ticker"] == "USD"

    def test_non_ibkr_brokers_ignored(self, db, monkeypatch):
        upsert_position(db, "0700.HK", "腾讯", "港股", "富途", "HKD", 100, 300, user_id="u1")
        db.commit()
        _stub(monkeypatch, [], {})
        assert ibkr_flex.reconcile(db, "u1")["diffs"] == []
