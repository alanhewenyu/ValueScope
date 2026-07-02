"""YTD attribution tests: pure formulas, baseline lifecycle, migration.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import os
import sqlite3

import pytest

from backend.services.ytd_calc import held_ytd, close_ytd


# ── Pure formulas ──────────────────────────────────────────

class TestHeldYtd:
    def test_no_baseline_returns_none(self):
        assert held_ytd(100, 80, 10, None, False) is None

    def test_diluted_standard(self):
        # Held 100 @ cost 10 at baseline bp=12; no trades. Price 18.
        bd = {'price': 12.0, 'quantity': 100.0, 'cost_price': 10.0}
        # pnl - baseline_unrealized = (18-10)*100 - (12-10)*100 = 600
        assert held_ytd(18.0, 10.0, 100.0, bd, False) == pytest.approx(600.0)

    def test_diluted_partial_sell_absorbs(self):
        # Baseline 100 @ 10, bp=12. Sold 40 @ 15 via Edit (correct diluted
        # workflow: no closed_trade) → diluted cost = (100*10-40*15)/60 = 6.667.
        # Held formula ALONE gives total YTD — the realized gain is absorbed.
        bd = {'price': 12.0, 'quantity': 100.0, 'cost_price': 10.0}
        cost = (100 * 10 - 40 * 15) / 60
        held = held_ytd(18.0, cost, 60.0, bd, False)
        # True total YTD: (15-12)*40 sold + (18-12)*60 held = 480
        assert held == pytest.approx(480.0)

    def test_average_partial_sell(self):
        # Average account: cost stays 10 after selling 40. Held YTD = drift on 60.
        bd = {'price': 12.0, 'quantity': 100.0, 'cost_price': 10.0}
        held = held_ytd(18.0, 10.0, 60.0, bd, True)
        assert held == pytest.approx((18.0 - 12.0) * 60)
        sold = close_ytd(15.0, 40.0, 12.0, None)
        assert held + sold == pytest.approx(480.0)  # same truth as diluted

    def test_average_add_uses_standard_formula(self):
        # qty grew above baseline → weighted-average algebra holds.
        bd = {'price': 12.0, 'quantity': 100.0, 'cost_price': 10.0}
        # Bought 50 more @ 14 → cost = (100*10+50*14)/150 = 11.333
        cost = (100 * 10 + 50 * 14) / 150
        got = held_ytd(18.0, cost, 150.0, bd, True)
        # True YTD: old shares from bp, new from cost: (18-12)*100 + (18-14)*50 = 800
        assert got == pytest.approx(800.0)

    def test_mid_year_position_baseline_at_cost(self):
        # New position: baseline price == cost → YTD from cost.
        bd = {'price': 85.3, 'quantity': 40.0, 'cost_price': 85.3}
        assert held_ytd(90.0, 85.3, 40.0, bd, False) == pytest.approx((90.0 - 85.3) * 40)
        assert held_ytd(90.0, 82.68, 20.0, {'price': 82.68, 'quantity': 20.0, 'cost_price': 82.68}, True) \
            == pytest.approx((90.0 - 82.68) * 20)


class TestCloseYtd:
    def test_with_baseline(self):
        assert close_ytd(108.3, 30.0, 101.91, 0.0) == pytest.approx((108.3 - 101.91) * 30)

    def test_without_baseline_falls_back_to_realized(self):
        assert close_ytd(108.3, 30.0, None, 1416.75) == 1416.75

    def test_missing_details_falls_back(self):
        assert close_ytd(None, 30.0, 101.91, 999.0) == 999.0


# ── DB lifecycle ───────────────────────────────────────────

@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolated portfolio DB with full schema + migrations."""
    path = str(tmp_path / "test_portfolio.db")
    from backend.services import portfolio_db as pdb
    monkeypatch.setattr(pdb, 'DB_PATH', path)
    pdb.init_db(path)
    conn = pdb.get_conn(path)
    yield conn, pdb
    conn.close()


class TestBaselineLifecycle:
    def test_new_position_creates_baseline_at_cost(self, db):
        conn, pdb = db
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 10, 150.0)
        conn.commit()
        from datetime import datetime
        year = datetime.now().year
        b = pdb.get_ytd_baselines(conn, year)
        assert b[('AAPL', 'IB')]['price'] == 150.0
        assert b[('AAPL', 'IB')]['cost_price'] == 150.0
        assert b[('AAPL', 'IB')]['quantity'] == 10

    def test_update_does_not_reset_baseline(self, db):
        conn, pdb = db
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 10, 150.0)
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 20, 160.0)  # add
        conn.commit()
        from datetime import datetime
        b = pdb.get_ytd_baselines(conn, datetime.now().year)
        assert b[('AAPL', 'IB')]['price'] == 150.0  # unchanged

    def test_rebuy_after_full_close_resets_baseline(self, db):
        conn, pdb = db
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 10, 150.0)
        conn.execute("DELETE FROM positions WHERE ticker='AAPL'")  # full close
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 5, 200.0)  # re-buy
        conn.commit()
        from datetime import datetime
        b = pdb.get_ytd_baselines(conn, datetime.now().year)
        assert b[('AAPL', 'IB')]['price'] == 200.0  # reset to new cost
        assert b[('AAPL', 'IB')]['quantity'] == 5

    def test_same_ticker_two_brokers_independent(self, db):
        conn, pdb = db
        pdb.upsert_position(conn, 'CRCL', 'Circle', '美股', '富途', 'USD', 40, 85.3)
        pdb.upsert_position(conn, 'CRCL', 'Circle', '美股', '盈透', 'USD', 20, 82.68)
        conn.commit()
        from datetime import datetime
        b = pdb.get_ytd_baselines(conn, datetime.now().year)
        assert b[('CRCL', '富途')]['price'] == 85.3
        assert b[('CRCL', '盈透')]['price'] == 82.68


