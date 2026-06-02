"""
ALIZA PROBABILITY ENGINE

Mengonversi bullish/bearish score menjadi probabilitas 0–100%.
"""

import logging


def calculate_probabilities(bullish_score, bearish_score):
    """
    total = bullish_score + bearish_score
    Jika total == 0 → return 50 / 50
    Else:
      bullish_probability = int((bullish_score / total) * 100)
      bearish_probability = 100 - bullish_probability

    Return: {"bullish_probability": int, "bearish_probability": int}
    """
    try:
        b = int(bullish_score) if bullish_score is not None else 0
        s = int(bearish_score) if bearish_score is not None else 0
        b = max(0, b)
        s = max(0, s)
        total = b + s
        if total == 0:
            return {"bullish_probability": 50, "bearish_probability": 50}
        bullish_probability = int((b / total) * 100)
        bearish_probability = 100 - bullish_probability
        # Cap: hindari output 100% / 0%
        bullish_probability = min(bullish_probability, 85)
        bearish_probability = max(15, 100 - bullish_probability)
        if bearish_probability > 85:
            bearish_probability = 85
            bullish_probability = 15
        return {
            "bullish_probability": min(100, max(0, bullish_probability)),
            "bearish_probability": min(100, max(0, bearish_probability)),
        }
    except Exception as e:
        logging.debug("probability_engine: %s", e)
        return {"bullish_probability": 50, "bearish_probability": 50}
