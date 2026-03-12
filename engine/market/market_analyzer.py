import requests
import numpy as np
import time
from datetime import datetime

from engine.brain.trading_brain import TradingBrain
from engine.market.market_radar import market_radar
from engine.market.market_universe import MAJOR_COINS

HEADERS = {"User-Agent": "AlizaAI"}

FEAR_URL = "https://api.alternative.me/fng/"
GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

# =========================
# COINGECKO COIN IDS
# =========================

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "TRX": "tron",
    "TON": "toncoin",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "APT": "aptos",
    "ATOM": "cosmos"
}

# =========================
# CACHE
# =========================

last_fear = None
last_fear_update = 0

last_dominance = None
last_dom_update = 0

# =========================
# MARKET CHART
# =========================

def get_coin_market_chart(symbol, days=200):

    coin_id = COINGECKO_IDS.get(symbol)

    if not coin_id:
        return []

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

    try:

        params = {
            "vs_currency": "usd",
            "days": days
        }

        res = requests.get(url, params=params, headers=HEADERS, timeout=10)

        if res.status_code != 200:
            return []

        data = res.json()

        prices = [p[1] for p in data.get("prices", [])]

        return prices

    except Exception as e:

        print(f"{symbol} chart error:", e)

        return []

# =========================
# FEAR & GREED
# =========================

def get_fear_greed():

    global last_fear, last_fear_update

    if last_fear and time.time() - last_fear_update < 300:
        return last_fear

    try:

        res = requests.get(FEAR_URL, timeout=10)

        if res.status_code != 200:
            return last_fear

        data = res.json()

        fear = int(data["data"][0]["value"])

        last_fear = fear
        last_fear_update = time.time()

        return fear

    except Exception:

        return last_fear

# =========================
# BTC DOMINANCE
# =========================

def get_btc_dominance():

    global last_dominance, last_dom_update

    if last_dominance and time.time() - last_dom_update < 300:
        return last_dominance

    try:

        res = requests.get(GLOBAL_URL, headers=HEADERS, timeout=10)

        if res.status_code != 200:
            return last_dominance

        data = res.json()

        dominance = data["data"]["market_cap_percentage"]["btc"]

        last_dominance = round(dominance, 2)
        last_dom_update = time.time()

        return last_dominance

    except Exception:

        return last_dominance

# =========================
# MOVING AVERAGE
# =========================

def moving_average(data, period):

    if len(data) < period:
        return None

    return float(np.mean(data[-period:]))

# =========================
# RSI
# =========================

def calculate_rsi(prices, period=14):

    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)

    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period

    if losses == 0:
        return 100

    rs = gains / losses

    return float(100 - (100 / (1 + rs)))

# =========================
# SUPPORT / RESISTANCE
# =========================

def calculate_support_resistance(prices):

    if len(prices) < 30:
        return None, None

    recent = prices[-30:]

    support = min(recent)
    resistance = max(recent)

    return round(support, 2), round(resistance, 2)

# =========================
# SINGLE MARKET ANALYSIS
# =========================

def market_signal(symbol="BTC"):

    symbol = symbol.upper()

    prices = get_coin_market_chart(symbol)

    if not prices:
        return {"error": "unable to fetch market data"}

    price = prices[-1]

    ma50 = moving_average(prices, 50)
    ma200 = moving_average(prices, 200)

    rsi = calculate_rsi(prices)

    support, resistance = calculate_support_resistance(prices)

    fear = get_fear_greed()
    dominance = get_btc_dominance()

    radar = market_radar(fear, dominance) if fear and dominance else {}

    trend = "SIDEWAYS"

    if ma50 and ma200:
        trend = "BULLISH" if ma50 > ma200 else "BEARISH"

    market_data = {

        "symbol": symbol,
        "price": round(price, 2),

        "trend": trend,
        "rsi": round(rsi, 2) if rsi else None,

        "support": support,
        "resistance": resistance,

        "fear_greed": fear,
        "dominance": dominance,

        "cycle_phase": radar.get("cycle_phase"),
        "funding_status": radar.get("funding_status"),
        "whale_activity": radar.get("whale_activity"),
        "stablecoin_flow": radar.get("stablecoin_flow"),
        "open_interest_level": radar.get("open_interest_level"),
        "liquidation_risk": radar.get("liquidation_risk"),
        "market_phase_prediction": radar.get("market_phase_prediction"),
        "bull_probability": radar.get("bull_probability"),
        "market_risk_score": radar.get("market_risk_score"),

        "timestamp": datetime.utcnow().isoformat()

    }

    brain = TradingBrain()
    trade_setup = brain.analyze(market_data)

    market_data["trade_setup"] = trade_setup

    return market_data

# =========================
# TREND ANALYZER
# =========================

def analyze_trend(change):

    if change is None:
        return "UNKNOWN"

    if change > 3:
        return "BULLISH"

    if change < -3:
        return "BEARISH"

    return "SIDEWAYS"

# =========================
# MULTI MARKET SCAN
# =========================

def multi_market_scan():

    results = {}

    try:

        ids = ",".join(COINGECKO_IDS.values())

        url = "https://api.coingecko.com/api/v3/simple/price"

        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }

        res = requests.get(url, params=params, headers=HEADERS, timeout=10)

        if res.status_code != 200:
            return {coin: "ERROR" for coin in MAJOR_COINS}

        data = res.json()

        for symbol in MAJOR_COINS:

            coin_id = COINGECKO_IDS.get(symbol)

            if not coin_id:
                results[symbol] = "UNKNOWN"
                continue

            coin_data = data.get(coin_id)

            if not coin_data:
                results[symbol] = "UNKNOWN"
                continue

            change = coin_data.get("usd_24h_change")

            results[symbol] = analyze_trend(change)

    except Exception as e:

        print("Market scan error:", e)

        results = {coin: "ERROR" for coin in MAJOR_COINS}

    return results


# =========================
# BTC SIGNAL WRAPPER
# =========================

def btc_signal():
    return market_signal("BTC")