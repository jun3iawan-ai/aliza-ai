"""
ALIZA QUANT MARKET MODEL

Menggabungkan analisis market (BTC, prediksi) menjadi satu skor market
dan bias (BULLISH / NEUTRAL / BEARISH / HIGH RISK).
"""

from engine.utils.market_cache import get_market_data
from engine.intelligence.predictive_market_ai import calculate_market_predictions


def calculate_market_score():
    """
    Gabungkan data BTC dan prediksi market menjadi skor 0-100 dan market_bias.
    Return dict: market_score, market_bias, plus konteks (trend, fear_greed, whale_activity, market_risk_score).
    """
    result = {
        "market_score": 50,
        "market_bias": "NEUTRAL",
        "trend": None,
        "fear_greed": None,
        "whale_activity": None,
        "market_risk_score": None,
    }

    btc = get_market_data("BTC")
    if not btc or btc.get("error"):
        result["market_score"] = 50
        result["market_bias"] = "NEUTRAL"
        return result

    trend = btc.get("trend")
    fear_greed = btc.get("fear_greed")
    whale_activity = btc.get("whale_activity")
    market_risk_score = btc.get("market_risk_score")
    liquidation_risk = btc.get("liquidation_risk")

    result["trend"] = trend
    result["fear_greed"] = fear_greed
    result["whale_activity"] = whale_activity
    result["market_risk_score"] = market_risk_score

    predictions = calculate_market_predictions()
    breakout_probability = predictions.get("breakout_probability", 0)
    crash_probability = predictions.get("crash_probability", 0)

    score = 50

    # TREND
    if trend == "BULLISH":
        score += 25
    elif trend == "BEARISH":
        score -= 25

    # FEAR GREED
    if fear_greed is not None:
        if fear_greed < 20:
            score += 20
        elif fear_greed > 80:
            score -= 20

    # WHALE
    if whale_activity == "HIGH":
        score += 10
    elif whale_activity == "EXTREME":
        score += 15

    # MARKET RISK
    if market_risk_score == "HIGH":
        score -= 20
    if liquidation_risk == "HIGH":
        score -= 15

    # PREDICTION
    if breakout_probability > 60:
        score += 20
    if crash_probability > 50:
        score -= 20

    # LIMIT SCORE
    score = max(0, min(100, score))
    result["market_score"] = score

    # MARKET BIAS
    if score >= 65:
        result["market_bias"] = "BULLISH"
    elif score >= 50:
        result["market_bias"] = "NEUTRAL"
    elif score >= 35:
        result["market_bias"] = "BEARISH"
    else:
        result["market_bias"] = "HIGH RISK"

    return result


def format_quant_report(data):
    """
    Format laporan Quant Market Model untuk Telegram (Bahasa Indonesia).
    """
    if not data:
        return "Data quant tidak tersedia."

    score = data.get("market_score", 0)
    bias = data.get("market_bias", "—")
    trend = data.get("trend")
    fear = data.get("fear_greed")
    whale = data.get("whale_activity")
    risk = data.get("market_risk_score")

    trend_str = trend if trend else "—"
    fear_str = fear if fear is not None else "—"
    whale_str = whale if whale else "—"
    risk_str = risk if risk else "—"

    message = (
        "🧬 ALIZA QUANT MARKET MODEL\n\n"
        f"Market Score : {score} / 100\n\n"
        f"Market Bias : {bias}\n\n"
        "Market Context\n"
        f"BTC Trend : {trend_str}\n"
        f"Fear & Greed : {fear_str}\n"
        f"Whale Activity : {whale_str}\n"
        f"Market Risk : {risk_str}"
    )
    return message
