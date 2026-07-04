# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Portfolio Tracker API — positions, cash, snapshots, KPI.

All data lives in a local SQLite database (PORTFOLIO_DB_PATH env var).
This router is only active when the database file exists, keeping the
public deployment unaffected.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.routers.auth import get_current_user

logger = logging.getLogger("valuescope.portfolio.api")

router = APIRouter()

# ── Helpers ──────────────────────────────────────────────

def _get_db_path() -> str:
    from backend.services.portfolio_db import DB_PATH
    return DB_PATH


def _require_db() -> str:
    """Return DB_PATH, auto-creating if missing."""
    path = _get_db_path()
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        from backend.services.portfolio_db import init_db
        init_db(path)
        logger.info("Auto-created portfolio DB at %s", path)
    return path


def _query(path: str, sql: str, params=()):
    """Execute SQL and return list of dicts."""
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# ── Pydantic models ──────────────────────────────────────

class PositionIn(BaseModel):
    ticker: str
    name: str
    market: str
    broker: str
    quantity: float
    cost_price: float
    currency: str = "CNY"
    status: str = "open"


class CashIn(BaseModel):
    account: str
    currency: str
    balance: float


class AccountSettingIn(BaseModel):
    broker: str
    capital_mode: str = "cost"  # 'cost' or 'deposit'
    deposit_cny: float = 0
    deposit_fx: float = 1.0
    notes: str = ""
    cost_method: str = "diluted"  # 'diluted' (re-avg on sell) or 'average' (IBKR)
    hk_connect: bool = False  # 港股通: HK sale proceeds settle in CNY


class DepositRecordIn(BaseModel):
    broker: str
    amount_cny: float  # signed: deposit > 0, withdrawal < 0
    fx_rate: float = 1.0
    deposit_date: str = ""
    notes: str = ""
    currency: str = "CNY"
    amount: Optional[float] = None  # original-currency amount (defaults to amount_cny / fx_rate)
    update_cash: bool = False  # also move the matching cash balance


class MarginIn(BaseModel):
    broker: str
    category: str  # 'in_house' or 'off_exchange'
    currency: str = "CNY"
    amount: float


class ClosedTradeIn(BaseModel):
    ticker: str
    name: str
    market: str
    broker: str
    quantity: float
    buy_price: float
    sell_price: float
    realized_pnl: float
    realized_pnl_cny: float
    currency: str = "CNY"


# ── Endpoints ────────────────────────────────────────────

@router.get("/status")
def portfolio_status(user_id: Optional[str] = Depends(get_current_user)):
    """Check if portfolio feature is available.

    For logged-in users, auto-create the database so the onboarding
    flow (account setup, import templates) is shown instead of a
    technical 'not configured' error.
    """
    path = _get_db_path()
    if not os.path.exists(path) and user_id and user_id != "local":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        from backend.services.portfolio_db import init_db
        init_db(path)
        logger.info("Auto-created portfolio DB for user %s at %s", user_id, path)
    exists = os.path.exists(path)
    return {"available": exists, "db_path": path if exists else None}


@router.get("/portfolios")
def list_portfolios():
    """Return available portfolios and which is currently active."""
    from backend.services.portfolio_db import PORTFOLIOS, DB_PATH
    items = [{"name": name, "active": os.path.abspath(path) == os.path.abspath(DB_PATH)}
             for name, path in PORTFOLIOS]
    if not items:
        items = [{"name": "Default", "active": True}]
    return items


@router.post("/portfolios/switch")
def switch_portfolio(name: str = Query(...)):
    """Switch the active portfolio DB by name."""
    from backend.services.portfolio_db import PORTFOLIOS, set_active_portfolio, init_db
    for pname, ppath in PORTFOLIOS:
        if pname == name:
            set_active_portfolio(ppath)
            init_db()
            return {"active": name}
    raise HTTPException(404, f"Portfolio '{name}' not found")


@router.get("/positions")
def list_positions(status: str = Query("open", pattern="^(open|closed|all)$"), user_id: str = Depends(get_current_user)):
    """List portfolio positions."""
    path = _require_db()
    if status == "all":
        sql = "SELECT * FROM positions WHERE user_id=? ORDER BY market, broker, name"
        return _query(path, sql, (user_id,))
    else:
        sql = "SELECT * FROM positions WHERE status=? AND user_id=? ORDER BY market, broker, name"
        return _query(path, sql, (status, user_id))


@router.post("/positions")
def upsert_position_api(pos: PositionIn, user_id: str = Depends(get_current_user)):
    """Create or update a position (upsert by ticker+broker)."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_position, get_conn
    init_db()
    with get_conn() as conn:
        upsert_position(
            conn, ticker=pos.ticker, name=pos.name, market=pos.market,
            broker=pos.broker, quantity=pos.quantity,
            cost_price=pos.cost_price, currency=pos.currency, user_id=user_id,
        )
        conn.commit()
    return {"ok": True}


@router.delete("/positions/{ticker}/{broker}")
def delete_position_api(ticker: str, broker: str, user_id: str = Depends(get_current_user)):
    """Delete a position by ticker+broker."""
    path = _require_db()
    import sqlite3 as _sqlite3
    with _sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM positions WHERE ticker=? AND broker=? AND user_id=?", (ticker, broker, user_id)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Position not found")
    return {"ok": True}


@router.get("/closed-trades")
def list_closed_trades(user_id: str = Depends(get_current_user)):
    """List all closed (realized) trades."""
    path = _require_db()
    return _query(path, "SELECT * FROM closed_trades WHERE user_id=? ORDER BY market, abs(realized_pnl) DESC", (user_id,))


@router.post("/closed-trades")
def add_closed_trade(trade: ClosedTradeIn, user_id: str = Depends(get_current_user)):
    """Record a closed trade."""
    _require_db()
    import datetime as _dt
    from backend.services.portfolio_db import (
        init_db, insert_closed_trade, get_conn, compute_locked_ytd_cny,
    )
    init_db()
    with get_conn() as conn:
        # Lock this sale's YTD attribution now, while the baseline still
        # describes the lot being sold — immune to later baseline resets
        # (full close + re-buy) and FX drift.
        ytd_locked = compute_locked_ytd_cny(
            conn, ticker=trade.ticker, broker=trade.broker, market=trade.market,
            currency=trade.currency, quantity=trade.quantity,
            close_price=trade.sell_price, realized_pnl=trade.realized_pnl,
            realized_pnl_cny=trade.realized_pnl_cny, user_id=user_id,
        )
        insert_closed_trade(
            conn, ticker=trade.ticker, name=trade.name, market=trade.market,
            broker=trade.broker, currency=trade.currency,
            realized_pnl=trade.realized_pnl,
            realized_pnl_cny=trade.realized_pnl_cny,
            quantity=trade.quantity,
            cost_price=trade.buy_price, close_price=trade.sell_price,
            close_date=_dt.date.today().isoformat(),
            ytd_pnl_cny_locked=ytd_locked,
            user_id=user_id,
        )
        conn.commit()
    return {"ok": True}


@router.get("/cash")
def list_cash(user_id: str = Depends(get_current_user)):
    """List cash balances across all accounts."""
    path = _require_db()
    return _query(path, "SELECT * FROM cash_balances WHERE user_id=? ORDER BY account", (user_id,))


@router.post("/cash")
def update_cash(cash: CashIn, user_id: str = Depends(get_current_user)):
    """Update cash balance for an account."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_cash, get_conn
    init_db()
    with get_conn() as conn:
        upsert_cash(conn, account=cash.account, currency=cash.currency, balance=cash.balance, user_id=user_id)
        conn.commit()
    return {"ok": True}


