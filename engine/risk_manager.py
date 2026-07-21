"""
Minimal risk guard sebelum trade setup diterima.
"""

import logging
import math

logger = logging.getLogger(__name__)

MAX_RISK_PERCENT = 0.02  # 2%
MIN_RR = 2
MAX_OPEN_TRADES = 3

try:
    from engine.trading.trade_manager import get_active_trades
except ImportError:
    get_active_trades = None


def _current_open_trades() -> int | None:
    if get_active_trades is None:
        logger.error("Trade rejected: active-trade store unavailable")
        return None
    try:
        rows = get_active_trades()
        return len(rows) if rows else 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Trade rejected: failed to read open trades: %s", exc)
        return None


def validate_proposed_trade(entry, stop_loss, tp1, side) -> bool:
    """Validasi level, arah, risk, RR, dan batas posisi secara fail-closed."""
    if entry is None or stop_loss is None or tp1 is None or side is None:
        return False
    try:
        e = float(entry)
        sl = float(stop_loss)
        tp = float(tp1)
    except (TypeError, ValueError):
        return False
    if not all(math.isfinite(value) and value > 0 for value in (e, sl, tp)):
        return False

    normalized_side = str(side).strip().upper()
    if normalized_side == "LONG":
        if not sl < e < tp:
            logger.info("Trade rejected: invalid LONG level direction")
            return False
    elif normalized_side == "SHORT":
        if not tp < e < sl:
            logger.info("Trade rejected: invalid SHORT level direction")
            return False
    else:
        logger.info("Trade rejected: invalid side")
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

    open_trades = _current_open_trades()
    if open_trades is None:
        return False
    if open_trades >= MAX_OPEN_TRADES:
        logger.info("Trade rejected: max open trades")
        return False

    return True
