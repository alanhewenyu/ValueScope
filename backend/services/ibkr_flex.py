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
_LASTGOOD_KEY = "ibkr_flex_stmt_lastgood"
_LASTGOOD_TTL = 3 * 86400  # fallback when IBKR's gateway is in its
                           # maintenance window — the statement is EOD, so
                           # yesterday evening's pull is still the newest
                           # data that exists until the next US close
_COOLDOWN_KEY = "ibkr_flex_cooldown"
_COOLDOWN_TTL = 900  # after a failure, back off — hammering during IBKR's
                     # maintenance windows escalates 1001 into a 1025 lockout

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
        # some statements already carry the .T suffix in the symbol
        return sym if sym.upper().endswith(".T") else sym + ".T"
    return sym


def _last_good(pc) -> dict | None:
    """Most recent successful statement, marked stale for the caller."""
    lg = pc.get(_LASTGOOD_KEY)
    if lg is not None and "accounts" in lg:
        return {**lg, "stale": True}
    return None


def fetch_statement(force: bool = False) -> dict | None:
    """Two-step Flex pull. Returns parsed dict or None (disabled/failure).

    On gateway failure (IBKR's nightly maintenance window regularly rejects
    or drops requests during Beijing daytime) falls back to the last
    successful statement with stale=True — an EOD report doesn't get any
    fresher by retrying, and a review-only recon against yesterday's close
    beats silently showing nothing.
    """
    if not enabled():
        return None
    from backend import persistent_cache as pc
    if not force:
        cached = pc.get(_CACHE_KEY)
        if cached is not None and "accounts" in cached:
            return cached
        if pc.get(_COOLDOWN_KEY) is not None:
            return _last_good(pc)

    tok = os.getenv("IBKR_FLEX_TOKEN")
    qid = os.getenv("IBKR_FLEX_QUERY_ID")
    try:
        req = urllib.request.Request(
            f"{_BASE}.SendRequest?t={tok}&q={qid}&v=3",
            headers={"User-Agent": "valuescope/1.0"})
        r1 = urllib.request.urlopen(req, timeout=30).read().decode()
        m = re.search(r"<ReferenceCode>(\d+)</ReferenceCode>", r1)
        if not m:
            # 1001 = generation window/throttle, 1025 = lockout from retries.
            # Single attempt + cooldown; the next page load after TTL retries.
            logger.warning("Flex SendRequest failed: %s", r1[:160])
            pc.put(_COOLDOWN_KEY, 1, ttl=_COOLDOWN_TTL)
            return _last_good(pc)
        ref = m.group(1)
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
            pc.put(_COOLDOWN_KEY, 1, ttl=_COOLDOWN_TTL)
            return _last_good(pc)
        data = _parse(xml)
    except Exception as e:
        logger.warning("Flex fetch failed: %s: %s", type(e).__name__, e)
        pc.put(_COOLDOWN_KEY, 1, ttl=_COOLDOWN_TTL)
        return _last_good(pc)
    if data:
        from datetime import datetime
        data["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        data["stale"] = False
        pc.put(_CACHE_KEY, data, ttl=_CACHE_TTL)
        pc.put(_LASTGOOD_KEY, data, ttl=_LASTGOOD_TTL)
        # keep the raw XML a day for debugging field availability
        # (e.g. whether the query carries openPrice) without extra pulls
        pc.put("ibkr_flex_raw", xml, ttl=86400)
    return data


def _parse(xml: str) -> dict:
    """One FlexStatement node per account — the query may span several."""
    root = ET.fromstring(xml)
    accounts: dict[str, dict] = {}
    for stmt in root.findall(".//FlexStatement"):
        acct = stmt.get("accountId") or "?"
        positions = []
        for p in stmt.findall(".//OpenPosition"):
            try:
                # IBKR distinguishes two costs: openPrice = trading average
                # (what TWS shows and the tracker records) vs costBasisPrice =
                # tax basis (adjusted for corp actions / ROC / wash sales).
                # Reconcile against the trading average; fall back to tax basis
                # only if openPrice isn't in the query.
                open_px = p.get("openPrice")
                tax_basis = float(p.get("costBasisPrice") or 0)
                positions.append({
                    "ticker": map_ticker(p.get("symbol"), p.get("listingExchange"), p.get("currency")),
                    "symbol": p.get("symbol"),
                    "name": p.get("description") or p.get("symbol"),
                    "currency": p.get("currency"),
                    "quantity": float(p.get("position") or 0),
                    "cost_price": float(open_px) if open_px not in (None, "") else tax_basis,
                    "tax_basis": tax_basis,
                    "mark_price": float(p.get("markPrice") or 0),
                })
            except (TypeError, ValueError):
                continue
        cash = {}
        for c in stmt.findall(".//CashReportCurrency"):
            ccy = c.get("currency")
            try:
                if ccy and ccy != "BASE_SUMMARY":
                    cash[ccy] = float(c.get("endingCash") or 0)
            except (TypeError, ValueError):
                continue
        # Trade executions (stocks only — FX conversions etc. excluded):
        # these let reconcile-apply book sells with real fill prices.
        # NB: the Trades section carries no assetCategory attribute, so FX
        # conversions are recognised by their CCY.CCY symbol instead.
        trades = []
        for t in stmt.findall(".//Trade"):
            if (t.get("assetCategory") or "STK") != "STK":
                continue
            if re.fullmatch(r"[A-Z]{3}\.[A-Z]{3}", t.get("symbol") or ""):
                continue  # currency pair (e.g. USD.JPY) — an FX conversion
            try:
                d = t.get("tradeDate") or ""
                if len(d) == 8 and d.isdigit():
                    d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                trades.append({
                    "ticker": map_ticker(t.get("symbol"), t.get("listingExchange") or t.get("exchange"), t.get("currency")),
                    "quantity": float(t.get("quantity") or 0),  # signed: sells < 0
                    "price": float(t.get("tradePrice") or 0),
                    "date": d,
                    "currency": t.get("currency"),
                })
            except (TypeError, ValueError):
                continue
        # Cash transactions (present once the query's CashTransactions
        # section is enabled): dividends / withholding tax / interest —
        # feeds the per-position dividend ledger
        cash_txs = []
        for ct in stmt.findall(".//CashTransaction"):
            typ = ct.get("type") or ""
            if typ not in ("Dividends", "Payment In Lieu Of Dividends",
                           "Withholding Tax", "Broker Interest Paid",
                           "Broker Interest Received"):
                continue
            try:
                d = (ct.get("settleDate") or ct.get("dateTime") or ct.get("reportDate") or "")[:10]
                if len(d) == 8 and d.isdigit():
                    d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
                sym = ct.get("symbol") or ""
                cash_txs.append({
                    "ticker": map_ticker(sym, ct.get("listingExchange"), ct.get("currency")) if sym else None,
                    "type": typ,
                    "currency": ct.get("currency"),
                    "amount": float(ct.get("amount") or 0),
                    "date": d,
                    "description": ct.get("description") or "",
                })
            except (TypeError, ValueError):
                continue
        accounts[acct] = {
            "report_date": stmt.get("toDate"),
            "positions": positions,
            "cash": cash,
            "trades": trades,
            "cash_transactions": cash_txs,
            "trade_count": len(trades),
            "account": acct,
        }
    return {"accounts": accounts}


def _account_map() -> dict[str, str]:
    """IBKR_FLEX_MAP=Individual:U16028525,Joint:U19288500 — portfolio→account."""
    raw = os.getenv("IBKR_FLEX_MAP", "")
    out = {}
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _active_portfolio_name() -> str | None:
    from backend.services.portfolio_db import PORTFOLIOS, DB_PATH
    for name, path in PORTFOLIOS:
        if os.path.abspath(path) == os.path.abspath(DB_PATH):
            return name
    return None


def _pick_statement(fetched: dict | None) -> dict | None:
    """Statement for the active portfolio: mapped via IBKR_FLEX_MAP when the
    query spans several accounts; the sole account otherwise."""
    if not fetched or not fetched.get("accounts"):
        return None
    accounts = fetched["accounts"]
    if len(accounts) == 1:
        return next(iter(accounts.values()))
    return accounts.get(_account_map().get(_active_portfolio_name() or ""))


def _ensure_dividend_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dividend_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            account TEXT,
            ticker TEXT,
            type TEXT NOT NULL,
            currency TEXT,
            amount REAL NOT NULL,
            date TEXT,
            description TEXT,
            source TEXT DEFAULT 'ibkr_flex',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(user_id, account, date, ticker, type, amount, description)
        )""")


def _sync_cash_transactions(conn, stmt: dict, user_id: str) -> int:
    """Append broker-reported dividends/tax/interest into the ledger.

    Fact feed, not a user decision: rows are append-only and deduped on the
    full natural key, so re-pulling the same statement is idempotent. The
    ledger is what makes per-position *total* return (incl. dividends)
    computable long-term — cost basis stays untouched by design.
    """
    txs = stmt.get("cash_transactions") or []
    if not txs:
        return 0
    _ensure_dividend_table(conn)
    n = 0
    for t in txs:
        # NULLs are pairwise-distinct in SQLite UNIQUE constraints — store
        # empty strings so the dedupe key actually dedupes
        cur = conn.execute(
            "INSERT OR IGNORE INTO dividend_log "
            "(user_id, account, ticker, type, currency, amount, date, description) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, stmt.get("account") or "", t["ticker"] or "", t["type"],
             t["currency"] or "", t["amount"], t["date"] or "", t["description"] or ""))
        n += cur.rowcount
    return n


def _ensure_ignore_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ibkr_recon_ignores (
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            ticker TEXT NOT NULL,
            tracker_val REAL,
            ibkr_val REAL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (user_id, kind, ticker)
        )""")


