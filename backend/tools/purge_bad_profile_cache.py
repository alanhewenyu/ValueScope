# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""One-off cleanup: delete poisoned profile entries from the persistent cache.

A failed akshare/Sina quote fetch used to get cached with price=0, which
poisons WACC (equity weight 0 → WACC=0) and shows ¥0.00 on stock pages.
The write paths now refuse to persist those, and reads self-heal, but this
purges anything already sitting in data/api_cache.db.

Usage:  python -m backend.tools.purge_bad_profile_cache [--dry-run]
"""

from __future__ import annotations

import pickle
import sqlite3
import sys

from backend.persistent_cache import _DB_PATH


def purge(dry_run: bool = False) -> None:
    conn = sqlite3.connect(_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT key, value FROM api_cache WHERE key LIKE 'profile:%'"
        ).fetchall()
        bad_keys = []
        for key, blob in rows:
            try:
                profile = pickle.loads(blob)
                price = float(profile.get("price") or 0)
            except Exception:
                bad_keys.append(key)  # unreadable entry — drop it too
                continue
            if price != price or price <= 0:  # NaN or non-positive
                bad_keys.append(key)
                print(f"  bad: {key} (price={profile.get('price')!r}, "
                      f"marketCap={profile.get('marketCap')!r})")

        print(f"{len(rows)} profile entries scanned, {len(bad_keys)} poisoned")
        if bad_keys and not dry_run:
            conn.executemany("DELETE FROM api_cache WHERE key=?",
                             [(k,) for k in bad_keys])
            conn.commit()
            print(f"deleted {len(bad_keys)} entries")
        elif bad_keys:
            print("dry run — nothing deleted")
    finally:
        conn.close()


if __name__ == "__main__":
    purge(dry_run="--dry-run" in sys.argv)
