import requests
from datetime import datetime

HEADERS = {"User-Agent": "AlizaAI Radar"}

# Whale transaction detector
BLOCKCHAIN_LARGE_TX = (
    "https://api.blockchair.com/bitcoin/transactions"
    "?q=value>500000000000&limit=5"
)


def get_large_transactions():
    """
    Ambil transaksi BTC besar sebagai indikator whale activity
    """

    try:

        res = requests.get(
            BLOCKCHAIN_LARGE_TX,
            headers=HEADERS,
            timeout=10
        )

        if res.status_code != 200:
            return []

        data = res.json()

        txs = data.get("data", [])

        whales = []

        for tx in txs:

            whales.append({
                "hash": tx.get("hash"),
                "value_satoshi": tx.get("value")
            })

        return whales

    except Exception as e:

        print("whale error:", e)

        return []


def estimate_risk(fear_greed, dominance):
    """
    Model sederhana crash risk estimation
    """

    risk = 0

    if fear_greed is not None and fear_greed < 20:
        risk += 2

    if dominance is not None and dominance > 55:
        risk += 1

    if risk >= 3:
        level = "HIGH"
    elif risk == 2:
        level = "MEDIUM"
    else:
        level = "LOW"

    probability = min(90, 40 + risk * 20)

    return {
        "risk_level": level,
        "crash_probability": probability
    }


def market_radar(fear_greed, dominance):

    whales = get_large_transactions()

    risk = estimate_risk(fear_greed, dominance)

    return {

        "whale_transactions": len(whales),

        "risk_level": risk["risk_level"],

        "crash_probability": risk["crash_probability"],

        "timestamp": datetime.utcnow().isoformat()

    }