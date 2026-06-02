"""
ALIZA LIQUIDATION CASCADE DETECTOR

Mendeteksi kemungkinan Long Liquidation atau Short Squeeze menggunakan
data dari market snapshot (tanpa panggilan API langsung).
"""

import logging


def detect_liquidation_cascade(coin, market_data):
    """
    Analisis sinyal liquidation cascade: long liquidation atau short squeeze.

    Input:
      - coin: nama coin (untuk logging)
      - market_data: snapshot data untuk coin tersebut

    Field: trend, rsi, market_risk_score

    Aturan:
      LONG LIQUIDATION: trend == "BEARISH", rsi <= 35, market_risk_score == "HIGH"
      SHORT SQUEEZE:    trend == "BULLISH", rsi >= 65, market_risk_score == "HIGH"

    Return:
      - LONG_LIQUIDATION: {"liquidation_signal": True, "type": "LONG_LIQUIDATION"}
      - SHORT_SQUEEZE:    {"liquidation_signal": True, "type": "SHORT_SQUEEZE"}
      - Tidak terpenuhi:  {"liquidation_signal": False}
    """
    try:
        if not market_data or not isinstance(market_data, dict):
            logging.debug("Liquidation detector %s signal=%s", coin, False)
            return {"liquidation_signal": False}

        trend = (market_data.get("trend") or "").strip().upper()
        market_risk = (market_data.get("market_risk_score") or "").strip().upper()
        rsi_raw = market_data.get("rsi")

        try:
            rsi_val = float(rsi_raw) if rsi_raw is not None else None
        except (TypeError, ValueError):
            rsi_val = None

        high_risk = market_risk == "HIGH"

        # LONG LIQUIDATION
        if trend == "BEARISH" and rsi_val is not None and rsi_val <= 35 and high_risk:
            liq_signal = True
            logging.debug("Liquidation detector %s signal=%s", coin, liq_signal)
            return {
                "liquidation_signal": True,
                "type": "LONG_LIQUIDATION",
            }

        # SHORT SQUEEZE
        if trend == "BULLISH" and rsi_val is not None and rsi_val >= 65 and high_risk:
            liq_signal = True
            logging.debug("Liquidation detector %s signal=%s", coin, liq_signal)
            return {
                "liquidation_signal": True,
                "type": "SHORT_SQUEEZE",
            }

        liq_signal = False
        logging.debug("Liquidation detector %s signal=%s", coin, liq_signal)
        return {"liquidation_signal": False}
    except Exception as e:
        logging.debug("liquidation_detector error %s: %s", coin, e)
        return {"liquidation_signal": False}
