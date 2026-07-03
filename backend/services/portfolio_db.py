# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Portfolio database schema, migrations, and CRUD operations.

Extracted from portfolio-tracker/db.py — genericized for any user.
All personal configuration (broker names, capital amounts) comes from
environment variables, never hardcoded.
"""

from __future__ import annotations

import json
import sqlite3
import os
from datetime import datetime
from typing import Any

import logging

logger = logging.getLogger("valuescope.portfolio")

# ── Database path ──
DB_PATH = os.environ.get(
    'PORTFOLIO_DB_PATH',
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 'data', 'portfolio.db'),
)

# ── Multi-portfolio support ──
# Format: PORTFOLIOS=Name1:file1.db,Name2:file2.db
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')


def _parse_portfolios() -> list[tuple[str, str]]:
    """Parse PORTFOLIOS env var into [(name, abs_path), ...]."""
    raw = os.environ.get('PORTFOLIOS', '').strip()
    if not raw:
        return []
    result = []
    for item in raw.split(','):
        item = item.strip()
        if ':' not in item:
            continue
        name, path = item.split(':', 1)
        name, path = name.strip(), path.strip()
        if not os.path.isabs(path):
            path = os.path.join(_DATA_DIR, path)
        result.append((name, path))
    return result


PORTFOLIOS = _parse_portfolios()


# ── Capital configuration (all from env, no hardcoded values) ──
# Deposit mode: track capital as fixed deposit amount (advanced)
# Cost mode: capital = sum of position costs (default for new users)
DEPOSIT_CAPITAL = float(os.environ.get('DEPOSIT_CAPITAL', '0'))
DEPOSIT_FX_RATE = float(os.environ.get('DEPOSIT_FX_RATE', '1.0'))
B_SHARE_CAPITAL = float(os.environ.get('B_SHARE_CAPITAL', '0'))
DEPOSIT_MODE = DEPOSIT_CAPITAL > 0 or B_SHARE_CAPITAL > 0

# Brokers covered by deposit capital (comma-separated from env)
# e.g. DEPOSIT_BROKERS=Broker_A,Broker_B
_raw_brokers = os.environ.get('DEPOSIT_BROKERS', '').strip()
DEPOSIT_BROKERS: set[str] = set(b.strip() for b in _raw_brokers.split(',') if b.strip()) if _raw_brokers else set()


def set_active_portfolio(db_path: str, capital: float = 0,
                         deposit_fx: float = 1.0, b_capital: float = 0,
                         deposit_brokers: set[str] | None = None):
    """Switch the active database.

    Capital configuration now lives in each DB's account_settings table,
    so only DB_PATH needs to change. Legacy params kept for compatibility.
    """
    global DB_PATH
    DB_PATH = db_path


# ── Schema ──

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS positions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT NOT NULL,
    name        TEXT NOT NULL,
    market      TEXT NOT NULL,
    broker      TEXT NOT NULL,
    currency    TEXT NOT NULL,
    quantity    REAL NOT NULL DEFAULT 0,
    cost_price  REAL NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'open',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS closed_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT,
    name         TEXT NOT NULL,
    market       TEXT NOT NULL,
    broker       TEXT NOT NULL,
    currency     TEXT NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    close_date   TEXT,
    notes        TEXT,
    quantity     REAL,
    cost_price   REAL,
    close_price  REAL,
    cost_total   REAL,
    ytd_pnl_cny_locked REAL
);

CREATE TABLE IF NOT EXISTS cash_balances (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account    TEXT NOT NULL,
    currency   TEXT NOT NULL,
    balance    REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(account, currency)
);

CREATE TABLE IF NOT EXISTS nav_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL UNIQUE,
    net_asset_value  REAL,
    capital_invested REAL,
    pnl              REAL,
    equity_nav       REAL,
    benchmark_value  REAL
);

CREATE TABLE IF NOT EXISTS fx_rates (
    currency   TEXT PRIMARY KEY,
    rate_to_cny REAL NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS margin_balances (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    broker     TEXT NOT NULL,
    category   TEXT NOT NULL,
    currency   TEXT NOT NULL DEFAULT 'CNY',
    amount     REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(broker, category, currency)
);

CREATE TABLE IF NOT EXISTS industry_cache (
    ticker     TEXT PRIMARY KEY,
    sector     TEXT,
    industry   TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS account_settings (
    broker        TEXT PRIMARY KEY,
    capital_mode  TEXT NOT NULL DEFAULT 'cost',
    deposit_cny   REAL NOT NULL DEFAULT 0,
    deposit_fx    REAL NOT NULL DEFAULT 1.0,
    notes         TEXT,
    cost_method   TEXT NOT NULL DEFAULT 'diluted',
    updated_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS deposit_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    broker       TEXT NOT NULL,
    amount_cny   REAL NOT NULL,
    fx_rate      REAL NOT NULL DEFAULT 1.0,
    deposit_date TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_deposit_broker ON deposit_history(broker);

CREATE TABLE IF NOT EXISTS daily_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL UNIQUE,
    total_assets  REAL,
    net_assets    REAL,
    equity_mv_cny REAL,
    cash_cny      REAL,
    leverage_cny  REAL,
    total_pnl_cny REAL,
    market_data   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS snapshot_market_detail (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date     TEXT NOT NULL,
    market   TEXT NOT NULL,
    currency TEXT NOT NULL,
    mv       REAL NOT NULL DEFAULT 0,
    UNIQUE(date, market, currency)
);

CREATE TABLE IF NOT EXISTS ytd_baseline_prices (
    year       INTEGER NOT NULL,
    ticker     TEXT NOT NULL,
    broker     TEXT NOT NULL DEFAULT '',
    price      REAL NOT NULL,
    currency   TEXT NOT NULL,
    date       TEXT NOT NULL,
    quantity   REAL,
    cost_price REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    user_id    TEXT NOT NULL DEFAULT 'local',
    UNIQUE(year, ticker, broker, user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_ticker_broker ON positions(ticker, broker);
CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market);
CREATE INDEX IF NOT EXISTS idx_positions_broker ON positions(broker);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_closed_market ON closed_trades(market);
CREATE INDEX IF NOT EXISTS idx_smd_date ON snapshot_market_detail(date);
CREATE INDEX IF NOT EXISTS idx_ytd_year ON ytd_baseline_prices(year);
"""


# ── Connection ──

def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Migrations (all idempotent) ──

