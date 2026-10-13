"""
ALIZA MARKET UNIVERSE
Daftar crypto yang dianalisa oleh Aliza.
Watchlist = daftar coin portofolio dari bot Porto (/var/lib/porto/coins.json).
"""

import logging
import os
import threading
import time

from engine.market import watchlist_source as _wl

logger = logging.getLogger(__name__)

# Daftar LAMA (fallback terakhir bila /var/lib/porto/coins.json belum pernah terbaca & tak ada cache).
# Sumber utama sekarang: daftar portofolio bot Porto (lihat watchlist_source.py).
LEGACY_CORE_COINS = (
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "SUI", "ARB", "PEPE", "JTO",
    "ETHFI", "WLD", "OM", "ASTER", "XPL",
    "TAO", "HYPE", "XAUT",
)

# Tiga list ini DIPERBARUI DI TEMPAT (in-place) oleh refresh_watchlist(), sehingga modul yang
# meng-import MAJOR_COINS / CORE_COINS langsung ikut berubah tanpa restart.
CORE_COINS = list(LEGACY_CORE_COINS)

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
    if coins is None:
        maybe_refresh_watchlist()
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
        "unsupported": [c for c in selected if _unsupported(c)],
    }


def _unsupported(coin):
    try:
        from engine.market import coin_support
        return coin_support.is_unsupported(coin)
    except Exception:  # noqa: BLE001
        return False


def _apply_watchlist(symbols):
    """Ganti isi CORE/MAJOR/TRADABLE_COINS di tempat (objek list tetap sama)."""
    new = list(symbols)
    for lst in (CORE_COINS, MAJOR_COINS, TRADABLE_COINS):
        if lst != new:
            lst[:] = new


def refresh_watchlist(force=False):
    """Baca ulang daftar Porto bila perlu dan terapkan. Return dict hasil (symbols,status,reason,changed)."""
    res = _wl.refresh(LEGACY_CORE_COINS, force=force)
    _apply_watchlist(res["symbols"])
    return res


def maybe_refresh_watchlist():
    """Versi aman untuk jalur panas: tidak pernah melempar, murah (stat file tiap >=5 detik)."""
    try:
        return refresh_watchlist()
    except Exception as e:  # noqa: BLE001
        logger.warning("watchlist refresh gagal: %s", e)
        return None


def pending_watchlist_notice():
    return _wl.pending_notice()


def mark_watchlist_announced():
    _wl.mark_announced()


def get_watchlist_status():
    return _wl.get_status()


def get_analyzable_coins(coins=None, now=None):
    """Coin pantau yang punya data (buang yang tak ada di spot MAUPUN futures Binance, mis. BONE)."""
    try:
        from engine.market import coin_support
        coin_support.maybe_refresh()
    except Exception:  # noqa: BLE001
        pass
    return [c for c in get_polling_coins(coins, now) if not _unsupported(c)]


# Muat daftar saat modul pertama kali di-import (tanpa notifikasi; notifikasi dikirim job).
maybe_refresh_watchlist()
