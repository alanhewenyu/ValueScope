"""TWR unitization tests: inception, flow handling, weekend gaps, edge cases.

Run: .venv/bin/python -m pytest backend/tests/ -q
"""
import os

import pytest

from backend.services.portfolio_db import (
    init_db, get_conn, upsert_snapshot, add_deposit_record, roll_units,
    compute_capital, upsert_cash,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "twr_test.db")
    init_db(path)
    conn = get_conn(path)
    yield conn
    conn.close()


def _snap(conn, date, net_assets, user="u1"):
    """Roll units and persist a snapshot, mirroring take_snapshot's flow."""
    res = roll_units(conn, user, date, net_assets)
    units, unit_nav = res if res else (None, None)
    upsert_snapshot(conn, date, net_assets, net_assets, net_assets, 0, 0, 0,
                    user_id=user, units=units, unit_nav=unit_nav)
    conn.commit()
    return units, unit_nav


class TestInception:
    def test_first_snapshot_incepts_at_one(self, db):
        units, nav = _snap(db, "2026-07-01", 100000)
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(100000)

    def test_zero_assets_not_unitized(self, db):
        res = roll_units(db, "u1", "2026-07-01", 0)
        assert res is None

    def test_history_before_inception_ignored(self, db):
        # A dated legacy flow BEFORE inception must not distort T0
        add_deposit_record(db, "IBKR", 50000, deposit_date="2026-01-15", user_id="u1")
        units, nav = _snap(db, "2026-07-01", 100000)
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(100000)


class TestContinuitySeed:
    def test_inception_continues_legacy_ratio(self, db):
        # T0 seed = NAV/Capital so the published curve has no seam
        res = roll_units(db, "u1", "2026-07-04", 150000, capital=100000)
        assert res is not None
        units, nav = res
        assert nav == pytest.approx(1.5)
        assert units == pytest.approx(100000)

    def test_rolls_forward_from_seeded_nav(self, db):
        upsert_snapshot(db, "2026-07-04", 150000, 150000, 150000, 0, 0, 0,
                        user_id="u1", units=100000, unit_nav=1.5)
        db.commit()
        res = roll_units(db, "u1", "2026-07-06", 165000)
        assert res is not None
        units, nav = res
        assert nav == pytest.approx(1.65)
        assert units == pytest.approx(100000)

    def test_zero_capital_falls_back_to_one(self, db):
        res = roll_units(db, "u1", "2026-07-04", 50000, capital=0)
        assert res is not None
        units, nav = res
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(50000)


class TestRolling:
    def test_market_gain_moves_nav_not_units(self, db):
        _snap(db, "2026-07-01", 100000)
        units, nav = _snap(db, "2026-07-02", 105000)
        assert nav == pytest.approx(1.05)
        assert units == pytest.approx(100000)

    def test_deposit_moves_units_not_nav(self, db):
        _snap(db, "2026-07-01", 100000)
        # Deposit 50k on 07-02; market flat → NAV must stay 1.0
        add_deposit_record(db, "IBKR", 50000, deposit_date="2026-07-02", user_id="u1")
        units, nav = _snap(db, "2026-07-02", 150000)
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(150000)

    def test_deposit_plus_gain_separates_cleanly(self, db):
        _snap(db, "2026-07-01", 100000)
        # Deposit 50k AND the original 100k gained 2% → nav 1.02
        add_deposit_record(db, "IBKR", 50000, deposit_date="2026-07-02", user_id="u1")
        units, nav = _snap(db, "2026-07-02", 152000)
        assert nav == pytest.approx(1.02)
        assert units == pytest.approx(100000 + 50000 / 1.02)

    def test_withdrawal_redeems_units(self, db):
        _snap(db, "2026-07-01", 100000)
        add_deposit_record(db, "IBKR", -30000, deposit_date="2026-07-02", user_id="u1")
        units, nav = _snap(db, "2026-07-02", 70000)
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(70000)

    def test_weekend_flow_rolls_into_next_snapshot(self, db):
        # Snapshots skip Sun/Mon; a Saturday deposit lands in Tuesday's roll
        _snap(db, "2026-07-03", 100000)  # Friday
        add_deposit_record(db, "IBKR", 20000, deposit_date="2026-07-04", user_id="u1")  # Sat
        units, nav = _snap(db, "2026-07-07", 120000)  # Tuesday
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(120000)

    def test_users_are_isolated(self, db):
        _snap(db, "2026-07-01", 100000, user="u1")
        add_deposit_record(db, "IBKR", 99999, deposit_date="2026-07-02", user_id="u2")
        _, nav = _snap(db, "2026-07-02", 100000, user="u1")
        assert nav == pytest.approx(1.0)  # u2's flow must not touch u1


