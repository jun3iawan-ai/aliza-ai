"""
ALIZA ALTSEASON MODEL

Menghitung probabilitas altseason dari snapshot (dominance BTC, jumlah alt bullish).
Hanya menggunakan data snapshot; tidak ada API call.
"""

import logging


def calculate_altseason_probability(markets):
    """
    Hitung probabilitas altseason (0–100) dari data markets.

    Input: markets = dict symbol -> market_data (dari snapshot["data"]).
    Gunakan: BTC dominance, jumlah altcoin bullish.

    Return: {"altseason_probability": int} range 0–100.
    """
    try:
        if not markets or not isinstance(markets, dict):
            return {"altseason_probability": 0}

        btc_data = markets.get("BTC")
        dominance = 50.0
        if btc_data and isinstance(btc_data, dict):
            d = btc_data.get("dominance")
            try:
                dominance = float(d) if d is not None else 50.0
            except (TypeError, ValueError):
                pass

        alt_bullish = 0
        alt_total = 0
        for symbol, data in markets.items():
            if not data or not isinstance(data, dict):
                continue
            if symbol.upper() == "BTC":
                continue
            alt_total += 1
            if (data.get("trend") or "").strip().upper() == "BULLISH":
                alt_bullish += 1

        # Base: lower dominance → higher altseason prob
        # Bonus: more altcoins bullish → higher prob
        base = max(0, 100 - dominance)  # 0–100
        if alt_total > 0:
            pct_bullish = (alt_bullish / alt_total) * 100
            prob = int((base * 0.4 + pct_bullish * 0.6))
        else:
            prob = int(base * 0.5)
        prob = max(0, min(100, prob))
        return {"altseason_probability": prob}
    except Exception as e:
        logging.debug("altseason_model error: %s", e)
        return {"altseason_probability": 0}