def _migrate_closed_trades(conn):
    """Add quantity/cost/price/pnl_cny columns to closed_trades."""
    for col, col_type in [
        ('quantity', 'REAL'), ('cost_price', 'REAL'), ('close_price', 'REAL'),
        ('cost_total', 'REAL'), ('realized_pnl_cny', 'REAL'),
        ('ytd_pnl_cny_locked', 'REAL'),
    ]:
        try:
            conn.execute(f"ALTER TABLE closed_trades ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass


def _migrate_margin_multi_currency(conn):
    """Migrate margin_balances UNIQUE to (broker, category, currency)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='margin_balances'"
    ).fetchone()
    if not row:
        return
    ddl = row[0] if isinstance(row, (tuple, list)) else row['sql']
    if 'UNIQUE(broker, category, currency)' in ddl:
        return
    conn.execute("""
        CREATE TABLE IF NOT EXISTS margin_balances_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT, broker TEXT NOT NULL,
            category TEXT NOT NULL, currency TEXT NOT NULL DEFAULT 'CNY',
            amount REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            UNIQUE(broker, category, currency))""")
    conn.execute("""
        INSERT OR IGNORE INTO margin_balances_new (broker, category, currency, amount, updated_at)
        SELECT broker, category, currency, amount, updated_at FROM margin_balances""")
    conn.execute("DROP TABLE margin_balances")
    conn.execute("ALTER TABLE margin_balances_new RENAME TO margin_balances")
    conn.commit()


def _migrate_snapshot_market_data(conn):
    try:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN market_data TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_positions_created_at(conn):
    try:
        conn.execute("ALTER TABLE positions ADD COLUMN created_at TEXT")
    except sqlite3.OperationalError:
        return
    conn.execute("UPDATE positions SET created_at = updated_at WHERE created_at IS NULL")
    conn.commit()


def _migrate_snapshot_capital(conn):
    try:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN capital REAL")
    except sqlite3.OperationalError:
        pass


def _migrate_snapshot_market_pnl(conn):
    try:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN market_pnl TEXT")
    except sqlite3.OperationalError:
        pass


def _migrate_snapshot_realized_pnl(conn):
    try:
        conn.execute("ALTER TABLE daily_snapshots ADD COLUMN realized_pnl_cny REAL")
    except sqlite3.OperationalError:
        pass
    nulls = conn.execute(
        "SELECT date FROM daily_snapshots WHERE realized_pnl_cny IS NULL"
    ).fetchall()
    if nulls:
        for row in nulls:
            sd = row[0]
            rpnl = conn.execute("""
                SELECT COALESCE(SUM(realized_pnl_cny), 0) FROM closed_trades
                WHERE close_date IS NULL OR close_date <= ?
            """, (sd,)).fetchone()[0]
            conn.execute(
                "UPDATE daily_snapshots SET realized_pnl_cny = ? WHERE date = ?",
                (rpnl, sd))


def _migrate_snapshot_stock_pnl(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_stock_pnl (
            date TEXT NOT NULL, ticker TEXT NOT NULL, name TEXT,
            market TEXT, pnl_cny REAL DEFAULT 0,
            PRIMARY KEY (date, ticker))""")


def _migrate_backfill_realized_pnl_cny(conn):
    """Backfill realized_pnl_cny for existing closed trades."""
    count = conn.execute(
        "SELECT COUNT(*) FROM closed_trades WHERE realized_pnl_cny IS NOT NULL"
    ).fetchone()[0]
    if count > 0:
        return
    fx = {'CNY': 1.0, 'USD': 6.897, 'HKD': 0.882, 'JPY': 0.04378}
    for row in conn.execute("SELECT currency, rate_to_cny FROM fx_rates"):
        fx[row[0]] = row[1]
    for row in conn.execute("SELECT id, currency, realized_pnl FROM closed_trades"):
        rate = fx.get(row['currency'], 1.0)
        pnl_cny = row['realized_pnl'] * rate
        conn.execute("UPDATE closed_trades SET realized_pnl_cny=? WHERE id=?",
                      (pnl_cny, row['id']))
    conn.commit()


def _migrate_backfill_market_detail(conn):
    """Backfill snapshot_market_detail from existing market_data JSON."""
    count = conn.execute("SELECT COUNT(*) FROM snapshot_market_detail").fetchone()[0]
    if count > 0:
        return
    rows = conn.execute(
        "SELECT date, market_data FROM daily_snapshots WHERE market_data IS NOT NULL"
    ).fetchall()
    for date_val, md_json in rows:
        try:
            data = json.loads(md_json)
        except Exception:
            continue
        for market, val in data.items():
            if isinstance(val, dict):
                for cur, mv in val.items():
                    conn.execute("""
                        INSERT OR IGNORE INTO snapshot_market_detail (date, market, currency, mv)
                        VALUES (?, ?, ?, ?)""", (date_val, market, cur, mv))
            else:
                conn.execute("""
                    INSERT OR IGNORE INTO snapshot_market_detail (date, market, currency, mv)
                    VALUES (?, ?, 'CNY', ?)""", (date_val, market, val))
    conn.commit()


def _migrate_ytd_add_qty_cost(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ytd_baseline_prices)").fetchall()]
    if 'quantity' in cols:
        return
    conn.execute("ALTER TABLE ytd_baseline_prices ADD COLUMN quantity REAL")
    conn.execute("ALTER TABLE ytd_baseline_prices ADD COLUMN cost_price REAL")
    conn.execute("""
        UPDATE ytd_baseline_prices
        SET quantity = (SELECT SUM(p.quantity) FROM positions p
                        WHERE p.ticker = ytd_baseline_prices.ticker AND p.status = 'open'),
            cost_price = (SELECT p.cost_price FROM positions p
                          WHERE p.ticker = ytd_baseline_prices.ticker AND p.status = 'open'
                          LIMIT 1)""")
    conn.commit()


def _migrate_stock_pnl_add_market_pk(conn):
    pk_cols = [r[1] for r in conn.execute("PRAGMA table_info(snapshot_stock_pnl)").fetchall()
               if r[5] > 0]
    if 'market' in pk_cols:
        return
    conn.executescript("""
        DROP TABLE IF EXISTS snapshot_stock_pnl;
        CREATE TABLE snapshot_stock_pnl (
            date TEXT NOT NULL, ticker TEXT NOT NULL, name TEXT,
            market TEXT NOT NULL DEFAULT '', pnl_cny REAL DEFAULT 0,
            PRIMARY KEY (date, ticker, market));""")


