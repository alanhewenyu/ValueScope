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

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
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


class AccountSettingIn(BaseModel):
    broker: str
    capital_mode: str = "cost"  # 'cost' or 'deposit'
    deposit_cny: float = 0
    deposit_fx: float = 1.0
    notes: str = ""


class DepositRecordIn(BaseModel):
    broker: str
    amount_cny: float
    fx_rate: float = 1.0
    deposit_date: str = ""
    notes: str = ""


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
def portfolio_status():
    """Check if portfolio feature is available (DB exists)."""
    path = _get_db_path()
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
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_position, get_conn
    init_db()
    with get_conn() as conn:
        upsert_position(
            conn, ticker=pos.ticker, name=pos.name, market=pos.market,
            broker=pos.broker, quantity=pos.quantity,
            cost_price=pos.cost_price, currency=pos.currency,
        )
        conn.commit()
    return {"ok": True}


@router.delete("/positions/{ticker}/{broker}")
def delete_position_api(ticker: str, broker: str):
    """Delete a position by ticker+broker."""
    path = _require_db()
    import sqlite3 as _sqlite3
    with _sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM positions WHERE ticker=? AND broker=?", (ticker, broker)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Position not found")
    return {"ok": True}


@router.get("/closed-trades")
def list_closed_trades():
    """List all closed (realized) trades."""
    path = _require_db()
    return _query(path, "SELECT * FROM closed_trades ORDER BY market, abs(realized_pnl) DESC")


@router.post("/closed-trades")
def add_closed_trade(trade: ClosedTradeIn):
    """Record a closed trade."""
    _require_db()
    from backend.services.portfolio_db import init_db, insert_closed_trade, get_conn
    init_db()
    with get_conn() as conn:
        insert_closed_trade(
            conn, ticker=trade.ticker, name=trade.name, market=trade.market,
            broker=trade.broker, currency=trade.currency,
            realized_pnl=trade.realized_pnl,
            realized_pnl_cny=trade.realized_pnl_cny,
            quantity=trade.quantity,
            cost_price=trade.buy_price, close_price=trade.sell_price,
        )
        conn.commit()
    return {"ok": True}


@router.get("/cash")
def list_cash():
    """List cash balances across all accounts."""
    path = _require_db()
    return _query(path, "SELECT * FROM cash_balances ORDER BY account")


@router.post("/cash")
def update_cash(cash: CashIn):
    """Update cash balance for an account."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_cash, get_conn
    init_db()
    with get_conn() as conn:
        upsert_cash(conn, account=cash.account, currency=cash.currency, balance=cash.balance)
        conn.commit()
    return {"ok": True}


@router.delete("/cash/{account}/{currency}")
def delete_cash_api(account: str, currency: str):
    """Delete a cash balance row by account+currency."""
    path = _require_db()
    import sqlite3 as _sqlite3
    with _sqlite3.connect(path) as conn:
        cursor = conn.execute(
            "DELETE FROM cash_balances WHERE account=? AND currency=?",
            (account, currency))
        conn.commit()
    if cursor.rowcount == 0:
        raise HTTPException(404, "Cash row not found")
    return {"ok": True}


@router.get("/account-settings")
def list_account_settings():
    """List all account capital settings."""
    _require_db()
    from backend.services.portfolio_db import init_db, get_account_settings, get_conn
    init_db()
    with get_conn() as conn:
        return get_account_settings(conn)


@router.post("/account-settings")
def upsert_account_setting_api(setting: AccountSettingIn):
    """Create or update account capital settings."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_account_setting, get_conn
    init_db()
    with get_conn() as conn:
        upsert_account_setting(
            conn, broker=setting.broker, capital_mode=setting.capital_mode,
            deposit_cny=setting.deposit_cny, deposit_fx=setting.deposit_fx,
            notes=setting.notes,
        )
        conn.commit()
    return {"ok": True}


@router.delete("/account-settings/{broker}")
def delete_account_setting_api(broker: str):
    """Delete account capital settings (reverts to cost mode)."""
    _require_db()
    from backend.services.portfolio_db import init_db, delete_account_setting, get_conn
    init_db()
    with get_conn() as conn:
        affected = delete_account_setting(conn, broker)
        conn.commit()
        if affected == 0:
            raise HTTPException(status_code=404, detail="Account setting not found")
    return {"ok": True}


