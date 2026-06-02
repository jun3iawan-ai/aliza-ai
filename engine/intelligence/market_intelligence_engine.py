"""
ALIZA MARKET INTELLIGENCE ENGINE

Menggabungkan regime, altseason probability, dan whale flow dari snapshot.
Layer tambahan; tidak mengubah data contract atau pipeline.
"""

import logging

try:
    from engine.intelligence.market_regime_detector import detect_market_regime
except ImportError:
    detect_market_regime = None

try:
    from engine.intelligence.altseason_model import calculate_altseason_probability
except ImportError:
    calculate_altseason_probability = None

try:
    from engine.intelligence.whale_flow_analyzer import analyze_whale_flow
except ImportError:
    analyze_whale_flow = None


def generate_market_intelligence(snapshot):
    """
    Generate market intelligence dari snapshot.

    Input: snapshot = dict dengan "data" (symbol -> market_data).
    Ambil BTC data, panggil detect_market_regime, calculate_altseason_probability,
    analyze_whale_flow; gabungkan hasil.

    Return: {
        "market_regime": str,
        "altseason_probability": int,
        "whale_pressure": str,
    }
    """
    result = {
        "market_regime": "UNKNOWN",
        "altseason_probability": 0,
        "whale_pressure": "NEUTRAL",
    }
    try:
        data = snapshot.get("data") or {}
        if not data:
            return result

        btc_data = data.get("BTC")

        if detect_market_regime and btc_data:
            regime_out = detect_market_regime(btc_data)
            result["market_regime"] = regime_out.get("market_regime", "UNKNOWN")

        if calculate_altseason_probability:
            prob_out = calculate_altseason_probability(data)
            result["altseason_probability"] = prob_out.get("altseason_probability", 0)

        if analyze_whale_flow and btc_data:
            flow_out = analyze_whale_flow(btc_data)
            result["whale_pressure"] = flow_out.get("whale_pressure", "NEUTRAL")

        return result
    except Exception as e:
        logging.warning("market_intelligence_engine error: %s", e)
        return result
