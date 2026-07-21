"""Deterministic fee, slippage, and futures funding calculations."""

from __future__ import annotations

import math
from bisect import bisect_right


FEE_PER_SIDE = 0.001
SLIPPAGE_PER_SIDE = 0.0005
FALLBACK_FUNDING_PER_8H = 0.0001


def effective_entry(raw_price, side, slippage=SLIPPAGE_PER_SIDE):
    price = float(raw_price)
    return price * (1 + slippage) if side == "LONG" else price * (1 - slippage)


def effective_exit(raw_price, side, slippage=SLIPPAGE_PER_SIDE):
    price = float(raw_price)
    return price * (1 - slippage) if side == "LONG" else price * (1 + slippage)


def funding_cost_pct(entry_ms, exit_ms, funding_history, fallback_rate=FALLBACK_FUNDING_PER_8H):
    """Return total short funding cost as a positive percentage and method."""
    if exit_ms <= entry_ms:
        return 0.0, "none"
    intervals = max(1, math.ceil((exit_ms - entry_ms) / (8 * 60 * 60 * 1000)))
    history = sorted(funding_history or [], key=lambda item: int(item["timestamp"]))
    timestamps = [int(item["timestamp"]) for item in history]
    total = 0.0
    used_history = False
    for index in range(intervals):
        target = entry_ms + (index + 1) * 8 * 60 * 60 * 1000
        pos = bisect_right(timestamps, target) - 1
        if pos >= 0:
            total += float(history[pos]["funding_rate"])
            used_history = True
        else:
            total += fallback_rate
    return total, "binance_history" if used_history else "fallback_0.01pct_8h"


def calculate_trade_pnl(side, entry_raw, exit_raw, notional, entry_ms, exit_ms, funding_history=None, fee_per_side=FEE_PER_SIDE, slippage_per_side=SLIPPAGE_PER_SIDE):
    """Net PnL percentage/USDT with two-sided fee+slippage and short funding."""
    entry = effective_entry(entry_raw, side, slippage=slippage_per_side)
    exit_price = effective_exit(exit_raw, side, slippage=slippage_per_side)
    gross_return = (exit_price / entry - 1) if side == "LONG" else (entry / exit_price - 1)
    fee_pct = 2 * float(fee_per_side)
    funding_pct, funding_method = (0.0, "none")
    if side == "SHORT":
        funding_pct, funding_method = funding_cost_pct(entry_ms, exit_ms, funding_history)
    net_pct = gross_return - fee_pct - funding_pct
    return {
        "gross_pnl_pct": round(gross_return * 100, 8),
        "fee_pct": fee_pct * 100,
        "slippage_pct": 2 * float(slippage_per_side) * 100,
        "funding_pct": funding_pct * 100,
        "funding_method": funding_method,
        "pnl_pct": round(net_pct * 100, 8),
        "pnl_usdt": round(float(notional) * net_pct, 8),
    }
