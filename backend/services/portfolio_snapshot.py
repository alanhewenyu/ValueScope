# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Daily portfolio snapshot — designed to run via cron.

Captures end-of-day NAV, equity, cash, leverage, and P&L for all markets.
All prices are fetched fresh. Results written to daily_snapshots table.

Usage:
    python3 -m backend.services.portfolio_snapshot              # snapshot for today
    python3 -m backend.services.portfolio_snapshot --dry-run    # print without writing

Cron (run at 06:00 Beijing time every day):
    0 6 * * * cd /Users/Alan/valuescope && python3 -m backend.services.portfolio_snapshot >> data/snapshot.log 2>&1
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

from backend.services.portfolio_db import (
    DB_PATH, get_conn, upsert_snapshot, upsert_fx, init_db, compute_capital,
)
from backend.services.portfolio_prices import fetch_price, fetch_fx_rate


def _fmt(val):
    return f"{val:,.0f}" if val is not None else "—"


def take_snapshot(dry_run=False):
    """Fetch all prices, compute NAV, write snapshot."""
    # Skip Sun/Mon — US market closed Sat/Sun, Beijing time is +1 day
    if datetime.now().weekday() in (6, 0):  # 6=Sun, 0=Mon
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] No trading day (Sun/Mon), skipping.")
        return None

    init_db()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f"Portfolio Snapshot  {ts}")
    print(f"{'='*55}")

    conn = get_conn()

    # ── FX rates ──
    fx = {"CNY": 1.0}
    for cur in ("USD", "HKD", "JPY"):
        rate = fetch_fx_rate(cur)
        if rate and rate > 0:
            fx[cur] = rate
            if not dry_run:
                upsert_fx(conn, cur, rate)
        else:
            row = conn.execute(
                "SELECT rate_to_cny FROM fx_rates WHERE currency=?", (cur,)
            ).fetchone()
            if row:
                fx[cur] = row[0]
                print(f"  WARN: live FX failed for {cur}, using DB fallback {row[0]}")
            else:
                print(f"  WARN: no FX rate for {cur}, defaulting to 1.0")
                fx[cur] = 1.0

    print(f"FX: USD={fx.get('USD',0):.4f}  HKD={fx.get('HKD',0):.5f}  JPY={fx.get('JPY',0):.5f}")

    # ── Positions ──
    positions = conn.execute("""
        SELECT ticker, name, market, broker, currency, quantity, cost_price
        FROM positions WHERE status='open'
    """).fetchall()

    equity_mv = 0.0
    total_cost_cny = 0.0
    total_pnl_cny = 0.0
    stale_count = 0
    market_mv = {}
    market_pnl = {}

    # Parallel price fetch
    from concurrent.futures import ThreadPoolExecutor
    _tickers = [pos["ticker"] for pos in positions]
    def _fetch_one(t):
        p, _ = fetch_price(t, regular_only=True)
        return p
    try:
        with ThreadPoolExecutor(max_workers=min(len(_tickers) or 1, 8)) as pool:
            _fetched = list(pool.map(_fetch_one, _tickers, timeout=60))
    except Exception:
        _fetched = [None] * len(_tickers)

    for i, pos in enumerate(positions):
        ticker, name, market, broker, currency, qty, cost_price = (
            pos["ticker"], pos["name"], pos["market"], pos["broker"],
            pos["currency"], pos["quantity"], pos["cost_price"],
        )
        rate = fx.get(currency, 1.0)

        price = _fetched[i]
        if price is None:
            price = cost_price
            stale_count += 1

        mv_cny = qty * price * rate
        cost_cny = qty * cost_price * rate
        pnl_cny = mv_cny - cost_cny

        equity_mv += mv_cny
        total_cost_cny += cost_cny
        total_pnl_cny += pnl_cny
        market_mv[market] = market_mv.get(market, 0) + mv_cny
        market_pnl[market] = market_pnl.get(market, 0) + pnl_cny

    print(f"\nPositions: {len(positions)} ({stale_count} stale prices)")
    print(f"Equity MV:  ¥{_fmt(equity_mv)}")

    # Guard: abort if too many prices are stale
    if positions and stale_count / len(positions) > 0.5:
        print(f"\n✗ ABORT: {stale_count}/{len(positions)} prices stale — "
              f"environment likely broken. Snapshot NOT saved.")
        conn.close()
        return None

    # ── Cash ──
    cash_cny = 0.0
    for row in conn.execute("SELECT currency, balance FROM cash_balances"):
        cash_cny += row["balance"] * fx.get(row["currency"], 1.0)
    print(f"Cash:       ¥{_fmt(cash_cny)}")

    # ── Leverage ──
    in_house = 0.0
    off_exchange = 0.0
    for row in conn.execute("SELECT category, currency, amount FROM margin_balances"):
        rate = fx.get(row["currency"], 1.0)
        amt_cny = row["amount"] * rate
        if row["category"] == "in_house":
            in_house += amt_cny
        elif row["category"] == "off_exchange":
            off_exchange += amt_cny
    total_leverage = in_house + off_exchange
    print(f"Leverage:   ¥{_fmt(total_leverage)} (in={_fmt(in_house)}, off={_fmt(off_exchange)})")

    # ── Metrics ──
    total_assets = equity_mv + cash_cny
    net_assets = total_assets - total_leverage
    pnl_pct = (total_pnl_cny / total_cost_cny * 100) if total_cost_cny > 0 else 0

    print(f"\nTotal Assets: ¥{_fmt(total_assets)}")
    print(f"Net Assets:   ¥{_fmt(net_assets)}")
    print(f"Unrealized:   ¥{_fmt(total_pnl_cny)} ({pnl_pct:+.1f}%)")

    # ── Capital ──
    capital = compute_capital(conn, fx)
    print(f"Capital:      ¥{_fmt(capital)}")

    # ── Write snapshot ──
    today = datetime.now().strftime("%Y-%m-%d")
    market_json = json.dumps(market_mv, ensure_ascii=False)
    print(f"Market MV:    {market_json}")

    if dry_run:
        print(f"\n[DRY RUN] Would write snapshot for {today}")
    else:
        market_pnl_json = json.dumps(market_pnl, ensure_ascii=False)
        upsert_snapshot(conn, today, total_assets, net_assets,
                        equity_mv, cash_cny, total_leverage, total_pnl_cny,
                        market_data=market_json, capital=capital,
                        market_pnl=market_pnl_json)

        # Auto-create YTD baselines if none exist for current year
        from backend.services.portfolio_db import get_ytd_baselines, record_ytd_baselines
        current_year = datetime.now().year
        existing = get_ytd_baselines(conn, current_year)
        if not existing and positions:
            ticker_data = {}
            for i, pos in enumerate(positions):
                p = _fetched[i] if _fetched[i] is not None else pos["cost_price"]
                # Keyed per (ticker, broker) — same ticker across accounts
                # gets one baseline each (qty/cost differ per account).
                ticker_data[(pos["ticker"], pos["broker"])] = (
                    p, pos["currency"], pos["quantity"], pos["cost_price"]
                )
            record_ytd_baselines(conn, current_year, ticker_data, today)
            print(f"  Auto-recorded YTD baselines for {current_year} ({len(ticker_data)} tickers)")

        conn.commit()
        print(f"\n✓ Snapshot saved for {today}")

    conn.close()

    return {
        "date": today,
        "total_assets": total_assets,
        "net_assets": net_assets,
        "equity_mv": equity_mv,
        "cash_cny": cash_cny,
        "leverage": total_leverage,
        "pnl": total_pnl_cny,
    }


