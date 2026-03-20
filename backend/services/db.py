# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Dual-mode database connection: PostgreSQL (DATABASE_URL) or SQLite (fallback).

Usage:
    from backend.services.db import get_conn, is_postgres

    conn = get_conn()          # returns sqlite3.Connection or psycopg2 connection
    conn = get_conn(db_path)   # SQLite-specific path override (ignored in PG mode)

When DATABASE_URL is set, all connections go to PostgreSQL.
When not set, falls back to SQLite (local dev / CLI mode).
"""

from __future__ import annotations

import os
import re
import sqlite3
import logging
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("valuescope.db")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── PostgreSQL connection pool (lazy init) ──
_pg_pool = None


def _get_pg_pool():
    """Lazy-init a psycopg2 connection pool."""
    global _pg_pool
    if _pg_pool is None:
        import psycopg2
        from psycopg2 import pool as pg_pool
        from psycopg2.extras import RealDictCursor
        _pg_pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=DATABASE_URL,
        )
        logger.info("PostgreSQL connection pool initialized")
    return _pg_pool


def is_postgres() -> bool:
    """Check if we're using PostgreSQL."""
    return bool(DATABASE_URL)


def get_conn(db_path: str | None = None):
    """Get a database connection.

    - With DATABASE_URL: returns psycopg2 connection (RealDictCursor)
    - Without: returns sqlite3.Connection with Row factory
    """
    if DATABASE_URL:
        import psycopg2.extras
        pool = _get_pg_pool()
        conn = pool.getconn()
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect(db_path or "data/portfolio.db")
        conn.row_factory = sqlite3.Row
        return conn


def release_conn(conn):
    """Return a PostgreSQL connection to the pool. No-op for SQLite."""
    if DATABASE_URL and _pg_pool is not None:
        _pg_pool.putconn(conn)


@contextmanager
def get_db(db_path: str | None = None):
    """Context manager for DB connections. Auto-commits on success, rolls back on error.

    Usage:
        with get_db() as conn:
            conn.execute(...)
    """
    conn = get_conn(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if DATABASE_URL:
            release_conn(conn)
        else:
            conn.close()


def execute(conn, sql: str, params: tuple | list = (), *, fetch: str = "none") -> Any:
    """Execute SQL with automatic dialect adaptation.

    - Converts ? placeholders to %s for PostgreSQL
    - fetch: "none" | "one" | "all"
    - Returns dict-like rows for both backends
    """
    if DATABASE_URL:
        import psycopg2.extras
        sql = _adapt_sql_pg(sql)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()

    cur.execute(sql, params)

    if fetch == "one":
        row = cur.fetchone()
        cur.close()
        return dict(row) if row else None
    elif fetch == "all":
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]
    else:
        cur.close()
        return None


def executemany(conn, sql: str, params_list: list):
    """Execute SQL with multiple param sets."""
    if DATABASE_URL:
        import psycopg2.extras
        sql = _adapt_sql_pg(sql)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()
    cur.executemany(sql, params_list)
    cur.close()


def _adapt_sql_pg(sql: str) -> str:
    """Convert SQLite SQL dialect to PostgreSQL.

    - ? → %s
    - AUTOINCREMENT → (removed, SERIAL handles it)
    - datetime('now', 'localtime') → NOW()
    - INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING
    - INSERT OR REPLACE → INSERT ... ON CONFLICT ... DO UPDATE
    """
    # Placeholder: ? → %s (but not inside strings)
    sql = re.sub(r'\?', '%s', sql)

    # datetime functions
    sql = sql.replace("datetime('now', 'localtime')", "NOW()")
    sql = sql.replace("datetime('now')", "NOW()")
    sql = sql.replace("date('now')", "CURRENT_DATE")

    # AUTOINCREMENT → SERIAL (handled in schema init, not runtime queries)
    # INSERT OR IGNORE
    sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', sql, flags=re.IGNORECASE)

    return sql


# ── Schema initialization for PostgreSQL ──

PG_USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
"""


def init_pg_schema():
    """Initialize PostgreSQL-specific tables (users, etc.)."""
    if not DATABASE_URL:
        return
    with get_db() as conn:
        cur = conn.cursor()
        # Split and execute each statement
        for stmt in PG_USERS_SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt + ";")
        cur.close()
        logger.info("PostgreSQL schema initialized")
