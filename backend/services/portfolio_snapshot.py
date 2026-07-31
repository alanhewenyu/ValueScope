# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Daily portfolio snapshot — designed to run via cron.

Captures end-of-day NAV, equity, cash, leverage, and P&L for all markets.
All prices are fetched fresh. Results written to daily_snapshots table.

Usage:
    python3 -m backend.services.portfolio_snapshot              # snapshot for today
    python3 -m backend.services.portfolio_snapshot --dry-run    # print without writing

Cron (run at 06:00 Beijing time every day):
    0 6 * * * cd /path/to/valuescope && python3 -m backend.services.portfolio_snapshot >> data/snapshot.log 2>&1
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
    roll_units,
)
from backend.services.portfolio_prices import fetch_price, fetch_fx_rate


def _fmt(val):
    return f"{val:,.0f}" if val is not None else "—"


def _now_cn() -> datetime:
    """Beijing time — explicit so the logic also works in UTC containers."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def take_snapshot(dry_run=False, user_id: str = "local", force: bool = False):
    """Fetch all prices, compute NAV, write snapshot (per user).

    force=True bypasses the Sun/Mon skip — used for the day-0 snapshot when
    a new user finishes onboarding (they should see their curve start today,
    whatever day it is; weekend prices are the weekend guard's problem)."""
    now_cn = _now_cn()
    # Skip Sun/Mon — US market closed Sat/Sun, Beijing time is +1 day
    if not force and now_cn.weekday() in (6, 0):  # 6=Sun, 0=Mon
        print(f"[{now_cn:%Y-%m-%d %H:%M}] No trading day (Sun/Mon), skipping.")
        return None

    init_db()
    ts = now_cn.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*55}")
    print(f"Portfolio Snapshot  {ts}  (user: {user_id})")
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
        FROM positions WHERE status='open' AND user_id=?
    """, (user_id,)).fetchall()

    equity_mv = 0.0
    total_cost_cny = 0.0
    total_pnl_cny = 0.0
    stale_count = 0
    market_mv = {}
    market_pnl = {}

    # Parallel price fetch
    from concurrent.futures import ThreadPoolExecutor
    _tickers = [pos["ticker"] for pos in positions]
    # Batch the mainland/HK quotes into one request before fanning out —
    # eastmoney drops connections when the whole book hits it at once.
    try:
        from backend.services.portfolio_prices import prime_price_cache
        prime_price_cache(_tickers)
    except Exception:
        pass  # best-effort; per-ticker path still works
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

    # ── Cash (IBKR-style: negative balance = margin loan) ──
    pos_cash = 0.0
    neg_cash = 0.0  # margin loans expressed as negative cash
    cash_ccy: dict[str, float] = {}  # signed CNY exposure by currency
    for row in conn.execute("SELECT currency, balance FROM cash_balances WHERE user_id=?", (user_id,)):
        v = row["balance"] * fx.get(row["currency"], 1.0)
        cash_ccy[row["currency"]] = cash_ccy.get(row["currency"], 0.0) + v
        if v >= 0:
            pos_cash += v
        else:
            neg_cash += -v
    cash_cny = pos_cash
    print(f"Cash:       ¥{_fmt(pos_cash)}" + (f"  (margin via negative cash: ¥{_fmt(neg_cash)})" if neg_cash else ""))

    # ── Leverage: legacy in_house rows + negative cash + off-exchange ──
    in_house = 0.0
    off_exchange = 0.0
    for row in conn.execute("SELECT category, currency, amount FROM margin_balances WHERE user_id=?", (user_id,)):
        rate = fx.get(row["currency"], 1.0)
        amt_cny = row["amount"] * rate
        # Liability denominated in a currency = negative exposure to it
        cash_ccy[row["currency"]] = cash_ccy.get(row["currency"], 0.0) - amt_cny
        if row["category"] == "in_house":
            in_house += amt_cny
        elif row["category"] == "off_exchange":
            off_exchange += amt_cny
    total_leverage = in_house + neg_cash + off_exchange
    print(f"Leverage:   ¥{_fmt(total_leverage)} (in={_fmt(in_house)}, neg_cash={_fmt(neg_cash)}, off={_fmt(off_exchange)})")

    # ── Metrics ──
    total_assets = equity_mv + cash_cny
    net_assets = total_assets - total_leverage
    pnl_pct = (total_pnl_cny / total_cost_cny * 100) if total_cost_cny > 0 else 0

    print(f"\nTotal Assets: ¥{_fmt(total_assets)}")
    print(f"Net Assets:   ¥{_fmt(net_assets)}")
    print(f"Unrealized:   ¥{_fmt(total_pnl_cny)} ({pnl_pct:+.1f}%)")

    # ── Capital ──
    capital = compute_capital(conn, fx, user_id=user_id)
    print(f"Capital:      ¥{_fmt(capital)}")

    # ── Write snapshot ──
    today = now_cn.strftime("%Y-%m-%d")
    market_json = json.dumps(market_mv, ensure_ascii=False)
    print(f"Market MV:    {market_json}")

    # ── TWR unitization. Inception seeds unit_nav at NAV/Capital so the
    #    series continues the legacy performance curve without a seam ──
    unit_res = roll_units(conn, user_id, today, net_assets, capital=capital)
    units, unit_nav = unit_res if unit_res else (None, None)
    if unit_nav is not None:
        print(f"Unit NAV:     {unit_nav:.4f}  ({units:,.0f} units)")

    if dry_run:
        print(f"\n[DRY RUN] Would write snapshot for {today}")
    else:
        market_pnl_json = json.dumps(market_pnl, ensure_ascii=False)
        upsert_snapshot(conn, today, total_assets, net_assets,
                        equity_mv, cash_cny, total_leverage, total_pnl_cny,
                        market_data=market_json, capital=capital,
                        market_pnl=market_pnl_json, user_id=user_id,
                        units=units, unit_nav=unit_nav,
                        fx_json=json.dumps(fx),
                        cash_json=json.dumps(cash_ccy, ensure_ascii=False))

        # Auto-create YTD baselines if none exist for current year
        from backend.services.portfolio_db import get_ytd_baselines, record_ytd_baselines
        current_year = now_cn.year
        existing = get_ytd_baselines(conn, current_year, user_id=user_id)
        if not existing and positions:
            ticker_data = {}
            for i, pos in enumerate(positions):
                p = _fetched[i] if _fetched[i] is not None else pos["cost_price"]
                # Keyed per (ticker, broker) — same ticker across accounts
                # gets one baseline each (qty/cost differ per account).
                ticker_data[(pos["ticker"], pos["broker"])] = (
                    p, pos["currency"], pos["quantity"], pos["cost_price"]
                )
            record_ytd_baselines(conn, current_year, ticker_data, today, user_id=user_id)
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

    # All portfolio DBs, not just the active one (Joint lives in its own file)
    from backend.services.portfolio_db import PORTFOLIOS
    sources = [Path(p) for _, p in PORTFOLIOS] or [Path(DB_PATH)]

    today = datetime.now().strftime("%Y-%m-%d")
    for src in sources:
        if not src.exists():
            print(f"  WARN: DB not found at {src}, skipping backup")
            continue
        prefix = src.stem  # portfolio / portfolio_child
        dst = backup_dir / f"{prefix}_{today}.db"

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
            print(f"  WARN: backup failed for {prefix}: {e}")
            continue

        shutil.copy2(str(dst), str(backup_dir / f"{prefix}_latest.db"))

        # Retention: prune old dailies for this prefix, keep 1st-of-month
        for f in sorted(backup_dir.glob(f"{prefix}_????-??-??.db")):
            date_str = f.stem.replace(f"{prefix}_", "")
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if dt.day == 1:
                continue
            if (datetime.now() - dt).days > keep_daily:
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
