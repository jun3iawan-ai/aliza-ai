"""
ALIZA TRADE HISTORY TRACKER

Mencatat trade open dan close ke data/trade_history.json.
Learning system hanya membaca file ini; tidak mengubah database.
"""

import json
import logging
import os
from datetime import datetime

HISTORY_PATH = "data/trade_history.json"


def _load_history():
    """Load trade history from file. Return dict with 'closed' and 'opens' lists."""
    if not os.path.isfile(HISTORY_PATH):
        return {"closed": [], "opens": []}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"closed": [], "opens": []}
        return {
            "closed": data.get("closed") if isinstance(data.get("closed"), list) else [],
            "opens": data.get("opens") if isinstance(data.get("opens"), list) else [],
        }
    except Exception as e:
        logging.debug("trade_history_tracker load: %s", e)
        return {"closed": [], "opens": []}


def _save_history(data):
    """Write trade history to file."""
    try:
        os.makedirs(os.path.dirname(HISTORY_PATH) or ".", exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.warning("trade_history_tracker save: %s", e)


def record_trade_open(trade):
    """
    Catat trade yang baru dibuka.
    trade: dict dengan minimal coin, setup, entry; optional confidence, timestamp.
    """
    if not trade or not isinstance(trade, dict):
        return
    try:
        data = _load_history()
        record = {
            "coin": str(trade.get("coin", "")),
            "setup": str(trade.get("setup", "")),
            "entry": float(trade["entry"]) if trade.get("entry") is not None else 0.0,
            "timestamp": str(trade.get("timestamp") or datetime.utcnow().isoformat()),
        }
        data["opens"].append(record)
        _save_history(data)
    except Exception as e:
        logging.debug("record_trade_open: %s", e)


def record_trade_close(trade):
    """
    Catat trade yang ditutup. Append ke daftar closed.
    trade: dict dengan coin, setup, entry, exit, result ("WIN"|"LOSS"), rr, confidence, timestamp.
    """
    if not trade or not isinstance(trade, dict):
        return
    try:
        data = _load_history()
        record = {
            "coin": str(trade.get("coin", "")),
            "setup": str(trade.get("setup", "")),
            "entry": float(trade["entry"]) if trade.get("entry") is not None else 0.0,
            "exit": float(trade["exit"]) if trade.get("exit") is not None else 0.0,
            "result": "WIN" if str(trade.get("result", "")).upper() == "WIN" else "LOSS",
            "rr": float(trade["rr"]) if trade.get("rr") is not None else 0.0,
            "confidence": int(trade["confidence"]) if trade.get("confidence") is not None else 0,
            "timestamp": str(trade.get("timestamp") or datetime.utcnow().isoformat()),
        }
        data["closed"].append(record)
        _save_history(data)
    except Exception as e:
        logging.debug("record_trade_close: %s", e)


def get_closed_history():
    """Return list of closed trades (untuk analyzer)."""
    return _load_history().get("closed", [])
