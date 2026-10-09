"""Mesin level support/resistance terpadu (9 Okt 2026).

Satu sumber level untuk semua tampilan: pivot swing HARIAN 90 hari (titik
balik nyata), dikelompokkan bila berdekatan ≤1,2%, lalu dipilih level
TERDEKAT di bawah (support) dan di atas (resistance) harga, lapis 1 & 2.

Menggantikan: (A) min/max 20 candle 4H (~3 hari, terlalu pendek untuk swing),
(B) cluster 3 high tertinggi/3 low terendah 90 hari (ekstrem, bukan terdekat),
(C) pemilihan Info Coin dari daftar B.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

KLINES_URL = "https://api.binance.com/api/v3/klines"
FUTURES_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
DAYS = 90
PIVOT_K = 3            # pivot = high/low tertinggi/terendah di jendela ±3 hari (swing)
CLUSTER_PCT = 0.012    # level berjarak ≤1,2% digabung
MIN_GAP_PCT = 0.002    # level dalam ±0,2% dari harga tidak dihitung support/resistance
CACHE_SEC = 3600
SOURCE_LABEL = "pivot harian 90 hari"

_cache: dict[str, dict[str, Any]] = {}


def _fetch_daily(symbol: str) -> dict[str, list[float]] | None:
    """OHLC harian candle TERTUTUP (candle hari ini yang berjalan dibuang)."""
    sym = f"{symbol.strip().upper()}USDT"
    try:
        r = requests.get(KLINES_URL, params={"symbol": sym, "interval": "1d", "limit": DAYS + 1}, timeout=12)
        if r.status_code != 200:
            logger.warning("key_levels: HTTP %s untuk %s", r.status_code, sym)
            return None
        rows = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("key_levels: fetch %s gagal: %s", sym, e)
        return None
    rows = [x for x in rows if isinstance(x, (list, tuple)) and len(x) >= 5][:-1]
    if len(rows) < DAYS * 0.6:
        # Histori spot pendek (coin baru listing spot) → coba candle futures USDT-M.
        try:
            rf = requests.get(FUTURES_KLINES_URL, params={"symbol": sym, "interval": "1d", "limit": DAYS + 1}, timeout=12)
            if rf.status_code == 200:
                fut = [x for x in rf.json() if isinstance(x, (list, tuple)) and len(x) >= 5][:-1]
                if len(fut) > len(rows):
                    rows = fut
        except Exception as e:  # noqa: BLE001
            logger.debug("key_levels: futures fallback %s gagal: %s", sym, e)
    if len(rows) < 2 * PIVOT_K + 5:
        return None
    return {
        "high": [float(x[2]) for x in rows],
        "low": [float(x[3]) for x in rows],
        "close": [float(x[4]) for x in rows],
    }


def daily_ohlc(symbol: str) -> dict[str, list[float]] | None:
    sym = symbol.strip().upper()
    hit = _cache.get(sym)
    if hit and time.time() - hit["ts"] < CACHE_SEC:
        return hit["data"]
    data = _fetch_daily(sym)
    if data is not None:
        _cache[sym] = {"ts": time.time(), "data": data}
    elif hit:
        return hit["data"]  # data lama lebih baik daripada tidak ada
    return data


def pivot_levels(highs: list[float], lows: list[float], k: int = PIVOT_K,
                 cluster_pct: float = CLUSTER_PCT) -> list[dict[str, float]]:
    """Pivot high/low → dikelompokkan → [{level, touches}] urut naik."""
    pts: list[float] = []
    n = min(len(highs), len(lows))
    for i in range(k, n - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            pts.append(highs[i])
        if lows[i] == min(lows[i - k:i + k + 1]):
            pts.append(lows[i])
    clusters: list[list[float]] = []
    for v in sorted(pts):
        if clusters and (v - clusters[-1][0]) / clusters[-1][0] <= cluster_pct:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [{"level": sum(c) / len(c), "touches": len(c)} for c in clusters]


def nearest(levels: list[dict[str, float]], price: float) -> dict[str, Any]:
    below = [x for x in levels if x["level"] < price * (1 - MIN_GAP_PCT)]
    above = [x for x in levels if x["level"] > price * (1 + MIN_GAP_PCT)]
    below.sort(key=lambda x: -x["level"])
    above.sort(key=lambda x: x["level"])

    def _g(lst, i, key="level"):
        return lst[i][key] if len(lst) > i else None

    return {
        "support": _g(below, 0), "support_touches": _g(below, 0, "touches"),
        "support2": _g(below, 1),
        "resistance": _g(above, 0), "resistance_touches": _g(above, 0, "touches"),
        "resistance2": _g(above, 1),
    }


def levels_for(symbol: str) -> dict[str, Any] | None:
    """Semua level pivot + close harian terakhir (tanpa harga) — untuk breakout."""
    data = daily_ohlc(symbol)
    if not data:
        return None
    lv = pivot_levels(data["high"], data["low"])
    if not lv:
        return None
    return {"levels": [x["level"] for x in lv], "prev_close": data["close"][-1], "source": SOURCE_LABEL}


def key_levels(symbol: str, price: float | None) -> dict[str, Any] | None:
    """Level kunci terdekat untuk harga saat ini, atau None bila data tidak ada."""
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    data = daily_ohlc(symbol)
    if not data:
        return None
    lv = pivot_levels(data["high"], data["low"])
    if not lv:
        return None
    out = nearest(lv, p)
    out.update({"levels": [x["level"] for x in lv], "prev_close": data["close"][-1], "source": SOURCE_LABEL})
    return out