def _val_matches(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1e-6, abs(b) * 1e-6)


def reconcile(conn, user_id: str = "local", broker_prefix: str = "盈透") -> dict | None:
    """Diff Flex statement vs tracker positions/cash. Review-only — no writes.

    Multi-account: picks the statement mapped to the active portfolio via
    IBKR_FLEX_MAP; with a single-account query it just uses that account.

    Known intentional differences (e.g. transfer-in positions keeping the
    original pre-transfer cost while IBKR carries a different basis) can be
    whitelisted via ignore_diffs(); an ignore is pinned to BOTH sides'
    values, so if either side moves the diff resurfaces.

    One write does happen here: broker-reported cash transactions
    (dividends/tax/interest) are appended to dividend_log — a deduped
    fact feed, not a bookkeeping decision.
    """
    fetched = fetch_statement()
    stmt = _pick_statement(fetched)
    if stmt is None:
        return None
    _sync_cash_transactions(conn, stmt, user_id)

    rows = conn.execute(
        "SELECT ticker, quantity, cost_price, broker FROM positions "
        "WHERE user_id=? AND broker LIKE ? AND quantity > 0",
        (user_id, broker_prefix + "%")).fetchall()
    tracker = {r[0]: {"quantity": r[1], "cost_price": r[2], "broker": r[3]} for r in rows}
    flex = {p["ticker"]: p for p in stmt["positions"]}

    diffs = []
    cost_notes = []
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
        # Cost is NOT a reconciliation item — Flex carries the tax-lot basis
        # (FIFO), which permanently diverges from the average-cost figure
        # TWS displays (and the tracker keeps) after any partial sell or
        # capital-classified distribution. Institutions reconcile qty/cash/MV
        # and keep cost in their own books; we do the same and surface the
        # lot-basis gap as advisory info only. Entry errors still get caught:
        # a wrong price shows up as a cash diff.
        c0, c1 = tp["cost_price"] or 0, fp["cost_price"] or 0
        if abs(c1 - c0) > max(_COST_ABS_TOL, abs(c0) * _COST_REL_TOL):
            cost_notes.append({"kind": "cost", "ticker": tk,
                               "ibkr": round(c1, 4), "tracker": c0,
                               "note": "口径差（Flex 税务批次 vs 平均成本）"})
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

    _ensure_ignore_table(conn)
    ignores = {(r["kind"], r["ticker"]): (r["tracker_val"], r["ibkr_val"])
               for r in conn.execute(
                   "SELECT kind, ticker, tracker_val, ibkr_val "
                   "FROM ibkr_recon_ignores WHERE user_id=?", (user_id,))}
    visible = []
    ignored = 0
    for d in diffs:
        ig = ignores.get((d["kind"], d["ticker"]))
        if ig and _val_matches(d.get("tracker"), ig[0]) and _val_matches(d.get("ibkr"), ig[1]):
            ignored += 1
        else:
            visible.append(d)

    return {
        "report_date": stmt["report_date"],
        "account": stmt["account"],
        "checked_positions": len(flex),
        "trade_count": stmt["trade_count"],
        "diffs": visible,
        "cost_notes": cost_notes,
        "ignored": ignored,
        "stale": bool(fetched.get("stale")),
        "fetched_at": fetched.get("fetched_at"),
    }


