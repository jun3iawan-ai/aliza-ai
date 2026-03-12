from engine.market.market_analyzer import market_signal
from engine.market.market_universe import MAJOR_COINS

# memory agar tidak spam alert
CRASH_MEMORY = {}


def calculate_crash_probability(data):

    score = 0

    if data.get("market_risk_score") == "HIGH":
        score += 30

    if data.get("stablecoin_flow") == "HIGH OUTFLOW":
        score += 20

    if data.get("funding_status") == "EXTREME":
        score += 15

    if data.get("liquidation_risk") == "HIGH":
        score += 15

    if data.get("whale_activity") == "HIGH":
        score += 10

    if data.get("market_phase_prediction") == "DISTRIBUTION":
        score += 10

    return score


def detect_market_crash():

    alerts = []

    for coin in MAJOR_COINS:

        data = market_signal(coin)

        if not data or "error" in data:
            continue

        probability = calculate_crash_probability(data)

        # trigger jika probability tinggi
        if probability < 60:
            continue

        last_alert = CRASH_MEMORY.get(coin)

        # smart memory
        if last_alert == probability:
            continue

        CRASH_MEMORY[coin] = probability

        message = (
            "🚨 POTENSI CRASH MARKET\n\n"
            f"Market : {coin}\n\n"
            f"Probabilitas Crash : {probability}%\n\n"
            f"Risk Score : {data.get('market_risk_score')}\n"
            f"Whale Activity : {data.get('whale_activity')}\n"
            f"Stablecoin Flow : {data.get('stablecoin_flow')}\n"
            f"Funding Status : {data.get('funding_status')}\n"
            f"Liquidation Risk : {data.get('liquidation_risk')}\n"
        )

        alerts.append(message)

    return alerts