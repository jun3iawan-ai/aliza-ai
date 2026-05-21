"""
Cache data market per symbol; get_all_market_data() untuk scan multi-coin.
Digunakan oleh opportunity_scanner saat snapshot sudah stale (>90s).
"""

import time

from engine.market_signal import generate_signal
from engine.market.market_universe import MAJOR_COINS

try:
    from engine.market.dynamic_universe import get_tradable_coins
except Exception:
    get_tradable_coins = None

CACHE = {}
CACHE_TIME = 180


def get_market_data(symbol):
    """Ambil data market untuk symbol (cache atau fetch)."""
    now = time.time()
    key = (symbol or "").upper()
    if key in CACHE:
        entry = CACHE[key]
        if now - entry.get("time", 0) < CACHE_TIME:
            return entry.get("data")
    try:
        data = generate_signal(key)
        CACHE[key] = {"data": data, "time": now}
        return data
    except Exception:
        return None


def get_all_market_data():
    """Dict symbol -> market_data untuk semua coin (tradable atau MAJOR_COINS)."""
    coins = get_tradable_coins() if get_tradable_coins else None
    if not coins:
        coins = list(MAJOR_COINS)
    out = {}
    for symbol in coins:
        data = get_market_data(symbol)
        if data:
            out[symbol] = data
    return out