@router.delete("/cash/{account}/{currency}")
def delete_cash_api(account: str, currency: str, user_id: str = Depends(get_current_user)):
    """Delete a cash balance row by account+currency."""
    path = _require_db()
    import sqlite3 as _sqlite3
    with _sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM cash_balances WHERE account=? AND currency=? AND user_id=?",
            (account, currency, user_id))
        conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(404, "Cash row not found")
    return {"ok": True}


@router.get("/account-settings")
def list_account_settings(user_id: str = Depends(get_current_user)):
    """List all account capital settings."""
    _require_db()
    from backend.services.portfolio_db import init_db, get_account_settings, get_conn
    init_db()
    with get_conn() as conn:
        return get_account_settings(conn, user_id=user_id)


@router.post("/account-settings")
def upsert_account_setting_api(setting: AccountSettingIn, user_id: str = Depends(get_current_user)):
    """Create or update account capital settings."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_account_setting, get_conn
    init_db()
    with get_conn() as conn:
        upsert_account_setting(
            conn, broker=setting.broker, capital_mode=setting.capital_mode,
            deposit_cny=setting.deposit_cny, deposit_fx=setting.deposit_fx,
            notes=setting.notes, cost_method=setting.cost_method, user_id=user_id,
            hk_connect=setting.hk_connect,
        )
        conn.commit()
    return {"ok": True}


@router.delete("/account-settings/{broker}")
def delete_account_setting_api(broker: str, user_id: str = Depends(get_current_user)):
    """Delete account capital settings (reverts to cost mode)."""
    _require_db()
    from backend.services.portfolio_db import init_db, delete_account_setting, get_conn
    init_db()
    with get_conn() as conn:
        affected = delete_account_setting(conn, broker, user_id=user_id)
        conn.commit()
        if affected == 0:
            raise HTTPException(status_code=404, detail="Account setting not found")
    return {"ok": True}


class MergeAccountRequest(BaseModel):
    source: str       # account to merge FROM (will be deleted)
    target: str       # account to merge INTO (will be kept)


@router.post("/merge-accounts")
def merge_accounts(req: MergeAccountRequest, user_id: str = Depends(get_current_user)):
    """Merge one account into another: rename all records from source to target, then delete source settings."""
    _require_db()
    from backend.services.portfolio_db import init_db, get_conn
    init_db()

    if req.source == req.target:
        raise HTTPException(status_code=400, detail="Source and target must be different")

    with get_conn() as conn:
        # Count affected records
        counts = {}
        for table, col in [("positions", "broker"), ("cash_balances", "account"),
                           ("closed_trades", "broker"), ("deposit_history", "broker")]:
            try:
                cur = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=? AND user_id=?",
                                   (req.source, user_id))
                counts[table] = cur.fetchone()[0]
            except Exception:
                counts[table] = 0

        if sum(counts.values()) == 0:
            # No records to merge — just check if source account_settings exists
            cur = conn.execute("SELECT COUNT(*) FROM account_settings WHERE broker=? AND user_id=?",
                               (req.source, user_id))
            if cur.fetchone()[0] == 0:
                raise HTTPException(status_code=404, detail=f"Account '{req.source}' not found")

        # Rename all records from source to target
        for table, col in [("positions", "broker"), ("closed_trades", "broker"),
                           ("deposit_history", "broker")]:
            try:
                conn.execute(f"UPDATE {table} SET {col}=? WHERE {col}=? AND user_id=?",
                             (req.target, req.source, user_id))
            except Exception:
                pass

        # Cash balances: merge by summing if target already has same currency entry
        try:
            source_cash = conn.execute(
                "SELECT currency, balance FROM cash_balances WHERE account=? AND user_id=?",
                (req.source, user_id)
            ).fetchall()
            for currency, balance in source_cash:
                existing = conn.execute(
                    "SELECT balance FROM cash_balances WHERE account=? AND currency=? AND user_id=?",
                    (req.target, currency, user_id)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE cash_balances SET balance=?, updated_at=datetime('now','localtime') "
                        "WHERE account=? AND currency=? AND user_id=?",
                        (existing[0] + balance, req.target, currency, user_id)
                    )
                else:
                    conn.execute(
                        "UPDATE cash_balances SET account=? WHERE account=? AND currency=? AND user_id=?",
                        (req.target, req.source, currency, user_id)
                    )
            # Delete any remaining source cash rows
            conn.execute("DELETE FROM cash_balances WHERE account=? AND user_id=?",
                         (req.source, user_id))
        except Exception:
            pass

        # Delete source account_settings
        conn.execute("DELETE FROM account_settings WHERE broker=? AND user_id=?",
                     (req.source, user_id))

        conn.commit()

    return {
        "ok": True,
        "merged": counts,
        "message": f"Merged '{req.source}' into '{req.target}'",
    }


@router.get("/flows")
def list_all_flows(limit: int = Query(200, ge=1, le=1000),
                   user_id: str = Depends(get_current_user)):
    """All cash-flow records across brokers, newest first (Flows tab)."""
    path = _require_db()
    return _query(path, """
        SELECT * FROM deposit_history WHERE user_id=?
        ORDER BY COALESCE(deposit_date, substr(created_at, 1, 10)) DESC, id DESC
        LIMIT ?
    """, (user_id, limit))


@router.get("/deposit-history/{broker}")
def list_deposit_history(broker: str, user_id: str = Depends(get_current_user)):
    """List deposit history records for a broker."""
    _require_db()
    from backend.services.portfolio_db import init_db, get_deposit_history, get_conn
    init_db()
    with get_conn() as conn:
        return get_deposit_history(conn, broker, user_id=user_id)


@router.post("/deposit-history")
def add_deposit_record_api(data: DepositRecordIn, user_id: str = Depends(get_current_user)):
    """Add a deposit record and auto-recalculate totals."""
    _require_db()
    from backend.services.portfolio_db import init_db, add_deposit_record, get_conn
    init_db()
    with get_conn() as conn:
        add_deposit_record(conn, data.broker, data.amount_cny,
                           data.fx_rate, data.deposit_date, data.notes, user_id=user_id,
                           currency=data.currency, amount=data.amount,
                           update_cash=data.update_cash)
        conn.commit()
    return {"ok": True}


@router.delete("/deposit-history/{record_id}")
def delete_deposit_record_api(record_id: int, user_id: str = Depends(get_current_user)):
    """Delete a deposit history record and recalculate totals."""
    _require_db()
    from backend.services.portfolio_db import init_db, delete_deposit_record, get_conn
    init_db()
    with get_conn() as conn:
        broker = delete_deposit_record(conn, record_id, user_id=user_id)
        conn.commit()
        if not broker:
            raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True}


@router.get("/margin")
def list_margin(user_id: str = Depends(get_current_user)):
    """List margin/leverage balances."""
    path = _require_db()
    return _query(path, "SELECT * FROM margin_balances WHERE user_id=? ORDER BY broker", (user_id,))


@router.post("/margin")
def update_margin(m: MarginIn, user_id: str = Depends(get_current_user)):
    """Update a margin/leverage balance."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_margin, get_conn
    init_db()
    with get_conn() as conn:
        upsert_margin(conn, broker=m.broker, category=m.category,
                      currency=m.currency, amount=m.amount, user_id=user_id)
        conn.commit()
    return {"ok": True}


