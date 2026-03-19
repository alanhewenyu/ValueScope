# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""SQLite cache for AI-extracted financial data.

Stores AI-extracted financials so the slow extraction only runs once per
ticker per period.  When the FMP API eventually catches up, the cache entry
is auto-invalidated and API data is used.

DB location: data/freshness_cache.db
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger("valuescope.freshness_cache")

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "freshness_cache.db")


def _ensure_table(db_path: str | None = None):
    path = db_path or _DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_extracted_financials (
                ticker       TEXT NOT NULL,
                period_key   TEXT NOT NULL,
                market       TEXT NOT NULL,
                data_json    TEXT NOT NULL,
                source       TEXT NOT NULL,
                source_url   TEXT,
                ai_engine    TEXT,
                extracted_at TEXT DEFAULT (datetime('now','localtime')),
                UNIQUE(ticker, period_key)
            )
        """)


def get_cached(ticker: str, period_key: str, db_path: str | None = None) -> dict | None:
    """Return cached AI-extracted data dict, or None if not cached."""
    try:
        _ensure_table(db_path)
        path = db_path or _DB_PATH
        with sqlite3.connect(path) as conn:
            row = conn.execute(
                "SELECT data_json, source, source_url, ai_engine, extracted_at "
                "FROM ai_extracted_financials WHERE ticker=? AND period_key=?",
                (ticker, period_key),
            ).fetchone()
        if row:
            return {
                "data": json.loads(row[0]),
                "source": row[1],
                "source_url": row[2],
                "ai_engine": row[3],
                "extracted_at": row[4],
            }
    except Exception as e:
        logger.debug("freshness cache read error: %s", e)
    return None


def put_cached(
    ticker: str,
    period_key: str,
    market: str,
    data: dict,
    source: str,
    source_url: str | None = None,
    ai_engine: str | None = None,
    db_path: str | None = None,
):
    """Store AI-extracted financial data in the cache."""
    try:
        _ensure_table(db_path)
        path = db_path or _DB_PATH
        with sqlite3.connect(path) as conn:
            conn.execute(
                """INSERT INTO ai_extracted_financials
                   (ticker, period_key, market, data_json, source, source_url, ai_engine)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, period_key) DO UPDATE SET
                       data_json=excluded.data_json,
                       source=excluded.source,
                       source_url=excluded.source_url,
                       ai_engine=excluded.ai_engine,
                       extracted_at=datetime('now','localtime')
                """,
                (ticker, period_key, market, json.dumps(data, ensure_ascii=False),
                 source, source_url, ai_engine),
            )
    except Exception as e:
        logger.warning("freshness cache write error: %s", e)


def invalidate(ticker: str, period_key: str | None = None, db_path: str | None = None):
    """Remove cached entries.  If period_key is None, remove all for ticker."""
    try:
        _ensure_table(db_path)
        path = db_path or _DB_PATH
        with sqlite3.connect(path) as conn:
            if period_key:
                conn.execute(
                    "DELETE FROM ai_extracted_financials WHERE ticker=? AND period_key=?",
                    (ticker, period_key),
                )
            else:
                conn.execute(
                    "DELETE FROM ai_extracted_financials WHERE ticker=?",
                    (ticker,),
                )
    except Exception as e:
        logger.debug("freshness cache invalidate error: %s", e)
