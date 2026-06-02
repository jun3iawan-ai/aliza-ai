"""
Dynamic Market Universe — AlizaAI
Hybrid universe: CORE_COINS (tetap) + dynamic opportunity coins.
Dynamic: scan top 200, filter liquidity (vol > 20M), rank volatility, rank trend strength → top 10.
Cache diperbarui setiap 24 jam.
"""

import time
import logging
import requests
import numpy as np

from engine.market.market_universe import CORE_COINS, MAJOR_COINS

# Fallback when CoinGecko fails or returns empty; always return at least these
FALLBACK_COINS = list(MAJOR_COINS) if MAJOR_COINS else list(CORE_COINS)

MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

MIN_VOLUME_24H = 20_000_000   # 20M USD
MIN_MARKET_CAP = 200_000_000  # 200M USD
TOP_BY_VOLATILITY = 40
TOP_BY_TREND = 10   # top 10 dynamic opportunity coins
UNIVERSE_CACHE_SEC = 24 * 3600  # 24 jam
MAX_RETRIES = 3
BACKOFF = [1, 2, 4]

HEADERS = {"User-Agent": "AlizaAI"}
TIMEOUT = 15
BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"
MIN_OHLC_POINTS = 50  # minimal data OHLC untuk ranking

# Cache: dynamic-only list (top 10), map symbol -> coin_id, last refresh time
_dynamic_coins = []
_coin_id_map = {}
_last_refresh = 0
_last_successful_coins = None

# TTL cache: skip CoinGecko if recent result still valid
_universe_cache = None
_cache_timestamp = 0
CACHE_TTL = 1800  # 30 minutes


def _safe_get_json(url, params=None, timeout=TIMEOUT):
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.warning("dynamic_universe request failed %s: %s", url, e)
    return None


def _is_on_binance(symbol):
    """Cek apakah symbol tersedia di Binance (USDT pair)."""
    if not symbol:
        return False
    try:
        sym = (symbol or "").upper().strip()
        r = requests.get(
            BINANCE_TICKER_URL,
            params={"symbol": f"{sym}USDT"},
            headers=HEADERS,
            timeout=5,
        )
        if r.status_code != 200:
            return False
        data = r.json()
        return isinstance(data, dict) and data.get("price") is not None
    except Exception:
        return False


def _moving_average(prices, period):
    if not prices or len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def _calculate_rsi(prices, period=14):
    if not prices or len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100 - (100 / (1 + rs)))


def _fetch_market_chart_prices(coin_id, days=200):
    """Return list of prices (oldest to newest) for coin_id, or [] on failure."""
    url = MARKET_CHART_URL.format(coin_id=coin_id)
    params = {"vs_currency": "usd", "days": days}
    data = _safe_get_json(url, params=params, timeout=TIMEOUT)
    if not isinstance(data, dict):
        return []
    raw = data.get("prices", [])
    if not isinstance(raw, list):
        return []
    pairs = []
    for p in raw:
        try:
            pairs.append((int(p[0]), float(p[1])))
        except (IndexError, TypeError, ValueError):
            continue
    pairs.sort(key=lambda x: x[0])
    return [pr for _, pr in pairs]


def _trend_strength_score(prices):
    """
    Trend strength: MA trend + RSI momentum.
    Returns float score (higher = stronger trend, can be negative for bearish).
    """
    if not prices or len(prices) < 200:
        return 0.0
    ma50 = _moving_average(prices, 50)
    ma200 = _moving_average(prices, 200)
    rsi = _calculate_rsi(prices)
    if ma50 is None or ma200 is None:
        ma_signal = 0
    else:
        ma_signal = 1.0 if ma50 > ma200 else -1.0
    if rsi is None:
        rsi_signal = 0
    else:
        rsi_signal = (rsi - 50) / 50.0  # -1 to 1
    return ma_signal * 50.0 + rsi_signal * 50.0