@router.get("/fx-rates")
def get_fx_rates():
    """Get live FX rates (with DB fallback)."""
    path = _require_db()
    from backend.services.portfolio_prices import get_fx_rates as _get_fx
    return _get_fx(db_path=path)


@router.get("/prices/{ticker}")
def get_price(ticker: str):
    """Fetch live price for a single ticker."""
    from backend.services.portfolio_prices import fetch_price, get_previous_close
    price, currency = fetch_price(ticker)
    prev_close = get_previous_close(ticker)
    if price is None:
        raise HTTPException(status_code=404, detail=f"No price for {ticker}")
    return {"ticker": ticker, "price": price, "currency": currency, "prev_close": prev_close}


@router.get("/holdings")
def get_enriched_holdings(user_id: str = Depends(get_current_user)):
    """Get positions enriched with live prices, P&L, daily/YTD returns.

    This is the main data endpoint for the portfolio dashboard — combines
    positions + prices + FX + YTD baselines into a single response.
    """
    path = _require_db()
    from backend.services.portfolio_db import init_db, get_ytd_baselines, get_conn, get_dcf_valuations, compute_capital
    from backend.services.portfolio_prices import (
        fetch_price, get_previous_close, get_fx_rates as _get_fx,
        refresh_all_prices,
    )
    from backend.services.ytd_calc import held_ytd
    import pandas as pd

    init_db()

    # Load positions
    positions = _query(path, "SELECT * FROM positions WHERE status='open' AND user_id=? ORDER BY market, broker, name", (user_id,))
    if not positions:
        return {"holdings": [], "fx": {"CNY": 1.0}, "summary": {}}

    # Per-broker cost convention. 'average' brokers (e.g. Interactive Brokers)
    # keep the true weighted-average cost on a partial sell — realized P&L is
    # booked in closed_trades — so their stocks get fund-style YTD attribution.
    # 'diluted' (default) re-averages cost on sell to absorb realized gains.
    broker_cost_method = {
        r['broker']: (r['cost_method'] or 'diluted')
        for r in _query(path, "SELECT broker, cost_method FROM account_settings WHERE user_id=?", (user_id,))
    }

    # Load industry cache — backfill any tickers missing from cache
    industry_rows = _query(path, "SELECT ticker, sector, industry FROM industry_cache")
    industry_map = {r['ticker']: {'sector': r['sector'] or '', 'industry': r['industry'] or ''} for r in industry_rows}
    all_tickers = [p['ticker'] for p in positions]
    missing_tickers = [t for t in all_tickers if t not in industry_map or (not industry_map[t].get('sector') and not industry_map[t].get('industry'))]
    if missing_tickers:
        from backend.services.portfolio_fmp import fetch_all_industries
        fetched = fetch_all_industries(missing_tickers, db_path=path)
        for t, (sector, industry) in fetched.items():
            industry_map[t] = {'sector': sector or '', 'industry': industry or ''}

    # Load DCF valuations from ValueScope DB
    dcf_map = get_dcf_valuations()

    # Get FX rates
    fx = _get_fx(db_path=path)

    # Prefetch all prices in parallel
    refresh_all_prices(db_path=path)

    # Load YTD baselines — auto-create for new positions missing a baseline
    import datetime
    current_year = datetime.date.today().year
    with get_conn() as conn:
        ytd_baselines = get_ytd_baselines(conn, current_year, user_id=user_id)

        # Backfill baselines for positions added after the yearly snapshot
        missing_baseline = [
            p for p in positions
            if (p['ticker'], p['broker']) not in ytd_baselines
        ]
        if missing_baseline:
            from backend.services.portfolio_db import record_ytd_baselines
            ticker_data = {}
            for p in missing_baseline:
                # Use cost_price as baseline: new mid-year positions start YTD from cost
                ticker_data[(p['ticker'], p['broker'])] = (
                    p['cost_price'], p['currency'], p['quantity'], p['cost_price']
                )
            today_str = datetime.date.today().isoformat()
            record_ytd_baselines(conn, current_year, ticker_data, today_str, user_id=user_id)
            conn.commit()
            # Reload after backfill
            ytd_baselines = get_ytd_baselines(conn, current_year, user_id=user_id)

    # Enrich each position
    holdings = []
    total_equity_cny = 0
    total_cost_cny = 0
    total_pnl_cny = 0
    total_daily_pnl_cny = 0
    total_ytd_pnl_cny = 0

    for pos in positions:
        ticker = pos['ticker']
        qty = pos['quantity']
        cost = pos['cost_price']
        currency = pos['currency']
        rate = fx.get(currency, 1.0)

        # Live price
        price, _ = fetch_price(ticker)
        price_stale = price is None
        if price is None:
            price = cost

        mv = qty * price
        cost_total = qty * cost
        pnl = mv - cost_total
        pnl_pct = (pnl / cost_total * 100) if cost_total != 0 else 0
        mv_cny = mv * rate
        pnl_cny = pnl * rate

        # Daily P&L
        # For positions created today, use cost as base instead of previous close
        import datetime as _dt
        _today_str = _dt.date.today().isoformat()
        _created_today = pos.get('created_at', '')[:10] == _today_str

        # Non-trading day handling is done at the data source level:
        # - Eastmoney: f86 timestamp check → prev_close = price when data is stale
        # - yfinance (non-USD): bar date check → prev_close = last bar close when not today
        # - yfinance (USD extended): prev_close = reg_price (same-day close)
        # - Fund NAV: nav_date check → prev_nav = nav when stale
        # When prev_close == price, daily_pnl naturally = 0.

        prev_close = get_previous_close(ticker)
        if _created_today and not price_stale:
            # New position today: daily P&L = current price vs cost
            daily_pnl = (price - cost) * qty
            daily_pnl_pct = (price / cost - 1) * 100 if cost > 0 else 0
            daily_pnl_cny = daily_pnl * rate
        elif prev_close and prev_close > 0 and not price_stale:
            daily_pnl = (price - prev_close) * qty
            daily_pnl_pct = (price / prev_close - 1) * 100
            daily_pnl_cny = daily_pnl * rate
        else:
            daily_pnl = daily_pnl_pct = daily_pnl_cny = None

        # YTD P&L for held shares only. Sold shares' YTD contribution is captured
        # in closed_trades (aggregated below).
        #
        # Stocks use the cost-adjustment convention: cost_price is re-averaged
        # after each partial sell to absorb realized gains, so `pnl - baseline_unrealized`
        # gives correct YTD.
        #
        # Average-cost instruments don't adjust cost on a partial sell: funds
        # (market='基金', industry standard) and stocks on 'average' brokers like
        # Interactive Brokers. For a partial sell the held YTD is just price drift
        # on remaining units: `(price - bp) × current_qty`. The sold units' realized
        # YTD contribution is locked at sell-time in a closed_trade and picked up by
        # the partial-close branch of the closed_trades aggregation below.
        # Adds (qty > b_qty) still use the standard formula since cost is then a
        # weighted average and the algebra works out.
        uses_avg_cost = (
            pos.get('market') == '基金'
            or broker_cost_method.get(pos.get('broker'), 'diluted') == 'average'
        )
        ytd_pnl = ytd_pnl_pct = ytd_pnl_cny = None
        bd = None
        if ytd_baselines:
            bd = (ytd_baselines.get((ticker, pos['broker']))
                  or ytd_baselines.get((ticker, '')))  # legacy broker-less row
        ytd_pnl = held_ytd(price, cost, qty, bd, uses_avg_cost)
        if ytd_pnl is not None:
            ytd_pnl_pct = (ytd_pnl / cost_total * 100) if cost_total != 0 else 0
            ytd_pnl_cny = ytd_pnl * rate
        # else: no baseline — ytd_pnl stays None (KPI YTD uses snapshot-based calculation)

        total_equity_cny += mv_cny
        total_cost_cny += cost_total * rate
        total_pnl_cny += pnl_cny
        if daily_pnl_cny is not None:
            total_daily_pnl_cny += daily_pnl_cny
        if ytd_pnl_cny is not None:
            total_ytd_pnl_cny += ytd_pnl_cny

        # Industry
        ind = industry_map.get(ticker, {})
        # DCF
        dcf_info = dcf_map.get(ticker)
        dcf_price = dcf_info['dcf_price'] if dcf_info else None
        mos_pct = None
        if dcf_price and price and dcf_price > 0:
            mos_pct = round((dcf_price - price) / dcf_price * 100, 2)

        holdings.append({
            **pos,
            "price": price,
            "price_stale": price_stale,
            "market_value": mv,
            "market_value_cny": mv_cny,
            "cost_total": cost_total,
            "pnl": pnl,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_cny": pnl_cny,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": round(daily_pnl_pct, 2) if daily_pnl_pct is not None else None,
            "daily_pnl_cny": daily_pnl_cny,
            "ytd_pnl": ytd_pnl,
            "ytd_pnl_pct": round(ytd_pnl_pct, 2) if ytd_pnl_pct is not None else None,
            "ytd_pnl_cny": ytd_pnl_cny,
            "sector": ind.get('sector', ''),
            "industry": ind.get('industry', ''),
            "dcf_price": dcf_price,
            "mos_pct": mos_pct,
            "weight": 0,  # filled below
        })

    # Calculate weights
    for h in holdings:
        h["weight"] = round(h["market_value_cny"] / total_equity_cny * 100, 2) if total_equity_cny > 0 else 0

    # Cash summary — auto-create cash rows for each currency a broker holds positions in
    cash_rows = _query(path, "SELECT * FROM cash_balances WHERE user_id=? ORDER BY account", (user_id,))
    existing_pairs = {(r['account'], r['currency']) for r in cash_rows}
    # Collect all (broker, currency) pairs from positions
    needed_pairs = set()
    for pos in positions:
        needed_pairs.add((pos['broker'], pos['currency']))
    missing_pairs = needed_pairs - existing_pairs
    if missing_pairs:
        with get_conn() as conn:
            for broker, currency in sorted(missing_pairs):
                conn.execute("""
                    INSERT INTO cash_balances (account, currency, balance, updated_at, user_id)
                    VALUES (?, ?, 0, datetime('now','localtime'), ?)
                """, (broker, currency, user_id))
            conn.commit()
        # Re-fetch after insert
        cash_rows = _query(path, "SELECT * FROM cash_balances WHERE user_id=? ORDER BY account", (user_id,))
    # IBKR-style: negative balances are margin loans, counted as leverage
    _cash_vals = [r['balance'] * fx.get(r['currency'], 1.0) for r in cash_rows]
    cash_cny = sum(v for v in _cash_vals if v >= 0)
    neg_cash_cny = sum(-v for v in _cash_vals if v < 0)

    # Margin / leverage (legacy in_house rows + negative cash + off-exchange)
    margin_rows = _query(path, "SELECT * FROM margin_balances WHERE user_id=?", (user_id,))
    leverage_cny = neg_cash_cny + sum(r['amount'] * fx.get(r['currency'], 1.0) for r in margin_rows)

    total_assets = total_equity_cny + cash_cny
    net_assets = total_assets - leverage_cny

    # Compute capital using the proper deposit-mode formula
    with get_conn() as conn:
        capital = compute_capital(conn, fx, user_id=user_id)
    total_pnl_capital = net_assets - capital  # Total P&L = Net Assets - Capital

    # YTD realized P&L from closed trades (by market).
    # For fully-closed tickers: aggregate Σ realized_pnl across all this year's trades
    # for that ticker and subtract baseline_unrealized once. Robust to share-count
    # changes, partial-sell + cost-basis adjustments, and mid-year buy-then-sell.
    # For partial-closed tickers (still in positions): contribute the YTD-attributable
    # slice of the realized gain, i.e. (close_price − baseline_price) × qty × fx.
    # This locks the sold portion's YTD at sell-time (won't drift with current price)
    # and combines correctly with the fund's held formula (price - bp) × current_qty.
    # Falls back to stored realized_pnl_cny when close_price/qty are missing
    # (legacy records, e.g. Excel-imported partials).
    import datetime as _dt
    from collections import defaultdict
    ytd_start = f"{_dt.date.today().year}-01-01"
    open_pairs = {(p['ticker'], p['broker']) for p in positions}
    ytd_realized_by_market: dict[str, float] = {}
    ytd_realized_total = 0.0

    def _baseline_for(tk: str, brk: str):
        return ytd_baselines.get((tk, brk)) or ytd_baselines.get((tk, ''))

    fc_groups: dict[tuple, dict] = defaultdict(
        lambda: {'realized_native': 0.0, 'market': 'Other', 'currency': 'CNY',
                 'locked_sum': 0.0, 'locked_all': True})

    for row in _query(path,
            "SELECT market, broker, ticker, currency, close_price, quantity, "
            "COALESCE(realized_pnl, 0) AS rpn, "
            "COALESCE(realized_pnl_cny, 0) AS rpl, "
            "ytd_pnl_cny_locked AS locked "
            "FROM closed_trades WHERE close_date >= ? AND user_id=?", (ytd_start, user_id)):
        ticker = row['ticker']
        mkt = row['market'] or 'Other'
        if ticker and (ticker, row['broker']) not in open_pairs:
            g = fc_groups[(ticker, row['broker'])]
            g['realized_native'] += row['rpn']
            g['market'] = mkt
            g['currency'] = row['currency']
            if row['locked'] is not None:
                g['locked_sum'] += row['locked']
            else:
                g['locked_all'] = False
        else:
            # Partial close: sold shares' YTD, locked at sell time.
            # Legacy rows (no locked value) fall back to computing from the
            # live baseline; last resort is the stored realized CNY.
            if row['locked'] is not None:
                contribution = row['locked']
            else:
                baseline = _baseline_for(ticker, row['broker']) if ticker else None
                close_price = row['close_price']
                qty_sold = row['quantity']
                if (baseline is not None and close_price is not None
                        and qty_sold is not None):
                    rate = fx.get(row['currency'], 1.0)
                    contribution = (close_price - baseline['price']) * qty_sold * rate
                else:
                    contribution = row['rpl']
            ytd_realized_by_market[mkt] = ytd_realized_by_market.get(mkt, 0) + contribution
            ytd_realized_total += contribution

    # Fully-closed (ticker, broker) groups. When every trade carries a locked
    # value, sum those (each sale locked at its own time). Otherwise use the
    # aggregate formula Σ realized − baseline_unrealized, robust to partial
    # sells with cost re-averaging and mid-year buy-then-sell.
    for (ticker, brk), g in fc_groups.items():
        rate = fx.get(g['currency'], 1.0)
        if g['locked_all']:
            contribution = g['locked_sum']
        else:
            baseline = _baseline_for(ticker, brk)
            if (baseline is not None
                    and baseline.get('cost_price') is not None
                    and baseline.get('quantity') is not None):
                baseline_unrealized = (baseline['price'] - baseline['cost_price']) * baseline['quantity']
                contribution = (g['realized_native'] - baseline_unrealized) * rate
            else:
                contribution = g['realized_native'] * rate
        ytd_realized_by_market[g['market']] = ytd_realized_by_market.get(g['market'], 0) + contribution
        ytd_realized_total += contribution

    total_ytd_pnl_cny += ytd_realized_total

    # Latest TWR unit NAV (from snapshots) so the KPI row can show it
    unit_nav = None
    unit_nav_date = None
    with get_conn() as conn:
        _r = conn.execute(
            "SELECT unit_nav, date FROM daily_snapshots "
            "WHERE user_id=? AND unit_nav IS NOT NULL ORDER BY date DESC LIMIT 1",
            (user_id,)).fetchone()
        if _r:
            unit_nav, unit_nav_date = _r[0], _r[1]

    summary = {
        "unit_nav": round(unit_nav, 4) if unit_nav else None,
        "unit_nav_date": unit_nav_date,
        "equity_cny": round(total_equity_cny, 2),
        "cash_cny": round(cash_cny, 2),
        "leverage_cny": round(leverage_cny, 2),
        "total_assets": round(total_assets, 2),
        "net_assets": round(net_assets, 2),
        "capital": round(capital, 2),
        "total_pnl_cny": round(total_pnl_cny, 2),
        "total_pnl_capital": round(total_pnl_capital, 2),
        "total_cost_cny": round(total_cost_cny, 2),
        "total_pnl_pct": round(total_pnl_cny / total_cost_cny * 100, 2) if total_cost_cny != 0 else 0,
        "daily_pnl_cny": round(total_daily_pnl_cny, 2),
        "ytd_pnl_cny": round(total_ytd_pnl_cny, 2),
    }

    return {
        "holdings": holdings, "fx": fx, "cash": cash_rows, "summary": summary,
        "ytd_realized_by_market": {k: round(v, 2) for k, v in ytd_realized_by_market.items()},
    }


