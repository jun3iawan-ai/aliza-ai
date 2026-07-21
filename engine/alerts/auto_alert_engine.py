"""
ALIZA AUTO ALERT ENGINE

Mengumpulkan peluang trading berkualitas tinggi untuk unified gateway (process_signal).
Hanya menggunakan data dari opportunity scanner; tidak ada API call baru.
"""

import logging
import math
import os

from engine.signal_engine import build_unified_signal

def _load_min_score() -> float:
    raw = os.getenv("AUTO_ALERT_MIN_SCORE", "70")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logging.getLogger(__name__).error(
            "AUTO_ALERT_MIN_SCORE harus berupa angka dalam rentang 0-100"
        )
        raise RuntimeError("AUTO_ALERT_MIN_SCORE must be between 0 and 100") from None
    if not math.isfinite(value) or not 0 <= value <= 100:
        logging.getLogger(__name__).error(
            "AUTO_ALERT_MIN_SCORE di luar rentang score 0-100: %r", raw
        )
        raise RuntimeError("AUTO_ALERT_MIN_SCORE must be between 0 and 100")
    return value


# Threshold alert; score berasal dari signal_quality_engine (0-100).
MIN_SCORE = _load_min_score()
MIN_RR = 2.5
MIN_CONFIDENCE = 65


def _safe_float(val, default=0.0):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _format_alert_message(opp):
    """Format pesan Telegram sesuai spesifikasi."""
    coin = opp.get("coin", "")
    setup = opp.get("setup", "")
    entry = opp.get("entry")
    sl = opp.get("sl")
    tp1 = opp.get("tp1")
    tp2 = opp.get("tp2")
    rr = opp.get("rr")
    confidence = opp.get("confidence")
    score = opp.get("score")

    def _num(x):
        if x is None:
            return "—"
        try:
            return round(float(x), 2)
        except (TypeError, ValueError):
            return "—"

    lines = [
        "🚨 ALIZA TRADE ALERT",
        "",
        f"{coin} {setup}",
        "",
        f"Entry : {_num(entry)}",
        f"SL : {_num(sl)}",
        f"TP1 : {_num(tp1)}",
        f"TP2 : {_num(tp2)}",
        "",
        f"RR : {_num(rr)}",
        f"Confidence : {confidence}",
        f"Score : {_num(score)}",
    ]
    return "\n".join(lines)


def process_auto_alerts(opportunities):
    """
    Filter opportunity yang memenuhi syarat alert (score≥160, rr≥2.5, confidence≥65).
    Return list untuk gateway: message + signal (unified) per item.
    Dedup & risk ditangani oleh engine.signal_engine.process_signal.
    """
    if not opportunities:
        return []

    to_send = []

    for opp in opportunities:
        score = _safe_float(opp.get("score"), 0)
        rr = _safe_float(opp.get("rr"), 0)
        confidence = _safe_float(opp.get("confidence"), 0)

        if score < MIN_SCORE or rr < MIN_RR or confidence < MIN_CONFIDENCE:
            continue

        coin = (opp.get("coin") or "").strip()
        setup = (opp.get("setup") or "").strip()
        if not coin:
            continue

        sig = build_unified_signal(
            source="auto_alert",
            coin=coin,
            setup=setup,
            entry=opp.get("entry"),
            sl=opp.get("sl"),
            tp1=opp.get("tp1"),
            tp2=opp.get("tp2"),
            rr=opp.get("rr"),
            confidence=opp.get("confidence"),
        )

        to_send.append({
            "message": _format_alert_message(opp),
            "coin": coin,
            "setup": setup,
            "signal": sig,
        })

    return to_send