class TestLockedAttribution:
    def _setup(self, conn, pdb, cost_method='average'):
        pdb.upsert_account_setting(conn, broker='IB', capital_mode='cost',
                                   cost_method=cost_method)
        conn.execute("INSERT OR REPLACE INTO fx_rates (currency, rate_to_cny) VALUES ('USD', 7.0)")

    def test_average_partial_from_baseline(self, db):
        conn, pdb = db
        self._setup(conn, pdb, 'average')
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 10, 150.0)
        conn.commit()
        # Sell 4 @ 180; realized (avg cost) = (180-150)*4 = 120, cny = 840
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='AAPL', broker='IB', market='美股', currency='USD',
            quantity=4, close_price=180.0, realized_pnl=120.0, realized_pnl_cny=840.0)
        # baseline bp = cost 150 → (180-150)*4 * implied_fx(7.0) = 840
        assert locked == pytest.approx(840.0)

    def test_diluted_full_close_subtracts_baseline_unrealized_once(self, db):
        conn, pdb = db
        self._setup(conn, pdb, 'diluted')
        # Baseline: 100 @ cost 10, bp 12 (year-start snapshot, not creation).
        pdb.upsert_position(conn, 'MT', 'Maotai', 'A股', 'IB', 'CNY', 100, 10.0)
        conn.execute("UPDATE ytd_baseline_prices SET price=12.0 WHERE ticker='MT'")
        # Edit-workflow partial sell 40 @ 15 absorbed → cost 6.667, qty 60.
        pdb.upsert_position(conn, 'MT', 'Maotai', 'A股', 'IB', 'CNY', 60, 400 / 60)
        conn.commit()
        # Final full close 60 @ 18: realized vs diluted cost = (18-6.667)*60 = 680
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='MT', broker='IB', market='A股', currency='CNY',
            quantity=60, close_price=18.0, realized_pnl=680.0, realized_pnl_cny=680.0)
        # 680 - (12-10)*100 = 480 = true total YTD (sold 40 + final 60)
        assert locked == pytest.approx(480.0)

    def test_diluted_partial_close_uses_bp(self, db):
        conn, pdb = db
        self._setup(conn, pdb, 'diluted')
        pdb.upsert_position(conn, 'MT', 'Maotai', 'A股', 'IB', 'CNY', 100, 10.0)
        conn.execute("UPDATE ytd_baseline_prices SET price=12.0 WHERE ticker='MT'")
        conn.commit()
        # Partial 40 @ 15 recorded via Close (warned-against): (15-12)*40 = 120
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='MT', broker='IB', market='A股', currency='CNY',
            quantity=40, close_price=15.0, realized_pnl=200.0, realized_pnl_cny=200.0)
        assert locked == pytest.approx(120.0)

    def test_fund_uses_average_formula_regardless_of_broker(self, db):
        conn, pdb = db
        self._setup(conn, pdb, 'diluted')
        pdb.upsert_position(conn, '001071', '华安', '基金', 'IB', 'CNY', 1000, 2.0)
        conn.execute("UPDATE ytd_baseline_prices SET price=2.5 WHERE ticker='001071'")
        conn.commit()
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='001071', broker='IB', market='基金', currency='CNY',
            quantity=400, close_price=3.0, realized_pnl=400.0, realized_pnl_cny=400.0)
        assert locked == pytest.approx((3.0 - 2.5) * 400)

    def test_locked_no_baseline_falls_back_to_realized_cny(self, db):
        conn, pdb = db
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='NOPE', broker='IB', market='美股', currency='USD',
            quantity=4, close_price=180.0, realized_pnl=120.0, realized_pnl_cny=840.0)
        assert locked == 840.0

    def test_locked_fx_table_fallback_when_realized_zero(self, db):
        conn, pdb = db
        self._setup(conn, pdb, 'average')
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 10, 150.0)
        conn.commit()
        # Sold at cost: realized 0 → implied fx unusable → table fx
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='AAPL', broker='IB', market='美股', currency='USD',
            quantity=4, close_price=150.0, realized_pnl=0.0, realized_pnl_cny=0.0)
        assert locked == pytest.approx(0.0)

    def test_locked_immune_to_baseline_reset(self, db):
        conn, pdb = db
        self._setup(conn, pdb, 'average')
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 10, 150.0)
        locked = pdb.compute_locked_ytd_cny(
            conn, ticker='AAPL', broker='IB', market='美股', currency='USD',
            quantity=10, close_price=180.0, realized_pnl=300.0, realized_pnl_cny=2100.0)
        pdb.insert_closed_trade(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD',
                                realized_pnl=300.0, realized_pnl_cny=2100.0,
                                quantity=10, close_price=180.0,
                                ytd_pnl_cny_locked=locked)
        # Full close + re-buy resets baseline to 200 — stored lock must not move.
        conn.execute("DELETE FROM positions WHERE ticker='AAPL'")
        pdb.upsert_position(conn, 'AAPL', 'Apple', '美股', 'IB', 'USD', 5, 200.0)
        conn.commit()
        row = conn.execute("SELECT ytd_pnl_cny_locked FROM closed_trades WHERE ticker='AAPL'").fetchone()
        assert row[0] == pytest.approx(2100.0)  # (180-150)*10*7


