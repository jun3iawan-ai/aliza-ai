"""
ALIZA BIAS SCORE ENGINE

Menghitung bullish_score dan bearish_score dari snapshot (BTC + market_intelligence).
Hanya membaca snapshot; tidak mengubah pipeline.
"""

import logging


def calculate_market_bias(snapshot):
    """
    Hitung skor bias dari snapshot["data"]["BTC"] dan snapshot["market_intelligence"].

    Rule:
      trend BULLISH → bullish +30, BEARISH → bearish +30
      rsi > 60 → bullish +10, rsi < 40 → bearish +10
      market_regime TREND → bullish +10, DOWNTREND → bearish +10
      whale_pressure BUYING → bullish +10, SELLING → bearish +10
      altseason_probability > 60 → bullish +10

    Return: {"bullish_score": int, "bearish_score": int}
    """
    bullish_score = 0
    bearish_score = 0
    try:
        if not snapshot or not isinstance(snapshot, dict):
            return {"bullish_score": 0, "bearish_score": 0}

        data = snapshot.get("data") or {}
        btc = data.get("BTC") if isinstance(data, dict) else None
        mi = snapshot.get("market_intelligence") or {}
        if not isinstance(mi, dict):
            mi = {}

        if btc and isinstance(btc, dict):
            trend = (btc.get("trend") or "").strip().upper()
            if trend == "BULLISH":
                bullish_score += 30
            elif trend == "BEARISH":
                bearish_score += 30

            rsi = btc.get("rsi")
            if rsi is not None:
                try:
                    r = float(rsi)
                    if r > 60:
                        bullish_score += 10
                    elif r < 40:
                        bearish_score += 10
                except (TypeError, ValueError):
                    pass

        regime = (mi.get("market_regime") or "").strip().upper()
        if regime == "TREND":
            bullish_score += 10
        elif regime == "DOWNTREND":
            bearish_score += 10

        whale = (mi.get("whale_pressure") or "").strip().upper()
        if whale == "BUYING":
            bullish_score += 10
        elif whale == "SELLING":
            bearish_score += 10

        alt_prob = mi.get("altseason_probability")
        if alt_prob is not None:
            try:
                if int(alt_prob) > 60:
                    bullish_score += 10
            except (TypeError, ValueError):
                pass

        return {"bullish_score": max(0, bullish_score), "bearish_score": max(0, bearish_score)}
    except Exception as e:
        logging.debug("bias_score_engine: %s", e)
        return {"bullish_score": 0, "bearish_score": 0}
