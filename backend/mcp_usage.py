# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Local usage log for MCP tool calls.

MCP usage is the product's north-star metric, but until now it lived only in
GA4 — which samples nothing here but does hide the one number that matters
(unique callers over time) behind a UI, applies its own 30-minute session
model, and cannot answer "did this caller come back next week". Writing a
row locally costs microseconds and makes the metric queryable.

Stores the same pseudonymous caller id analytics.py sends to GA (salted hash
of the IP, never the IP itself), so the two can be reconciled. Rows older
than MCP_USAGE_RETENTION_DAYS are dropped on write.

DB location: data/mcp_usage.db (same volume as portfolio.db). If the disk is
unavailable every operation degrades to a silent no-op — usage logging must
never fail a tool call.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time

from . import analytics

logger = logging.getLogger("valuescope.mcp_usage")

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "mcp_usage.db")

_RETENTION_DAYS = int(os.environ.get("MCP_USAGE_RETENTION_DAYS", "400"))

_init_lock = threading.Lock()
_initialized = False
_disabled = False
_write_count = 0
_PRUNE_EVERY = 200  # drop expired rows every N writes


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_init() -> bool:
    """Create the table on first use. False if persistence is unavailable."""
    global _initialized, _disabled
    if _initialized:
        return True
    if _disabled:
        return False
    with _init_lock:
        if _initialized:
            return True
        if _disabled:
            return False
        try:
            os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
            with _connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS mcp_calls (
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts         REAL NOT NULL,
                        day        TEXT NOT NULL,
                        caller     TEXT NOT NULL,
                        tool       TEXT NOT NULL,
                        phase      TEXT,
                        market     TEXT,
                        ticker     TEXT,
                        used_trial INTEGER NOT NULL DEFAULT 0,
                        internal   INTEGER NOT NULL DEFAULT 0
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_mcp_calls_day ON mcp_calls(day)")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mcp_calls_caller_day ON mcp_calls(caller, day)"
                )
            _initialized = True
            return True
        except Exception as e:
            logger.warning(
                "MCP usage log unavailable (%s: %s) — usage metrics disabled", type(e).__name__, e
            )
            _disabled = True
            return False


def _prune(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM mcp_calls WHERE ts < ?", (time.time() - _RETENTION_DAYS * 86400,))


def record(tool: str, ip: str, params: dict | None = None) -> None:
    """Log one MCP tool call. Never raises."""
    global _write_count
    if not _ensure_init():
        return
    p = params or {}
    try:
        now = time.time()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO mcp_calls (ts, day, caller, tool, phase, market, ticker,"
                " used_trial, internal) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    now,
                    time.strftime("%Y-%m-%d", time.gmtime(now)),
                    analytics.caller_id(ip),
                    tool,
                    p.get("phase"),
                    p.get("market"),
                    p.get("ticker"),
                    1 if str(p.get("used_trial")).lower() == "true" else 0,
                    1 if analytics.is_internal(ip) else 0,
                ),
            )
            _write_count += 1
            if _write_count % _PRUNE_EVERY == 0:
                _prune(conn)
    except Exception as e:
        logger.debug("MCP usage write failed: %s", e)


def summary(days: int = 30, include_internal: bool = False) -> dict:
    """Usage rollup for the last `days` days. Empty dict if logging is off."""
    if not _ensure_init():
        return {"available": False}
    since_ts = time.time() - days * 86400
    where = "ts >= ?" + ("" if include_internal else " AND internal = 0")
    args: tuple = (since_ts,)
    try:
        with _connect() as conn:
            conn.row_factory = sqlite3.Row
            daily = [
                {"day": r["day"], "calls": r["calls"], "callers": r["callers"]}
                for r in conn.execute(
                    f"SELECT day, COUNT(*) AS calls, COUNT(DISTINCT caller) AS callers"
                    f" FROM mcp_calls WHERE {where} GROUP BY day ORDER BY day",
                    args,
                )
            ]
            totals = conn.execute(
                f"SELECT COUNT(*) AS calls, COUNT(DISTINCT caller) AS callers"
                f" FROM mcp_calls WHERE {where}",
                args,
            ).fetchone()
            markets = {
                r["market"] or "unknown": r["calls"]
                for r in conn.execute(
                    f"SELECT market, COUNT(*) AS calls FROM mcp_calls WHERE {where}"
                    f" GROUP BY market ORDER BY calls DESC",
                    args,
                )
            }
            # A caller active on 2+ distinct days is the cheap stand-in for
            # retention: one-shot tyre-kickers dominate, so this is the number
            # to watch rather than raw call count.
            returning = conn.execute(
                f"SELECT COUNT(*) AS n FROM (SELECT caller FROM mcp_calls WHERE {where}"
                f" GROUP BY caller HAVING COUNT(DISTINCT day) >= 2)",
                args,
            ).fetchone()["n"]
            # Callers whose very first call ever falls inside the window.
            new_callers = conn.execute(
                f"SELECT COUNT(*) AS n FROM (SELECT caller, MIN(ts) AS first_ts FROM mcp_calls"
                f" WHERE {'internal = 0' if not include_internal else '1=1'}"
                f" GROUP BY caller HAVING first_ts >= ?)",
                (since_ts,),
            ).fetchone()["n"]
        callers = totals["callers"] or 0
        return {
            "available": True,
            "days": days,
            "calls": totals["calls"] or 0,
            "unique_callers": callers,
            "new_callers": new_callers,
            "returning_callers": returning,
            "returning_rate": round(returning / callers, 3) if callers else 0.0,
            "calls_per_caller": round((totals["calls"] or 0) / callers, 1) if callers else 0.0,
            "by_market": markets,
            "daily": daily,
        }
    except Exception as e:
        logger.debug("MCP usage summary failed: %s", e)
        return {"available": False}
