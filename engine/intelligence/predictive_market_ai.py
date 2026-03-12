"""
ALIZA PREDICTIVE MARKET AI

Menghitung probabilitas pergerakan market (breakout, reversal, crash)
dari data BTC cache dan memformat laporan untuk Telegram.
"""

from engine.utils.market_cache import get_market_data


def calculate_market_predictions():
    """
    Ambil data BTC dari cache, hitung:
    - Breakout Probability (max 100)
    - Reversal Probability (max 100)
    - Crash Probability (max 100)
    Return dict dengan skor dan konteks (trend, fear_greed, market_risk) untuk report.
    """
    result = {
        "breakout_probability": 0,
        "reversal_probability": 0,
        "crash_probability": 0,
        "trend": None,
        "fear_greed": None,
        "market_risk_score": None,
    }

    btc = get_market_data("BTC")
    if not btc or btc.get("error"):
        return result

    trend = btc.get("trend")
    rsi = btc.get("rsi")
    fear_greed = btc.get("fear_greed")
    whale_activity = btc.get("whale_activity")
    stablecoin_flow = btc.get("stablecoin_flow")
    market_risk_score = btc.get("market_risk_score")
    liquidation_risk = btc.get("liquidation_risk")

    result["trend"] = trend
    result["fear_greed"] = fear_greed
    result["market_risk_score"] = market_risk_score

    # -------------------------
    # BREAKOUT PROBABILITY
    # -------------------------
    breakout = 0
    if trend == "BULLISH":
        breakout += 30
    if rsi is not None and rsi > 55:
        breakout += 20
    if whale_activity in ("HIGH", "EXTREME"):
        breakout += 20
    if stablecoin_flow == "HIGH INFLOW":
        breakout += 30
    result["breakout_probability"] = min(breakout, 100)

    # -------------------------
    # REVERSAL PROBABILITY
    # -------------------------
    reversal = 0
    if rsi is not None and rsi < 30:
        reversal += 40
    if fear_greed is not None and fear_greed < 20:
        reversal += 30
    if whale_activity in ("HIGH", "EXTREME"):
        reversal += 30
    result["reversal_probability"] = min(reversal, 100)

    # -------------------------
    # CRASH PROBABILITY
    # -------------------------
    crash = 0
    if market_risk_score == "HIGH":
        crash += 40
    if liquidation_risk == "HIGH":
        crash += 30
    if whale_activity == "EXTREME":
        crash += 30
    result["crash_probability"] = min(crash, 100)

    return result


def format_prediction_report(data):
    """
    Format laporan Predictive Market AI untuk Telegram (Bahasa Indonesia).
    """
    if not data:
        return "Data prediksi tidak tersedia."

    breakout = data.get("breakout_probability", 0)
    reversal = data.get("reversal_probability", 0)
    crash = data.get("crash_probability", 0)
    trend = data.get("trend")
    fear = data.get("fear_greed")
    risk = data.get("market_risk_score")

    trend_str = trend if trend else "—"
    fear_str = fear if fear is not None else "—"
    risk_str = risk if risk else "—"

    message = (
        "🔮 ALIZA PREDICTIVE MARKET AI\n\n"
        f"Breakout Probability : {breakout}%\n"
        f"Reversal Probability : {reversal}%\n"
        f"Crash Probability : {crash}%\n\n"
        "Market Context\n"
        f"BTC Trend : {trend_str}\n"
        f"Fear & Greed : {fear_str}\n"
        f"Market Risk : {risk_str}"
    )
    return message
