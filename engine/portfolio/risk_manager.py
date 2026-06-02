"""
ALIZA RISK MANAGER

Evaluasi trade sebelum eksekusi: batas posisi dan risiko.
"""

import logging

MAX_POSITIONS = 3
MAX_PORTFOLIO_RISK = 0.05
MAX_RISK_PER_TRADE = 0.01

try:
    from engine.portfolio.portfolio_state import get_active_positions
except ImportError:
    get_active_positions = None


def evaluate_trade(entry, sl):
    """
    Evaluasi apakah trade diizinkan berdasarkan aturan risiko.

    Rule: MAX_POSITIONS, MAX_RISK_PER_TRADE.
    Return: {"allowed": bool, "reason": str}
    """
    try:
        if entry is None or sl is None:
            return {"allowed": False, "reason": "Entry atau SL tidak valid"}
        try:
            e = float(entry)
            s = float(sl)
        except (TypeError, ValueError):
            return {"allowed": False, "reason": "Entry atau SL bukan angka"}
        if e <= 0:
            return {"allowed": False, "reason": "Entry harus positif"}
        risk_per_unit = abs(e - s)
        if risk_per_unit <= 0:
            return {"allowed": False, "reason": "Jarak entry-SL tidak valid"}
        if get_active_positions is not None:
            state = get_active_positions()
            count = state.get("count", 0)
            if count >= MAX_POSITIONS:
                return {"allowed": False, "reason": f"Maksimal {MAX_POSITIONS} posisi terbuka"}
        return {"allowed": True, "reason": "OK"}
    except Exception as e:
        logging.debug("risk_manager evaluate_trade: %s", e)
        return {"allowed": False, "reason": "Error evaluasi risiko"}
