"""
ALIZA ALTSEASON DETECTOR

Mendeteksi kemungkinan capital berpindah dari BTC ke altcoins menggunakan
data dari market snapshot (tanpa panggilan API langsung).
"""

import logging


def detect_altseason(coin, market_data, btc_data):
    """
    Analisis sinyal altseason: BTC sideways + altcoin bullish + momentum.

    Input:
      - coin: nama coin (untuk logging)
      - market_data: snapshot data untuk coin tersebut
      - btc_data: snapshot data untuk BTC

    Aturan:
      1) BTC SIDEWAYS   : btc_data["trend"] == "SIDEWAYS"
      2) ALTCOIN BULLISH: market_data["trend"] == "BULLISH"
      3) ALT MOMENTUM   : market_data["rsi"] >= 60

    Jika semua terpenuhi: return {"altseason_signal": True, "confidence": "MEDIUM"}
    Jika tidak: return {"altseason_signal": False}
    """
    try:
        if not market_data or not isinstance(market_data, dict):
            logging.debug("Altseason detector %s signal=%s", coin, False)
            return {"altseason_signal": False}

        trend = (market_data.get("trend") or "").strip().upper()
        rsi_raw = market_data.get("rsi")

        try:
            rsi_val = float(rsi_raw) if rsi_raw is not None else None
        except (TypeError, ValueError):
            rsi_val = None

        btc_trend = None
        if btc_data and isinstance(btc_data, dict):
            btc_trend = (btc_data.get("trend") or "").strip().upper()

        btc_sideways = btc_trend == "SIDEWAYS"
        alt_bullish = trend == "BULLISH"
        alt_momentum = rsi_val is not None and rsi_val >= 60

        altseason_signal = bool(btc_sideways and alt_bullish and alt_momentum)
        logging.debug("Altseason detector %s signal=%s", coin, altseason_signal)

        if altseason_signal:
            return {
                "altseason_signal": True,
                "confidence": "MEDIUM",
            }
        return {"altseason_signal": False}
    except Exception as e:
        logging.debug("altseason_detector error %s: %s", coin, e)
        return {"altseason_signal": False}
