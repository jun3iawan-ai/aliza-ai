"""
ALIZA WHALE ACCUMULATION DETECTOR

Mendeteksi kemungkinan whale sedang mengakumulasi aset sebelum pump
menggunakan data dari market snapshot (tanpa panggilan API langsung).
"""

import logging


def detect_whale_accumulation(coin, market_data):
    """
    Analisis sinyal whale accumulation: aktivitas whale + market sideways + RSI recovering.

    Input:
      - coin: nama coin (untuk logging)
      - market_data: snapshot data untuk coin tersebut

    Field: trend, rsi, whale_activity

    Aturan:
      1) Whale Activity   : whale_activity in ["HIGH", "EXTREME"]
      2) Market Sideways  : trend == "SIDEWAYS"
      3) RSI Recovering   : 45 <= rsi <= 60

    Jika semua terpenuhi: return {"whale_accumulation": True, "confidence": "MEDIUM"}
    Jika tidak: return {"whale_accumulation": False}
    """
    try:
        if not market_data or not isinstance(market_data, dict):
            logging.debug("Whale accumulation detector %s signal=%s", coin, False)
            return {"whale_accumulation": False}

        trend = (market_data.get("trend") or "").strip().upper()
        whale_activity = market_data.get("whale_activity")
        rsi_raw = market_data.get("rsi")

        try:
            rsi_val = float(rsi_raw) if rsi_raw is not None else None
        except (TypeError, ValueError):
            rsi_val = None

        whale_ok = str(whale_activity).upper() in ("HIGH", "EXTREME")
        sideways = trend == "SIDEWAYS"
        rsi_recovering = rsi_val is not None and 45 <= rsi_val <= 60

        whale_signal = bool(whale_ok and sideways and rsi_recovering)
        logging.debug("Whale accumulation detector %s signal=%s", coin, whale_signal)

        if whale_signal:
            return {
                "whale_accumulation": True,
                "confidence": "MEDIUM",
            }
        return {"whale_accumulation": False}
    except Exception as e:
        logging.debug("whale_accumulation_detector error %s: %s", coin, e)
        return {"whale_accumulation": False}
