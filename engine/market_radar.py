import requests
from datetime import datetime

from engine.crypto_intelligence import (
    get_funding_rate,
    analyze_funding,
    altseason_index,
    altseason_status
)

from engine.smart_money_tracker import (
    stablecoin_inflow,
    smart_money_score
)

from engine.liquidation_monitor import (
    get_open_interest,
    analyze_open_interest,
    liquidation_risk
)

from engine.market_ai_predictor import (
    market_phase,
    bull_probability,
    market_risk_score
)

HEADERS = {"User-Agent": "AlizaAI Radar"}

BLOCKCHAIN_TX_API = (
    "https://api.blockchair.com/bitcoin/transactions"
    "?q=value>300000000000&limit=20"
)

# =========================
# FETCH WHALE TRANSACTIONS
# =========================

def get_large_transactions():

    try:

        res = requests.get(
            BLOCKCHAIN_TX_API,
            headers=HEADERS,
            timeout=10
        )

        if res.status_code != 200:
            return []

        data = res.json()

        txs = data.get("data", [])

        whales = []

        for tx in txs:

            value_btc = tx.get("value", 0) / 100000000

            whales.append({
                "hash": tx.get("hash"),
                "value_btc": round(value_btc, 2)
            })

        return whales

    except Exception as e:

        print("whale fetch error:", e)

        return []


# =========================
# WHALE INTENSITY
# =========================

def whale_intensity(whales):

    count = len(whales)

    if count >= 10:
        return "EXTREME"

    if count >= 5:
        return "HIGH"

    if count >= 2:
        return "MEDIUM"

    return "LOW"


# =========================
# BTC CYCLE DETECTOR
# =========================

def detect_btc_cycle(fear, dominance):

    if fear is None:
        return "UNKNOWN"

    if fear < 20 and dominance > 55:
        return "ACCUMULATION"

    if fear > 70:
        return "EUPHORIA"

    if fear > 50:
        return "BULL"

    return "BEAR"


# =========================
# CRASH RISK MODEL
# =========================

def crash_risk_model(fear, dominance):

    risk = 0

    if fear and fear < 20:
        risk += 2

    if dominance and dominance > 55:
        risk += 1

    if risk >= 3:
        return "HIGH", 80

    if risk == 2:
        return "MEDIUM", 60

    return "LOW", 30


# =========================
# MAIN RADAR
# =========================

def market_radar(fear, dominance):

    whales = get_large_transactions()

    whale_level = whale_intensity(whales)

    cycle = detect_btc_cycle(fear, dominance)

    crash_level, crash_probability = crash_risk_model(
        fear,
        dominance
    )

    # =========================
    # CRYPTO INTELLIGENCE
    # =========================

    funding_rate = get_funding_rate()

    funding_status = analyze_funding(funding_rate)

    alt_index = altseason_index(dominance)

    alt_status = altseason_status(alt_index)

    # =========================
    # SMART MONEY TRACKER
    # =========================

    stablecoin_flow = stablecoin_inflow()

    smart_money = smart_money_score(
        whale_level,
        funding_status,
        cycle
    )

    # =========================
    # LIQUIDATION MONITOR
    # =========================

    open_interest = get_open_interest()

    oi_level = analyze_open_interest(open_interest)

    liquidation_signal = liquidation_risk(
        oi_level,
        funding_status
    )

    # =========================
    # AI MARKET PREDICTOR
    # =========================

    phase_prediction = market_phase(
        cycle,
        funding_status,
        smart_money
    )

    bull_prob = bull_probability(
        cycle,
        whale_level,
        smart_money,
        stablecoin_flow
    )

    risk_score = market_risk_score(
        crash_probability,
        liquidation_signal
    )

    # =========================
    # SIGNAL LOGIC
    # =========================

    bottom_signal = True if cycle == "ACCUMULATION" else False

    return {

        "cycle_phase": cycle,

        "bottom_signal": bottom_signal,

        "altseason": alt_status,

        "altseason_index": alt_index,

        "funding_rate": funding_rate,

        "funding_status": funding_status,

        "whale_activity": whale_level,

        "whale_transactions": len(whales),

        "stablecoin_flow": stablecoin_flow,

        "smart_money_signal": smart_money,

        "open_interest": open_interest,

        "open_interest_level": oi_level,

        "liquidation_risk": liquidation_signal,

        "risk_level": crash_level,

        "crash_probability": crash_probability,

        "market_phase_prediction": phase_prediction,

        "bull_probability": bull_prob,

        "market_risk_score": risk_score,

        "timestamp": datetime.utcnow().isoformat()

    }