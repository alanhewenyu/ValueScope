"""Pure YTD attribution formulas — no I/O, unit-testable.

Two cost conventions per broker (account_settings.cost_method):
  'diluted': broker re-averages cost_price on partial sell, absorbing realized
             gains into the remaining position (Chinese brokers, Futu).
  'average': cost_price stays at the true weighted-average buy price; realized
             P&L is booked separately in closed_trades (IBKR). Funds
             (market='基金') follow this convention regardless of broker.

Baselines are per (year, ticker, broker): price/quantity/cost captured at
year start, or at position creation for mid-year (re-)buys (price == cost).
"""


def held_ytd(price: float, cost: float, qty: float,
             baseline: dict | None, uses_avg_cost: bool) -> float | None:
    """YTD P&L (native currency) for the currently-held shares of a position.

    baseline: {'price': bp, 'quantity': b_qty, 'cost_price': b_cost} or None.
    Returns None when no baseline exists (KPI falls back to snapshots).

    Diluted: cost absorbs realized gains, so pnl - baseline_unrealized is exact
    across partial sells and adds.
    Average partial sell (qty < b_qty): held YTD is price drift on remaining
    units, (price - bp) * qty; the sold units' YTD is locked in closed_trades.
    Average adds (qty >= b_qty): cost is a weighted average, standard formula
    holds.
    """
    if baseline is None:
        return None
    bp = baseline['price']
    b_qty = baseline.get('quantity')
    b_cost = baseline.get('cost_price')
    pnl = (price - cost) * qty
    if uses_avg_cost and b_qty is not None and qty < b_qty:
        return (price - bp) * qty
    if b_qty is not None and b_cost is not None:
        return pnl - (bp - b_cost) * b_qty
    return pnl - (bp - cost) * qty


def close_ytd(sell_price: float | None, qty: float | None,
              baseline_price: float | None, realized_pnl: float) -> float:
    """YTD attribution (native currency) of a sale, computed at sell time.

    With a baseline: (sell - bp) * qty — measures the sold shares from the
    year-start price. Mid-year positions get baselines at cost on creation,
    so this equals realized P&L for them.
    Without a baseline (or missing trade details): realized P&L itself.
    """
    if baseline_price is not None and sell_price is not None and qty is not None:
        return (sell_price - baseline_price) * qty
    return realized_pnl