@router.get("/snapshots")
def list_snapshots(limit: int = Query(90, ge=1, le=365), user_id: str = Depends(get_current_user)):
    """Get daily snapshots (most recent first)."""
    path = _require_db()
    return _query(path, "SELECT * FROM daily_snapshots WHERE user_id=? ORDER BY date DESC LIMIT ?", (user_id, limit))


@router.get("/nav-history")
def get_nav_history(user_id: str = Depends(get_current_user)):
    """Get NAV history for performance charting."""
    path = _require_db()
    return _query(path, "SELECT * FROM nav_history WHERE user_id=? ORDER BY date", (user_id,))


@router.get("/benchmarks")
def get_benchmarks(start: str = "2024-01-01"):
    """Fetch benchmark index data (CSI 300, S&P 500, Hang Seng) via yfinance.

    Returns {name: [{date, close}, ...]} for each benchmark.
    """
    try:
        import yfinance as yf
        import pandas as pd
    except ImportError:
        return {}

    benchmarks = {
        "CSI 300": "000300.SS",
        "S&P 500": "^GSPC",
        "Hang Seng": "^HSI",
    }
    end = (pd.Timestamp.now() + pd.DateOffset(days=1)).strftime("%Y-%m-%d")
    results: dict[str, list] = {}
    for name, ticker in benchmarks.items():
        try:
            hist = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if hist is not None and not hist.empty:
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.droplevel(1)
                df = hist[["Close"]].reset_index()
                df.columns = ["date", "close"]
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                results[name] = df.to_dict(orient="records")
        except Exception:
            pass
    return results