@router.get("/deposit-history/{broker}")
def list_deposit_history(broker: str):
    """List deposit history records for a broker."""
    _require_db()
    from backend.services.portfolio_db import init_db, get_deposit_history, get_conn
    init_db()
    with get_conn() as conn:
        return get_deposit_history(conn, broker)


@router.post("/deposit-history")
def add_deposit_record_api(data: DepositRecordIn):
    """Add a deposit record and auto-recalculate totals."""
    _require_db()
    from backend.services.portfolio_db import init_db, add_deposit_record, get_conn
    init_db()
    with get_conn() as conn:
        add_deposit_record(conn, data.broker, data.amount_cny,
                           data.fx_rate, data.deposit_date, data.notes)
        conn.commit()
    return {"ok": True}


@router.delete("/deposit-history/{record_id}")
def delete_deposit_record_api(record_id: int):
    """Delete a deposit history record and recalculate totals."""
    _require_db()
    from backend.services.portfolio_db import init_db, delete_deposit_record, get_conn
    init_db()
    with get_conn() as conn:
        broker = delete_deposit_record(conn, record_id)
        conn.commit()
        if not broker:
            raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True}


@router.get("/margin")
def list_margin():
    """List margin/leverage balances."""
    path = _require_db()
    return _query(path, "SELECT * FROM margin_balances ORDER BY broker")


