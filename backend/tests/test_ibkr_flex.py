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

    def test_jpy_suffix_idempotent(self):
        # some statements already carry .T in the symbol — don't double-append
        assert ibkr_flex.map_ticker("6479.T", "TSEJ", "JPY") == "6479.T"
        assert ibkr_flex.map_ticker("6479.T", None, "JPY") == "6479.T"


def _stub(monkeypatch, positions, cash, trades=None, account="U1"):
    stmt = {"report_date": "2026-07-03", "account": account, "trade_count": 0,
            "positions": positions, "cash": cash, "trades": trades or []}
    monkeypatch.setattr(ibkr_flex, "fetch_statement",
                        lambda force=False: {"accounts": {account: stmt}})


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

    def test_qty_diff_and_cost_advisory(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("NVDA", 170, 105.0)], {})
        r = ibkr_flex.reconcile(db, "u1")
        # cost divergence is advisory (tax-lot vs average), not a recon diff
        assert {d["kind"] for d in r["diffs"]} == {"qty"}
        assert [c["ticker"] for c in r["cost_notes"]] == ["NVDA"]

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

    def test_multi_account_picks_mapped_statement(self, db, monkeypatch):
        upsert_position(db, "QQQ", "Invesco QQQ", "美股", "盈透", "USD", 11, 586.62, user_id="u1")
        db.commit()
        s1 = {"report_date": "2026-07-03", "account": "U16028525", "trade_count": 0,
              "positions": [_pos("AAPL", 150, 196.033)], "cash": {}}
        s2 = {"report_date": "2026-07-03", "account": "U19288500", "trade_count": 0,
              "positions": [_pos("QQQ", 11, 586.62)], "cash": {}}
        monkeypatch.setattr(ibkr_flex, "fetch_statement",
                            lambda force=False: {"accounts": {"U16028525": s1, "U19288500": s2}})
        monkeypatch.setenv("IBKR_FLEX_MAP", "Individual:U16028525,Joint:U19288500")
        monkeypatch.setattr(ibkr_flex, "_active_portfolio_name", lambda: "Joint")
        r = ibkr_flex.reconcile(db, "u1")
        assert r["account"] == "U19288500" and r["diffs"] == []

    def test_ignore_pins_to_both_values(self, db, monkeypatch):
        upsert_position(db, "0700.HK", "腾讯", "港股", "盈透U1", "HKD", 200, 332.32, user_id="u1")
        db.commit()
        _stub(monkeypatch, [], {})  # position absent at IBKR but no fills → known diff
        r = ibkr_flex.reconcile(db, "u1")
        assert len(r["diffs"]) == 1 and r["ignored"] == 0
        res = ibkr_flex.ignore_diffs(db, [{"kind": "missing_ibkr", "ticker": "0700.HK"}], "u1")
        assert res["ignored"] == [{"kind": "missing_ibkr", "ticker": "0700.HK"}]
        r2 = ibkr_flex.reconcile(db, "u1")
        assert r2["diffs"] == [] and r2["ignored"] == 1
        # tracker side moves → resurfaces
        upsert_position(db, "0700.HK", "腾讯", "港股", "盈透U1", "HKD", 300, 332.32, user_id="u1")
        db.commit()
        r3 = ibkr_flex.reconcile(db, "u1")
        assert len(r3["diffs"]) == 1 and r3["ignored"] == 0
        # clear works
        assert ibkr_flex.clear_ignores(db, "u1") == 1

    def test_cash_transactions_parse_and_ledger_sync(self, db, monkeypatch):
        xml = """<FlexQueryResponse><FlexStatements><FlexStatement accountId="U1" toDate="2026-07-10">
        <CashTransactions>
          <CashTransaction type="Dividends" symbol="300" listingExchange="SEHK" currency="HKD"
            amount="3000" settleDate="20260710" description="0300.HK DIVIDEND"/>
          <CashTransaction type="Withholding Tax" symbol="300" listingExchange="SEHK" currency="HKD"
            amount="-300" settleDate="20260710" description="0300.HK TAX"/>
          <CashTransaction type="Broker Interest Paid" symbol="" currency="USD"
            amount="-42.5" settleDate="20260710" description="USD DEBIT INT"/>
          <CashTransaction type="Deposits/Withdrawals" symbol="" currency="USD"
            amount="9999" settleDate="20260710" description="ignored type"/>
        </CashTransactions>
        </FlexStatement></FlexStatements></FlexQueryResponse>"""
        parsed = ibkr_flex._parse(xml)
        txs = parsed["accounts"]["U1"]["cash_transactions"]
        assert len(txs) == 3
        assert txs[0]["ticker"] == "0300.HK" and txs[0]["amount"] == 3000
        # ledger sync is idempotent
        stmt = parsed["accounts"]["U1"]
        assert ibkr_flex._sync_cash_transactions(db, stmt, "u1") == 3
        assert ibkr_flex._sync_cash_transactions(db, stmt, "u1") == 0
        net = db.execute(
            "SELECT SUM(amount) FROM dividend_log WHERE user_id='u1' AND ticker='0300.HK'"
        ).fetchone()[0]
        assert net == 2700

    def test_fx_conversion_trades_excluded(self):
        xml = """<FlexQueryResponse><FlexStatements><FlexStatement accountId="U1" toDate="2026-07-10">
        <OpenPositions></OpenPositions>
        <Trades>
          <Trade symbol="USD.JPY" quantity="-0.22" tradePrice="162.4" tradeDate="20260710" currency="JPY"/>
          <Trade symbol="ECL" quantity="10" tradePrice="274.0" tradeDate="20260709" currency="USD"/>
        </Trades>
        </FlexStatement></FlexStatements></FlexQueryResponse>"""
        parsed = ibkr_flex._parse(xml)
        trades = parsed["accounts"]["U1"]["trades"]
        assert len(trades) == 1 and trades[0]["ticker"] == "ECL"
        assert trades[0]["date"] == "2026-07-09"

    def test_multi_account_unmapped_returns_none(self, db, monkeypatch):
        s = {"report_date": "2026-07-03", "account": "U1", "trade_count": 0,
             "positions": [], "cash": {}}
        monkeypatch.setattr(ibkr_flex, "fetch_statement",
                            lambda force=False: {"accounts": {"U1": s, "U2": dict(s, account="U2")}})
        monkeypatch.setenv("IBKR_FLEX_MAP", "")
        monkeypatch.setattr(ibkr_flex, "_active_portfolio_name", lambda: None)
        assert ibkr_flex.reconcile(db, "u1") is None