@router.post("/snapshot")
def record_snapshot():
    """Trigger a manual snapshot capture (EOD equivalent)."""
    path = _require_db()
    from backend.services.portfolio_db import init_db, upsert_snapshot
    init_db()
    # The actual snapshot logic would reuse the enriched holdings computation
    # For now, return a placeholder — full implementation in Phase 4
    raise HTTPException(status_code=501, detail="Snapshot recording via API — coming in Phase 4")


# ── Import / Export ─────────────────────────────────────

_TEMPLATES = {
    "positions": {
        "headers": ["ticker", "name", "market", "broker", "currency", "quantity", "cost_price"],
        "rows": [
            ["600809.SS", "山西汾酒", "A股", "中信", "CNY", "200", "162.85"],
            ["GOOGL", "谷歌", "美股", "富途", "USD", "15", "635.1"],
        ],
        "filename": "positions_template.csv",
    },
    "cash": {
        "headers": ["account", "currency", "balance"],
        "rows": [
            ["中信", "CNY", "8057"],
            ["招商银行", "CNY", "9569"],
        ],
        "filename": "cash_template.csv",
    },
    "portfolio": {
        "headers": ["ticker", "name", "market", "broker", "currency", "quantity", "cost_price", "cash_balance"],
        "rows": [
            ["600809.SS", "山西汾酒", "A股", "中信", "CNY", "200", "162.85", ""],
            ["GOOGL", "谷歌", "美股", "富途", "USD", "15", "635.1", ""],
            ["", "", "", "中信", "CNY", "", "", "8057"],
            ["", "", "", "富途", "HKD", "", "", "35000"],
        ],
        "filename": "portfolio_template.csv",
    },
}


