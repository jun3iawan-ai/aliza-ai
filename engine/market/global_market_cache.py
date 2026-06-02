"""
ALIZA GLOBAL MARKET CACHE

Caches fear_greed and btc_dominance to reduce global API calls.
Refresh interval: 300 seconds (5 minutes).
Used by market_analyzer; snapshot engine and trading brain are unchanged.
"""

import logging
import threading
import time
import requests

CACHE_REFRESH_INTERVAL = 300  # seconds

HEADERS = {"User-Agent": "AlizaAI"}
FEAR_GREED_URL = "https://api.alternative.me/fng/"
DOMINANCE_URL = "https://api.coingecko.com/api/v3/global"
# Fallback when CoinGecko rate-limits (429) or fails — public global metrics.
DOMINANCE_FALLBACK_URL = "https://api.coinpaprika.com/v1/global"
TIMEOUT = 12

# Module-level cache state
_cache = {
    "fear_greed": 50.0,
    "btc_dominance": 50.0,
    "timestamp": 0.0,
}
_lock = threading.Lock()


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fetch_fear_greed():
    """Fetch Fear & Greed Index from API. Returns float, default 50."""
    try:
        r = requests.get(FEAR_GREED_URL, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            d = r.json()
            v = (d.get("data") or [{}])[0].get("value")
            return _safe_float(v, 50.0)
    except Exception as e:
        logging.debug("global_market_cache: fear_greed fetch failed: %s", e)
    return 50.0


def _fetch_btc_dominance_coingecko():
    """CoinGecko /global — may return 429 when API quota exhausted."""
    try:
        r = requests.get(DOMINANCE_URL, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            logging.warning(
                "global_market_cache: CoinGecko global HTTP %s (btc dominance)",
                r.status_code,
            )
            return None
        d = r.json()
        st = d.get("status")
        if isinstance(st, dict) and st.get("error_code"):
            logging.warning(
                "global_market_cache: CoinGecko error %s — %s",
                st.get("error_code"),
                st.get("error_message", ""),
            )
            return None
        data = d.get("data") or {}
        mcp = data.get("market_cap_percentage") or {}
        val = _safe_float(mcp.get("btc"), None)
        if val is not None:
            return val
    except Exception as e:
        logging.warning("global_market_cache: CoinGecko dominance request failed: %s", e)
    return None


def _fetch_btc_dominance_fallback():
    """CoinPaprika /v1/global — bitcoin_dominance_percentage."""
    try:
        r = requests.get(DOMINANCE_FALLBACK_URL, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            logging.warning(
                "global_market_cache: CoinPaprika global HTTP %s",
                r.status_code,
            )
            return None
        d = r.json()
        val = _safe_float(d.get("bitcoin_dominance_percentage"), None)
        if val is not None:
            logging.info(
                "global_market_cache: BTC dominance from CoinPaprika fallback: %.4f%%",
                val,
            )
        return val
    except Exception as e:
        logging.warning("global_market_cache: CoinPaprika dominance failed: %s", e)
        return None


def _fetch_btc_dominance():
    """Fetch BTC dominance: CoinGecko first, then CoinPaprika if rate-limited or parse error."""
    try:
        val = _fetch_btc_dominance_coingecko()
        if val is not None:
            return val
    except Exception as e:
        logging.warning("global_market_cache: CoinGecko dominance exception: %s", e)
    val_fb = _fetch_btc_dominance_fallback()
    if val_fb is not None:
        return val_fb
    logging.warning("global_market_cache: btc_dominance unavailable — using default 50.0")
    return 50.0


def _refresh():
    """Update cache from APIs. Caller must hold _lock or call via get_global_market_data."""
    fear_greed = _fetch_fear_greed()
    btc_dominance = _fetch_btc_dominance()
    _cache["fear_greed"] = fear_greed
    _cache["btc_dominance"] = btc_dominance
    _cache["timestamp"] = time.time()


def get_global_market_data():
    """
    Return cached fear_greed, btc_dominance, and timestamp.
    Refreshes from API if cache is empty or older than CACHE_REFRESH_INTERVAL.
    Returns dict: fear_greed (float), btc_dominance (float), timestamp (float).
    """
    now = time.time()
    with _lock:
        if now - _cache["timestamp"] >= CACHE_REFRESH_INTERVAL:
            _refresh()
        return {
            "fear_greed": _cache["fear_greed"],
            "btc_dominance": _cache["btc_dominance"],
            "timestamp": _cache["timestamp"],
        }
