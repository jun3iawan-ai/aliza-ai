import time

from engine.market.market_analyzer import market_signal
from engine.market.market_universe import MAJOR_COINS


# =========================
# CACHE STORAGE
# =========================

CACHE = {}

CACHE_TIME = 60


# =========================
# GET MARKET DATA WITH CACHE
# =========================

def get_market_data(symbol):

    now = time.time()

    cached = CACHE.get(symbol)

    if cached:

        timestamp = cached["time"]

        if now - timestamp < CACHE_TIME:

            return cached["data"]

    # fetch new data

    data = market_signal(symbol)

    CACHE[symbol] = {
        "data": data,
        "time": now
    }

    return data


# =========================
# GET ALL MARKET DATA
# =========================

def get_all_market_data():

    results = {}

    for coin in MAJOR_COINS:

        results[coin] = get_market_data(coin)

    return results