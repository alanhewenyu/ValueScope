# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""SQLite-backed persistent cache for expensive data fetches.

Complements the in-memory caches in data_cache.py: memory is the hot layer
(fast, short TTL), this is the warm layer (survives restarts/deploys, long
TTL). Financial statements only change quarterly, so serving day-old data
beats making every cold visitor wait 5-20s for a live akshare/FMP fetch.

Values are pickled because financial data dicts contain pandas DataFrames.

DB location: data/api_cache.db (same volume as portfolio.db /
freshness_cache.db). If the disk is unavailable, every operation degrades
to a silent no-op so the in-memory layer keeps working.
"""

from __future__ import annotations

import logging
import os
import pickle
import sqlite3
import threading
import time

logger = logging.getLogger("valuescope.persistent_cache")

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "api_cache.db")

_init_lock = threading.Lock()
_initialized = False
_disabled = False  # set when disk init fails; all ops become no-ops
_put_count = 0
_EVICT_EVERY = 50  # purge expired rows every N puts


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_init() -> bool:
    """Create table on first use. Returns False if persistence is unavailable."""
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
                    CREATE TABLE IF NOT EXISTS api_cache (
                        key        TEXT PRIMARY KEY,
                        value      BLOB NOT NULL,
                        expires_at REAL NOT NULL,
                        created_at REAL NOT NULL
                    )
                """)
            _initialized = True
            return True
        except Exception as e:
            logger.warning("Persistent cache unavailable (%s: %s) — falling back to memory only",
                           type(e).__name__, e)
            _disabled = True
            return False


def get(key: str):
    """Return cached value, or None if missing/expired/unavailable."""
    if not _ensure_init():
        return None
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM api_cache WHERE key=?", (key,)
            ).fetchone()
        if row is None:
            return None
        value_blob, expires_at = row
        if time.time() > expires_at:
            return None
        return pickle.loads(value_blob)
    except Exception as e:
        logger.debug("Persistent cache get failed for %s: %s", key, e)
        return None


def put(key: str, value, ttl: int) -> None:
    """Store value with TTL in seconds. Silently no-ops on any failure."""
    global _put_count
    if not _ensure_init():
        return
    try:
        blob = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        now = time.time()
        with _connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_cache (key, value, expires_at, created_at) "
                "VALUES (?, ?, ?, ?)",
                (key, blob, now + ttl, now),
            )
            _put_count += 1
            if _put_count % _EVICT_EVERY == 0:
                conn.execute("DELETE FROM api_cache WHERE expires_at < ?", (now,))
    except Exception as e:
        logger.debug("Persistent cache put failed for %s: %s", key, e)