def _migrate_backfill_stock_pnl_ytd_base(conn):
    """Backfill snapshot_stock_pnl for the YTD base date."""
    cur_year = datetime.now().year
    row = conn.execute(
        "SELECT MAX(date) FROM snapshot_market_detail WHERE date < ?",
        (f'{cur_year}-01-01',)).fetchone()
    if not row or not row[0]:
        row = conn.execute(
            "SELECT MIN(date) FROM snapshot_market_detail WHERE date >= ?",
            (f'{cur_year}-01-01',)).fetchone()
    if not row or not row[0]:
        return
    base_date = row[0]
    existing = conn.execute(
        "SELECT COUNT(*) FROM snapshot_stock_pnl WHERE date = ?", (base_date,)
    ).fetchone()[0]
    if existing > 0:
        return
    fx = {'CNY': 1.0}
    for r in conn.execute("SELECT currency, rate_to_cny FROM fx_rates"):
        fx[r[0]] = r[1]
    if not fx.get('USD'):
        return
    pos_info = {}
    for r in conn.execute("SELECT ticker, name, market FROM positions"):
        pos_info[r[0]] = (r[1], r[2])
    stock_pnl = {}
    for r in conn.execute(
        "SELECT ticker, price, currency, quantity, cost_price "
        "FROM ytd_baseline_prices WHERE year = ?", (cur_year,)
    ).fetchall():
        tk, price, cur = r[0], r[1], r[2]
        qty = r[3] if r[3] is not None else 0
        cost = r[4] if r[4] is not None else price
        pnl_cny = (price - cost) * qty * fx.get(cur, 1.0)
        name, market = pos_info.get(tk, (tk, ''))
        key = (tk, market)
        if key in stock_pnl:  # multiple broker rows per ticker — accumulate
            stock_pnl[key]['pnl_cny'] += pnl_cny
        else:
            stock_pnl[key] = {'name': name, 'market': market, 'pnl_cny': pnl_cny}
    for r in conn.execute(
        "SELECT ticker, name, market, realized_pnl_cny FROM closed_trades "
        "WHERE (close_date IS NULL OR close_date <= ?) AND realized_pnl_cny IS NOT NULL",
        (base_date,)
    ).fetchall():
        tk, nm, mkt, rpnl = r[0], r[1], r[2] or '', r[3]
        key = (tk, mkt)
        if key in stock_pnl:
            stock_pnl[key]['pnl_cny'] += rpnl
        else:
            stock_pnl[key] = {'name': nm, 'market': mkt, 'pnl_cny': rpnl}
    for (tk, _mkt), sp in stock_pnl.items():
        conn.execute(
            "INSERT OR IGNORE INTO snapshot_stock_pnl "
            "(date, ticker, name, market, pnl_cny) VALUES (?, ?, ?, ?, ?)",
            (base_date, tk, sp['name'], sp['market'], sp['pnl_cny']))
    conn.commit()


# ── Init ──

def init_db(db_path: str | None = None) -> None:
    """Initialize database schema and run all migrations."""
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_closed_trades(conn)
        _migrate_margin_multi_currency(conn)
        _migrate_snapshot_market_data(conn)
        _migrate_positions_created_at(conn)
        _migrate_snapshot_capital(conn)
        _migrate_snapshot_market_pnl(conn)
        _migrate_snapshot_realized_pnl(conn)
        _migrate_snapshot_stock_pnl(conn)
        _migrate_backfill_realized_pnl_cny(conn)
        _migrate_backfill_market_detail(conn)
        _migrate_ytd_add_qty_cost(conn)
        _migrate_stock_pnl_add_market_pk(conn)
        _migrate_backfill_stock_pnl_ytd_base(conn)
        _migrate_seed_account_settings(conn)
        _migrate_add_user_id(conn)
        _migrate_add_cost_method(conn)
        _migrate_ytd_baseline_broker(conn)
        _migrate_snapshot_unique_per_user(conn)
        _migrate_twr_columns(conn)


def _migrate_seed_account_settings(conn):
    """Seed account_settings from env vars on first run, so existing
    configuration is preserved when switching from env to DB-driven capital.

    Only seeds for the DEFAULT portfolio (matching PORTFOLIO_DB_PATH env).
    Multi-portfolio setups manage their own settings per DB.
    """
    try:
        existing = conn.execute("SELECT COUNT(*) FROM account_settings").fetchone()[0]
        if existing > 0:
            return  # already seeded
    except Exception:
        return

    # Skip env-based seeding for non-default portfolios in multi-portfolio setup
    if PORTFOLIOS:
        default_path = os.environ.get('PORTFOLIO_DB_PATH', os.path.join(_DATA_DIR, 'portfolio.db'))
        if os.path.abspath(DB_PATH) != os.path.abspath(default_path):
            return

    # Seed from env vars (one-time migration)
    if DEPOSIT_CAPITAL > 0:
        for broker in DEPOSIT_BROKERS:
            conn.execute(
                "INSERT OR IGNORE INTO account_settings (broker, capital_mode, deposit_cny, deposit_fx) "
                "VALUES (?, 'deposit', ?, ?)",
                (broker, DEPOSIT_CAPITAL, DEPOSIT_FX_RATE))
    if B_SHARE_CAPITAL > 0:
        conn.execute(
            "INSERT OR IGNORE INTO account_settings (broker, capital_mode, deposit_cny, deposit_fx) "
            "VALUES (?, 'deposit', ?, 1.0)",
            ('B股', B_SHARE_CAPITAL))
    conn.commit()


def _migrate_add_cost_method(conn):
    """Add cost_method to account_settings (idempotent).

    'diluted' (default): broker re-averages 持仓成本 on partial sell to absorb
        realized gains (Chinese brokers, Futu). The tracker reads the new cost
        off the broker screen.
    'average': cost stays at true weighted-average buy price on partial sell;
        realized P&L is booked separately in closed_trades (Interactive Brokers).
        Stocks on such accounts are treated like funds for YTD attribution.
    """
    try:
        conn.execute(
            "ALTER TABLE account_settings ADD COLUMN cost_method TEXT NOT NULL DEFAULT 'diluted'")
    except sqlite3.OperationalError:
        pass  # already exists
    conn.commit()


