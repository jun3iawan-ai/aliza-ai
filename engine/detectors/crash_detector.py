"""
ALIZA CRASH DETECTOR

Mendeteksi potensi crash market menggunakan data dari market snapshot.
Rule kontekstual: crash_risk hanya True jika HIGH risk plus bearish/overbought/liquidation kuat.
"""

import logging


def detect_crash_risk(market_data):
    """
    Crash risk hanya True jika kontekstual:

    1) Market risk HIGH dan trend BEARISH
    2) Market risk HIGH dan RSI sangat overbought (>= 70)
    3) Market risk HIGH dan liquidation_risk sangat kuat (jika tersedia)

    Return: {"crash_risk": bool}
    """
    try:
        if not market_data or not isinstance(market_data, dict):
            return {"crash_risk": False}

        trend = str(market_data.get("trend", "")).strip().upper()
        rsi = market_data.get("rsi")
        market_risk = str(market_data.get("market_risk_score", "")).strip().upper()
        liquidation_risk = str(market_data.get("liquidation_risk", "")).strip().upper()

        rsi_val = None
        try:
            if rsi is not None:
                rsi_val = float(rsi)
        except (TypeError, ValueError):
            pass

        high_risk = market_risk == "HIGH"
        bearish_trend = trend == "BEARISH"
        overbought = rsi_val is not None and rsi_val >= 70
        liquidation_strong = liquidation_risk in ("HIGH", "EXTREME")

        crash_risk = high_risk and (bearish_trend or overbought or liquidation_strong)
        logging.debug("Crash detector risk=%s", crash_risk)
        return {"crash_risk": crash_risk}
    except Exception as e:
        logging.debug("crash_detector error: %s", e)
        return {"crash_risk": False}