class TestEdgeCases:
    def test_undated_flow_ignored(self, db):
        _snap(db, "2026-07-01", 100000)
        add_deposit_record(db, "IBKR", 50000, deposit_date="", user_id="u1")
        _, nav = _snap(db, "2026-07-02", 100000)
        assert nav == pytest.approx(1.0)

    def test_flow_larger_than_assets_reincepts(self, db):
        _snap(db, "2026-07-01", 100000)
        # Bad data: flow claims more than total assets → engine re-incepts
        add_deposit_record(db, "IBKR", 500000, deposit_date="2026-07-02", user_id="u1")
        units, nav = _snap(db, "2026-07-02", 120000)
        assert nav == pytest.approx(1.0)
        assert units == pytest.approx(120000)


class TestCashCoupling:
    def test_update_cash_moves_balance(self, db):
        add_deposit_record(db, "IBKR", 71000, fx_rate=7.1, deposit_date="2026-07-02",
                           user_id="u1", currency="USD", amount=10000, update_cash=True)
        row = db.execute(
            "SELECT balance FROM cash_balances WHERE account='IBKR' AND currency='USD' AND user_id='u1'"
        ).fetchone()
        assert row[0] == pytest.approx(10000)

    def test_withdrawal_decreases_balance(self, db):
        add_deposit_record(db, "IBKR", 71000, fx_rate=7.1, deposit_date="2026-07-02",
                           user_id="u1", currency="USD", amount=10000, update_cash=True)
        add_deposit_record(db, "IBKR", -35500, fx_rate=7.1, deposit_date="2026-07-03",
                           user_id="u1", currency="USD", amount=-5000, update_cash=True)
        row = db.execute(
            "SELECT balance FROM cash_balances WHERE account='IBKR' AND currency='USD' AND user_id='u1'"
        ).fetchone()
        assert row[0] == pytest.approx(5000)


class TestCapitalBase:
    """Unified capital: frozen opening value + net dated flows."""

    def test_freeze_then_flows(self, db):
        assert compute_capital(db, {}, 'u1') == 0  # freeze at 0 (empty accounts)
        add_deposit_record(db, 'IBKR', 100000, deposit_date='2099-01-02', user_id='u1')
        assert compute_capital(db, {}, 'u1') == pytest.approx(100000)
        add_deposit_record(db, 'IBKR', -30000, deposit_date='2099-01-03', user_id='u1')
        assert compute_capital(db, {}, 'u1') == pytest.approx(70000)

    def test_cash_edits_no_longer_move_capital(self, db):
        # Legacy cost-mode let dividends/fees leak into 本金 via the cash
        # term; frozen-base capital only moves on flows
        compute_capital(db, {}, 'u1')
        upsert_cash(db, 'IBKR', 'USD', 99999, user_id='u1')
        assert compute_capital(db, {}, 'u1') == 0

    def test_users_frozen_independently(self, db):
        compute_capital(db, {}, 'u1')
        add_deposit_record(db, 'IBKR', 50000, deposit_date='2099-01-02', user_id='u2')
        assert compute_capital(db, {}, 'u1') == 0
        assert compute_capital(db, {}, 'u2') == pytest.approx(50000)
