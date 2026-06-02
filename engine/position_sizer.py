"""
Position Sizing Calculator — Aliza-AI
Fase 1: Fixed Fractional berbasis account balance dari .env

Referensi arsitektur: docs/architecture/position-sizing.md
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.02"))
DEFAULT_MAX_ALLOCATION = float(os.getenv("MAX_ALLOCATION_PER_TRADE", "0.30"))
DEFAULT_MAX_TOTAL_RISK = float(os.getenv("MAX_TOTAL_RISK", "0.06"))


def get_account_balance() -> float:
    """Ambil account balance. Prioritas: user_config DB > .env > 0."""
    try:
        from engine.user_config import get_balance

        return get_balance()
    except ImportError:
        pass
    try:
        balance = float(os.getenv("ACCOUNT_BALANCE", "0"))
        return balance if balance > 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


@dataclass
class PositionSizeResult:
    size_units: float
    size_usdt: float
    risk_amount_usdt: float
    risk_percent: float
    allocation_percent: float
    limited_by: str
    warnings: list[str] = field(default_factory=list)


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    account_balance: Optional[float] = None,
    risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
    max_allocation: float = DEFAULT_MAX_ALLOCATION,
    current_open_risk_usdt: float = 0.0,
    max_total_risk: float = DEFAULT_MAX_TOTAL_RISK,
) -> Optional[PositionSizeResult]:
    """
    Hitung position size optimal.
    Lihat docs/architecture/position-sizing.md §2 untuk formula detail.
    """
    if account_balance is None:
        account_balance = get_account_balance()

    if account_balance <= 0:
        logger.debug("Account balance tidak di-set, skip position sizing")
        return None

    if entry_price <= 0 or stop_loss <= 0:
        logger.error("Entry (%s) atau SL (%s) invalid", entry_price, stop_loss)
        return None

    sl_distance = abs(entry_price - stop_loss)
    if sl_distance == 0:
        logger.error("Entry dan SL sama — tidak bisa hitung size")
        return None

    warnings: list[str] = []

    max_risk_usdt = account_balance * max_total_risk
    remaining_risk = max_risk_usdt - current_open_risk_usdt

    if remaining_risk <= 0:
        warnings.append("Risk budget portfolio sudah penuh")
        return PositionSizeResult(
            size_units=0.0,
            size_usdt=0.0,
            risk_amount_usdt=0.0,
            risk_percent=0.0,
            allocation_percent=0.0,
            limited_by="total_risk_exceeded",
            warnings=warnings,
        )

    risk_amount = min(account_balance * risk_per_trade, remaining_risk)
    size_by_risk = risk_amount / sl_distance
    value_by_risk = size_by_risk * entry_price

    max_value = account_balance * max_allocation
    size_by_alloc = max_value / entry_price

    if value_by_risk <= max_value:
        final_size = size_by_risk
        limited_by = "risk"
    else:
        final_size = size_by_alloc
        risk_amount = final_size * sl_distance
        limited_by = "allocation"
        warnings.append(f"Size dikurangi oleh max allocation ({max_allocation * 100:.0f}%)")

    final_value = final_size * entry_price
    actual_risk_pct = (final_size * sl_distance) / account_balance
    alloc_pct = final_value / account_balance

    if alloc_pct > 0.5:
        warnings.append(f"Alokasi {alloc_pct * 100:.1f}% > 50% akun — review manual")

    sl_pct = sl_distance / entry_price if entry_price else 0.0
    if sl_pct <= 0.005:
        warnings.append("SL terlalu dekat (≤ 0.5%), size besar — review manual")

    return PositionSizeResult(
        size_units=round(final_size, 6),
        size_usdt=round(final_value, 2),
        risk_amount_usdt=round(risk_amount, 2),
        risk_percent=round(actual_risk_pct * 100, 2),
        allocation_percent=round(alloc_pct * 100, 2),
        limited_by=limited_by,
        warnings=warnings,
    )


def get_current_open_risk(active_trades: list[Any], account_balance: float) -> float:
    """
    Hitung total risk USDT dari posisi terbuka.

    Jika trade punya quantity → risk = |entry - sl| × quantity
    Jika trade TIDAK punya quantity → asumsi risk = RISK_PER_TRADE × balance per posisi
    """
    if not active_trades or account_balance <= 0:
        return 0.0

    total_risk = 0.0
    default_per_trade = account_balance * DEFAULT_RISK_PER_TRADE

    for trade in active_trades:
        try:
            if isinstance(trade, dict):
                entry = float(trade.get("entry") or 0)
                sl = float(trade.get("stop_loss") or 0)
                qty = float(trade.get("quantity") or 0)
            else:
                t = tuple(trade)
                n = len(t)
                if n >= 8:
                    entry = float(t[3] or 0)
                    sl = float(t[4] or 0)
                    qty = float(t[7] or 0)
                elif n >= 7:
                    entry = float(t[3] or 0)
                    sl = float(t[4] or 0)
                    qty = 0.0
                elif n >= 6:
                    entry = float(t[2] or 0)
                    sl = float(t[3] or 0)
                    qty = 0.0
                else:
                    total_risk += default_per_trade
                    continue
        except (ValueError, TypeError, IndexError):
            total_risk += default_per_trade
            continue

        if qty > 0 and entry > 0 and sl > 0:
            total_risk += abs(entry - sl) * qty
        elif entry > 0 and sl > 0:
            total_risk += default_per_trade
        else:
            total_risk += default_per_trade

    return round(total_risk, 2)