class TestApplyDiffs:
    def test_apply_cash_and_cost(self, db, monkeypatch):
        upsert_position(db, "TXN", "TI", "美股", "盈透U1", "USD", 10, 288.101, user_id="u1")
        upsert_cash(db, "盈透U1", "USD", -8993.0, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("TXN", 10, 285.9)], {"USD": -9007.06})
        res = ibkr_flex.apply_diffs(
            db, [{"kind": "cost", "ticker": "TXN"}, {"kind": "cash", "ticker": "USD"}], "u1")
        assert [(d["kind"], d["ticker"]) for d in res["applied"]] == [
            ("cost", "TXN"), ("cash", "USD")]
        assert res["skipped"] == []
        assert db.execute("SELECT cost_price FROM positions WHERE ticker='TXN'").fetchone()[0] == 285.9
        assert db.execute("SELECT balance FROM cash_balances WHERE currency='USD'").fetchone()[0] == -9007.06
        # diffs now clear
        assert ibkr_flex.reconcile(db, "u1")["diffs"] == []

    def test_apply_new_currency_reuses_account_name(self, db, monkeypatch):
        upsert_cash(db, "盈透U1", "USD", 100.0, user_id="u1")
        db.commit()
        _stub(monkeypatch, [], {"USD": 100.0, "JPY": -36.23})
        res = ibkr_flex.apply_diffs(db, [{"kind": "cash", "ticker": "JPY"}], "u1")
        assert res["applied"][0]["value"] == -36.23
        row = db.execute("SELECT account, balance FROM cash_balances WHERE currency='JPY'").fetchone()
        assert row[0] == "盈透U1" and row[1] == -36.23

    def test_apply_missing_tracker_creates_position(self, db, monkeypatch):
        upsert_position(db, "AAPL", "Apple", "美股", "盈透U1", "USD", 150, 196.033, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("AAPL", 150, 196.033),
                            dict(_pos("ECL", 10, 274.0), name="ECOLAB INC")], {})
        res = ibkr_flex.apply_diffs(db, [{"kind": "missing_tracker", "ticker": "ECL"}], "u1")
        assert res["applied"] == [{"kind": "missing_tracker", "ticker": "ECL", "value": 10}]
        row = db.execute("SELECT name, market, broker, quantity, cost_price FROM positions WHERE ticker='ECL'").fetchone()
        assert tuple(row) == ("ECOLAB INC", "美股", "盈透U1", 10, 274.0)
        # YTD baseline seeded at cost for the new position
        bl = db.execute("SELECT price FROM ytd_baseline_prices WHERE ticker='ECL'").fetchone()
        assert bl and bl[0] == 274.0
        assert ibkr_flex.reconcile(db, "u1")["diffs"] == []

    def test_missing_ibkr_without_fills_falls_back_to_manual(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [], {})  # position gone at IBKR, but no fills in window
        res = ibkr_flex.apply_diffs(db, [{"kind": "missing_ibkr", "ticker": "NVDA"}], "u1")
        assert res["applied"] == [] and res["skipped"][0]["reason"] == "no_trade_details"
        assert db.execute("SELECT quantity FROM positions WHERE ticker='NVDA'").fetchone()[0] == 160

    def test_stale_diffs_skipped(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("NVDA", 160, 102.661)], {})
        res = ibkr_flex.apply_diffs(
            db, [{"kind": "cost", "ticker": "NVDA"}], "u1")  # not in current diffs
        assert res["applied"] == []
        assert {s["reason"] for s in res["skipped"]} == {"stale_diff"}

    def test_apply_qty_buy_copies_broker_average(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("NVDA", 170, 105.5)], {})
        res = ibkr_flex.apply_diffs(db, [{"kind": "qty", "ticker": "NVDA"}], "u1")
        assert res["applied"][0]["value"] == 170
        row = db.execute("SELECT quantity, cost_price FROM positions WHERE ticker='NVDA'").fetchone()
        assert tuple(row) == (170, 105.5)
        # no realized P&L on a buy
        assert db.execute("SELECT COUNT(*) FROM closed_trades").fetchone()[0] == 0

    def test_apply_qty_sell_books_closed_trade(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("NVDA", 150, 102.661)], {},
              trades=[{"ticker": "NVDA", "quantity": -10, "price": 180.0,
                       "date": "2026-07-09", "currency": "USD"}])
        res = ibkr_flex.apply_diffs(db, [{"kind": "qty", "ticker": "NVDA"}], "u1")
        assert res["applied"][0]["value"] == 150
        assert db.execute("SELECT quantity FROM positions WHERE ticker='NVDA'").fetchone()[0] == 150
        ct = db.execute("SELECT quantity, close_price, realized_pnl, close_date FROM closed_trades").fetchone()
        assert tuple(ct)[:2] == (10, 180.0)
        assert abs(ct[2] - (180.0 - 102.661) * 10) < 1e-6
        assert ct[3] == "2026-07-09"

    def test_apply_sell_without_fills_skipped(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [_pos("NVDA", 150, 102.661)], {})  # no trade details
        res = ibkr_flex.apply_diffs(db, [{"kind": "qty", "ticker": "NVDA"}], "u1")
        assert res["applied"] == []
        assert res["skipped"][0]["reason"] == "no_trade_details"
        assert db.execute("SELECT quantity FROM positions WHERE ticker='NVDA'").fetchone()[0] == 160

    def test_apply_full_close_books_and_deletes(self, db, monkeypatch):
        upsert_position(db, "NVDA", "Nvidia", "美股", "盈透U1", "USD", 160, 102.661, user_id="u1")
        db.commit()
        _stub(monkeypatch, [], {},
              trades=[{"ticker": "NVDA", "quantity": -100, "price": 180.0,
                       "date": "2026-07-09", "currency": "USD"},
                      {"ticker": "NVDA", "quantity": -60, "price": 181.0,
                       "date": "2026-07-09", "currency": "USD"}])
        res = ibkr_flex.apply_diffs(db, [{"kind": "missing_ibkr", "ticker": "NVDA"}], "u1")
        assert res["applied"][0]["value"] == 0
        assert db.execute("SELECT COUNT(*) FROM positions WHERE ticker='NVDA' AND quantity>0").fetchone()[0] == 0
        ct = db.execute("SELECT quantity, close_price FROM closed_trades").fetchone()
        assert ct[0] == 160
        assert abs(ct[1] - (100 * 180.0 + 60 * 181.0) / 160) < 1e-9
