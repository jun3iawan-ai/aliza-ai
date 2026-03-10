import requests

# =========================
# FUNDING RATE
# =========================

FUNDING_API = "https://fapi.binance.com/fapi/v1/premiumIndex"


def get_funding_rate():

    try:

        res = requests.get(FUNDING_API, timeout=10)

        data = res.json()

        for item in data:

            if item["symbol"] == "BTCUSDT":

                rate = float(item["lastFundingRate"])

                return rate

        return None

    except Exception as e:

        print("funding rate error:", e)

        return None


# =========================
# FUNDING ANALYSIS
# =========================

def analyze_funding(rate):

    if rate is None:
        return "UNKNOWN"

    if rate > 0.05:
        return "LONG OVERCROWDED"

    if rate < -0.05:
        return "SHORT OVERCROWDED"

    return "NORMAL"


# =========================
# ALTSEASON INDEX
# =========================

def altseason_index(dominance):

    if dominance is None:
        return 0

    index = max(0, min(100, int((60 - dominance) * 5)))

    return index


# =========================
# ALTSEASON STATUS
# =========================

def altseason_status(index):

    if index > 75:
        return "ALTSEASON"

    if index > 50:
        return "ALT GROWTH"

    if index > 25:
        return "NEUTRAL"

    return "BTC DOMINANCE"