@router.get("/import-template/{template_type}")
def download_import_template(template_type: str):
    """Download a CSV template with headers and example rows."""
    if template_type not in _TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template type: {template_type}. Use: {list(_TEMPLATES)}")
    tpl = _TEMPLATES[template_type]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(tpl["headers"])
    for row in tpl["rows"]:
        writer.writerow(row)
    # Encode with BOM for Excel compatibility
    content = buf.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{tpl["filename"]}"'},
    )


@router.post("/import")
async def import_csv(file: UploadFile = File(...), user_id: str = Depends(get_current_user)):
    """Import positions or cash from a CSV file upload."""
    _require_db()
    from backend.services.portfolio_db import (
        init_db, get_conn, upsert_position, upsert_cash, upsert_account_setting,
    )
    init_db()

    # Read and decode file content (handle BOM)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("utf-8")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV file")

    # Normalize headers (strip whitespace)
    headers = [h.strip().lower() for h in reader.fieldnames]

    # Detect type: mixed (has both ticker and cash_balance), positions-only, or cash-only
    has_ticker_col = "ticker" in headers
    has_cash_balance_col = "cash_balance" in headers
    has_account_col = "account" in headers

    if has_ticker_col:
        csv_type = "mixed" if has_cash_balance_col else "positions"
    elif has_account_col:
        csv_type = "cash"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot detect CSV type from headers: {reader.fieldnames}. "
                   "Must have 'ticker' column (positions/mixed) or 'account' column (cash).",
        )

    imported_positions = 0
    imported_cash = 0
    accounts_created: list[str] = []
    errors: list[str] = []

    with get_conn() as conn:
        # Collect existing brokers/accounts
        existing_brokers = {
            r[0] for r in conn.execute("SELECT broker FROM account_settings WHERE user_id=?", (user_id,)).fetchall()
        }
        existing_cash_accounts = {
            r[0] for r in conn.execute("SELECT DISTINCT account FROM cash_balances WHERE user_id=?", (user_id,)).fetchall()
        }

        for i, raw_row in enumerate(reader, start=2):
            row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}
            try:
                ticker = row.get("ticker", "").strip()
                cash_balance_str = row.get("cash_balance", "").strip()

                if csv_type == "cash":
                    # Pure cash CSV (account, currency, balance)
                    account = row["account"]
                    currency = row.get("currency", "CNY")
                    balance = float(row.get("balance", 0))
                    if not account:
                        errors.append(f"Row {i}: account is required")
                        continue
                    upsert_cash(conn, account=account, currency=currency, balance=balance, user_id=user_id)
                    imported_cash += 1

                elif ticker:
                    # Position row (has ticker)
                    name = row.get("name", "")
                    market = row.get("market", "")
                    broker = row.get("broker", "")
                    currency = row.get("currency", "CNY")
                    quantity = float(row.get("quantity", 0))
                    cost_price = float(row.get("cost_price", 0))

                    if not broker:
                        errors.append(f"Row {i}: broker is required for position rows")
                        continue

                    # Auto-create account_settings for new brokers
                    if broker not in existing_brokers:
                        upsert_account_setting(conn, broker=broker, capital_mode="cost", user_id=user_id)
                        existing_brokers.add(broker)
                        accounts_created.append(broker)

                    # Auto-create cash row for new broker (balance 0)
                    if broker not in existing_cash_accounts:
                        upsert_cash(conn, account=broker, currency="CNY", balance=0, user_id=user_id)
                        existing_cash_accounts.add(broker)

                    upsert_position(
                        conn, ticker=ticker, name=name, market=market,
                        broker=broker, currency=currency,
                        quantity=quantity, cost_price=cost_price, user_id=user_id,
                    )
                    imported_positions += 1

                elif cash_balance_str and csv_type == "mixed":
                    # Cash row in mixed CSV (ticker is empty, cash_balance has value)
                    account = row.get("broker", "")
                    currency = row.get("currency", "CNY")
                    balance = float(cash_balance_str)
                    if not account:
                        errors.append(f"Row {i}: broker is required for cash rows")
                        continue
                    upsert_cash(conn, account=account, currency=currency, balance=balance, user_id=user_id)
                    existing_cash_accounts.add(account)
                    imported_cash += 1

                else:
                    # Skip empty rows silently
                    pass

            except (ValueError, KeyError) as exc:
                errors.append(f"Row {i}: {exc}")

        conn.commit()

    # Detect similar broker names that might be duplicates
    warnings: list[str] = []
    all_brokers = list(existing_brokers)
    for i, a in enumerate(all_brokers):
        for b in all_brokers[i + 1:]:
            if a == b:
                continue
            # Check if one contains the other (e.g. "中信" vs "中信证券")
            if a in b or b in a:
                warnings.append(f"账户名 \"{a}\" 和 \"{b}\" 相似，是否为同一账户？如有误请在「设置」中统一。"
                                f" / Similar accounts \"{a}\" and \"{b}\" — same broker? Fix in Settings if needed.")

    imported = imported_positions + imported_cash
    result_type = "positions" if imported_cash == 0 else ("cash" if imported_positions == 0 else "mixed")
    return {
        "ok": True,
        "type": result_type,
        "imported": imported,
        "imported_positions": imported_positions,
        "imported_cash": imported_cash,
        "accounts_created": accounts_created,
        "errors": errors,
        "warnings": warnings,
    }