def _migrate_ytd_baseline_broker(conn):
    """Re-key ytd_baseline_prices from (year, ticker) to (year, ticker, broker, user_id).

    A ticker-keyed baseline breaks when the same ticker is held in multiple
    accounts (shared bp/qty/cost corrupt every account's YTD) and when a
    position is fully closed and re-bought (stale row blocks the cost-based
    refresh).

    Backfill per old row:
      - 0 open positions (fully-closed ticker): keep one row, broker='' —
        legacy marker still readable by the closed-trades aggregation.
      - 1 open position: assign its broker; keep original qty/cost (they are
        baseline-era values the diluted algebra needs).
      - N open positions: one row per broker with that broker's current
        qty/cost and the original baseline price. Approximation — the old
        row can't be split exactly; known cases repaired via data fix.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ytd_baseline_prices)").fetchall()]
    if 'broker' in cols:
        return
    conn.execute("ALTER TABLE ytd_baseline_prices RENAME TO ytd_baseline_prices_old")
    conn.execute("""
        CREATE TABLE ytd_baseline_prices (
            year       INTEGER NOT NULL,
            ticker     TEXT NOT NULL,
            broker     TEXT NOT NULL DEFAULT '',
            price      REAL NOT NULL,
            currency   TEXT NOT NULL,
            date       TEXT NOT NULL,
            quantity   REAL,
            cost_price REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            user_id    TEXT NOT NULL DEFAULT 'local',
            UNIQUE(year, ticker, broker, user_id))""")
    old_rows = conn.execute(
        "SELECT year, ticker, price, currency, date, quantity, cost_price, created_at, user_id "
        "FROM ytd_baseline_prices_old").fetchall()
    for row in old_rows:
        year, ticker, price, currency, date_val, qty, cost, created, uid = row
        positions = conn.execute(
            "SELECT broker, quantity, cost_price FROM positions "
            "WHERE ticker=? AND status='open' AND user_id=?", (ticker, uid)).fetchall()
        if len(positions) <= 1:
            broker = positions[0][0] if positions else ''
            conn.execute(
                "INSERT OR IGNORE INTO ytd_baseline_prices "
                "(year, ticker, broker, price, currency, date, quantity, cost_price, created_at, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (year, ticker, broker, price, currency, date_val, qty, cost, created, uid))
        else:
            for b, b_qty, b_cost in positions:
                conn.execute(
                    "INSERT OR IGNORE INTO ytd_baseline_prices "
                    "(year, ticker, broker, price, currency, date, quantity, cost_price, created_at, user_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (year, ticker, b, price, currency, date_val, b_qty, b_cost, created, uid))
    conn.execute("DROP TABLE ytd_baseline_prices_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ytd_year ON ytd_baseline_prices(year)")
    conn.commit()


def _migrate_add_user_id(conn):
    """Add user_id column to user-level tables for multi-user support.

    Default 'local' preserves backward compatibility — existing data belongs
    to the implicit local user. Multi-user mode (PostgreSQL) will use real IDs.
    SQLite unique constraints can't be altered, so we recreate tables that need
    compound unique keys including user_id.
    """
    # Tables that just need the column (no unique constraint change)
    for table in ['closed_trades', 'deposit_history', 'daily_snapshots',
                  'nav_history', 'snapshot_market_detail', 'snapshot_stock_pnl',
                  'ytd_baseline_prices']:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")
        except sqlite3.OperationalError:
            pass  # already exists

    # positions: UNIQUE(ticker, broker) → UNIQUE(ticker, broker, user_id)
    _recreate_with_user_id(conn, 'positions', """
        CREATE TABLE positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL, name TEXT NOT NULL, market TEXT NOT NULL,
            broker TEXT NOT NULL, currency TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0, cost_price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open',
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            created_at TEXT,
            user_id TEXT NOT NULL DEFAULT 'local',
            UNIQUE(ticker, broker, user_id))""",
        'ticker, broker, user_id')

    # cash_balances: UNIQUE(account, currency) → UNIQUE(account, currency, user_id)
    _recreate_with_user_id(conn, 'cash_balances', """
        CREATE TABLE cash_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL, currency TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            user_id TEXT NOT NULL DEFAULT 'local',
            UNIQUE(account, currency, user_id))""",
        'account, currency, user_id')

    # margin_balances: UNIQUE(broker, category, currency) → UNIQUE(broker, category, currency, user_id)
    _recreate_with_user_id(conn, 'margin_balances', """
        CREATE TABLE margin_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL, category TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            amount REAL NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            user_id TEXT NOT NULL DEFAULT 'local',
            UNIQUE(broker, category, currency, user_id))""",
        'broker, category, currency, user_id')

    # account_settings: PRIMARY KEY(broker) → UNIQUE(broker, user_id)
    _recreate_with_user_id(conn, 'account_settings', """
        CREATE TABLE account_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL, capital_mode TEXT NOT NULL DEFAULT 'cost',
            deposit_cny REAL NOT NULL DEFAULT 0, deposit_fx REAL NOT NULL DEFAULT 1.0,
            notes TEXT,
            cost_method TEXT NOT NULL DEFAULT 'diluted',
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            user_id TEXT NOT NULL DEFAULT 'local',
            UNIQUE(broker, user_id))""",
        'broker, user_id')

    # Rebuild indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_user ON positions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cash_user ON cash_balances(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_closed_user ON closed_trades(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_margin_user ON margin_balances(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_settings_user ON account_settings(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deposit_user ON deposit_history(user_id)")
    conn.commit()


def _migrate_twr_columns(conn):
    """TWR unitization: fund-style units on snapshots, currency on flows.

    - daily_snapshots.units / unit_nav: outstanding units and NAV per unit.
      First snapshot after deploy is the inception (T0): unit_nav = 1.0,
      units = net_assets. History before T0 stays NULL — never backfilled.
    - deposit_history.currency / amount: original-currency amount so a flow
      can also update the matching cash balance (amount_cny stays the
      CNY-converted value used by capital totals and the unit engine).
    """
    for table, col, ddl in [
        ("daily_snapshots", "units", "units REAL"),
        ("daily_snapshots", "unit_nav", "unit_nav REAL"),
        ("deposit_history", "currency", "currency TEXT NOT NULL DEFAULT 'CNY'"),
        ("deposit_history", "amount", "amount REAL"),
        # 港股通: HK stocks bought via mainland brokers settle sales in CNY
        # at the day's FX, not in HKD
        ("account_settings", "hk_connect", "hk_connect INTEGER NOT NULL DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        except sqlite3.OperationalError:
            pass  # already exists
    conn.commit()


def roll_units(conn: sqlite3.Connection, user_id: str, date: str,
               net_assets: float) -> tuple[float, float] | None:
    """Fund-style unitization step for one snapshot day.

    unit_nav_D = (net_assets_D − net_flow_D) / units_prev   (flows priced at
    day-D close, so a deposit can't inflate that day's return)
    units_D    = units_prev + net_flow_D / unit_nav_D

    net_flow covers dated flows since the previous unitized snapshot
    (exclusive) through `date` (inclusive) — weekend/holiday flows roll into
    the next trading-day snapshot. Undated legacy flows are ignored: history
    before inception is collapsed into the opening balance by design.

    Returns (units, unit_nav), or None when the account isn't unitizable
    (zero/negative net assets at inception).
    """
    prev = conn.execute("""
        SELECT date, units FROM daily_snapshots
        WHERE user_id=? AND units IS NOT NULL AND units > 0 AND date < ?
        ORDER BY date DESC LIMIT 1
    """, (user_id, date)).fetchone()

    if prev is None:
        # Inception (T0): the whole pre-history becomes the opening balance
        if net_assets <= 0:
            return None
        return (net_assets, 1.0)

    prev_date, prev_units = prev[0], prev[1]
    flow = conn.execute("""
        SELECT COALESCE(SUM(amount_cny), 0) FROM deposit_history
        WHERE user_id=? AND deposit_date IS NOT NULL
          AND deposit_date > ? AND deposit_date <= ?
    """, (user_id, prev_date, date)).fetchone()[0]

    unit_nav = (net_assets - flow) / prev_units
    if unit_nav <= 0:
        # Pathological (flow larger than assets — bad data): re-incept
        # rather than producing a negative NAV
        return (net_assets, 1.0) if net_assets > 0 else None
    units = prev_units + flow / unit_nav
    if units <= 0:
        return None
    return (units, unit_nav)


def _migrate_snapshot_unique_per_user(conn):
    """daily_snapshots: UNIQUE(date) → UNIQUE(date, user_id).

    The original single-user schema allowed one snapshot row per date, so in
    the shared multi-user DB every user after the first got silently dropped
    by INSERT OR IGNORE. Rebuild preserving all existing columns and rows.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='daily_snapshots'"
    ).fetchone()
    if not row or "UNIQUE(date, user_id)" in (row[0] or ""):
        return
    cols_info = conn.execute("PRAGMA table_info(daily_snapshots)").fetchall()
    cols = [c[1] for c in cols_info if c[1] != "id"]
    col_list = ", ".join(cols)
    # Rebuild with the same columns, compound unique key
    col_defs = ",\n            ".join(
        f"{c[1]} {c[2]}" + (" NOT NULL" if c[3] and c[1] != "id" else "")
        + (f" DEFAULT ({c[4]})" if c[4] is not None else "")
        for c in cols_info if c[1] != "id"
    )
    conn.execute("ALTER TABLE daily_snapshots RENAME TO daily_snapshots_old")
    conn.execute(f"""
        CREATE TABLE daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {col_defs},
            UNIQUE(date, user_id)
        )
    """)
    conn.execute(f"""
        INSERT INTO daily_snapshots ({col_list})
        SELECT {col_list} FROM daily_snapshots_old
    """)
    conn.execute("DROP TABLE daily_snapshots_old")
    conn.commit()


