"""
ALIZA PREDICTION ENGINE

Menghasilkan prediksi arah market (bullish/bearish probability, bias, confidence)
dari snapshot. Hanya membaca snapshot; tidak mengubah pipeline.
"""

import logging

try:
    from engine.prediction.bias_score_engine import calculate_market_bias
except ImportError:
    calculate_market_bias = None

try:
    from engine.prediction.probability_engine import calculate_probabilities
except ImportError:
    calculate_probabilities = None


def generate_market_prediction(snapshot):
    """
    1. Panggil calculate_market_bias(snapshot)
    2. Panggil calculate_probabilities(bullish_score, bearish_score)
    3. Bias: bullish_probability > bearish_probability → BULLISH, else → BEARISH
    4. Confidence: > 70 → HIGH, 55–70 → MEDIUM, < 55 → LOW

    Return: {
        "bullish_probability": int,
        "bearish_probability": int,
        "bias": str,
        "confidence": str,
    }
    """
    result = {
        "bullish_probability": 50,
        "bearish_probability": 50,
        "bias": "NEUTRAL",
        "confidence": "LOW",
    }
    try:
        if calculate_market_bias is None or calculate_probabilities is None:
            return result

        bias_out = calculate_market_bias(snapshot)
        bull_s = bias_out.get("bullish_score", 0)
        bear_s = bias_out.get("bearish_score", 0)

        prob_out = calculate_probabilities(bull_s, bear_s)
        bull_p = prob_out.get("bullish_probability", 50)
        bear_p = prob_out.get("bearish_probability", 50)

        result["bullish_probability"] = bull_p
        result["bearish_probability"] = bear_p

        if bull_p > bear_p:
            result["bias"] = "BULLISH"
        else:
            result["bias"] = "BEARISH"

        if bull_p > 70 or bear_p > 70:
            result["confidence"] = "HIGH"
        elif bull_p > 55 or bear_p > 55:
            result["confidence"] = "MEDIUM"
        else:
            result["confidence"] = "LOW"

        return result
    except Exception as e:
        logging.debug("prediction_engine: %s", e)
        return result