def backup_db(keep_daily=7):
    """Backup portfolio.db using SQLite backup API (safe, no corruption risk).

    Backup directory: BACKUP_DIR env var, or <project>/data/backups/
    Retention: keep last `keep_daily` daily + all 1st-of-month backups.
    """
    _env_dir = os.environ.get("BACKUP_DIR", "").strip()
    if _env_dir:
        backup_dir = Path(_env_dir).expanduser()
    else:
        backup_dir = Path(DB_PATH).parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    src = Path(DB_PATH)
    if not src.exists():
        print(f"  WARN: DB not found at {src}, skipping backup")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    dst = backup_dir / f"portfolio_{today}.db"

    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()
        size_mb = dst.stat().st_size / (1024 * 1024)
        print(f"✓ Backup saved: {dst}  ({size_mb:.1f} MB)")
    except Exception as e:
        dst_conn.close()
        src_conn.close()
        print(f"  WARN: backup failed: {e}")
        return

    latest = backup_dir / "portfolio_latest.db"
    shutil.copy2(str(dst), str(latest))

    # Retention: prune old daily backups, keep monthly (1st of month)
    backups = sorted(backup_dir.glob("portfolio_????-??-??.db"))
    for f in backups:
        name = f.stem
        date_str = name.replace("portfolio_", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if dt.day == 1:
            continue
        age = (datetime.now() - dt).days
        if age > keep_daily:
            f.unlink()
            print(f"  Pruned old backup: {f.name}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    from backend.services.portfolio_db import PORTFOLIOS, set_active_portfolio

    if PORTFOLIOS:
        # Multi-portfolio: snapshot each one
        for name, path in PORTFOLIOS:
            print(f"\n{'#'*55}")
            print(f"# Portfolio: {name}")
            print(f"{'#'*55}")
            set_active_portfolio(path)
            init_db()
            take_snapshot(dry_run=dry)
        # Restore to first (default) portfolio
        set_active_portfolio(PORTFOLIOS[0][1])
    else:
        take_snapshot(dry_run=dry)

    if not dry:
        backup_db()
