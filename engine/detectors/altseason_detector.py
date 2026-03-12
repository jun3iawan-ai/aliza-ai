from engine.market.market_analyzer import market_signal
from engine.market.market_universe import MAJOR_COINS

# =========================
# MEMORY
# =========================

ALTSEASON_MEMORY = None


def detect_altseason():

    global ALTSEASON_MEMORY

    alerts = []

    btc_data = market_signal("BTC")

    if not btc_data or "error" in btc_data:
        return alerts

    dominance = btc_data.get("dominance")
    cycle = btc_data.get("cycle_phase")
    prediction = btc_data.get("market_phase_prediction")
    stable = btc_data.get("stablecoin_flow")

    score = 0

    # =========================
    # BTC DOMINANCE
    # =========================

    if dominance < 52:
        score += 40

    elif dominance < 55:
        score += 25

    # =========================
    # MARKET PHASE
    # =========================

    if prediction == "BULLISH":
        score += 25

    if cycle == "EXPANSION":
        score += 20

    # =========================
    # LIQUIDITY
    # =========================

    if stable == "HIGH INFLOW":
        score += 15

    # =========================
    # ALTSEASON PROBABILITY
    # =========================

    probability = min(score, 100)

    if probability < 60:
        return alerts

    # =========================
    # MEMORY CHECK
    # =========================

    if ALTSEASON_MEMORY == probability:
        return alerts

    ALTSEASON_MEMORY = probability

    message = (
        "🔥 ALTSEASON SIGNAL\n\n"
        f"Probabilitas Altseason : {probability}%\n\n"
        f"BTC Dominance : {dominance}%\n"
        f"Market Phase : {prediction}\n"
        f"Cycle Phase : {cycle}\n"
        f"Stablecoin Flow : {stable}\n\n"
        "Potensi : Altcoin mulai outperform BTC"
    )

    alerts.append(message)

    return alerts