def ignore_diffs(conn, items: list[dict], user_id: str = "local",
                 broker_prefix: str = "盈透") -> dict:
    """Whitelist selected current diffs — pinned to today's values on both
    sides so any future movement re-surfaces them."""
    recon = reconcile(conn, user_id=user_id, broker_prefix=broker_prefix)
    if not recon:
        return {"ignored": [], "skipped": [{**it, "reason": "no_statement"} for it in items]}
    current = {(d["kind"], d["ticker"]): d for d in recon["diffs"]}
    _ensure_ignore_table(conn)
    done, skipped = [], []
    for it in items:
        d = current.get((it.get("kind"), it.get("ticker")))
        if d is None:
            skipped.append({**it, "reason": "not_in_current_diffs"})
            continue
        conn.execute(
            "INSERT OR REPLACE INTO ibkr_recon_ignores "
            "(user_id, kind, ticker, tracker_val, ibkr_val) VALUES (?,?,?,?,?)",
            (user_id, d["kind"], d["ticker"], d.get("tracker"), d.get("ibkr")))
        done.append({"kind": d["kind"], "ticker": d["ticker"]})
    return {"ignored": done, "skipped": skipped}


def clear_ignores(conn, user_id: str = "local") -> int:
    _ensure_ignore_table(conn)
    cur = conn.execute("DELETE FROM ibkr_recon_ignores WHERE user_id=?", (user_id,))
    return cur.rowcount


