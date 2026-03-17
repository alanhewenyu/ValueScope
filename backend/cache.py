# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Simple in-memory TTL cache for expensive API responses."""

import time
import threading
from typing import Any

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}  # key -> (expiry_ts, value)

# Maximum cache entries to prevent unbounded growth
_MAX_ENTRIES = 200


def get(key: str) -> Any | None:
    """Return cached value if exists and not expired, else None."""
    entry = _store.get(key)
    if entry is None:
        return None
    expiry, value = entry
    if time.monotonic() > expiry:
        # Expired — lazy cleanup
        _store.pop(key, None)
        return None
    return value


def put(key: str, value: Any, ttl: int = 3600) -> None:
    """Store a value with TTL in seconds (default 1 hour)."""
    with _lock:
        # Evict expired entries if cache is getting large
        if len(_store) >= _MAX_ENTRIES:
            now = time.monotonic()
            expired = [k for k, (exp, _) in _store.items() if now > exp]
            for k in expired:
                del _store[k]
            # If still too large, evict oldest entries
            if len(_store) >= _MAX_ENTRIES:
                oldest = sorted(_store.items(), key=lambda x: x[1][0])
                for k, _ in oldest[: len(oldest) // 4]:
                    del _store[k]
        _store[key] = (time.monotonic() + ttl, value)


def make_key(*parts: str) -> str:
    """Build a cache key from parts."""
    return ":".join(parts)