@router.post("/margin")
def update_margin(m: MarginIn):
    """Update a margin/leverage balance."""
    _require_db()
    from backend.services.portfolio_db import init_db, upsert_margin, get_conn
    init_db()
    with get_conn() as conn:
        upsert_margin(conn, broker=m.broker, category=m.category,
                      currency=m.currency, amount=m.amount)
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
def get_enriched_holdings():
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
    import pandas as pd

    init_db()

    # Load positions
    positions = _query(path, "SELECT * FROM positions WHERE status='open' ORDER BY market, broker, name")
    if not positions:
        return {"holdings": [], "fx": {"CNY": 1.0}, "summary": {}}

    # Load industry cache
    industry_rows = _query(path, "SELECT ticker, sector, industry FROM industry_cache")
    industry_map = {r['ticker']: {'sector': r['sector'] or '', 'industry': r['industry'] or ''} for r in industry_rows}

    # Load DCF valuations from ValueScope DB
    dcf_map = get_dcf_valuations()

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
        # For positions created today, use cost as base instead of previous close
        import datetime as _dt
        _today_str = _dt.date.today().isoformat()
        _created_today = pos.get('created_at', '')[:10] == _today_str
        _updated_today = pos.get('updated_at', '')[:10] == _today_str

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

        # YTD P&L
        ytd_pnl = ytd_pnl_pct = ytd_pnl_cny = None
        bd = ytd_baselines.get(ticker) if ytd_baselines else None
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
    cash_rows = _query(path, "SELECT * FROM cash_balances ORDER BY account")
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
                    INSERT INTO cash_balances (account, currency, balance, updated_at)
                    VALUES (?, ?, 0, datetime('now','localtime'))
                """, (broker, currency))
            conn.commit()
        # Re-fetch after insert
        cash_rows = _query(path, "SELECT * FROM cash_balances ORDER BY account")
    cash_cny = sum(r['balance'] * fx.get(r['currency'], 1.0) for r in cash_rows)

    # Margin / leverage
    margin_rows = _query(path, "SELECT * FROM margin_balances")
    leverage_cny = sum(r['amount'] * fx.get(r['currency'], 1.0) for r in margin_rows)

    total_assets = total_equity_cny + cash_cny
    net_assets = total_assets - leverage_cny

    # Compute capital using the proper deposit-mode formula
    with get_conn() as conn:
        capital = compute_capital(conn, fx)
    total_pnl_capital = net_assets - capital  # Total P&L = Net Assets - Capital

    # YTD realized P&L from closed trades (by market)
    import datetime as _dt
    ytd_start = f"{_dt.date.today().year}-01-01"
    ytd_realized_by_market: dict[str, float] = {}
    ytd_realized_total = 0.0
    for row in _query(path,
            "SELECT market, COALESCE(realized_pnl_cny, 0) AS rpl "
            "FROM closed_trades WHERE close_date >= ?", (ytd_start,)):
        mkt = row['market'] or 'Other'
        ytd_realized_by_market[mkt] = ytd_realized_by_market.get(mkt, 0) + row['rpl']
        ytd_realized_total += row['rpl']

    total_ytd_pnl_cny += ytd_realized_total

    summary = {
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
def list_snapshots(limit: int = Query(90, ge=1, le=365)):
    """Get daily snapshots (most recent first)."""
    path = _require_db()
    return _query(path, "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT ?", (limit,))


@router.get("/nav-history")
def get_nav_history():
    """Get NAV history for performance charting."""
    path = _require_db()
    return _query(path, "SELECT * FROM nav_history ORDER BY date")


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
async def import_csv(file: UploadFile = File(...)):
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

    # Detect type
    if "ticker" in headers:
        csv_type = "positions"
    elif "account" in headers:
        csv_type = "cash"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot detect CSV type from headers: {reader.fieldnames}. "
                   "Positions CSV must have 'ticker' column; cash CSV must have 'account' column.",
        )

    imported = 0
    accounts_created: list[str] = []
    errors: list[str] = []

    with get_conn() as conn:
        if csv_type == "positions":
            # Collect existing brokers in account_settings
            existing_brokers = {
                r[0] for r in conn.execute("SELECT broker FROM account_settings").fetchall()
            }
            existing_cash_accounts = {
                r[0] for r in conn.execute("SELECT DISTINCT account FROM cash_balances").fetchall()
            }

            for i, raw_row in enumerate(reader, start=2):
                # Normalize keys
                row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}
                try:
                    ticker = row["ticker"]
                    name = row.get("name", "")
                    market = row.get("market", "")
                    broker = row.get("broker", "")
                    currency = row.get("currency", "CNY")
                    quantity = float(row.get("quantity", 0))
                    cost_price = float(row.get("cost_price", 0))

                    if not ticker or not broker:
                        errors.append(f"Row {i}: ticker and broker are required")
                        continue

                    # Auto-create account_settings for new brokers
                    if broker not in existing_brokers:
                        upsert_account_setting(conn, broker=broker, capital_mode="cost")
                        existing_brokers.add(broker)
                        accounts_created.append(broker)

                    # Auto-create cash row for new broker
                    if broker not in existing_cash_accounts:
                        upsert_cash(conn, account=broker, currency="CNY", balance=0)
                        existing_cash_accounts.add(broker)

                    upsert_position(
                        conn, ticker=ticker, name=name, market=market,
                        broker=broker, currency=currency,
                        quantity=quantity, cost_price=cost_price,
                    )
                    imported += 1
                except (ValueError, KeyError) as exc:
                    errors.append(f"Row {i}: {exc}")

        else:  # cash
            for i, raw_row in enumerate(reader, start=2):
                row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}
                try:
                    account = row["account"]
                    currency = row.get("currency", "CNY")
                    balance = float(row.get("balance", 0))

                    if not account:
                        errors.append(f"Row {i}: account is required")
                        continue

                    upsert_cash(conn, account=account, currency=currency, balance=balance)
                    imported += 1
                except (ValueError, KeyError) as exc:
                    errors.append(f"Row {i}: {exc}")

        conn.commit()

    return {
        "ok": True,
        "type": csv_type,
        "imported": imported,
        "accounts_created": accounts_created,
        "errors": errors,
    }


@router.get("/export")
def export_all():
    """Export all portfolio data as JSON backup."""
    path = _require_db()
    return {
        "positions": _query(path, "SELECT * FROM positions ORDER BY market, broker, name"),
        "cash_balances": _query(path, "SELECT * FROM cash_balances ORDER BY account"),
        "account_settings": _query(path, "SELECT * FROM account_settings ORDER BY broker"),
        "closed_trades": _query(path, "SELECT * FROM closed_trades ORDER BY market, name"),
    }
