"""
ALIZA DRAWDOWN PROTECTOR

Baca trade_history.json; jika loss streak terakhir >= 3, blok trading baru.
"""

import logging

try:
    from engine.learning.trade_history_tracker import get_closed_history
except ImportError:
    get_closed_history = None

LOSS_STREAK_THRESHOLD = 3


def check_drawdown():
    """
    Hitung loss streak terakhir dari closed trades (urutan terbaru di akhir list).

    Jika streak loss >= 3: return {"trading_allowed": False}
    Else: return {"trading_allowed": True}
    """
    if get_closed_history is None:
        return {"trading_allowed": True}
    try:
        closed = get_closed_history()
        if not closed or not isinstance(closed, list):
            return {"trading_allowed": True}
        streak = 0
        for t in reversed(closed):
            if not isinstance(t, dict):
                continue
            result = str(t.get("result", "")).upper()
            if result == "LOSS":
                streak += 1
            else:
                break
        if streak >= LOSS_STREAK_THRESHOLD:
            return {"trading_allowed": False, "loss_streak": streak}
        return {"trading_allowed": True}
    except Exception as e:
        logging.debug("drawdown_protector: %s", e)
        return {"trading_allowed": True}
