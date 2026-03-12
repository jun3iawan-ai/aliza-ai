import requests

STABLECOIN_API = "https://stablecoins.llama.fi/stablecoins"


# =========================
# STABLECOIN INFLOW
# =========================

def stablecoin_inflow():

    try:

        res = requests.get(STABLECOIN_API, timeout=10)

        if res.status_code != 200:
            return "UNKNOWN"

        data = res.json()

        coins = data.get("peggedAssets")

        if not coins:
            return "UNKNOWN"

        total_marketcap = 0

        for coin in coins:

            marketcap = coin.get("circulating", {}).get("peggedUSD")

            if marketcap:
                total_marketcap += marketcap

        total_billion = total_marketcap / 1_000_000_000

        if total_billion > 150:
            return "HIGH INFLOW"

        if total_billion > 100:
            return "NORMAL"

        return "LOW"

    except Exception as e:

        print("stablecoin inflow error:", e)

        return "UNKNOWN"


# =========================
# SMART MONEY SCORE
# =========================

def smart_money_score(whale_level, funding_status, cycle):

    score = 0

    if whale_level in ["HIGH", "EXTREME"]:
        score += 2

    if funding_status == "SHORT OVERCROWDED":
        score += 2

    if cycle == "ACCUMULATION":
        score += 1

    if score >= 4:
        return "STRONG BUY"

    if score >= 2:
        return "BUY"

    if score == 1:
        return "NEUTRAL"

    return "WEAK"