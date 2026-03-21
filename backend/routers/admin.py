# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Admin API — user management, system stats, diagnostics.

Access controlled via ADMIN_EMAILS environment variable (comma-separated).
Only authenticated users whose email is in that list can access these endpoints.
"""

from __future__ import annotations

import os
import sys
import shutil
import logging
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends

from backend.routers.auth import require_auth, _get_db as _get_users_db

logger = logging.getLogger("valuescope.admin")

router = APIRouter()

# ── Admin auth ──

ADMIN_EMAILS: set[str] = set()
_raw = os.environ.get("ADMIN_EMAILS", "").strip()
if _raw:
    ADMIN_EMAILS = {e.strip().lower() for e in _raw.split(",") if e.strip()}


def require_admin(request: Request) -> str:
    """Verify the caller is an authenticated admin user.

    Returns user_id if authorized, raises 403 otherwise.
    """
    user_id = require_auth(request)

    if not ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin not configured")

    # Look up the user's email
    conn = _get_users_db()
    row = conn.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    if not row or row["email"].lower() not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin access required")

    return user_id


# ── Helpers ──

def _get_valuations_db_path() -> str:
    return os.environ.get(
        "VS_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "data", "valuations.db"),
    )


def _get_portfolio_db_path() -> str:
    return os.environ.get(
        "PORTFOLIO_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "data", "portfolio.db"),
    )


def _safe_query(db_path: str, sql: str, params=()):
    """Execute a query against a db file, returning [] if db doesn't exist."""
    if not os.path.exists(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _safe_count(db_path: str, sql: str, params=()) -> int:
    if not os.path.exists(db_path):
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            return conn.execute(sql, params).fetchone()[0]
    except Exception:
        return 0


def _file_size_mb(path: str) -> float:
    try:
        return round(os.path.getsize(path) / (1024 * 1024), 2) if os.path.exists(path) else 0
    except Exception:
        return 0


# ── Endpoints ──

@router.get("/stats")
def admin_stats(_: str = Depends(require_admin)):
    """System overview: user count, valuation count, today's signups, disk usage."""
    val_db = _get_valuations_db_path()
    port_db = _get_portfolio_db_path()

    total_users = _safe_count(val_db, "SELECT COUNT(*) FROM users")
    total_valuations = _safe_count(val_db, "SELECT COUNT(*) FROM valuations")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_signups = _safe_count(val_db, "SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (f"{today}%",))

    # Disk usage
    data_dir = os.path.dirname(val_db)
    disk = shutil.disk_usage(data_dir) if os.path.exists(data_dir) else None

    return {
        "total_users": total_users,
        "total_valuations": total_valuations,
        "today_signups": today_signups,
        "db_size_mb": {
            "valuations": _file_size_mb(val_db),
            "portfolio": _file_size_mb(port_db),
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 1) if disk else None,
            "free_gb": round(disk.free / (1024**3), 1) if disk else None,
            "used_pct": round((disk.used / disk.total) * 100, 1) if disk else None,
        },
    }


@router.get("/users")
def admin_users(_: str = Depends(require_admin)):
    """List all registered users with their valuation and portfolio counts."""
    val_db = _get_valuations_db_path()

    if not os.path.exists(val_db):
        return {"users": []}

    with sqlite3.connect(val_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT u.id, u.email, u.created_at,
                   COALESCE(v.cnt, 0) AS valuation_count
            FROM users u
            LEFT JOIN (SELECT user_id, COUNT(*) AS cnt FROM valuations GROUP BY user_id) v
                ON v.user_id = u.id
            ORDER BY u.created_at DESC
        """).fetchall()

    users = []
    port_db = _get_portfolio_db_path()
    for r in rows:
        portfolio_count = 0
        if os.path.exists(port_db):
            portfolio_count = _safe_count(port_db,
                "SELECT COUNT(*) FROM positions WHERE user_id=?", (r["id"],))
        users.append({
            "id": r["id"],
            "email": r["email"],
            "created_at": r["created_at"],
            "valuation_count": r["valuation_count"],
            "portfolio_count": portfolio_count,
        })

    return {"users": users}


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: str, admin_id: str = Depends(require_admin)):
    """Delete a user and all their data (valuations, portfolio)."""
    if user_id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    val_db = _get_valuations_db_path()
    port_db = _get_portfolio_db_path()

    deleted = False

    if os.path.exists(val_db):
        with sqlite3.connect(val_db) as conn:
            conn.execute("DELETE FROM valuations WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM password_reset_tokens WHERE user_id=?", (user_id,))
            cursor = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.commit()
            if cursor.rowcount > 0:
                deleted = True

    if os.path.exists(port_db):
        with sqlite3.connect(port_db) as conn:
            for table in ("positions", "cash_balances", "closed_trades",
                          "margin_balances", "account_settings", "deposit_history",
                          "nav_history", "daily_snapshots", "snapshot_stock_pnl",
                          "snapshot_market_detail", "ytd_baseline_prices"):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
                except Exception:
                    pass  # table may not have user_id yet
            conn.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")

    return {"ok": True, "deleted_user_id": user_id}


@router.get("/system")
def admin_system(_: str = Depends(require_admin)):
    """System diagnostics: Python version, API key status, disk space."""
    env_keys = {
        "DEEPSEEK_API_KEY": bool(os.environ.get("DEEPSEEK_API_KEY", "")),
        "SERPER_API_KEY": bool(os.environ.get("SERPER_API_KEY", "")),
        "FMP_API_KEY": bool(os.environ.get("FMP_API_KEY", "")),
        "RESEND_API_KEY": bool(os.environ.get("RESEND_API_KEY", "")),
        "JWT_SECRET": bool(os.environ.get("JWT_SECRET", "")),
        "ADMIN_EMAILS": bool(os.environ.get("ADMIN_EMAILS", "")),
    }

    data_dir = os.path.dirname(_get_valuations_db_path())
    disk = shutil.disk_usage(data_dir) if os.path.exists(data_dir) else None

    return {
        "python_version": sys.version.split()[0],
        "api_keys": env_keys,
        "data_dir": data_dir,
        "disk": {
            "total_gb": round(disk.total / (1024**3), 1) if disk else None,
            "free_gb": round(disk.free / (1024**3), 1) if disk else None,
        },
    }
