"""
ALIZA MARKET INTELLIGENCE

Analyze overall crypto market environment using snapshot data only.
Does not call any external API.
"""

import logging


def analyze_market_environment(snapshot):
    """
    Analyze market environment from snapshot. Returns market_phase, crash_warning, btc_trend, btc_rsi.
    Snapshot must be the dict returned by get_market_snapshot().
    """
    data = snapshot.get("data", {}) or {}
    btc = data.get("BTC")

    if not btc:
        return {
            "market_phase": "UNKNOWN",
            "crash_warning": False,
            "btc_trend": "UNKNOWN",
            "btc_rsi": None,
        }

    price = btc.get("price")
    rsi = btc.get("rsi")
    trend = btc.get("trend")
    support = btc.get("support")

    # Determine market phase
    if rsi is not None and rsi < 35:
        phase = "ACCUMULATION"
    elif rsi is not None and rsi > 70:
        phase = "OVERBOUGHT"
    elif trend == "BULLISH":
        phase = "BULL TREND"
    elif trend == "BEARISH":
        phase = "BEAR TREND"
    else:
        phase = "NEUTRAL"

    # Crash detection
    crash_warning = False
    try:
        if price is not None and support is not None:
            if price < support * 0.97:
                crash_warning = True
    except Exception:
        pass

    return {
        "market_phase": phase,
        "crash_warning": crash_warning,
        "btc_trend": trend,
        "btc_rsi": rsi,
    }
