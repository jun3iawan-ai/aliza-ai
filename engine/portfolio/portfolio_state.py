"""
ALIZA PORTFOLIO STATE

Mengambil posisi aktif dari trade manager untuk Portfolio AI.
Tidak mengubah database; hanya membaca.
"""

import logging

try:
    from engine.trading.trade_manager import get_active_trades
except ImportError:
    get_active_trades = None


def get_active_positions():
    """
    Ambil posisi aktif dari trade manager.

    Return: {"count": int, "positions": list}
    positions: list of dict dengan coin, direction, setup, entry, stop_loss, tp1, tp2.
    """
    if get_active_trades is None:
        return {"count": 0, "positions": []}
    try:
        rows = get_active_trades()
        if not rows:
            return {"count": 0, "positions": []}
        positions = []
        for r in rows:
            if len(r) >= 10:
                positions.append({
                    "coin": r[0],
                    "direction": r[1],
                    "setup": r[2],
                    "entry": r[3],
                    "stop_loss": r[4],
                    "tp1": r[5],
                    "tp2": r[6],
                    "quantity": r[7],
                    "position_value_usdt": r[8],
                    "risk_usdt": r[9],
                })
            elif len(r) >= 7:
                positions.append({
                    "coin": r[0],
                    "direction": r[1],
                    "setup": r[2],
                    "entry": r[3],
                    "stop_loss": r[4],
                    "tp1": r[5],
                    "tp2": r[6],
                })
            elif len(r) >= 6:
                positions.append({
                    "coin": r[0],
                    "direction": "LONG" if "LONG" in str(r[1] or "") or r[1] == "OVERSOLD BOUNCE" else "SHORT",
                    "setup": r[1],
                    "entry": r[2],
                    "stop_loss": r[3],
                    "tp1": r[4],
                    "tp2": r[5],
                })
        return {"count": len(positions), "positions": positions}
    except Exception as e:
        logging.debug("portfolio_state get_active_positions: %s", e)
        return {"count": 0, "positions": []}