def scheduled_pull(attempts: int = 3, wait: int = 120) -> bool:
    """Evening cron entry: force-refresh the statement caches.

    Runs after the Flex statement lands (~14:00-20:00 Beijing) so page loads
    the next morning — inside IBKR's maintenance window — hit last-good
    instead of a dead gateway. Retries because single failures are common
    even in the good window.

    Usage (launchd, daily 19:10):
        python3 -m backend.services.ibkr_flex
    """
    if not enabled():
        print("IBKR Flex not configured (IBKR_FLEX_TOKEN/QUERY_ID missing)")
        return False
    for i in range(attempts):
        if i:
            time.sleep(wait)
        data = fetch_statement(force=True)
        # a stale last-good fallback is NOT success for the cron — the whole
        # point of the evening run is refreshing that fallback
        if data and data.get("accounts") and not data.get("stale"):
            accts = data["accounts"]
            print(f"✓ Flex statement cached: {len(accts)} account(s), "
                  f"report date {next(iter(accts.values()))['report_date']}")
            return True
        print(f"  attempt {i + 1}/{attempts} failed")
    return False


# Every diff kind is auto-appliable when the statement carries enough data;
# the semantics mirror the blessed manual paths so attribution survives:
#   cash            → sync balance (drift = interest/fees → retained earnings)
#   cost            → advisory only (see cost_notes); force-appliable via API
#   missing_tracker → fresh buy: create position, YTD baseline seeds at cost
#                     (at open the report's basis IS the purchase price)
#   qty  (increase) → buy more: sync qty, re-average our own cost with the
#                     fills — never copy the report's tax-lot basis
#   qty  (decrease) → partial sell: book closed_trade at the real fill price
#                     from the Trades section (same YTD-lock path as the
#                     Close tab), then sync qty; average cost stays put
#   missing_ibkr    → full close: book closed_trade, delete the position
# Sells fall back to a skip ("no_trade_details") when the statement's trade
# executions don't cover the quantity gap — e.g. the sale predates the
# report window — and then the Trade panel is the way.
AUTO_APPLY_KINDS = ("cash", "cost", "missing_tracker", "qty", "missing_ibkr")

_CCY_MARKET = {"HKD": "港股", "JPY": "日股", "CNY": "A股"}


def _book_sell(conn, pos_row, sells: list[dict], sold: float, user_id: str) -> dict:
    """Book a sell against a tracker position the way the Close tab does:
    realized P&L at the volume-weighted fill price, YTD attribution locked
    while the baseline still describes the lot."""
    from backend.services.portfolio_db import insert_closed_trade, compute_locked_ytd_cny
    from backend.services.portfolio_prices import get_fx_rates
    avg_px = sum(-t["quantity"] * t["price"] for t in sells) / sold
    realized = (avg_px - pos_row["cost_price"]) * sold
    try:
        rate = get_fx_rates().get(pos_row["currency"], 1.0)
    except Exception:
        rate = 1.0
    realized_cny = realized * rate
    ytd_locked = compute_locked_ytd_cny(
        conn, ticker=pos_row["ticker"], broker=pos_row["broker"],
        market=pos_row["market"], currency=pos_row["currency"],
        quantity=sold, close_price=avg_px, realized_pnl=realized,
        realized_pnl_cny=realized_cny, user_id=user_id)
    insert_closed_trade(
        conn, ticker=pos_row["ticker"], name=pos_row["name"],
        market=pos_row["market"], broker=pos_row["broker"],
        currency=pos_row["currency"], realized_pnl=realized,
        realized_pnl_cny=realized_cny, quantity=sold,
        cost_price=pos_row["cost_price"], close_price=avg_px,
        close_date=sells[-1]["date"] or None,
        ytd_pnl_cny_locked=ytd_locked, user_id=user_id)
    return {"sold": sold, "avg_px": avg_px, "realized": realized}