@router.get("/export")
def export_all(user_id: str = Depends(get_current_user)):
    """Export all portfolio data as JSON backup."""
    path = _require_db()
    return {
        "positions": _query(path, "SELECT * FROM positions WHERE user_id=? ORDER BY market, broker, name", (user_id,)),
        "cash_balances": _query(path, "SELECT * FROM cash_balances WHERE user_id=? ORDER BY account", (user_id,)),
        "account_settings": _query(path, "SELECT * FROM account_settings WHERE user_id=? ORDER BY broker", (user_id,)),
        "closed_trades": _query(path, "SELECT * FROM closed_trades WHERE user_id=? ORDER BY market, name", (user_id,)),
    }


@router.get("/export-excel")
def export_excel(user_id: str = Depends(get_current_user)):
    """Export portfolio data as a formatted Excel workbook."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill, numbers

    path = _require_db()

    positions = _query(path, """
        SELECT ticker, name, market, broker, currency, quantity, cost_price, status
        FROM positions WHERE user_id=? ORDER BY market, broker, name
    """, (user_id,))
    cash = _query(path, """
        SELECT account, currency, balance
        FROM cash_balances WHERE user_id=? ORDER BY account
    """, (user_id,))
    closed = _query(path, """
        SELECT ticker, name, market, broker, currency, quantity, cost_price,
               close_price, realized_pnl, realized_pnl_cny, close_date, notes
        FROM closed_trades WHERE user_id=? ORDER BY close_date DESC
    """, (user_id,))
    acct = _query(path, """
        SELECT broker, capital_mode, deposit_cny, deposit_fx, notes
        FROM account_settings WHERE user_id=? ORDER BY broker
    """, (user_id,))

    wb = Workbook()
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_text = Font(bold=True, color="FFFFFF", size=11)
    wrap = Alignment(wrap_text=True, vertical="top")

    def _write_sheet(ws, title, headers, rows):
        ws.title = title
        ws.append(headers)
        for cell in ws[1]:
            cell.font = header_text
            cell.fill = header_fill
        for row in rows:
            ws.append([row.get(h) for h in headers])
        # Auto-fit columns
        for col_cells in ws.columns:
            col_letter = col_cells[0].column_letter
            max_len = max((len(str(c.value or "")) for c in col_cells), default=8)
            ws.column_dimensions[col_letter].width = min(max_len + 3, 30)
        # Format numbers
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value, float):
                    cell.number_format = '#,##0.00'

    # Sheet 1: Holdings
    h_headers = ["ticker", "name", "market", "broker", "currency", "quantity", "cost_price", "status"]
    _write_sheet(wb.active, "Holdings", h_headers, positions)

    # Sheet 2: Cash
    ws_cash = wb.create_sheet()
    _write_sheet(ws_cash, "Cash", ["account", "currency", "balance"], cash)

    # Sheet 3: Closed Trades
    ws_closed = wb.create_sheet()
    ct_headers = ["ticker", "name", "market", "broker", "currency", "quantity",
                  "cost_price", "close_price", "realized_pnl", "realized_pnl_cny", "close_date", "notes"]
    _write_sheet(ws_closed, "Closed Trades", ct_headers, closed)

    # Sheet 4: Account Settings
    ws_acct = wb.create_sheet()
    _write_sheet(ws_acct, "Accounts", ["broker", "capital_mode", "deposit_cny", "deposit_fx", "notes"], acct)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    today = __import__("datetime").date.today().isoformat()
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Portfolio_{today}.xlsx"'},
    )


# ── Portfolio Event Feeds ──────────────────────────────────

import time
from urllib.request import urlopen, Request
import json as _json
from concurrent.futures import ThreadPoolExecutor, as_completed

_event_cache: dict[str, tuple[float, list]] = {}  # key → (timestamp, data)
_EVENT_TTL_NEWS = 600   # 10 min
_EVENT_TTL_OTHER = 3600  # 1 hour


def _cached_or_fetch(cache_key: str, ttl: int, fetch_fn):
    """Return cached data or call fetch_fn and cache result."""
    entry = _event_cache.get(cache_key)
    if entry and (time.time() - entry[0]) < ttl:
        return entry[1]
    data = fetch_fn()
    _event_cache[cache_key] = (time.time(), data)
    return data


def _fmp_get(path: str, apikey: str, params: str = "") -> list:
    """Quick FMP API GET, returns list or []."""
    if not apikey:
        return []
    url = f"https://financialmodelingprep.com/api/v3/{path}?apikey={apikey}{params}"
    try:
        req = Request(url, headers={"User-Agent": "ValueScope/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"FMP API error ({path}): {e}")
        return []


def _get_tickers_by_market(db_path: str, user_id: str = "local") -> dict[str, list[dict]]:
    """Group open tickers by market type."""
    from backend.services.portfolio_db import get_conn, get_open_tickers
    conn = get_conn(db_path)
    tickers = get_open_tickers(conn, user_id=user_id)
    conn.close()
    groups: dict[str, list[dict]] = {"us": [], "hk": [], "ashare": [], "jp": []}
    for t in tickers:
        mk = (t.get("market") or "").upper()
        tk = t["ticker"]
        if mk in ("SHZ", "SHA", "BJ") or tk.endswith((".SZ", ".SS", ".BJ")):
            groups["ashare"].append(t)
        elif mk == "HKSE" or tk.endswith(".HK"):
            groups["hk"].append(t)
        elif tk.endswith(".T"):
            groups["jp"].append(t)
        else:
            groups["us"].append(t)
    return groups


@router.get("/news")
def portfolio_news(apikey: str = Query("", description="FMP API key"), user_id: str = Depends(get_current_user)):
    """Aggregated news for all portfolio holdings."""
    path = _require_db()
    apikey = apikey or os.environ.get("FMP_API_KEY", "")

    def _fetch():
        groups = _get_tickers_by_market(path, user_id=user_id)
        all_news = []

        # FMP news for US + HK stocks
        fmp_tickers = [t["ticker"] for t in groups["us"] + groups["hk"]]
        if fmp_tickers and apikey:
            # FMP accepts comma-separated symbols
            symbols = ",".join(fmp_tickers[:20])  # limit to 20
            items = _fmp_get("stock_news", apikey, f"&tickers={symbols}&limit=30")
            for item in items:
                all_news.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("site", ""),
                    "date": item.get("publishedDate", ""),
                    "ticker": item.get("symbol", ""),
                    "image": item.get("image", ""),
                })

        # A-share news via akshare
        for t in groups["ashare"][:10]:
            try:
                import akshare as ak
                code = t["ticker"].split(".")[0]
                df = ak.stock_news_em(symbol=code)
                if df is not None and not df.empty:
                    for _, row in df.head(3).iterrows():
                        all_news.append({
                            "title": str(row.get("新闻标题", "")),
                            "url": str(row.get("新闻链接", "")),
                            "source": str(row.get("文章来源", "东方财富")),
                            "date": str(row.get("发布时间", "")),
                            "ticker": t["ticker"],
                            "image": "",
                        })
            except Exception as e:
                logger.warning(f"akshare news error for {t['ticker']}: {e}")

        # Sort by date descending
        all_news.sort(key=lambda x: x.get("date", ""), reverse=True)
        return all_news[:50]

    return _cached_or_fetch(f"news:{path}:{user_id}", _EVENT_TTL_NEWS, _fetch)


@router.get("/earnings-calendar")
def portfolio_earnings(apikey: str = Query("", description="FMP API key"), user_id: str = Depends(get_current_user)):
    """Upcoming and recent earnings for portfolio holdings."""
    path = _require_db()
    apikey = apikey or os.environ.get("FMP_API_KEY", "")

    def _fetch():
        from datetime import datetime, timedelta
        groups = _get_tickers_by_market(path, user_id=user_id)
        events = []

        fmp_tickers = groups["us"] + groups["hk"] + groups["jp"]
        ticker_names = {t["ticker"]: t.get("name", t["ticker"]) for t in fmp_tickers}
        ticker_set = set(ticker_names.keys())

        if apikey and fmp_tickers:
            # Fetch calendar for a date range and filter for our tickers
            today = datetime.now()
            from_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
            to_date = (today + timedelta(days=90)).strftime("%Y-%m-%d")
            items = _fmp_get("earning_calendar", apikey,
                             f"&from={from_date}&to={to_date}")

            for item in items:
                sym = item.get("symbol", "")
                if sym not in ticker_set:
                    continue
                eps_est = item.get("epsEstimated")
                eps_act = item.get("eps")
                status = "reported" if eps_act is not None else "upcoming"
                events.append({
                    "ticker": sym,
                    "name": ticker_names.get(sym, sym),
                    "date": item.get("date", ""),
                    "eps_estimated": eps_est,
                    "eps_actual": eps_act,
                    "revenue_estimated": item.get("revenueEstimated"),
                    "revenue_actual": item.get("revenue"),
                    "status": status,
                })

        # Sort: upcoming first (by date asc), then reported (by date desc)
        upcoming = sorted([e for e in events if e["status"] == "upcoming"],
                          key=lambda x: x["date"])
        reported = sorted([e for e in events if e["status"] == "reported"],
                          key=lambda x: x["date"], reverse=True)
        return upcoming + reported

    return _cached_or_fetch(f"earnings:{path}:{user_id}", _EVENT_TTL_OTHER, _fetch)


@router.get("/rating-changes")
def portfolio_ratings(apikey: str = Query("", description="FMP API key"), user_id: str = Depends(get_current_user)):
    """Recent analyst rating changes for portfolio holdings."""
    path = _require_db()
    apikey = apikey or os.environ.get("FMP_API_KEY", "")

    def _fetch():
        groups = _get_tickers_by_market(path, user_id=user_id)
        changes = []

        fmp_tickers = groups["us"] + groups["hk"]
        if apikey and fmp_tickers:
            from datetime import datetime, timedelta
            cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

            def _fetch_grades(t):
                items = _fmp_get(f"grade/{t['ticker']}", apikey, "&limit=10")
                result = []
                for item in items:
                    dt = item.get("date", "")[:10]
                    if dt < cutoff:
                        continue
                    prev = item.get("previousGrade", "")
                    new = item.get("newGrade", "")
                    direction = "maintain"
                    # Simple upgrade/downgrade detection
                    buy_words = {"buy", "overweight", "outperform", "strong buy", "positive"}
                    sell_words = {"sell", "underweight", "underperform", "strong sell", "negative"}
                    hold_words = {"hold", "neutral", "equal-weight", "market perform", "equal weight", "sector perform", "in-line"}
                    prev_l, new_l = prev.lower(), new.lower()
                    prev_rank = 3 if any(w in prev_l for w in buy_words) else (1 if any(w in prev_l for w in sell_words) else 2)
                    new_rank = 3 if any(w in new_l for w in buy_words) else (1 if any(w in new_l for w in sell_words) else 2)
                    if new_rank > prev_rank:
                        direction = "upgrade"
                    elif new_rank < prev_rank:
                        direction = "downgrade"

                    result.append({
                        "ticker": t["ticker"],
                        "name": t.get("name", t["ticker"]),
                        "date": dt,
                        "company": item.get("gradingCompany", ""),
                        "previous": prev,
                        "new": new,
                        "direction": direction,
                    })
                return result

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(_fetch_grades, t): t for t in fmp_tickers[:20]}
                for f in as_completed(futures):
                    try:
                        changes.extend(f.result())
                    except Exception as e:
                        logger.warning(f"Rating fetch error: {e}")

        changes.sort(key=lambda x: x["date"], reverse=True)
        return changes

    return _cached_or_fetch(f"ratings:{path}:{user_id}", _EVENT_TTL_OTHER, _fetch)
