"""Research-only E3 shadow signal generation.

This module is deliberately isolated from the production signal gateway.  It
only becomes active when ``SHADOW_E3_ENABLED=true`` and never calls
``process_signal`` (therefore it cannot enter production dedup/state).
"""

from __future__ import annotations

import logging
import os
import time
from collections import Counter
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import requests

from engine.brain.trading_brain import TradingBrain
from engine.market.features import average_true_range

logger = logging.getLogger(__name__)

KLINES_URL = "https://api.binance.com/api/v3/klines"
KLINE_LIMIT = 100
CACHE_TTL_SEC = 900
_cache: dict[str, tuple[float, list[dict[str, float | int]]]] = {}
_cache_lock = Lock()


def enabled() -> bool:
    return os.getenv("SHADOW_E3_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def dispatch_enabled() -> bool:
    return os.getenv("SHADOW_E3_DISPATCH", "false").strip().lower() in {"1", "true", "yes", "on"}


def dispatch_cooldown_sec() -> int:
    """Cooldown antar dispatch Telegram untuk kombinasi (coin, setup, side) yang
    sama, agar setup yang tetap terpenuhi lintas siklus snapshot (~60s) tidak
    re-fire tiap menit. Default 4 jam, selaras dengan cooldown checker riset
    lain (mis. near_support/near_resistance)."""
    try:
        return int(os.getenv("SHADOW_SIGNAL_COOLDOWN_SEC", "14400"))
    except ValueError:
        return 14400


def _closed_4h_klines(symbol: str) -> list[dict[str, float | int]]:
    coin = str(symbol or "").upper().replace("USDT", "")
    if not coin:
        return []
    now = time.time()
    with _cache_lock:
        cached = _cache.get(coin)
        if cached and now - cached[0] < CACHE_TTL_SEC:
            return list(cached[1])
    try:
        response = requests.get(
            KLINES_URL,
            params={"symbol": f"{coin}USDT", "interval": "4h", "limit": KLINE_LIMIT},
            timeout=10,
        )
        if response.status_code != 200:
            logger.warning("shadow_e3 kline HTTP %s coin=%s", response.status_code, coin)
            return []
        raw = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("shadow_e3 kline fetch failed coin=%s: %s", coin, exc)
        return []
    rows: list[dict[str, float | int]] = []
    now_ms = int(time.time() * 1000)
    for item in raw if isinstance(raw, list) else []:
        try:
            close_time = int(item[6])
            if close_time >= now_ms:
                continue
            rows.append({
                "open_time": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "close_time": close_time,
            })
        except (TypeError, ValueError, IndexError):
            continue
    with _cache_lock:
        _cache[coin] = (now, rows)
    return list(rows)


def build_shadow_signal(
    symbol: str,
    market_data: dict[str, Any],
    rows: list[dict[str, Any]],
    counters: Counter[str] | None = None,
) -> dict[str, Any] | None:
    """Build E3 levels from an already-produced market snapshot row.

    ``counters`` is purely observational bookkeeping for
    ``collect_shadow_signals`` (see below): when provided, exactly one bucket
    is incremented per call — matching whichever gate caused this call to
    return ``None``, or ``"success"`` when a candidate is produced. Passing
    it (or not) never changes the return value or any decision logic; it is
    a no-op side channel for logging/metrics only.
    """

    def _stop(reason: str) -> None:
        if counters is not None:
            counters[reason] += 1

    if not isinstance(market_data, dict) or len(rows or []) < 15:
        _stop("insufficient_rows")
        return None
    atr_values = average_true_range(rows, 14)
    atr = atr_values[-1] if atr_values else None
    if atr is None or float(atr) <= 0:
        _stop("atr_invalid")
        return None
    data = dict(market_data)
    data["symbol"] = symbol
    try:
        signal = TradingBrain().analyze(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("shadow_e3 TradingBrain failed coin=%s: %s", symbol, exc)
        _stop("trading_brain_exception")
        return None
    if not signal or signal.get("setup") in (None, "NO SETUP"):
        _stop("no_setup")
        return None
    setup = str(signal.get("setup"))
    entry = float(signal.get("entry") or data.get("price"))
    side = str(signal.get("side") or "").upper()
    if side not in {"LONG", "SHORT"} or entry <= 0:
        _stop("invalid_side_entry")
        return None
    if setup == "OVERSOLD BOUNCE":
        support = data.get("support")
        if support is None or entry > float(support) * 1.01:
            _stop("support_filter_reject")
            return None
    distance = float(atr)
    signal["coin"] = str(symbol).upper().replace("USDT", "")
    signal["side"] = side
    signal["entry"] = entry
    signal["sl"] = entry - distance if side == "LONG" else entry + distance
    signal["tp1"] = entry + 3 * distance if side == "LONG" else entry - 3 * distance
    signal["risk_reward"] = 3.0
    signal["atr_14"] = distance
    signal["source"] = "shadow_e3"
    signal["dispatch_status"] = "RECORDED"
    signal["signal_time"] = datetime.now(timezone.utc).isoformat()
    signal["regime"] = str(data.get("market_regime") or data.get("regime") or "UNKNOWN")
    _stop("success")
    return signal


def collect_shadow_signals(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if not enabled():
        return []
    rows_by_coin: list[dict[str, Any]] = []
    # Per-cycle, per-reason breakdown of why each coin did/didn't produce a
    # candidate this cycle. Purely in-memory, reset on every call (local
    # variable) — never persisted, never changes candidate generation.
    counters: Counter[str] = Counter()
    total_processed = 0
    for symbol, market_data in (snapshot.get("data") or {}).items():
        total_processed += 1
        rows = _closed_4h_klines(symbol)
        signal = build_shadow_signal(symbol, market_data, rows, counters=counters)
        if signal:
            rows_by_coin.append(signal)
    breakdown_total = sum(counters.values())
    assert breakdown_total == total_processed, (
        "shadow_e3 observability breakdown mismatch: breakdown_total=%d "
        "total_processed=%d counters=%s" % (breakdown_total, total_processed, dict(counters))
    )
    logger.info(
        "shadow_e3 candidates=%d (success=%d, no_setup=%d, atr_invalid=%d, "
        "insufficient_rows=%d, invalid_side_entry=%d, support_filter_reject=%d, "
        "trading_brain_exception=%d)",
        len(rows_by_coin),
        counters.get("success", 0),
        counters.get("no_setup", 0),
        counters.get("atr_invalid", 0),
        counters.get("insufficient_rows", 0),
        counters.get("invalid_side_entry", 0),
        counters.get("support_filter_reject", 0),
        counters.get("trading_brain_exception", 0),
    )
    return rows_by_coin


def format_shadow_message(signal: dict[str, Any]) -> str:
    return (
        "🧪 SHADOW/RISET — BUKAN SINYAL PRODUKSI\n\n"
        f"{signal.get('coin', '—')} {signal.get('setup', '—')} {signal.get('side', '—')}\n"
        f"Entry: {float(signal.get('entry', 0)):.8g}\n"
        f"SL (1×ATR): {float(signal.get('sl', 0)):.8g}\n"
        f"TP (3×ATR): {float(signal.get('tp1', 0)):.8g}\n"
        f"ATR14 4h: {float(signal.get('atr_14', 0)):.8g}"
    )
