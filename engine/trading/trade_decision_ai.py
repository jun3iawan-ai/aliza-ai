"""
ALIZA TRADE DECISION AI

Menilai kualitas setiap trade (score + status) berdasarkan RR, confidence,
trend alignment, market risk, dan whale activity sebelum dikirim ke Telegram.
"""

from engine.utils.market_cache import get_market_data


def evaluate_trade(signal):
    """
    Evaluasi signal trade: hitung score dan tentukan status.
    signal: dict dengan coin, setup, entry, sl, tp1, tp2, rr, confidence.
    Return: {"score": int, "status": str}
    """
    if not signal:
        return {"score": 0, "status": "AVOID"}

    score = 0

    rr = signal.get("rr")
    confidence = signal.get("confidence")
    setup = signal.get("setup") or ""
    coin = signal.get("coin")

    # -------------------------
    # DATA MARKET
    # -------------------------
    trend = None
    whale_activity = None
    market_risk_score = None

    if coin:
        try:
            market = get_market_data(coin)
            if market and not market.get("error"):
                trend = market.get("trend")
                whale_activity = market.get("whale_activity")
                market_risk_score = market.get("market_risk_score")
        except Exception:
            pass

    # -------------------------
    # RISK REWARD
    # -------------------------
    if rr is not None:
        if rr >= 3:
            score += 30
        elif rr >= 2:
            score += 20
        elif rr >= 1.5:
            score += 10

    # -------------------------
    # CONFIDENCE
    # -------------------------
    if confidence is not None:
        if confidence >= 80:
            score += 25
        elif confidence >= 70:
            score += 15
        elif confidence >= 60:
            score += 10

    # -------------------------
    # TREND ALIGNMENT
    # -------------------------
    if "SHORT" in setup and trend == "BEARISH":
        score += 20
    if "LONG" in setup and trend == "BULLISH":
        score += 20

    # -------------------------
    # MARKET RISK
    # -------------------------
    if market_risk_score == "HIGH":
        score -= 20

    # -------------------------
    # WHALE ACTIVITY
    # -------------------------
    if whale_activity in ("HIGH", "EXTREME"):
        score += 15

    # -------------------------
    # STATUS
    # -------------------------
    score = max(0, min(score, 100))

    if score >= 80:
        status = "HIGH QUALITY TRADE"
    elif score >= 65:
        status = "GOOD TRADE"
    elif score >= 50:
        status = "MODERATE"
    else:
        status = "AVOID"

    return {"score": score, "status": status}
