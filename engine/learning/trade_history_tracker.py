"""
ALIZA TRADE HISTORY TRACKER

record_trade_open()/record_trade_close() masih mencatat ke data/trade_history.json
untuk siapa pun yang ingin jurnal manual terpisah, tapi TIDAK ADA kode produksi yang
memanggilnya (dikonfirmasi audit 2026-07-25). get_closed_history() -- konsumen nyata
oleh confidence_adjuster/drawdown_protector/`/performance` -- membaca LANGSUNG dari
signal_tracking (SQLite), sumber kebenaran outcome sinyal live sejak Fase 1.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime

from engine.trading import signal_tracker

HISTORY_PATH = "data/trade_history.json"

DEFAULT_LEARNING_SOURCE = "deterministic"


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


def get_closed_history(source=None):
    """Return closed (WIN/LOSS) live outcomes dari signal_tracking, format
    setup/result/rr/confidence/timestamp yang dipakai analyze_strategy_performance()
    dan analyze_performance(). Urutan kronologis ASC (terlama dulu) agar konsumen
    yang mengasumsikan "terbaru di akhir list" (mis. drawdown_protector) tetap benar.

    Default source='deterministic' -- konsisten dengan get_signal_stats() default:
    mengecualikan shadow_e3 (riset, tidak boleh mencemari statistik produksi),
    llm (SPOT/advisory, belum ada outcome closed), dan legacy (data pre-Fase1).
    """
    src = source if source is not None else DEFAULT_LEARNING_SOURCE
    try:
        conn = sqlite3.connect(signal_tracker.DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT coin, setup, side, rr, confidence, status,
                   COALESCE(close_time, signal_time) AS ts
            FROM signal_tracking
            WHERE source = ? AND status IN ('WIN', 'LOSS')
            ORDER BY COALESCE(close_time, signal_time) ASC, id ASC
            """,
            (src,),
        ).fetchall()
        conn.close()
    except Exception as e:
        logging.warning("trade_history_tracker get_closed_history: %s", e)
        return []

    return [
        {
            "coin": row["coin"],
            "setup": row["setup"] or "",
            "side": row["side"],
            "result": row["status"],
            "rr": row["rr"],
            "confidence": row["confidence"],
            "timestamp": row["ts"],
        }
        for row in rows
    ]
