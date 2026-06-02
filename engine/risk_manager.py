"""
Minimal risk guard sebelum trade setup diterima.
"""

import logging

logger = logging.getLogger(__name__)

MAX_RISK_PERCENT = 0.02  # 2%
MIN_RR = 2
MAX_OPEN_TRADES = 3

try:
    from engine.trading.trade_manager import get_active_trades
except ImportError:
    get_active_trades = None


def _current_open_trades() -> int:
    if get_active_trades is None:
        return 0
    try:
        rows = get_active_trades()
        return len(rows) if rows else 0
    except Exception:
        return 0


def validate_proposed_trade(entry, stop_loss, tp1) -> bool:
    """
    Return True jika setup lolos guard; False jika ditolak (risk %, RR, atau batas posisi).
    """
    if entry is None or stop_loss is None or tp1 is None:
        return False
    try:
        e = float(entry)
        sl = float(stop_loss)
        tp = float(tp1)
    except (TypeError, ValueError):
        return False
    if e <= 0:
        return False

    risk = abs(e - sl) / e
    if risk > MAX_RISK_PERCENT:
        logger.info("Trade rejected: risk too high")
        return False

    risk_abs = abs(e - sl)
    if risk_abs <= 0:
        return False
    reward = abs(tp - e)
    rr = reward / risk_abs
    if rr < MIN_RR:
        logger.info("Trade rejected: RR too low")
        return False

    if _current_open_trades() >= MAX_OPEN_TRADES:
        logger.info("Trade rejected: max open trades")
        return False

    return True