def apply_diffs(conn, items: list[dict], user_id: str = "local",
                broker_prefix: str = "盈透") -> dict:
    """Apply selected reconcile diffs to the tracker (cash/cost only).

    Values come from the server-side statement, never from the client:
    each requested (kind, ticker) is re-derived against the current diff
    list and applied with the Flex number. Anything stale, ambiguous or
    manual-only lands in `skipped` with a reason.
    """
    recon = reconcile(conn, user_id=user_id, broker_prefix=broker_prefix)
    if not recon:
        return {"applied": [], "skipped": [
            {**it, "reason": "no_statement"} for it in items]}
    current = {(d["kind"], d["ticker"]) for d in recon["diffs"]}
    # cost sits in the advisory list, but stays force-appliable via API
    current |= {(d["kind"], d["ticker"]) for d in recon.get("cost_notes", [])}
    stmt = _pick_statement(fetch_statement())
    flex = {p["ticker"]: p for p in stmt["positions"]} if stmt else {}

    applied, skipped = [], []
    for it in items:
        kind, tk = it.get("kind"), it.get("ticker")
        if kind not in AUTO_APPLY_KINDS:
            skipped.append({**it, "reason": "manual_only"})
            continue
        if (kind, tk) not in current:
            # statement moved on since the banner rendered — don't write
            skipped.append({**it, "reason": "stale_diff"})
            continue
        if kind == "cost":
            fp = flex.get(tk)
            row = conn.execute(
                "SELECT broker FROM positions WHERE ticker=? AND user_id=? "
                "AND broker LIKE ? AND quantity > 0",
                (tk, user_id, broker_prefix + "%")).fetchone()
            if fp is None or row is None:
                skipped.append({**it, "reason": "not_found"})
                continue
            conn.execute(
                "UPDATE positions SET cost_price=?, "
                "updated_at=datetime('now','localtime') "
                "WHERE ticker=? AND broker=? AND user_id=?",
                (fp["cost_price"], tk, row[0], user_id))
            applied.append({"kind": kind, "ticker": tk,
                            "value": fp["cost_price"]})
        elif kind == "missing_tracker":
            fp = flex.get(tk)
            if fp is None:
                skipped.append({**it, "reason": "not_found"})
                continue
            # guard against ticker-convention mismatches (GOOG vs GOOGL):
            # never create on top of an existing row
            exists = conn.execute(
                "SELECT 1 FROM positions WHERE ticker=? AND user_id=? "
                "AND broker LIKE ? AND quantity > 0",
                (tk, user_id, broker_prefix + "%")).fetchone()
            if exists:
                skipped.append({**it, "reason": "already_exists"})
                continue
            row = conn.execute(
                "SELECT broker FROM positions WHERE user_id=? AND broker LIKE ? "
                "GROUP BY broker ORDER BY COUNT(*) DESC LIMIT 1",
                (user_id, broker_prefix + "%")).fetchone()
            broker = row[0] if row else broker_prefix + (stmt.get("account") or "")
            market = _CCY_MARKET.get(fp["currency"] or "", "美股")
            from backend.services.portfolio_db import upsert_position
            upsert_position(conn, tk, fp.get("name") or tk, market, broker,
                            fp["currency"], fp["quantity"], fp["cost_price"],
                            user_id=user_id)
            applied.append({"kind": kind, "ticker": tk,
                            "value": fp["quantity"]})
        elif kind in ("qty", "missing_ibkr"):
            pos_row = conn.execute(
                "SELECT ticker, name, market, broker, currency, quantity, cost_price "
                "FROM positions WHERE ticker=? AND user_id=? AND broker LIKE ? "
                "AND quantity > 0",
                (tk, user_id, broker_prefix + "%")).fetchone()
            if pos_row is None:
                skipped.append({**it, "reason": "not_found"})
                continue
            fp = flex.get(tk)
            target_qty = fp["quantity"] if fp else 0.0
            delta = target_qty - pos_row["quantity"]
            if delta > _QTY_TOL:
                # Bought more. The report's cost is NOT the new average: Flex
                # only ever carries tax-lot basis (FIFO), which permanently
                # diverges from the TWS average the tracker keeps once a
                # position has been partly sold. Copying it re-anchored the
                # whole holding to the tax basis on every top-up. Re-derive
                # the average from our own cost plus the actual fills, the
                # same arithmetic the Trade tab uses (fills at trade price,
                # commissions left out, matching TWS's default average).
                buys = [t for t in (stmt or {}).get("trades", [])
                        if t["ticker"] == tk and t["quantity"] > 0 and t["price"] > 0]
                bought = sum(t["quantity"] for t in buys)
                if abs(bought - delta) > _QTY_TOL:
                    skipped.append({**it, "reason": "no_trade_details"})
                    continue
                spend = sum(t["quantity"] * t["price"] for t in buys)
                new_cost = ((pos_row["quantity"] * (pos_row["cost_price"] or 0) + spend)
                            / target_qty)
                conn.execute(
                    "UPDATE positions SET quantity=?, cost_price=?, "
                    "updated_at=datetime('now','localtime') "
                    "WHERE ticker=? AND broker=? AND user_id=?",
                    (target_qty, new_cost, tk, pos_row["broker"], user_id))
                applied.append({"kind": kind, "ticker": tk, "value": target_qty})
            elif delta < -_QTY_TOL:
                # sold — need real fills covering the whole gap
                sells = [t for t in (stmt or {}).get("trades", [])
                         if t["ticker"] == tk and t["quantity"] < 0 and t["price"] > 0]
                sold = -sum(t["quantity"] for t in sells)
                if abs(sold - (-delta)) > _QTY_TOL:
                    skipped.append({**it, "reason": "no_trade_details"})
                    continue
                _book_sell(conn, pos_row, sells, sold, user_id)
                if target_qty > _QTY_TOL:
                    # Average-cost account: a partial sell leaves the average
                    # untouched. (Flex's basis moves here — it drops whichever
                    # lots FIFO consumed — which is exactly the divergence we
                    # must not import.)
                    conn.execute(
                        "UPDATE positions SET quantity=?, "
                        "updated_at=datetime('now','localtime') "
                        "WHERE ticker=? AND broker=? AND user_id=?",
                        (target_qty, tk, pos_row["broker"], user_id))
                else:
                    conn.execute(
                        "DELETE FROM positions WHERE ticker=? AND broker=? AND user_id=?",
                        (tk, pos_row["broker"], user_id))
                applied.append({"kind": kind, "ticker": tk, "value": target_qty})
            else:
                skipped.append({**it, "reason": "stale_diff"})
        else:  # cash — ticker field carries the currency
            amt = (stmt or {}).get("cash", {}).get(tk)
            if amt is None:
                skipped.append({**it, "reason": "not_found"})
                continue
            rows = conn.execute(
                "SELECT account FROM cash_balances WHERE user_id=? "
                "AND account LIKE ? AND currency=?",
                (user_id, broker_prefix + "%", tk)).fetchall()
            if len(rows) > 1:
                # several sub-accounts share the prefix — can't tell which
                # one drifted; leave it to the Manage panel
                skipped.append({**it, "reason": "ambiguous_accounts"})
                continue
            if rows:
                account = rows[0][0]
            else:
                # currency the tracker doesn't hold yet — reuse the account
                # name of existing broker rows, else derive from the statement
                r = conn.execute(
                    "SELECT account FROM cash_balances WHERE user_id=? "
                    "AND account LIKE ? LIMIT 1",
                    (user_id, broker_prefix + "%")).fetchone()
                account = r[0] if r else broker_prefix + (stmt.get("account") or "")
            from backend.services.portfolio_db import upsert_cash
            upsert_cash(conn, account, tk, amt, user_id=user_id)
            applied.append({"kind": kind, "ticker": tk, "value": amt})
    return {"applied": applied, "skipped": skipped,
            "report_date": recon["report_date"]}


if __name__ == "__main__":
    import sys
    from datetime import datetime as _dt
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    except ImportError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(f"[{_dt.now():%Y-%m-%d %H:%M:%S}] IBKR Flex scheduled pull")
    ok = scheduled_pull()
    sys.exit(0 if ok else 1)
