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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.routers import stock, valuation, relative

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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(stock.router, prefix="/api/stock", tags=["Stock"])
app.include_router(valuation.router, prefix="/api/valuation", tags=["Valuation"])
app.include_router(relative.router, prefix="/api/analysis", tags=["Analysis"])


@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}
