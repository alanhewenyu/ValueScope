# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Portfolio Tracker API — positions, cash, snapshots, KPI.

All data lives in a local SQLite database (PORTFOLIO_DB_PATH env var).
This router is only active when the database file exists, keeping the
public deployment unaffected.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("valuescope.portfolio.api")

router = APIRouter()

# ── Helpers ──────────────────────────────────────────────

def _get_db_path() -> str:
    from backend.services.portfolio_db import DB_PATH
    return DB_PATH


def _require_db() -> str:
    """Return DB_PATH or raise 404 if portfolio DB doesn't exist."""
    path = _get_db_path()
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Portfolio database not configured")
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
def portfolio_status():
    """Check if portfolio feature is available (DB exists)."""
    path = _get_db_path()
    exists = os.path.exists(path)
    return {"available": exists, "db_path": path if exists else None}


@router.get("/positions")
def list_positions(status: str = Query("open", pattern="^(open|closed|all)$")):
    """List portfolio positions."""
    path = _require_db()
    if status == "all":
        sql = "SELECT * FROM positions ORDER BY market, broker, name"
    else:
        sql = "SELECT * FROM positions WHERE status=? ORDER BY market, broker, name"
        return _query(path, sql, (status,))
    return _query(path, sql)


@router.post("/positions")
def upsert_position_api(pos: PositionIn):
    """Create or update a position (upsert by ticker+broker)."""
    path = _require_db()
    from backend.services.portfolio_db import init_db, upsert_position
    init_db()
    upsert_position(
        ticker=pos.ticker, name=pos.name, market=pos.market,
        broker=pos.broker, quantity=pos.quantity,
        cost_price=pos.cost_price, currency=pos.currency,
    )
    return {"ok": True}


@router.get("/closed-trades")
def list_closed_trades():
    """List all closed (realized) trades."""
    path = _require_db()
    return _query(path, "SELECT * FROM closed_trades ORDER BY market, abs(realized_pnl) DESC")


@router.post("/closed-trades")
def add_closed_trade(trade: ClosedTradeIn):
    """Record a closed trade."""
    path = _require_db()
    from backend.services.portfolio_db import init_db, insert_closed_trade
    init_db()
    insert_closed_trade(
        ticker=trade.ticker, name=trade.name, market=trade.market,
        broker=trade.broker, quantity=trade.quantity,
        buy_price=trade.buy_price, sell_price=trade.sell_price,
        realized_pnl=trade.realized_pnl,
        realized_pnl_cny=trade.realized_pnl_cny,
        currency=trade.currency,
    )
    return {"ok": True}


@router.get("/cash")
def list_cash():
    """List cash balances across all accounts."""
    path = _require_db()
    return _query(path, "SELECT * FROM cash_balances ORDER BY account")