class TestBrokerMigration:
    def _make_old_schema_db(self, path):
        """DB with pre-broker ytd_baseline_prices + positions."""
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT, name TEXT, market TEXT, broker TEXT, currency TEXT,
                quantity REAL, cost_price REAL, status TEXT DEFAULT 'open',
                updated_at TEXT, created_at TEXT, user_id TEXT DEFAULT 'local');
            CREATE TABLE ytd_baseline_prices (
                year INTEGER NOT NULL, ticker TEXT NOT NULL, price REAL NOT NULL,
                currency TEXT NOT NULL, date TEXT NOT NULL, quantity REAL,
                cost_price REAL,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                user_id TEXT NOT NULL DEFAULT 'local',
                UNIQUE(year, ticker));
        """)
        return conn

    def test_single_broker_keeps_baseline_era_values(self, tmp_path):
        from backend.services.portfolio_db import _migrate_ytd_baseline_broker
        conn = self._make_old_schema_db(str(tmp_path / "old.db"))
        conn.execute("INSERT INTO positions (ticker,name,market,broker,currency,quantity,cost_price) "
                     "VALUES ('600519','茅台','A股','中信','CNY', 100, 1500)")
        # baseline-era qty/cost differ from current position (partial sell since)
        conn.execute("INSERT INTO ytd_baseline_prices (year,ticker,price,currency,date,quantity,cost_price) "
                     "VALUES (2026,'600519',1600,'CNY','2026-01-01', 200, 1400)")
        _migrate_ytd_baseline_broker(conn)
        row = conn.execute("SELECT broker, quantity, cost_price FROM ytd_baseline_prices").fetchone()
        assert row == ('中信', 200, 1400)  # broker assigned, era values kept

    def test_multi_broker_splits_per_position(self, tmp_path):
        from backend.services.portfolio_db import _migrate_ytd_baseline_broker
        conn = self._make_old_schema_db(str(tmp_path / "old2.db"))
        conn.execute("INSERT INTO positions (ticker,name,market,broker,currency,quantity,cost_price) "
                     "VALUES ('CRCL','Circle','美股','富途','USD', 40, 85.3)")
        conn.execute("INSERT INTO positions (ticker,name,market,broker,currency,quantity,cost_price) "
                     "VALUES ('CRCL','Circle','美股','盈透','USD', 20, 82.68)")
        conn.execute("INSERT INTO ytd_baseline_prices (year,ticker,price,currency,date,quantity,cost_price) "
                     "VALUES (2026,'CRCL',101.91,'USD','2026-03-06', 111, 99.145)")
        _migrate_ytd_baseline_broker(conn)
        rows = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
            "SELECT broker, price, quantity, cost_price FROM ytd_baseline_prices")}
        assert rows['富途'] == (101.91, 40, 85.3)
        assert rows['盈透'] == (101.91, 20, 82.68)

    def test_closed_ticker_keeps_legacy_row(self, tmp_path):
        from backend.services.portfolio_db import _migrate_ytd_baseline_broker
        conn = self._make_old_schema_db(str(tmp_path / "old3.db"))
        conn.execute("INSERT INTO ytd_baseline_prices (year,ticker,price,currency,date,quantity,cost_price) "
                     "VALUES (2026,'GONE',50,'USD','2026-01-01', 10, 40)")
        _migrate_ytd_baseline_broker(conn)
        row = conn.execute("SELECT broker, price FROM ytd_baseline_prices").fetchone()
        assert row == ('', 50)

    def test_idempotent(self, tmp_path):
        from backend.services.portfolio_db import _migrate_ytd_baseline_broker
        conn = self._make_old_schema_db(str(tmp_path / "old4.db"))
        _migrate_ytd_baseline_broker(conn)
        _migrate_ytd_baseline_broker(conn)  # no-op, no crash
        assert 'broker' in [r[1] for r in conn.execute("PRAGMA table_info(ytd_baseline_prices)")]
