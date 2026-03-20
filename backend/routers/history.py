# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Valuation History API — search, view, delete past DCF valuations.

Replaces the Streamlit viewer.py with a proper REST API that the
Next.js frontend consumes.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from backend.routers.auth import get_current_user

logger = logging.getLogger("valuescope.history")

router = APIRouter()

# ── Helpers ──────────────────────────────────────────────

def _get_db_path() -> str:
    return os.environ.get(
        'VS_DB_PATH',
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     'data', 'valuations.db'),
    )


def _require_db() -> str:
    path = _get_db_path()
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Valuations database not found")
    return path


def _query(path: str, sql: str, params=()):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def _parse_json_fields(record: dict) -> dict:
    """Parse JSON string fields into actual objects for API response."""
    json_fields = [
        'summary_json', 'dcf_table_json', 'sensitivity_json',
        'wacc_sensitivity_json', 'ai_parameters_json',
    ]
    for field in json_fields:
        val = record.get(field)
        if val and isinstance(val, str):
            try:
                record[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass  # keep as string if not valid JSON
    return record


# ── Endpoints ────────────────────────────────────────────

@router.get("/status")
def history_status(user_id: str = Depends(get_current_user)):
    """Check if valuation history feature is available."""
    path = _get_db_path()
    exists = os.path.exists(path)
    count = 0
    if exists:
        try:
            with sqlite3.connect(path) as conn:
                # Check if valuations table exists first
                has_table = conn.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='valuations'"
                ).fetchone()[0]
                if has_table:
                    count = conn.execute("SELECT COUNT(*) FROM valuations WHERE user_id=?", (user_id,)).fetchone()[0]
        except Exception:
            pass
    return {"available": exists, "count": count}


@router.get("/filters")
def get_filter_options(user_id: str = Depends(get_current_user)):
    """Get available filter options (modes, AI engines) for the search UI."""
    path = _require_db()
    with sqlite3.connect(path) as conn:
        # Return empty filters if valuations table doesn't exist yet
        has_table = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='valuations'"
        ).fetchone()[0]
        if not has_table:
            return {"modes": [], "engines": []}
        modes = [r[0] for r in conn.execute("SELECT DISTINCT mode FROM valuations WHERE user_id=?", (user_id,)).fetchall()]
        engines = [r[0] for r in conn.execute(
            "SELECT DISTINCT ai_engine FROM valuations WHERE ai_engine IS NOT NULL AND user_id=?", (user_id,)
        ).fetchall()]
    return {"modes": modes, "engines": engines}


@router.get("/search")
def search_valuations(
    q: str = Query("", description="Search by ticker or company name"),
    modes: Optional[str] = Query(None, description="Comma-separated modes filter"),
    engines: Optional[str] = Query(None, description="Comma-separated AI engine filter"),
    date_start: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_end: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user),
):
    """Search valuation records with optional filters."""
    path = _require_db()

    with sqlite3.connect(path) as conn:
        has_table = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='valuations'"
        ).fetchone()[0]
        if not has_table:
            return {"records": [], "total": 0}

    sql = """SELECT id, ticker, company_name, valuation_date, mode, ai_engine, source,
               currency, reported_currency,
               price_per_share, gap_dcf_price, market_price, gap_market_price, gap_pct,
               gap_adjusted_price, gap_adjusted_price_reporting, forex_rate,
               revenue_growth_1, revenue_growth_2, ebit_margin, wacc, base_year, ttm_label
        FROM valuations WHERE user_id=?"""
    params: list = [user_id]

    if q:
        sql += " AND (company_name LIKE ? OR ticker LIKE ?)"
        params += [f'%{q}%', f'%{q}%']

    if modes:
        mode_list = [m.strip() for m in modes.split(',')]
        sql += f" AND mode IN ({','.join('?' * len(mode_list))})"
        params += mode_list

    if engines:
        engine_list = [e.strip() for e in engines.split(',')]
        sql += f" AND (ai_engine IN ({','.join('?' * len(engine_list))}) OR ai_engine IS NULL)"
        params += engine_list

    if date_start:
        sql += " AND valuation_date >= ?"
        params.append(date_start)

    if date_end:
        sql += " AND valuation_date <= ?"
        params.append(date_end)

    sql += " ORDER BY valuation_date DESC, company_name"
    sql += " LIMIT ? OFFSET ?"
    params += [limit, offset]

    results = _query(path, sql, params)
    return {"results": results, "count": len(results)}


@router.get("/{record_id}")
def get_valuation_detail(record_id: int, user_id: str = Depends(get_current_user)):
    """Get full detail for a single valuation record (including JSON fields)."""
    path = _require_db()
    rows = _query(path, "SELECT * FROM valuations WHERE id = ? AND user_id=?", (record_id, user_id))
    if not rows:
        raise HTTPException(status_code=404, detail="Valuation record not found")
    return _parse_json_fields(rows[0])


@router.delete("/{record_id}")
def delete_valuation(record_id: int, user_id: str = Depends(get_current_user)):
    """Delete a valuation record."""
    path = _require_db()
    with sqlite3.connect(path) as conn:
        cursor = conn.execute("DELETE FROM valuations WHERE id = ? AND user_id=?", (record_id, user_id))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True, "deleted_id": record_id}


@router.get("/{record_id}/compare")
def compare_to_current(record_id: int, user_id: str = Depends(get_current_user)):
    """Compare a historical valuation to current market price.

    Returns the original DCF price, the market price at valuation time,
    and the current live price for gap analysis.
    """
    path = _require_db()
    rows = _query(path, "SELECT ticker, price_per_share, gap_dcf_price, market_price, "
                        "gap_market_price, gap_pct, currency, valuation_date "
                        "FROM valuations WHERE id = ? AND user_id=?", (record_id, user_id))
    if not rows:
        raise HTTPException(status_code=404, detail="Record not found")

    record = rows[0]
    ticker = record.get('ticker')

    # Fetch current price
    current_price = None
    current_currency = None
    if ticker:
        try:
            import yfinance as yf
            fi = yf.Ticker(ticker).fast_info
            current_price = float(fi.last_price) if fi.last_price and fi.last_price > 0 else None
            current_currency = fi.currency
        except Exception:
            pass

    dcf_price = record.get('price_per_share') or record.get('gap_dcf_price')
    current_gap_pct = None
    if dcf_price and current_price and dcf_price > 0:
        current_gap_pct = round((dcf_price - current_price) / dcf_price * 100, 2)

    return {
        **record,
        "current_price": current_price,
        "current_currency": current_currency,
        "current_gap_pct": current_gap_pct,
    }