def _recreate_with_user_id(conn, table_name: str, new_ddl: str, unique_cols: str):
    """Recreate a table with user_id if it doesn't have one yet."""
    # Check if user_id already exists
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if 'user_id' in cols:
        return
    # Get existing column names (excluding id)
    existing_cols = [c for c in cols if c != 'id']
    col_list = ', '.join(existing_cols)
    conn.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_old")
    conn.execute(new_ddl)
    conn.execute(f"""
        INSERT INTO {table_name} ({col_list}, user_id)
        SELECT {col_list}, 'local' FROM {table_name}_old
    """)
    conn.execute(f"DROP TABLE {table_name}_old")
    conn.commit()


# ── Account settings helpers ──

def get_account_settings(conn: sqlite3.Connection, user_id: str = 'local') -> list[dict]:
    """Return all account settings as list of dicts."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM account_settings WHERE user_id=? ORDER BY broker",
        (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_account_setting(conn: sqlite3.Connection, broker: str,
                           capital_mode: str, deposit_cny: float = 0,
                           deposit_fx: float = 1.0, notes: str = '',
                           cost_method: str = 'diluted',
                           user_id: str = 'local',
                           hk_connect: bool = False) -> None:
    """Insert or update account capital settings.
    Also ensures a CNY cash row exists for this account (balance 0 if new).
    """
    conn.execute("""
        INSERT INTO account_settings (broker, capital_mode, deposit_cny, deposit_fx, notes, cost_method, updated_at, user_id, hk_connect)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, ?)
        ON CONFLICT(broker, user_id) DO UPDATE SET
            capital_mode = excluded.capital_mode,
            deposit_cny = excluded.deposit_cny,
            deposit_fx = excluded.deposit_fx,
            notes = excluded.notes,
            cost_method = excluded.cost_method,
            updated_at = excluded.updated_at,
            hk_connect = excluded.hk_connect
    """, (broker, capital_mode, deposit_cny, deposit_fx, notes, cost_method, user_id, int(hk_connect)))
    # Auto-create cash row if none exists for this account
    existing = conn.execute(
        "SELECT 1 FROM cash_balances WHERE account=? AND user_id=? LIMIT 1", (broker, user_id)
    ).fetchone()
    if not existing:
        row = conn.execute(
            "SELECT currency, COUNT(*) AS cnt FROM positions "
            "WHERE broker=? AND user_id=? AND status='open' GROUP BY currency ORDER BY cnt DESC LIMIT 1",
            (broker, user_id)
        ).fetchone()
        currency = row[0] if row else 'CNY'
        conn.execute("""
            INSERT INTO cash_balances (account, currency, balance, updated_at, user_id)
            VALUES (?, ?, 0, datetime('now','localtime'), ?)
        """, (broker, currency, user_id))


def delete_account_setting(conn: sqlite3.Connection, broker: str,
                           user_id: str = 'local') -> int:
    """Delete account setting. Returns rows affected."""
    cur = conn.execute("DELETE FROM account_settings WHERE broker=? AND user_id=?",
                       (broker, user_id))
    return cur.rowcount


# ── Deposit history ──

def get_deposit_history(conn: sqlite3.Connection, broker: str,
                        user_id: str = 'local') -> list[dict]:
    """Return deposit history records for a broker, newest first."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM deposit_history WHERE broker=? AND user_id=? ORDER BY created_at DESC",
        (broker, user_id)
    ).fetchall()
    return [dict(r) for r in rows]


