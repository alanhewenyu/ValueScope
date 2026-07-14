"""Bound concurrent slow upstream data fetches so they can't saturate the
shared thread pool and take the whole service down.

Sync API routes run on anyio's shared thread pool. akshare fetches to Chinese
data sources can hang for 30-70s; enough concurrent ones consume every worker
thread, and then even async /api/health and the MCP handshake time out — the
recurring "connection timeout" outage. This caps how many real fetches run at
once: excess fail fast with UpstreamBusy (→ HTTP 503, retry) instead of piling
up, so light endpoints always keep thread headroom (the pool is 128, this cap
is well below it).
"""

import os
import threading


class UpstreamBusy(Exception):
    """Concurrent-fetch limit reached. Mapped to HTTP 503 in main.py; the MCP
    server surfaces the message so the caller can retry."""


_MAX = int(os.environ.get("FETCH_MAX_CONCURRENCY", "48"))
_sem = threading.BoundedSemaphore(_MAX)


class fetch_slot:
    """Fail-fast bounded concurrency around one real upstream data fetch.

    Non-blocking acquire: if the limit is reached, raise UpstreamBusy rather
    than queueing (which would hold the worker thread). __exit__ only runs
    when __enter__ succeeded, so the release is always balanced.
    """

    def __enter__(self):
        if not _sem.acquire(blocking=False):
            raise UpstreamBusy(
                "数据服务繁忙（并发抓取已达上限），请稍后重试。"
                "Upstream data service busy; please retry shortly."
            )
        return self

    def __exit__(self, *exc):
        _sem.release()
        return False