def _refresh_universe():
    """Fetch top 200, filter liquidity (vol > 20M), rank volatility, rank trend strength → top 10."""
    global _dynamic_coins, _coin_id_map, _last_refresh, _last_successful_coins, _universe_cache, _cache_timestamp

    now = time.time()
    # Prevent frequent refresh
    if _dynamic_coins and (now - _last_refresh) < CACHE_TTL:
        return
    if _universe_cache and (now - _cache_timestamp) < CACHE_TTL:
        _dynamic_coins = list(_universe_cache)
        _last_refresh = now
        return

    data = None
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 50,
        "page": 1,
        "sparkline": "false",
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                MARKETS_URL,
                params=params,
                headers=HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                break
            else:
                logging.warning("dynamic_universe: retry %d", attempt + 1)
        except Exception:
            logging.warning("dynamic_universe: retry %d", attempt + 1)

        if attempt < MAX_RETRIES - 1:
            time.sleep(BACKOFF[attempt])

    if not isinstance(data, list) or len(data) == 0:
        if _universe_cache:
            _dynamic_coins = list(_universe_cache)
            _last_refresh = time.time()
            logging.warning("dynamic_universe: using cached universe")
            return
        logging.error("dynamic_universe: using fallback coins")
        _dynamic_coins = list(FALLBACK_COINS)
        _coin_id_map = {}
        _last_refresh = time.time()
        return

    logging.info("dynamic_universe: fetched %d coins", len(data))

    # Filter liquidity
    liquid = []
    for c in data:
        try:
            vol = c.get("total_volume")
            cap = c.get("market_cap")
            if vol is None or cap is None:
                continue
            if float(vol) < MIN_VOLUME_24H or float(cap) < MIN_MARKET_CAP:
                continue
            liquid.append(c)
        except (TypeError, ValueError):
            continue

    if not liquid:
        logging.warning("dynamic_universe: no coins pass liquidity filter, using fallback coins")
        _dynamic_coins = list(FALLBACK_COINS)
        _coin_id_map = {}
        _last_refresh = time.time()
        return

    # Volatility ranking: score = abs(price_change_24h) + ATR proxy (range/price)
    def vol_score(item):
        try:
            ch = item.get("price_change_percentage_24h")
            pct = abs(float(ch)) if ch is not None else 0.0
            price = float(item.get("current_price") or 1)
            high = float(item.get("high_24h") or price)
            low = float(item.get("low_24h") or price)
            if price and price > 0:
                atr_proxy = (high - low) / price * 100
            else:
                atr_proxy = 0
            return pct + atr_proxy
        except (TypeError, ValueError):
            return 0.0

    liquid.sort(key=vol_score, reverse=True)
    top_vol = liquid[:TOP_BY_VOLATILITY]

    # Trend strength: hanya coin yang ada di Binance dan punya data OHLC
    scored = []
    for i, coin in enumerate(top_vol):
        cid = coin.get("id")
        sym = (coin.get("symbol") or "").upper()
        if not cid or not sym:
            continue
        if not _is_on_binance(sym):
            continue
        time.sleep(0.25)  # rate limit
        prices = _fetch_market_chart_prices(cid)
        if not prices or len(prices) < MIN_OHLC_POINTS:
            continue
        score = _trend_strength_score(prices)
        scored.append((sym, cid, abs(score)))

    scored.sort(key=lambda x: x[2], reverse=True)
    top_dynamic = scored[:TOP_BY_TREND]

    _coin_id_map = {s: cid for s, cid, _ in top_dynamic}
    _dynamic_coins = [s for s, _, _ in top_dynamic]
    _last_successful_coins = list(_dynamic_coins)
    _universe_cache = list(_dynamic_coins)
    _cache_timestamp = time.time()
    _last_refresh = _cache_timestamp
    logging.info("dynamic_universe: refreshed, dynamic_coins=%s", _dynamic_coins)


def get_dynamic_coins():
    """Return list of top 10 dynamic opportunity symbols (uppercase). Refresh cache if older than 24h. Never returns empty."""
    global _last_refresh
    if (time.time() - _last_refresh) > UNIVERSE_CACHE_SEC:
        _refresh_universe()
    result = list(_dynamic_coins) if _dynamic_coins else list(FALLBACK_COINS)
    return result if result else list(CORE_COINS)


def get_tradable_coins():
    """Hybrid universe: CORE_COINS + dynamic_coins (no duplicate). Opportunity scanner hanya scan ini."""
    dynamic = get_dynamic_coins()
    core_set = set(CORE_COINS)
    dynamic_only = [c for c in dynamic if c not in core_set]
    return list(CORE_COINS) + dynamic_only


def get_coin_id(symbol):
    """Return CoinGecko coin id for symbol, or None."""
    global _coin_id_map, _last_refresh
    if not _coin_id_map or (time.time() - _last_refresh) > UNIVERSE_CACHE_SEC:
        _refresh_universe()
    return _coin_id_map.get((symbol or "").upper())