def _recalc_deposit_totals(conn: sqlite3.Connection, broker: str,
                           user_id: str = 'local') -> None:
    """Recalculate deposit_cny and weighted avg FX from deposit_history,
    then upsert into account_settings."""
    row = conn.execute("""
        SELECT COALESCE(SUM(amount_cny), 0) AS total,
               CASE WHEN SUM(amount_cny) > 0
                    THEN SUM(amount_cny * fx_rate) / SUM(amount_cny)
                    ELSE 1.0 END AS avg_fx
        FROM deposit_history WHERE broker=? AND user_id=?
    """, (broker, user_id)).fetchone()
    total_cny = row["total"] if row else 0
    avg_fx = row["avg_fx"] if row else 1.0
    conn.execute("""
        INSERT INTO account_settings (broker, capital_mode, deposit_cny, deposit_fx, updated_at, user_id)
        VALUES (?, 'deposit', ?, ?, datetime('now','localtime'), ?)
        ON CONFLICT(broker, user_id) DO UPDATE SET
            deposit_cny = excluded.deposit_cny,
            deposit_fx = excluded.deposit_fx,
            updated_at = excluded.updated_at
    """, (broker, total_cny, avg_fx, user_id))


def add_deposit_record(conn: sqlite3.Connection, broker: str,
                       amount_cny: float, fx_rate: float = 1.0,
                       deposit_date: str = '', notes: str = '',
                       user_id: str = 'local',
                       currency: str = 'CNY',
                       amount: float | None = None,
                       update_cash: bool = False) -> None:
    """Add a cash-flow record (deposit > 0, withdrawal < 0) and recalculate
    account_settings totals. amount is the original-currency value; with
    update_cash the matching cash balance moves in the same transaction so
    the flow ledger and cash can't drift apart."""
    if amount is None:
        amount = amount_cny / fx_rate if fx_rate else amount_cny
    conn.execute("""
        INSERT INTO deposit_history (broker, amount_cny, fx_rate, deposit_date, notes, user_id, currency, amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (broker, amount_cny, fx_rate, deposit_date or None, notes or None, user_id, currency, amount))
    _recalc_deposit_totals(conn, broker, user_id)
    if update_cash:
        row = conn.execute(
            "SELECT balance FROM cash_balances WHERE account=? AND currency=? AND user_id=?",
            (broker, currency, user_id)).fetchone()
        upsert_cash(conn, broker, currency, (row[0] if row else 0) + amount, user_id=user_id)


def delete_deposit_record(conn: sqlite3.Connection, record_id: int,
                          user_id: str = 'local') -> str:
    """Delete a deposit record by ID, recalculate totals. Returns broker name."""
    row = conn.execute("SELECT broker FROM deposit_history WHERE id=? AND user_id=?",
                       (record_id, user_id)).fetchone()
    if not row:
        return ""
    broker = row["broker"]
    conn.execute("DELETE FROM deposit_history WHERE id=? AND user_id=?", (record_id, user_id))
    _recalc_deposit_totals(conn, broker, user_id)
    return broker


# ── Capital computation ──

def compute_capital(conn: sqlite3.Connection, fx: dict[str, float],
                    user_id: str = 'local') -> float:
    """Compute total invested capital (CNY).

    Every account must be registered in account_settings with a capital_mode:
      - 'deposit': use fixed deposit_cny (ignores position cost, cash, realized P&L)
      - 'cost':    use position cost × FX + cash − realized P&L

    Capital = Σ deposit_cny (deposit accounts)
            + Σ position_cost (cost accounts)
            + Σ cash (cost accounts)
            − off-exchange leverage
            − Σ realized P&L (cost accounts)

    All matching is purely by broker name — no market-level logic needed.
    """
    conn.row_factory = sqlite3.Row
    settings = conn.execute(
        "SELECT broker, capital_mode, deposit_cny FROM account_settings WHERE user_id=?",
        (user_id,)
    ).fetchall()

    deposit_brokers: dict[str, float] = {}   # broker -> deposit_cny
    cost_brokers: set[str] = set()
    for r in settings:
        if r['capital_mode'] == 'deposit':
            deposit_brokers[r['broker']] = r['deposit_cny']
        else:
            cost_brokers.add(r['broker'])

    # Deposit total
    deposit_total = sum(deposit_brokers.values())

    # Position cost (cost-mode accounts only)
    position_cost = 0.0
    for row in conn.execute(
            "SELECT broker, currency, quantity, cost_price "
            "FROM positions WHERE status='open' AND user_id=?", (user_id,)):
        if row['broker'] in cost_brokers:
            position_cost += row['quantity'] * row['cost_price'] * fx.get(row['currency'], 1.0)

    # Cash (cost-mode accounts only; also include accounts not in any setting like banks)
    cash_cny = 0.0
    for row in conn.execute(
            "SELECT account, currency, balance FROM cash_balances WHERE user_id=?", (user_id,)):
        if row['account'] not in deposit_brokers:
            cash_cny += row['balance'] * fx.get(row['currency'], 1.0)

    # Off-exchange leverage
    margin_off = 0.0
    for row in conn.execute(
            "SELECT currency, amount FROM margin_balances "
            "WHERE category='off_exchange' AND user_id=?", (user_id,)):
        margin_off += row['amount'] * fx.get(row['currency'], 1.0)

    # Realized P&L (cost-mode accounts only)
    realised_pl = 0.0
    for row in conn.execute(
            "SELECT broker, COALESCE(realized_pnl_cny, 0) AS rpl FROM closed_trades "
            "WHERE user_id=?", (user_id,)):
        if row['broker'] in cost_brokers:
            realised_pl += row['rpl']

    return deposit_total + position_cost + cash_cny - margin_off - realised_pl


# ── DCF valuation integration (read-only) ──

def get_dcf_valuations() -> dict[str, dict]:
    """Read latest DCF valuation per ticker from ValueScope DB.

    Returns {ticker: {'dcf_price': float, 'date': str, 'currency': str}}.
    """
    db_path = os.environ.get('VS_DB_PATH')
    if not db_path or not os.path.exists(db_path):
        return {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT v.ticker, v.gap_adjusted_price, v.price_per_share,
                   v.currency, v.valuation_date
            FROM valuations v
            INNER JOIN (
                SELECT ticker, MAX(valuation_date) AS max_date
                FROM valuations GROUP BY ticker
            ) latest ON v.ticker = latest.ticker AND v.valuation_date = latest.max_date
        """).fetchall()
        conn.close()
        result = {}
        for r in rows:
            price = r['gap_adjusted_price'] or r['price_per_share']
            if price and price > 0:
                result[r['ticker']] = {
                    'dcf_price': round(price, 2),
                    'date': r['valuation_date'],
                    'currency': r['currency'],
                }
        return result
    except Exception:
        return {}


