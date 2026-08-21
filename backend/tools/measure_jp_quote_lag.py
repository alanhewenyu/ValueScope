# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Measure how far behind the exchange each Japan quote feed runs.

Yahoo resells Tokyo with a 20-minute delay (it says so in
``info['exchangeDataDelayedBy']``), which on an earnings day is a
double-digit move the tracker has not seen yet. Tencent's ``jp`` feed covers
the same names — this script answers whether it is any fresher.

Run it while Tokyo is trading (09:00-15:30 JST = 08:00-14:30 Beijing):

    .venv/bin/python -m backend.tools.measure_jp_quote_lag --minutes 30

Two independent readings come out of it:

  stamp lag  — how old the quote time the feed itself publishes is. A feed
               that stamps 14:12 at 14:32 is telling you it is 20min behind.
  lead time  — how long Yahoo takes to print a price Tencent already showed.
               If Tencent is real time and Yahoo is 20min delayed, every
               Tencent print reappears on Yahoo ~20min later; if both are
               equally delayed the two series move together at lag 0.

The second one is what actually matters, and it only means something when
the price moved during the window — a quiet 30 minutes proves nothing.
"""

from __future__ import annotations

import argparse
import datetime
import time
from collections import defaultdict
from zoneinfo import ZoneInfo

import requests

TOKYO = ZoneInfo("Asia/Tokyo")
BEIJING = ZoneInfo("Asia/Shanghai")

DEFAULT_TICKERS = ["8058.T", "8031.T", "8002.T", "8001.T", "8053.T"]


def _tencent(tickers: list[str]) -> dict[str, tuple[float, datetime.datetime | None]]:
    """{ticker: (price, quote time)} from Tencent. Its timestamps are Beijing."""
    codes = [f"jp{t.split('.')[0]}" for t in tickers]
    resp = requests.get("https://qt.gtimg.cn/q=" + ",".join(codes),
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
    resp.encoding = "gbk"
    out = {}
    for line in resp.text.strip().split("\n"):
        f = line.split("~")
        if len(f) < 35 or not f[3]:
            continue
        ticker = f[2].upper()
        try:
            stamp = datetime.datetime.strptime(f[30], "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING)
        except ValueError:
            stamp = None
        out[ticker] = (float(f[3]), stamp)
    return out


def _yahoo(tickers: list[str]) -> dict[str, tuple[float, datetime.datetime | None]]:
    """{ticker: (price, quote time)} from Yahoo, via yfinance's fast path."""
    import yfinance as yf
    out = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            price = info.get("regularMarketPrice")
            ts = info.get("regularMarketTime")
            if price:
                stamp = datetime.datetime.fromtimestamp(int(ts), TOKYO) if ts else None
                out[t] = (float(price), stamp)
        except Exception as e:  # noqa: BLE001 — a dead sample must not end the run
            print(f"    yahoo {t}: {type(e).__name__}: {e}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--interval", type=float, default=60, help="seconds between samples")
    ap.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    args = ap.parse_args()

    now_jst = datetime.datetime.now(TOKYO)
    if not (datetime.time(9, 0) <= now_jst.time() <= datetime.time(15, 30)) or now_jst.weekday() >= 5:
        print(f"WARNING: Tokyo is closed ({now_jst:%a %H:%M} JST). Lag is only "
              f"measurable during the session — the numbers below will be meaningless.\n")

    # {source: {ticker: [(sampled_at, price)]}}
    series: dict[str, dict[str, list]] = {"tencent": defaultdict(list), "yahoo": defaultdict(list)}
    stamp_lag: dict[str, list[float]] = defaultdict(list)

    deadline = time.time() + args.minutes * 60
    sample = 0
    while time.time() < deadline:
        sample += 1
        at = datetime.datetime.now(TOKYO)
        for source, fetch in (("tencent", _tencent), ("yahoo", _yahoo)):
            try:
                got = fetch(args.tickers)
            except Exception as e:  # noqa: BLE001
                print(f"  [{at:%H:%M:%S}] {source} failed: {type(e).__name__}: {e}")
                continue
            for ticker, (price, stamp) in got.items():
                series[source][ticker].append((at, price))
                if stamp:
                    stamp_lag[source].append((at - stamp).total_seconds() / 60)

        t = args.tickers[0]
        tx = series["tencent"][t][-1][1] if series["tencent"][t] else None
        yh = series["yahoo"][t][-1][1] if series["yahoo"][t] else None
        print(f"  [{at:%H:%M:%S} JST] sample {sample}: {t} tencent={tx} yahoo={yh}"
              f"{'  <- differ' if tx != yh else ''}")
        time.sleep(max(0.0, args.interval - (datetime.datetime.now(TOKYO) - at).total_seconds()))

    print("\n── published quote-time lag (minutes behind wall clock) ──")
    for source, lags in stamp_lag.items():
        if lags:
            print(f"  {source:8} min={min(lags):5.1f}  median={sorted(lags)[len(lags)//2]:5.1f}  max={max(lags):5.1f}")

    print("\n── does Yahoo repeat what Tencent already printed? ──")
    for ticker in args.tickers:
        tx, yh = series["tencent"][ticker], series["yahoo"][ticker]
        moves = len({p for _, p in tx})
        if moves < 2:
            print(f"  {ticker}: price never moved during the window — inconclusive")
            continue
        # For each Tencent print, when did that exact price first show up on Yahoo?
        leads = []
        for at, price in tx:
            later = [y_at for y_at, y_px in yh if y_px == price and y_at >= at]
            if later:
                leads.append((min(later) - at).total_seconds() / 60)
        if leads:
            print(f"  {ticker}: {len(leads)}/{len(tx)} Tencent prints reappeared on Yahoo, "
                  f"median {sorted(leads)[len(leads)//2]:.1f} min later ({moves} distinct prices)")
        else:
            print(f"  {ticker}: no Tencent print reappeared on Yahoo ({moves} distinct prices)")


if __name__ == "__main__":
    main()
