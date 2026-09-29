# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Give every `requests`-based upstream call a hard timeout.

akshare issues ~440 `requests.get(...)` calls with no timeout. requests then
hands `timeout=None` to urllib3, which blocks forever on a half-open socket —
and connections from Railway (Singapore) to eastmoney/sina go half-open often.

One such hang permanently holds a cold-fetch slot in routers/stock.py; six of
them take every A-share/HK profile and financials endpoint down until the
kernel finally reaps the socket. That is the 100%-503 outage pattern in the
Railway logs: healthy fetches finish in 0.4-4.2s, yet hours pass with zero
completions and every request rejected at the gate.

`socket.setdefaulttimeout()` does NOT fix this — requests overrides the global
default with an explicit None, so a blackhole address still hangs for minutes.
The adapter is the only reliable hook, and it also covers callers that reach
`Session.send()` directly.

Calls that pass their own timeout are left alone, so the deliberately long
ones (DeepSeek 300s, Serper 15-20s) keep working.
"""

import functools
import logging
import os

logger = logging.getLogger("valuescope.http_timeout")

# Generous next to real latency (healthy upstream fetches finish in 0.4-4.2s),
# tight enough that a hung socket frees its cold-fetch slot in well under a
# minute instead of never.
CONNECT_TIMEOUT = float(os.environ.get("VS_HTTP_CONNECT_TIMEOUT", "10"))
READ_TIMEOUT = float(os.environ.get("VS_HTTP_READ_TIMEOUT", "20"))

_installed = False


def install() -> bool:
    """Patch HTTPAdapter.send to supply a default timeout. Idempotent."""
    global _installed
    if _installed:
        return True

    try:
        from requests.adapters import HTTPAdapter
    except ImportError:  # requests missing — nothing to guard
        return False

    _orig_send = HTTPAdapter.send

    # requests always calls the adapter with keywords (Session.send does
    # `adapter.send(request, **kwargs)`), so taking **kwargs keeps this working
    # if the signature gains a parameter.
    @functools.wraps(_orig_send)
    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (CONNECT_TIMEOUT, READ_TIMEOUT)
        return _orig_send(self, request, **kwargs)

    HTTPAdapter.send = send
    _installed = True
    logger.info(
        "requests default timeout installed: connect=%.0fs read=%.0fs",
        CONNECT_TIMEOUT, READ_TIMEOUT,
    )
    return True
