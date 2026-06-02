"""
ALIZA WHALE FLOW ANALYZER

Analisis tekanan whale (buying/selling) dari market_data.
Menggunakan whale_activity, liquidation_risk, open_interest_level.
Hanya menggunakan data snapshot; tidak ada API call.
"""

import logging


def analyze_whale_flow(market_data):
    """
    Analisis whale flow dari market_data (biasanya BTC).

    Input: market_data dari snapshot.
    Gunakan: whale_activity, liquidation_risk, open_interest_level.

    Return: {"whale_pressure": "BUYING" | "SELLING" | "NEUTRAL"}
    """
    try:
        if not market_data or not isinstance(market_data, dict):
            return {"whale_pressure": "NEUTRAL"}

        whale = (market_data.get("whale_activity") or "").strip().upper()
        liquidation = (market_data.get("liquidation_risk") or "").strip().upper()
        oi = (market_data.get("open_interest_level") or "").strip().upper()

        # High liquidation risk → selling pressure
        if liquidation in ("HIGH", "EXTREME"):
            return {"whale_pressure": "SELLING"}

        # High whale activity + high OI → often accumulation (buying)
        if whale in ("HIGH", "EXTREME") and oi in ("HIGH", "RISING"):
            return {"whale_pressure": "BUYING"}

        if whale in ("HIGH", "EXTREME"):
            return {"whale_pressure": "BUYING"}

        if liquidation in ("MEDIUM", "ELEVATED"):
            return {"whale_pressure": "SELLING"}

        return {"whale_pressure": "NEUTRAL"}
    except Exception as e:
        logging.debug("whale_flow_analyzer error: %s", e)
        return {"whale_pressure": "NEUTRAL"}
