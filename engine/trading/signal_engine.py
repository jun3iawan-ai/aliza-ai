"""
ALIZA AUTO SIGNAL ENGINE

Scan market otomatis, pilih setup terbaik (RR >= 3, confidence >= 70),
dengan SMART SIGNAL FILTER: konteks BTC, trend alignment, market risk.
Format pesan signal untuk Telegram. Anti-spam: tidak kirim coin yang sama
dalam 30 menit.
"""

import logging
from datetime import datetime, timedelta

from engine.utils.market_cache import get_all_market_data, get_market_data
from engine.trading.trade_decision_ai import evaluate_trade


# =========================
# GLOBAL STATE (ANTI SPAM)
# =========================

LAST_SIGNAL = None       # coin terakhir yang dikirim (str atau None)
LAST_SIGNAL_TIME = None  # waktu terakhir kirim (datetime atau None)
ANTI_SPAM_WINDOW = 30    # menit


def can_send_signal(signal):
    """
    Return True jika signal boleh dikirim.
    Jika coin sama dengan LAST_SIGNAL dan masih dalam ANTISPAM_WINDOW, return False.
    """
    if signal is None:
        return False
    global LAST_SIGNAL, LAST_SIGNAL_TIME
    coin = signal.get("coin")
    now = datetime.now()
    if LAST_SIGNAL is None or LAST_SIGNAL_TIME is None:
        return True
    if coin != LAST_SIGNAL:
        return True
    return (now - LAST_SIGNAL_TIME) >= timedelta(minutes=ANTI_SPAM_WINDOW)


def record_signal_sent(signal):
    """Update global state setelah signal dikirim."""
    global LAST_SIGNAL, LAST_SIGNAL_TIME
    if signal:
        LAST_SIGNAL = signal.get("coin")
        LAST_SIGNAL_TIME = datetime.now()


# =========================
# BTC CONTEXT (SMART FILTER)
# =========================

def get_btc_context():
    """
    Ambil konteks market dari data BTC (trend, risk, phase).
    Menggunakan cache agar tidak memicu API tambahan.
    """
    try:
        btc = get_market_data("BTC")
        if not btc or isinstance(btc, dict) and btc.get("error"):
            return {}
        return {
            "btc_trend": btc.get("trend"),
            "market_risk": btc.get("market_risk_score"),
            "market_phase": btc.get("market_phase_prediction"),
        }
    except Exception as e:
        logging.warning("get_btc_context: %s", e)
        return {}


# =========================
# SCAN FOR SIGNALS
# =========================

def scan_for_signals():
    """
    Ambil semua market data dari cache, terapkan SMART SIGNAL FILTER,
    filter RR >= 3 dan confidence >= 70, pilih signal dengan RR tertinggi.
    Return dict signal (dengan btc_trend, market_risk) atau None.
    """
    try:
        markets = get_all_market_data()
    except Exception as e:
        logging.warning("scan_for_signals get_all_market_data: %s", e)
        return None

    if not markets:
        return None

    try:
        context = get_btc_context()
    except Exception as e:
        logging.warning("scan_for_signals get_btc_context: %s", e)
        context = {}

    # Rule: market_risk HIGH -> skip semua signal
    if context.get("market_risk") == "HIGH":
        return None

    btc_trend = context.get("btc_trend")
    market_phase = context.get("market_phase")
    candidates = []

    for coin, data in markets.items():

        try:

            if not data:
                continue

            trade_setup = data.get("trade_setup")

            if not trade_setup:
                continue

            setup = trade_setup.get("setup")
            entry = trade_setup.get("entry")
            sl = trade_setup.get("sl")
            tp1 = trade_setup.get("tp1")
            tp2 = trade_setup.get("tp2")
            rr = trade_setup.get("risk_reward")
            confidence = trade_setup.get("confidence")

            if rr is None or confidence is None:
                continue

            if rr < 3 or confidence < 70:
                continue

            # Trend alignment: BEARISH -> skip LONG
            if btc_trend == "BEARISH" and setup and "LONG" in setup:
                continue

            # Trend alignment: BULLISH -> skip SHORT
            if btc_trend == "BULLISH" and setup and "SHORT" in setup:
                continue

            # SIDEWAYS: kurangi confidence 10 poin
            if market_phase == "SIDEWAYS":
                confidence = (confidence - 10) if isinstance(confidence, (int, float)) else confidence

            candidates.append({
                "coin": coin,
                "setup": setup,
                "entry": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "rr": rr,
                "confidence": confidence,
            })

        except Exception as e:
            logging.warning("scan_for_signals candidate %s: %s", coin, e)
            continue

    if not candidates:
        return None

    # Ranking: sort by risk_reward tertinggi, ambil 1
    candidates.sort(key=lambda x: x["rr"], reverse=True)
    best = candidates[0]

    best["btc_trend"] = context.get("btc_trend")
    best["market_risk"] = context.get("market_risk")

    decision = evaluate_trade(best)
    best["trade_score"] = decision.get("score")
    best["trade_status"] = decision.get("status")

    return best


# =========================
# FORMAT PESAN TELEGRAM
# =========================

def format_signal_message(signal):
    """
    Format pesan Telegram untuk signal trading (Bahasa Indonesia),
    termasuk Market Context (BTC Trend, Market Risk).
    """
    if not signal:
        return ""

    coin = signal.get("coin", "")
    setup = signal.get("setup", "")
    entry = signal.get("entry")
    sl = signal.get("sl")
    tp1 = signal.get("tp1")
    tp2 = signal.get("tp2")
    rr = signal.get("rr")
    confidence = signal.get("confidence")
    btc_trend = signal.get("btc_trend")
    market_risk = signal.get("market_risk")
    trade_score = signal.get("trade_score")
    trade_status = signal.get("trade_status")

    def _n(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return round(v, 2)
        return v

    message = (
        "🚨 HIGH PROBABILITY TRADE\n\n"
        f"{coin} {setup}\n\n"
        f"Entry : {_n(entry)}\n"
        f"SL : {_n(sl)}\n"
        f"TP1 : {_n(tp1)}\n"
        f"TP2 : {_n(tp2)}\n\n"
        f"RR : {_n(rr)}\n"
        f"Confidence : {_n(confidence)}\n\n"
    )

    if trade_score is not None or trade_status:
        message += (
            "Trade Score\n"
            f"Score : {trade_score if trade_score is not None else '—'}\n"
            f"Status : {trade_status if trade_status else '—'}\n\n"
        )

    message += (
        "Market Context\n"
        f"BTC Trend : {btc_trend if btc_trend is not None else '—'}\n"
        f"Market Risk : {market_risk if market_risk is not None else '—'}\n\n"
        "Signal otomatis oleh AlizaAI"
    )
    return message
