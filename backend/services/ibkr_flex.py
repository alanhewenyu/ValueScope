# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""IBKR Flex Web Service sync — fetch, parse, reconcile against tracker.

Enabled when IBKR_FLEX_TOKEN + IBKR_FLEX_QUERY_ID are set (backend/.env).
The token is read-only (report access, no trading). Flex is EOD data: at
Beijing mornings the newest statement is the *previous* trade date — the
intended cadence is an evening pull (statement lands ~14:00-20:00 Beijing)
so positions are reconciled before the next US session opens.
"""
from __future__ import annotations

import logging
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

logger = logging.getLogger("valuescope.ibkr_flex")

_BASE = "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService"
_CACHE_KEY = "ibkr_flex_stmt"
_CACHE_TTL = 1800  # report is EOD; 30min is plenty

# Match tolerances: broker rounding on diluted/average cost displays
_QTY_TOL = 1e-4
_COST_ABS_TOL = 0.05
_COST_REL_TOL = 0.001
_CASH_TOL = 0.01


def enabled() -> bool:
    return bool(os.getenv("IBKR_FLEX_TOKEN") and os.getenv("IBKR_FLEX_QUERY_ID"))


def map_ticker(symbol: str, exchange: str | None, currency: str | None) -> str:
    """IBKR symbol → tracker ticker convention."""
    sym = (symbol or "").strip()
    exch = (exchange or "").upper()
    if exch == "SEHK" or (currency == "HKD" and sym.isdigit()):
        return sym.zfill(4) + ".HK"
    if exch in ("TSEJ", "TSE.JPN") or currency == "JPY":
        return sym + ".T"
    return sym


def fetch_statement(force: bool = False) -> dict | None:
    """Two-step Flex pull. Returns parsed dict or None (disabled/failure)."""
    if not enabled():
        return None
    from backend import persistent_cache as pc
    if not force:
        cached = pc.get(_CACHE_KEY)
        if cached is not None:
            return cached

    tok = os.getenv("IBKR_FLEX_TOKEN")
    qid = os.getenv("IBKR_FLEX_QUERY_ID")
    try:
        ref = None
        for attempt in range(3):
            req = urllib.request.Request(
                f"{_BASE}.SendRequest?t={tok}&q={qid}&v=3",
                headers={"User-Agent": "valuescope/1.0"})
            r1 = urllib.request.urlopen(req, timeout=30).read().decode()
            m = re.search(r"<ReferenceCode>(\d+)</ReferenceCode>", r1)
            if m:
                ref = m.group(1)
                break
            # ErrorCode 1001 = generation throttled — transient, back off
            logger.warning("Flex SendRequest attempt %d failed: %s", attempt + 1, r1[:160])
            time.sleep(20)
        if ref is None:
            return None
        xml = None
        for _ in range(6):
            time.sleep(4)
            req2 = urllib.request.Request(
                f"{_BASE}.GetStatement?t={tok}&q={ref}&v=3",
                headers={"User-Agent": "valuescope/1.0"})
            body = urllib.request.urlopen(req2, timeout=60).read().decode()
            if "<FlexQueryResponse" in body:
                xml = body
                break
        if xml is None:
            logger.warning("Flex report not ready after polling")
            return None
        data = _parse(xml)
    except Exception as e:
        logger.warning("Flex fetch failed: %s: %s", type(e).__name__, e)
        return None
    if data:
        pc.put(_CACHE_KEY, data, ttl=_CACHE_TTL)
    return data


def _parse(xml: str) -> dict:
    root = ET.fromstring(xml)
    stmt = root.find(".//FlexStatement")
    positions = []
    for p in root.findall(".//OpenPosition"):
        try:
            positions.append({
                "ticker": map_ticker(p.get("symbol"), p.get("listingExchange"), p.get("currency")),
                "symbol": p.get("symbol"),
                "currency": p.get("currency"),
                "quantity": float(p.get("position") or 0),
                "cost_price": float(p.get("costBasisPrice") or 0),
                "mark_price": float(p.get("markPrice") or 0),
            })
        except (TypeError, ValueError):
            continue
    cash = {}
    for c in root.findall(".//CashReportCurrency"):
        ccy = c.get("currency")
        try:
            if ccy and ccy != "BASE_SUMMARY":
                cash[ccy] = float(c.get("endingCash") or 0)
        except (TypeError, ValueError):
            continue
    trades = len(root.findall(".//Trade"))
    return {
        "report_date": stmt.get("toDate") if stmt is not None else None,
        "positions": positions,
        "cash": cash,
        "trade_count": trades,
        "account": stmt.get("accountId") if stmt is not None else None,
    }


def reconcile(conn, user_id: str = "local", broker_prefix: str = "盈透") -> dict | None:
    """Diff Flex statement vs tracker positions/cash. Review-only — no writes."""
    stmt = fetch_statement()
    if stmt is None:
        return None

    rows = conn.execute(
        "SELECT ticker, quantity, cost_price, broker FROM positions "
        "WHERE user_id=? AND broker LIKE ? AND quantity > 0",
        (user_id, broker_prefix + "%")).fetchall()
    tracker = {r[0]: {"quantity": r[1], "cost_price": r[2], "broker": r[3]} for r in rows}
    flex = {p["ticker"]: p for p in stmt["positions"]}

    diffs = []
    for tk, fp in flex.items():
        tp = tracker.get(tk)
        if tp is None:
            diffs.append({"kind": "missing_tracker", "ticker": tk,
                          "ibkr": fp["quantity"], "tracker": None,
                          "note": f"盈透持有 {fp['quantity']:g} 股，tracker 无此持仓"})
            continue
        if abs(fp["quantity"] - tp["quantity"]) > _QTY_TOL:
            diffs.append({"kind": "qty", "ticker": tk,
                          "ibkr": fp["quantity"], "tracker": tp["quantity"],
                          "note": "数量不一致"})
        c0, c1 = tp["cost_price"] or 0, fp["cost_price"] or 0
        if abs(c1 - c0) > max(_COST_ABS_TOL, abs(c0) * _COST_REL_TOL):
            diffs.append({"kind": "cost", "ticker": tk,
                          "ibkr": round(c1, 4), "tracker": c0,
                          "note": "成本不一致"})
    for tk, tp in tracker.items():
        if tk not in flex:
            diffs.append({"kind": "missing_ibkr", "ticker": tk,
                          "ibkr": None, "tracker": tp["quantity"],
                          "note": f"tracker 记有 {tp['quantity']:g} 股，盈透报表无此持仓"})

    cash_rows = conn.execute(
        "SELECT currency, SUM(balance) FROM cash_balances "
        "WHERE user_id=? AND account LIKE ? GROUP BY currency",
        (user_id, broker_prefix + "%")).fetchall()
    tracker_cash = {r[0]: r[1] or 0 for r in cash_rows}
    for ccy, amt in stmt["cash"].items():
        t = tracker_cash.get(ccy, 0)
        if abs(amt - t) > _CASH_TOL:
            diffs.append({"kind": "cash", "ticker": ccy,
                          "ibkr": round(amt, 2), "tracker": round(t, 2),
                          "note": f"{ccy} 现金余额不一致（差 {amt - t:+,.2f}）"})

    return {
        "report_date": stmt["report_date"],
        "account": stmt["account"],
        "checked_positions": len(flex),
        "trade_count": stmt["trade_count"],
        "diffs": diffs,
    }
