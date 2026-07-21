"""
ALIZA MARKET UNIVERSE
Daftar crypto yang dianalisa oleh Aliza.
Fixed watchlist 21 coin.
"""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# Fixed watchlist — tidak berubah secara dynamic
CORE_COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "SUI", "ARB", "PEPE", "JTO",
    "ETHFI", "WLD", "OM", "ASTER", "XPL",
    "TAO", "BONE", "FARTCOIN", "HYPE", "ZEREBRO",
    "XAUT",
]

# Tidak dipakai lagi — dynamic universe dinonaktifkan
DEFAULT_DYNAMIC_COINS = []

TRADABLE_COINS = list(CORE_COINS)

MAJOR_COINS = list(CORE_COINS)

DEFAULT_COIN_FAIL_THRESHOLD = 10
DEFAULT_COIN_SUSPEND_HOURS = 6.0
_coverage_lock = threading.RLock()
_coin_failure_counts = {}
_coin_suspended_until = {}


def _positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _positive_float_env(name, default):
    try:
        value = float(os.getenv(name, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def get_coin_fail_threshold():
    return _positive_int_env("COIN_FAIL_THRESHOLD", DEFAULT_COIN_FAIL_THRESHOLD)


def get_coin_suspend_hours():
    return _positive_float_env("COIN_SUSPEND_HOURS", DEFAULT_COIN_SUSPEND_HOURS)


def get_universe_exclude():
    raw = os.getenv("UNIVERSE_EXCLUDE", "")
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def reset_coverage_gate():
    """Reset state helper for tests/diagnostics; does not alter the watchlist."""
    with _coverage_lock:
        _coin_failure_counts.clear()
        _coin_suspended_until.clear()


def record_coin_validation(coin, valid, reason=None, now=None):
    """Record one validation result and suspend repeated failures."""
    symbol = str(coin or "").strip().upper()
    if not symbol:
        return
    current = float(time.time() if now is None else now)
    with _coverage_lock:
        if valid:
            if _coin_failure_counts.pop(symbol, 0):
                logger.info("universe_validation_reset coin=%s", symbol)
            _coin_suspended_until.pop(symbol, None)
            return
        count = _coin_failure_counts.get(symbol, 0) + 1
        _coin_failure_counts[symbol] = count
        threshold = get_coin_fail_threshold()
        if count >= threshold and symbol not in _coin_suspended_until:
            cooldown_hours = get_coin_suspend_hours()
            until = current + cooldown_hours * 3600.0
            _coin_suspended_until[symbol] = until
            logger.warning(
                "universe_suspend coin=%s failures=%d cooldown_hours=%.2f reason=%s",
                symbol, count, cooldown_hours, reason or "validation_failed",
            )


def get_polling_coins(coins=None, now=None):
    """Return coins allowed by static exclusions and active cooldowns."""
    selected = list(CORE_COINS if coins is None else coins)
    current = float(time.time() if now is None else now)
    excluded = get_universe_exclude()
    result = []
    with _coverage_lock:
        for raw in selected:
            symbol = str(raw or "").strip().upper()
            if not symbol or symbol in excluded:
                continue
            until = _coin_suspended_until.get(symbol)
            if until is not None:
                if current < until:
                    continue
                _coin_suspended_until.pop(symbol, None)
                _coin_failure_counts.pop(symbol, None)
                logger.info("universe_unsuspend coin=%s", symbol)
            result.append(symbol)
    return result


def get_universe_status(coins=None, now=None):
    current = float(time.time() if now is None else now)
    selected = list(CORE_COINS if coins is None else coins)
    polling = get_polling_coins(selected, current)
    excluded = get_universe_exclude()
    with _coverage_lock:
        suspended = {
            symbol: until for symbol, until in _coin_suspended_until.items()
            if current < until
        }
        failures = {symbol: count for symbol, count in _coin_failure_counts.items() if count}
    return {
        "polling": polling,
        "excluded": sorted(excluded.intersection({str(c).upper() for c in selected})),
        "suspended": suspended,
        "fail_counts": failures,
        "fail_threshold": get_coin_fail_threshold(),
        "suspend_hours": get_coin_suspend_hours(),
    }
