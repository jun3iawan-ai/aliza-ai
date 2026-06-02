"""
ALIZA MARKET REGIME DETECTOR

Menentukan regime market global dari data BTC snapshot.
Hanya menggunakan data snapshot; tidak ada API call.
"""

import logging


def detect_market_regime(market_data):
    """
    Deteksi regime market dari market_data (biasanya BTC).

    Input: market_data dari snapshot (trend, rsi, volatility optional).
    Rule:
      - trend BULLISH dan rsi > 60 → TREND
      - trend SIDEWAYS dan 40 ≤ rsi ≤ 60 → RANGE
      - trend BEARISH dan rsi < 40 → DOWNTREND
      - Jika volatility tinggi → VOLATILE

    Return: {"market_regime": str}
    """
    try:
        if not market_data or not isinstance(market_data, dict):
            return {"market_regime": "UNKNOWN"}

        trend = (market_data.get("trend") or "").strip().upper()
        rsi_raw = market_data.get("rsi")
        volatility = market_data.get("volatility")

        try:
            rsi = float(rsi_raw) if rsi_raw is not None else None
        except (TypeError, ValueError):
            rsi = None

        # Volatility tinggi → VOLATILE
        vol_high = False
        if volatility is not None:
            if isinstance(volatility, str) and str(volatility).upper() in ("HIGH", "EXTREME"):
                vol_high = True
            elif isinstance(volatility, (int, float)) and float(volatility) > 0.05:
                vol_high = True
        if vol_high:
            return {"market_regime": "VOLATILE"}

        if rsi is None:
            return {"market_regime": "UNKNOWN"}

        if trend == "BULLISH" and rsi > 60:
            return {"market_regime": "TREND"}
        if trend == "SIDEWAYS" and 40 <= rsi <= 60:
            return {"market_regime": "RANGE"}
        if trend == "BEARISH" and rsi < 40:
            return {"market_regime": "DOWNTREND"}

        # Fallback by trend
        if trend == "BULLISH":
            return {"market_regime": "TREND"}
        if trend == "BEARISH":
            return {"market_regime": "DOWNTREND"}
        return {"market_regime": "RANGE"}
    except Exception as e:
        logging.debug("market_regime_detector error: %s", e)
        return {"market_regime": "UNKNOWN"}