@router.post("/cash")
def update_cash(cash: CashIn):
    """Update cash balance for an account."""
    path = _require_db()
    from backend.services.portfolio_db import init_db, upsert_cash
    init_db()
    upsert_cash(account=cash.account, currency=cash.currency, balance=cash.balance)
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
def get_enriched_holdings():
    """Get positions enriched with live prices, P&L, daily/YTD returns.

    This is the main data endpoint for the portfolio dashboard — combines
    positions + prices + FX + YTD baselines into a single response.
    """
    path = _require_db()
    from backend.services.portfolio_db import init_db, get_ytd_baselines, get_conn
    from backend.services.portfolio_prices import (
        fetch_price, get_previous_close, get_fx_rates as _get_fx,
        refresh_all_prices,
    )
    import pandas as pd

    init_db()

    # Load positions
    positions = _query(path, "SELECT * FROM positions WHERE status='open' ORDER BY market, broker, name")
    if not positions:
        return {"holdings": [], "fx": {"CNY": 1.0}, "summary": {}}

    # Get FX rates
    fx = _get_fx(db_path=path)

    # Prefetch all prices in parallel
    refresh_all_prices(db_path=path)

    # Load YTD baselines
    import datetime
    current_year = datetime.date.today().year
    with get_conn() as conn:
        ytd_baselines = get_ytd_baselines(conn, current_year)

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
        prev_close = get_previous_close(ticker)
        if prev_close and prev_close > 0 and not price_stale:
            daily_pnl = (price - prev_close) * qty
            daily_pnl_pct = (price / prev_close - 1) * 100
            daily_pnl_cny = daily_pnl * rate
        else:
            daily_pnl = daily_pnl_pct = daily_pnl_cny = None

        # YTD P&L
        ytd_pnl = ytd_pnl_pct = ytd_pnl_cny = None
        if ytd_baselines:
            bd = ytd_baselines.get(ticker)
            if bd is not None:
                bp = bd['price']
                b_qty = bd.get('quantity')
                b_cost = bd.get('cost_price')
                if b_qty is not None and b_cost is not None:
                    baseline_unrealized = (bp - b_cost) * b_qty
                else:
                    baseline_unrealized = (bp - cost) * qty
                ytd_pnl = pnl - baseline_unrealized
                ytd_pnl_pct = (ytd_pnl / cost_total * 100) if cost_total != 0 else 0
                ytd_pnl_cny = ytd_pnl * rate
            else:
                # Position opened after baseline
                ytd_pnl = pnl
                ytd_pnl_pct = pnl_pct
                ytd_pnl_cny = pnl_cny

        total_equity_cny += mv_cny
        total_cost_cny += cost_total * rate
        total_pnl_cny += pnl_cny
        if daily_pnl_cny is not None:
            total_daily_pnl_cny += daily_pnl_cny
        if ytd_pnl_cny is not None:
            total_ytd_pnl_cny += ytd_pnl_cny

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
            "weight": 0,  # filled below
        })

    # Calculate weights
    for h in holdings:
        h["weight"] = round(h["market_value_cny"] / total_equity_cny * 100, 2) if total_equity_cny > 0 else 0

    # Cash summary
    cash_rows = _query(path, "SELECT * FROM cash_balances ORDER BY account")
    cash_cny = sum(r['balance'] * fx.get(r['currency'], 1.0) for r in cash_rows)

    # Margin / leverage
    margin_rows = _query(path, "SELECT * FROM margin_balances")
    leverage_cny = sum(r['amount'] * fx.get(r['currency'], 1.0) for r in margin_rows)

    total_assets = total_equity_cny + cash_cny
    net_assets = total_assets - leverage_cny

    summary = {
        "equity_cny": round(total_equity_cny, 2),
        "cash_cny": round(cash_cny, 2),
        "leverage_cny": round(leverage_cny, 2),
        "total_assets": round(total_assets, 2),
        "net_assets": round(net_assets, 2),
        "total_pnl_cny": round(total_pnl_cny, 2),
        "total_cost_cny": round(total_cost_cny, 2),
        "total_pnl_pct": round(total_pnl_cny / total_cost_cny * 100, 2) if total_cost_cny != 0 else 0,
        "daily_pnl_cny": round(total_daily_pnl_cny, 2),
        "ytd_pnl_cny": round(total_ytd_pnl_cny, 2),
    }

    return {"holdings": holdings, "fx": fx, "cash": cash_rows, "summary": summary}


@router.get("/snapshots")
def list_snapshots(limit: int = Query(90, ge=1, le=365)):
    """Get daily snapshots (most recent first)."""
    path = _require_db()
    return _query(path, "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT ?", (limit,))


@router.get("/nav-history")
def get_nav_history():
    """Get NAV history for performance charting."""
    path = _require_db()
    return _query(path, "SELECT * FROM nav_history ORDER BY date")


@router.post("/snapshot")
def record_snapshot():
    """Trigger a manual snapshot capture (EOD equivalent)."""
    path = _require_db()
    from backend.services.portfolio_db import init_db, upsert_snapshot
    init_db()
    # The actual snapshot logic would reuse the enriched holdings computation
    # For now, return a placeholder — full implementation in Phase 4
    raise HTTPException(status_code=501, detail="Snapshot recording via API — coming in Phase 4")