# ── Query helpers ──

def get_open_tickers(conn: sqlite3.Connection, user_id: str = 'local') -> list[dict]:
    """Return list of open positions with ticker, name, market."""
    rows = conn.execute(
        "SELECT DISTINCT ticker, name, market FROM positions WHERE status='open' AND user_id=?",
        (user_id,)
    ).fetchall()
    return [{"ticker": r[0], "name": r[1], "market": r[2]} for r in rows]


# ── CRUD operations ──

def upsert_position(conn: sqlite3.Connection, ticker: str, name: str, market: str,
                    broker: str, currency: str, quantity: float, cost_price: float,
                    user_id: str = 'local') -> None:
    is_new = conn.execute(
        "SELECT 1 FROM positions WHERE ticker=? AND broker=? AND user_id=? LIMIT 1",
        (ticker, broker, user_id)).fetchone() is None
    conn.execute("""
        INSERT INTO positions (ticker, name, market, broker, currency, quantity, cost_price,
                               status, updated_at, created_at, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'open', datetime('now','localtime'), datetime('now','localtime'), ?)
        ON CONFLICT(ticker, broker, user_id) DO UPDATE SET
            name = excluded.name, market = excluded.market,
            currency = excluded.currency, quantity = excluded.quantity,
            cost_price = excluded.cost_price,
            updated_at = CASE
                WHEN positions.quantity != excluded.quantity
                  OR abs(positions.cost_price - excluded.cost_price) > 0.0001
                THEN datetime('now','localtime') ELSE positions.updated_at END
    """, (ticker, name, market, broker, currency, quantity, cost_price, user_id))
    if is_new:
        # Baseline lifecycle: a brand-new position (incl. re-buy after a full
        # close this year) starts YTD from cost. Replace any stale baseline —
        # past sales' YTD attribution is locked on closed_trades at sell time,
        # so refreshing the baseline can't corrupt it.
        year = datetime.now().year
        conn.execute(
            "DELETE FROM ytd_baseline_prices WHERE year=? AND ticker=? AND broker=? AND user_id=?",
            (year, ticker, broker, user_id))
        conn.execute("""
            INSERT INTO ytd_baseline_prices
                (year, ticker, broker, price, currency, date, quantity, cost_price, user_id)
            VALUES (?, ?, ?, ?, ?, date('now', 'localtime'), ?, ?, ?)
        """, (year, ticker, broker, cost_price, currency, quantity, cost_price, user_id))


def insert_closed_trade(conn: sqlite3.Connection, ticker: str | None, name: str,
                        market: str, broker: str, currency: str, realized_pnl: float,
                        close_date: str | None = None, notes: str | None = None,
                        quantity: float | None = None, cost_price: float | None = None,
                        close_price: float | None = None, cost_total: float | None = None,
                        realized_pnl_cny: float | None = None,
                        ytd_pnl_cny_locked: float | None = None,
                        user_id: str = 'local') -> None:
    conn.execute("""
        INSERT INTO closed_trades (ticker, name, market, broker, currency, realized_pnl,
                                   close_date, notes, quantity, cost_price, close_price,
                                   cost_total, realized_pnl_cny, ytd_pnl_cny_locked, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticker, name, market, broker, currency, realized_pnl,
          close_date, notes, quantity, cost_price, close_price, cost_total,
          realized_pnl_cny, ytd_pnl_cny_locked, user_id))


def upsert_cash(conn: sqlite3.Connection, account: str, currency: str, balance: float,
                user_id: str = 'local') -> None:
    conn.execute("""
        INSERT INTO cash_balances (account, currency, balance, updated_at, user_id)
        VALUES (?, ?, ?, datetime('now','localtime'), ?)
        ON CONFLICT(account, currency, user_id) DO UPDATE SET
            balance = excluded.balance, updated_at = excluded.updated_at
    """, (account, currency, balance, user_id))


def upsert_nav(conn: sqlite3.Connection, date: str, nav: float, capital: float,
               pnl: float, equity_nav: float | None = None, benchmark: float | None = None) -> None:
    conn.execute("""
        INSERT INTO nav_history (date, net_asset_value, capital_invested, pnl, equity_nav, benchmark_value)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            net_asset_value = excluded.net_asset_value, capital_invested = excluded.capital_invested,
            pnl = excluded.pnl, equity_nav = excluded.equity_nav, benchmark_value = excluded.benchmark_value
    """, (date, nav, capital, pnl, equity_nav, benchmark))


def upsert_fx(conn: sqlite3.Connection, currency: str, rate: float) -> None:
    conn.execute("""
        INSERT INTO fx_rates (currency, rate_to_cny, updated_at)
        VALUES (?, ?, datetime('now','localtime'))
        ON CONFLICT(currency) DO UPDATE SET
            rate_to_cny = excluded.rate_to_cny, updated_at = excluded.updated_at
    """, (currency, rate))


def upsert_margin(conn: sqlite3.Connection, broker: str, category: str,
                  currency: str, amount: float, user_id: str = 'local') -> None:
    conn.execute("""
        INSERT INTO margin_balances (broker, category, currency, amount, updated_at, user_id)
        VALUES (?, ?, ?, ?, datetime('now','localtime'), ?)
        ON CONFLICT(broker, category, currency, user_id) DO UPDATE SET
            amount = excluded.amount, updated_at = excluded.updated_at
    """, (broker, category, currency, amount, user_id))


def upsert_snapshot(conn: sqlite3.Connection, date: str, total_assets: float,
                    net_assets: float, equity_mv: float, cash: float, leverage: float,
                    total_pnl: float, market_data: str | None = None,
                    capital: float | None = None, market_detail: dict | None = None,
                    market_pnl: str | None = None,
                    realized_pnl_cny: float | None = None,
                    stock_pnl: list[dict] | None = None,
                    user_id: str = 'local',
                    units: float | None = None,
                    unit_nav: float | None = None) -> None:
    """Record daily snapshot — first write of the day wins (no overwrite)."""
    conn.execute("""
        INSERT OR IGNORE INTO daily_snapshots
            (date, total_assets, net_assets, equity_mv_cny, cash_cny,
             leverage_cny, total_pnl_cny, market_data, capital, market_pnl,
             realized_pnl_cny, created_at, user_id, units, unit_nav)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'), ?, ?, ?)
    """, (date, total_assets, net_assets, equity_mv, cash, leverage, total_pnl,
          market_data, capital, market_pnl, realized_pnl_cny, user_id, units, unit_nav))

    if market_pnl:
        conn.execute("""
            UPDATE daily_snapshots SET market_pnl = ?
            WHERE date = ? AND user_id = ? AND market_pnl IS NULL""", (market_pnl, date, user_id))
    if realized_pnl_cny is not None:
        conn.execute("""
            UPDATE daily_snapshots SET realized_pnl_cny = ?
            WHERE date = ? AND user_id = ? AND realized_pnl_cny IS NULL""", (realized_pnl_cny, date, user_id))

    if market_detail:
        for market, cur_dict in market_detail.items():
            if isinstance(cur_dict, dict):
                for currency, mv in cur_dict.items():
                    conn.execute("""
                        INSERT OR IGNORE INTO snapshot_market_detail (date, market, currency, mv, user_id)
                        VALUES (?, ?, ?, ?, ?)""", (date, market, currency, mv, user_id))

    if stock_pnl:
        for sp in stock_pnl:
            conn.execute("""
                INSERT OR IGNORE INTO snapshot_stock_pnl (date, ticker, name, market, pnl_cny, user_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date, sp['ticker'], sp.get('name'), sp.get('market', ''), sp.get('pnl_cny', 0), user_id))


