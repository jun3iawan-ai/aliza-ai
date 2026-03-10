import requests

# =========================
# STABLECOIN INFLOW
# =========================

STABLECOIN_API = "https://api.coingecko.com/api/v3/global"


def stablecoin_inflow():

    try:

        res = requests.get(STABLECOIN_API, timeout=10)

        data = res.json()

        market_cap = data["data"]["total_market_cap"]["usd"]

        if market_cap > 2000000000000:
            return "HIGH"

        if market_cap > 1500000000000:
            return "MEDIUM"

        return "LOW"

    except Exception as e:

        print("stablecoin inflow error:", e)

        return "UNKNOWN"


# =========================
# SMART MONEY SCORE
# =========================

def smart_money_score(whale_activity, funding_status, cycle_phase):

    score = 0

    if whale_activity in ["HIGH", "EXTREME"]:
        score += 2

    if funding_status == "LONG OVERCROWDED":
        score += 1

    if cycle_phase == "ACCUMULATION":
        score += 2

    if score >= 4:
        return "ACCUMULATION"

    if score >= 2:
        return "WATCH"

    return "NEUTRAL"