"""
ALIZA WHALE SIGNAL ENGINE

Mendeteksi aktivitas whale yang signifikan (accumulation / distribution)
dari data market cache dan menghasilkan list alert untuk Telegram.
"""

import logging

from engine.utils.market_cache import get_all_market_data


# =========================
# SCAN WHALE SIGNALS
# =========================

def scan_whale_signals():
    """
    Ambil market data dari cache, terapkan rule accumulation dan distribution,
    return list alert (setiap item dict: coin, whale_activity, trend, rsi, type).
    """
    try:
        markets = get_all_market_data()
    except Exception as e:
        logging.warning("scan_whale_signals get_all_market_data: %s", e)
        return []

    if not markets:
        return []

    alerts = []

    for coin, data in markets.items():

        try:

            if not data:
                continue

            trend = data.get("trend")
            rsi = data.get("rsi")
            whale_activity = data.get("whale_activity")

            if trend is None or whale_activity is None:
                continue

            # RULE ACCUMULATION: bearish + whale HIGH/EXTREME + rsi < 45
            if (
                trend == "BEARISH"
                and whale_activity in ("HIGH", "EXTREME")
                and rsi is not None
                and rsi < 45
            ):
                alerts.append({
                    "coin": coin,
                    "whale_activity": whale_activity,
                    "trend": trend,
                    "rsi": rsi,
                    "type": "accumulation",
                })
                continue

            # RULE DISTRIBUTION: bullish + whale EXTREME + rsi > 60
            if (
                trend == "BULLISH"
                and whale_activity == "EXTREME"
                and rsi is not None
                and rsi > 60
            ):
                alerts.append({
                    "coin": coin,
                    "whale_activity": whale_activity,
                    "trend": trend,
                    "rsi": rsi,
                    "type": "sell_pressure",
                })

        except Exception as e:
            logging.warning("scan_whale_signals coin %s: %s", coin, e)
            continue

    return alerts


# =========================
# FORMAT ALERT
# =========================

def format_whale_alert(data):
    """
    Format pesan Telegram untuk whale alert.
    """
    if not data:
        return ""

    coin = data.get("coin", "")
    whale_activity = data.get("whale_activity", "")
    trend = data.get("trend", "")
    rsi = data.get("rsi")

    rsi_str = round(rsi, 2) if isinstance(rsi, (int, float)) else (rsi if rsi is not None else "—")

    message = (
        "🐋 WHALE ACTIVITY ALERT\n\n"
        f"Coin : {coin}\n"
        f"Whale Activity : {whale_activity}\n\n"
        f"Trend : {trend}\n"
        f"RSI : {rsi_str}\n\n"
        "Smart money terdeteksi aktif pada market ini."
    )
    return message
