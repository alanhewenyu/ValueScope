# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""ValueScope FastAPI Backend — wraps existing modeling engine as REST API."""

import os
import sys

# Add project root to path so `modeling` package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("valuescope")

# Load .env file so SERPER_API_KEY, DEEPSEEK_API_KEY etc. are available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars

# Pre-initialize mini_racer V8 engine on main thread to avoid crash
# when akshare triggers it from a request handler thread.
# See: https://github.com/niceto-dev/mini_racer/issues/
try:
    import py_mini_racer
    _ctx = py_mini_racer.MiniRacer()
    _ctx.eval("1+1")  # Force V8 init
    del _ctx
except Exception:
    pass

import anyio
import anyio.to_thread
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import time as _time

from backend.routers import stock, valuation, relative, portfolio, history, auth, admin

# Pre-load data and modules in background so first requests are faster
import threading, os
threading.Thread(target=stock._get_a_share_list, daemon=True).start()
threading.Thread(target=stock._get_ticker_list, daemon=True).start()

# Pre-import heavy modules (akshare, pandas, numpy) to avoid first-request penalty (~2s)
def _prewarm_imports():
    try:
        import akshare  # noqa: F401
        import pandas  # noqa: F401
        import openpyxl  # noqa: F401
    except ImportError:
        pass
threading.Thread(target=_prewarm_imports, daemon=True).start()
# Daily portfolio snapshot for web users — cloud only (local Mac uses cron)
if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("SNAPSHOT_SCHEDULER") == "1":
    from backend.services.snapshot_scheduler import start_scheduler
    start_scheduler()

# Pre-warm forex and market risk premium caches (FMP API, ~3s total)
_fmp_key = os.environ.get("FMP_API_KEY", "")
if _fmp_key:
    from modeling.data import fetch_forex_data, fetch_market_risk_premium
    threading.Thread(target=fetch_forex_data, args=(_fmp_key,), daemon=True).start()
    threading.Thread(target=fetch_market_risk_premium, args=(_fmp_key,), daemon=True).start()

app = FastAPI(
    title="ValueScope API",
    description="AI-Powered Stock Valuation & Analysis API",
    version="2.0.0",
)

# GZip — compress responses >= 500 bytes (~50% reduction for JSON)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS — allow Next.js dev server and production domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # Next.js dev
        "http://localhost:3001",
        "https://valuescope.app",     # production
        "https://www.valuescope.app",
    ],
    allow_origin_regex=r"https://valuescope-.*\.vercel\.app",  # Vercel preview deploys only
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Cache-Control rules for GET endpoints (path prefix → max-age in seconds)
_CACHE_RULES: list[tuple[str, int]] = [
    ("/api/stock/profile/", 300),        # 5 min — price changes
    ("/api/stock/financials/", 600),      # 10 min — quarterly data
    ("/api/stock/estimates/", 3600),      # 1 hour
    ("/api/analysis/scores/", 3600),      # 1 hour
    ("/api/analysis/valuation/", 3600),   # 1 hour
    ("/api/valuation/wacc/", 1800),       # 30 min
    ("/api/valuation/dcf-defaults/", 1800),  # 30 min
    ("/api/valuation/buffett/", 1800),    # 30 min
]

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with timing. Add Cache-Control headers for cacheable GET endpoints."""
    start = _time.time()
    response = await call_next(request)
    elapsed = (_time.time() - start) * 1000
    # Log slow requests (>5s) at WARNING level for visibility
    path = request.url.path
    level = logging.WARNING if elapsed > 5000 else logging.INFO
    logger.log(level, "%s %s %d %.0fms client=%s",
               request.method, path, response.status_code, elapsed,
               request.headers.get("x-forwarded-for", request.client.host if request.client else "-"))
    # Add Cache-Control for successful GET requests
    if request.method == "GET" and response.status_code == 200:
        for prefix, max_age in _CACHE_RULES:
            if path.startswith(prefix):
                response.headers["Cache-Control"] = f"public, max-age={max_age}"
                break
    return response

app.include_router(stock.router, prefix="/api/stock", tags=["Stock"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["Valuation"])
app.include_router(relative.router, prefix="/api/analysis", tags=["Analysis"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check():
    """Basic liveness check for uptime monitors (UptimeRobot etc.).

    async on purpose: sync endpoints run in the shared threadpool, and when
    crawler traffic saturates it with slow upstream fetches, even health
    checks queue and time out. The event loop answers this one directly.
    """
    return {"status": "ok", "version": "2.0.0"}


# Dedicated limiter so the deep health check never competes for the shared anyio
# threadpool. Sync endpoints (and to_thread.run_sync's default) draw from a single
# limiter that crawler traffic can saturate — when that happens even this check
# queues past the monitor's timeout and trips a false "down" alert. Its own budget
# guarantees it always gets a worker thread.
_DEEP_HEALTH_LIMITER = anyio.CapacityLimiter(2)


@app.get("/api/health/deep")
async def deep_health_check():
    """Deep health check: verify DeepSeek & Serper API keys are valid and have quota.

    Returns per-service status so UptimeRobot keyword monitoring can alert on failures.

    async on purpose: the blocking upstream calls run on a dedicated limiter
    (_DEEP_HEALTH_LIMITER) so a saturated shared threadpool can't make this endpoint
    hang. See health_check() for the underlying threadpool-saturation issue.
    """
    return await anyio.to_thread.run_sync(
        _deep_health_check_sync, limiter=_DEEP_HEALTH_LIMITER
    )


def _deep_health_check_sync():
    import requests as _req

    result = {"status": "ok", "version": "2.0.0", "services": {}}

    # --- DeepSeek API balance check ---
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if ds_key:
        try:
            resp = _req.get(
                "https://api.deepseek.com/user/balance",
                headers={"Authorization": f"Bearer {ds_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                # data: {"is_available": true, "balance_infos": [{"currency": "CNY", "total_balance": "...", "granted_balance": "...", "topped_up_balance": "..."}]}
                balance_infos = data.get("balance_infos", [])
                total = sum(float(b.get("total_balance", 0)) for b in balance_infos)
                result["services"]["deepseek"] = {
                    "status": "ok" if data.get("is_available") and total > 0 else "warning",
                    "available": data.get("is_available", False),
                    "balance": total,
                    "currency": balance_infos[0].get("currency", "CNY") if balance_infos else "CNY",
                }
                if total <= 0 or not data.get("is_available"):
                    result["status"] = "degraded"
            else:
                result["services"]["deepseek"] = {"status": "error", "detail": f"HTTP {resp.status_code}"}
                result["status"] = "degraded"
        except Exception as e:
            result["services"]["deepseek"] = {"status": "error", "detail": str(e)}
            result["status"] = "degraded"
    else:
        result["services"]["deepseek"] = {"status": "not_configured"}

    # --- Serper API credit check ---
    serper_key = os.environ.get("SERPER_API_KEY", "")
    if serper_key:
        try:
            resp = _req.get(
                "https://google.serper.dev/account",
                headers={"X-API-KEY": serper_key},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                credits = data.get("credits", 0)
                result["services"]["serper"] = {
                    "status": "ok" if credits > 0 else "warning",
                    "credits_remaining": credits,
                }
                if credits <= 0:
                    result["status"] = "degraded"
            else:
                result["services"]["serper"] = {"status": "error", "detail": f"HTTP {resp.status_code}"}
                result["status"] = "degraded"
        except Exception as e:
            result["services"]["serper"] = {"status": "error", "detail": str(e)}
            result["status"] = "degraded"
    else:
        result["services"]["serper"] = {"status": "not_configured"}

    return result
