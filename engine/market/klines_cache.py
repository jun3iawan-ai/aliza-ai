"""
ALIZA BINANCE KLINES CACHE

Cache untuk data klines Binance guna mengurangi API request dan risiko rate limit (429).
Key: (symbol, interval). TTL: 4h → 300s, 1d → 600s.
"""

import logging
import time

_klines_cache = {}

# TTL per interval (detik)
TTL_SEC = {
    "4h": 300,
    "1d": 600,
}
DEFAULT_TTL = 300


def _ttl_for_interval(interval):
    """Return TTL in seconds for the given interval."""
    if interval and isinstance(interval, str):
        return TTL_SEC.get(interval.strip().lower(), DEFAULT_TTL)
    return DEFAULT_TTL


def get_cached_klines(symbol, interval):
    """
    Return cached klines if ada dan masih valid.
    symbol: e.g. BTCUSDT
    interval: e.g. "4h", "1d"
    Returns list of close prices or None jika cache miss/expired.
    """
    if not symbol or not interval:
        return None
    key = (str(symbol).upper().strip(), str(interval).strip().lower())
    entry = _klines_cache.get(key)
    if not entry or not isinstance(entry, dict):
        return None
    ts = entry.get("timestamp")
    data = entry.get("data")
    if ts is None or data is None:
        return None
    ttl = _ttl_for_interval(interval)
    if (time.time() - ts) > ttl:
        return None
    return data if isinstance(data, list) else None


def set_cached_klines(symbol, interval, data):
    """
    Simpan klines ke cache.
    data: list of close prices (atau list dari raw klines; yang penting konsisten dengan get).
    """
    if not symbol or not interval:
        return
    if not isinstance(data, list):
        return
    key = (str(symbol).upper().strip(), str(interval).strip().lower())
    _klines_cache[key] = {
        "timestamp": time.time(),
        "data": data,
    }
