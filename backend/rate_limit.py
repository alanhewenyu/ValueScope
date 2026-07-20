# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Per-IP rate limiting for the public REST API.

Anonymous datacenter crawlers sweep the ticker pages 24/7 (8 API calls per
page, sequential ticker codes — see the 2026-07-20 OOM incident): each visit
churns pandas DataFrames whose freed pages glibc never returns to the OS, so
RSS climbs ~linearly until Railway's 8GB kill. Memory is ~97% of the Railway
bill, so this traffic costs real money while contributing zero users.

Two per-IP budgets, enforced only on unauthenticated /api/ requests:
- burst:  RATE_LIMIT_PER_MIN  (default 120/min ≈ 15 stock pages/min)
- daily:  RATE_LIMIT_PER_DAY  (default 800/day ≈ 100 stock pages/day)
Generous for any human; a sweep of thousands of tickers hits the ceiling.

Exempt: health checks (uptime monitors), /mcp (own quota in mcp_server),
CORS preflights, and requests carrying an Authorization header (logged-in
users; the crawler sends none — good enough until abuse proves otherwise).

Set either env var to 0 to disable that budget.
"""

import os
import threading
import time

_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
_PER_DAY = int(os.environ.get("RATE_LIMIT_PER_DAY", "800"))

# ip -> [minute_window_start, minute_count, day_window_start, day_count]
_counters: dict[str, list[float]] = {}
_lock = threading.Lock()
_MAX_TRACKED_IPS = 20_000  # hard bound; sweep drops expired windows


def _client_ip(scope) -> str:
    """First X-Forwarded-For hop — same convention as the request log."""
    for k, v in scope.get("headers", []):
        if k == b"x-forwarded-for":
            return v.decode(errors="replace").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "-"


def _sweep(now: float) -> None:
    """Drop IPs whose daily window has lapsed (called under _lock)."""
    stale = [ip for ip, c in _counters.items() if now - c[2] > 86400]
    for ip in stale:
        _counters.pop(ip, None)
    if len(_counters) > _MAX_TRACKED_IPS:
        # Still over bound (attack with rotating IPs): drop oldest windows
        oldest = sorted(_counters, key=lambda ip: _counters[ip][2])
        for ip in oldest[: len(oldest) // 4]:
            _counters.pop(ip, None)


def check(scope) -> int:
    """Return 0 if allowed, else the suggested Retry-After in seconds."""
    if _PER_MIN <= 0 and _PER_DAY <= 0:
        return 0
    path = scope.get("path", "")
    if not path.startswith("/api/") or path.startswith("/api/health"):
        return 0
    if scope.get("method") == "OPTIONS":
        return 0
    for k, _ in scope.get("headers", []):
        if k == b"authorization":
            return 0

    ip = _client_ip(scope)
    now = time.monotonic()
    with _lock:
        c = _counters.get(ip)
        if c is None:
            if len(_counters) >= _MAX_TRACKED_IPS:
                _sweep(now)
            c = _counters[ip] = [now, 0, now, 0]
        # roll windows
        if now - c[0] >= 60:
            c[0], c[1] = now, 0
        if now - c[2] >= 86400:
            c[2], c[3] = now, 0
        if _PER_DAY > 0 and c[3] >= _PER_DAY:
            return max(1, int(86400 - (now - c[2])))
        if _PER_MIN > 0 and c[1] >= _PER_MIN:
            return max(1, int(60 - (now - c[0])))
        c[1] += 1
        c[3] += 1
    return 0


class RateLimitMiddleware:
    """Pure-ASGI so throttled requests never touch the thread pool."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            retry_after = check(scope)
            if retry_after:
                body = (b'{"detail":"Rate limit exceeded. '
                        b'This API backs valuescope.app; for programmatic '
                        b'valuations use the MCP endpoint (/mcp)."}')
                await send({
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(retry_after).encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
