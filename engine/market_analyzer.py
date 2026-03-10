import requests
import numpy as np
import time
from datetime import datetime
from engine.trading_brain import TradingBrain
from engine.market_radar import market_radar

COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
BTC_DATA_URL = "https://api.coingecko.com/api/v3/coins/bitcoin"
GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
FEAR_URL = "https://api.alternative.me/fng/"

HEADERS = {"User-Agent": "Mozilla/5.0"}

# =========================
# CACHE
# =========================

last_prices = None
last_price_update = 0

last_dominance = None
last_dom_update = 0

last_fear = None
last_fear_update = 0


# =========================
# BTC PRICE
# =========================

def get_btc_market_chart(days=200):

    global last_prices, last_price_update

    if last_prices is not None and time.time() - last_price_update < 60:
        return last_prices

    try:

        params = {"vs_currency": "usd", "days": days}

        res = requests.get(
            COINGECKO_URL,
            params=params,
            headers=HEADERS,
            timeout=10
        )

        if res.status_code != 200:
            return last_prices or []

        data = res.json()

        prices = [p[1] for p in data.get("prices", [])]

        last_prices = prices
        last_price_update = time.time()

        return prices

    except Exception as e:

        print("BTC chart error:", e)

        return last_prices or []


# =========================
# FEAR & GREED
# =========================

def get_fear_greed():

    global last_fear, last_fear_update

    if last_fear is not None and time.time() - last_fear_update < 300:
        return last_fear

    try:

        res = requests.get(FEAR_URL, headers=HEADERS, timeout=10)

        if res.status_code != 200:
            return last_fear

        data = res.json()

        fear = int(data["data"][0]["value"])

        last_fear = fear
        last_fear_update = time.time()

        return fear

    except Exception as e:

        print("Fear & Greed error:", e)

        return last_fear


# =========================
# BTC DOMINANCE
# =========================

def get_btc_dominance():

    global last_dominance, last_dom_update

    if last_dominance is not None and time.time() - last_dom_update < 300:
        return last_dominance

    try:

        btc_res = requests.get(
            BTC_DATA_URL,
            headers=HEADERS,
            timeout=10
        )

        if btc_res.status_code != 200:
            return last_dominance

        btc_data = btc_res.json()

        btc_marketcap = btc_data["market_data"]["market_cap"]["usd"]

        global_res = requests.get(
            GLOBAL_URL,
            headers=HEADERS,
            timeout=10
        )

        if global_res.status_code != 200:
            return last_dominance

        global_data = global_res.json()

        total_marketcap = global_data["data"]["total_market_cap"]["usd"]

        dominance = (btc_marketcap / total_marketcap) * 100

        last_dominance = round(dominance, 2)
        last_dom_update = time.time()

        return last_dominance

    except Exception as e:

        print("Dominance error:", e)

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
# MAIN SIGNAL
# =========================

def btc_signal():

    prices = get_btc_market_chart()

    if not prices:
        return {"error": "unable to fetch btc data"}

    price = prices[-1]

    ma50 = moving_average(prices, 50)
    ma200 = moving_average(prices, 200)

    rsi = calculate_rsi(prices)

    fear = get_fear_greed()
    dominance = get_btc_dominance()

    # =========================
    # MARKET RADAR
    # =========================

    radar = market_radar(fear, dominance)

    support, resistance = calculate_support_resistance(prices)

    trend = "SIDEWAYS"

    if ma50 and ma200:
        trend = "BULLISH" if ma50 > ma200 else "BEARISH"

    # =========================
    # MARKET SCORE
    # =========================

    score = 0

    if rsi and rsi < 35:
        score += 25
    elif rsi and rsi > 70:
        score -= 25

    if ma200 and price < ma200:
        score += 25

    if fear and fear < 25:
        score += 25

    if trend == "BULLISH":
        score += 15
    elif trend == "BEARISH":
        score -= 35

    market_score = max(0, min(100, 50 + score))

    signal = "BUY" if market_score >= 70 else "SELL" if market_score <= 30 else "HOLD"

    # =========================
    # MARKET DATA OUTPUT
    # =========================

    market_data = {

        "price": round(price, 2),
        "rsi": round(rsi, 2) if rsi else None,
        "ma50": round(ma50, 2) if ma50 else None,
        "ma200": round(ma200, 2) if ma200 else None,

        "support": support,
        "resistance": resistance,

        "fear_greed": fear,
        "dominance": dominance,

        "trend": trend,

        "market_score": market_score,
        "signal": signal,

        # =================
        # RADAR DATA
        # =================

        "cycle_phase": radar.get("cycle_phase"),

        "funding_rate": radar.get("funding_rate"),
        "funding_status": radar.get("funding_status"),

        "whale_activity": radar.get("whale_activity"),
        "stablecoin_flow": radar.get("stablecoin_flow"),

        "smart_money_signal": radar.get("smart_money_signal"),

        "open_interest": radar.get("open_interest"),
        "open_interest_level": radar.get("open_interest_level"),

        "liquidation_risk": radar.get("liquidation_risk"),

        "market_phase_prediction": radar.get("market_phase_prediction"),
        "bull_probability": radar.get("bull_probability"),

        "market_risk_score": radar.get("market_risk_score"),

        "crash_probability": radar.get("crash_probability"),
        "crash_alert": radar.get("risk_level"),

        "timestamp": datetime.utcnow().isoformat()

    }

    brain = TradingBrain()
    trade_setup = brain.analyze(market_data)

    market_data["trade_setup"] = trade_setup

    return market_data