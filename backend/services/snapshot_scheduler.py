# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""In-process daily snapshot scheduler for cloud deployments.

The local Mac runs portfolio_snapshot via cron; the Railway container has no
cron, so registered web users never got NAV history. This daemon thread runs
the snapshot for every user with data, daily at 06:10 Beijing time (markets
worldwide closed by then; Sun/Mon skipped inside take_snapshot).

Enabled from backend.main when RAILWAY_ENVIRONMENT is set (auto on Railway)
or SNAPSHOT_SCHEDULER=1. Idempotent: daily_snapshots is INSERT OR IGNORE on
(date, user_id), so restarts/re-runs can't duplicate or overwrite.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger("valuescope.snapshot_scheduler")

_CN = ZoneInfo("Asia/Shanghai")
_RUN_HOUR, _RUN_MINUTE = 6, 10  # 06:10 Beijing — after the local cron's 06:05


def _seconds_until_next_run() -> float:
    now = datetime.now(_CN)
    nxt = now.replace(hour=_RUN_HOUR, minute=_RUN_MINUTE, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def _snapshot_all_users() -> None:
    from backend.services.portfolio_db import get_conn
    from backend.services.portfolio_snapshot import take_snapshot

    conn = get_conn()
    try:
        users = [r[0] for r in conn.execute("""
            SELECT DISTINCT user_id FROM positions WHERE status='open'
            UNION
            SELECT DISTINCT user_id FROM cash_balances WHERE balance > 0
        """).fetchall()]
    finally:
        conn.close()

    logger.info("Daily snapshot starting for %d user(s)", len(users))
    for uid in users:
        try:
            take_snapshot(user_id=uid)
        except Exception:
            logger.exception("Snapshot failed for user %s — continuing", uid)
    logger.info("Daily snapshot run finished")


def _loop() -> None:
    while True:
        wait = _seconds_until_next_run()
        logger.info("Next snapshot run in %.1f hours", wait / 3600)
        time.sleep(wait)
        try:
            _snapshot_all_users()
        except Exception:
            logger.exception("Snapshot run crashed — scheduler continues")
        time.sleep(120)  # don't double-fire within the same minute


def start_scheduler() -> None:
    threading.Thread(target=_loop, daemon=True, name="snapshot-scheduler").start()
    logger.info("Snapshot scheduler started (daily %02d:%02d Beijing)", _RUN_HOUR, _RUN_MINUTE)