# ── YTD baselines ──

def get_ytd_baselines(conn: sqlite3.Connection, year: int,
                      user_id: str = 'local') -> dict[tuple[str, str], dict]:
    """Return baselines keyed by (ticker, broker).

    Legacy rows (fully-closed tickers migrated without an open position)
    appear under (ticker, '') — callers fall back to that key.
    """
    rows = conn.execute(
        "SELECT ticker, broker, price, quantity, cost_price "
        "FROM ytd_baseline_prices WHERE year = ? AND user_id = ?",
        (year, user_id)).fetchall()
    result = {}
    for r in rows:
        result[(r[0], r[1])] = {
            'price': r[2], 'quantity': r[3], 'cost_price': r[4],
        }
    return result


def record_ytd_baselines(conn: sqlite3.Connection, year: int, ticker_data: dict,
                         date: str, user_id: str = 'local') -> None:
    """ticker_data: {(ticker, broker): (price, currency[, quantity, cost_price])}."""
    for (ticker, broker), vals in ticker_data.items():
        price, currency = vals[0], vals[1]
        qty = vals[2] if len(vals) > 2 else None
        cost = vals[3] if len(vals) > 3 else None
        conn.execute("""
            INSERT OR IGNORE INTO ytd_baseline_prices
                (year, ticker, broker, price, currency, date, quantity, cost_price, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (year, ticker, broker, price, currency, date, qty, cost, user_id))


def compute_locked_ytd_cny(conn: sqlite3.Connection, ticker: str | None, broker: str,
                           market: str, currency: str, quantity: float | None,
                           close_price: float | None, realized_pnl: float,
                           realized_pnl_cny: float | None,
                           user_id: str = 'local', year: int | None = None) -> float | None:
    """YTD attribution (CNY) of a sale, locked at sell time.

    Uses the baseline as it exists NOW — later baseline resets (full close +
    re-buy) or FX moves no longer corrupt past attribution.

    Convention-dependent (matches held_ytd so held + locked = total YTD):
      average/fund: (sell − bp) × qty — cost never absorbs gains, so each
        sale attributes its own shares from the baseline price.
      diluted FULL close: realized − (bp − b_cost) × b_qty — the trade's
        realized P&L (vs diluted cost) already contains all gains absorbed by
        earlier Edit-recorded partial sells; subtracting the group's baseline
        unrealized once completes the attribution.
      diluted partial close (warned-against workflow): (sell − bp) × qty,
        the historical behaviour.

    FX: implied sale-time rate (realized_pnl_cny / realized_pnl) when sane,
    else the stored fx_rates table.
    """
    if year is None:
        year = datetime.now().year
    baseline = None
    if ticker:
        row = conn.execute(
            "SELECT price, quantity, cost_price FROM ytd_baseline_prices "
            "WHERE year=? AND ticker=? AND broker=? AND user_id=?",
            (year, ticker, broker, user_id)).fetchone()
        if row is None:  # legacy broker-less row
            row = conn.execute(
                "SELECT price, quantity, cost_price FROM ytd_baseline_prices "
                "WHERE year=? AND ticker=? AND broker='' AND user_id=?",
                (year, ticker, user_id)).fetchone()
        if row:
            baseline = {'price': row[0], 'quantity': row[1], 'cost_price': row[2]}
    if baseline is None or close_price is None or quantity is None:
        return realized_pnl_cny  # attribution == realized; reuse its sale-time CNY

    cm_row = conn.execute(
        "SELECT cost_method FROM account_settings WHERE broker=? AND user_id=?",
        (broker, user_id)).fetchone()
    uses_avg_cost = (market == '基金'
                     or (cm_row and (cm_row[0] or 'diluted') == 'average'))

    bp = baseline['price']
    if uses_avg_cost:
        native = (close_price - bp) * quantity
    else:
        pos = conn.execute(
            "SELECT quantity FROM positions WHERE ticker=? AND broker=? AND user_id=? "
            "AND status='open'", (ticker, broker, user_id)).fetchone()
        is_full_close = pos is None or quantity >= pos[0] - 1e-9
        b_qty, b_cost = baseline.get('quantity'), baseline.get('cost_price')
        if is_full_close and b_qty is not None and b_cost is not None:
            native = realized_pnl - (bp - b_cost) * b_qty
        else:
            native = (close_price - bp) * quantity

    fx = None
    if realized_pnl and realized_pnl_cny is not None:
        implied = realized_pnl_cny / realized_pnl
        if 0.001 < implied < 100:
            fx = implied
    if fx is None:
        r = conn.execute("SELECT rate_to_cny FROM fx_rates WHERE currency=?", (currency,)).fetchone()
        fx = r[0] if r else 1.0
    return native * fx


if __name__ == '__main__':
    init_db()
    print(f"Database initialized at {DB_PATH}")
