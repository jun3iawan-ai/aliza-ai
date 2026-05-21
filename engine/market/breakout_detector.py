"""
Breakout detector: level support/resistance dari 90 candle daily Binance,
deteksi tembus dengan margin 0.5%, cooldown 4 jam per coin.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import requests

from engine.market.market_snapshot_engine import get_market_snapshot

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "AlizaAI"}
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
TIMEOUT = 15

WATCHLIST = ["BTC", "ETH", "BNB", "SOL", "XRP"]

# SR cache per symbol: {"resistance": [...], "support": [...], "ts": float}
_sr_cache: dict[str, dict[str, Any]] = {}
SR_CACHE_TTL_SEC = 4 * 3600

# Cooldown alert per symbol (unix time)
_last_alert_ts: dict[str, float] = {}
# Level terakhir yang sudah memicu alert breakout per coin (harga SR yang ditembus)
_broken_levels: dict[str, float] = {}
ALERT_COOLDOWN_SEC = 8 * 3600
MAX_BREAKOUT_DISTANCE_PCT = 0.02  # skip jika harga sudah >2% dari level

MARGIN_BREAKOUT = 0.005  # 0.5%
CLUSTER_PCT = 0.015  # 1.5%
KLINES_LIMIT = 90


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _cluster_level_means(values: list[float], resistance: bool, n: int = 3) -> list[float]:
    """
    Kelompokkan nilai yang selisih relatifnya < 1.5% ke cluster; ambil mean per cluster.
    Resistance: urut cluster by max tertinggi; Support: by min terendah.
    """
    if not values:
        return []
    ordered = sorted(values, reverse=resistance)
    clusters: list[list[float]] = []
    for v in ordered:
        if v <= 0:
            continue
        placed = False
        for cl in clusters:
            center = sum(cl) / len(cl)
            if abs(v - center) / center < CLUSTER_PCT:
                cl.append(v)
                placed = True
                break
        if not placed:
            clusters.append([v])
    if resistance:
        clusters.sort(key=lambda c: max(c), reverse=True)
    else:
        clusters.sort(key=lambda c: min(c))
    out: list[float] = []
    for c in clusters[:n]:
        out.append(sum(c) / len(c))
    return out


def _fetch_daily_high_low(symbol: str, limit: int = KLINES_LIMIT) -> tuple[list[float], list[float]] | None:
    sym = f"{symbol.strip().upper()}USDT"
    try:
        r = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": sym, "interval": "1d", "limit": min(limit, 1000)},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("breakout_detector: Binance klines HTTP %s for %s", r.status_code, sym)
            return None
        data = r.json()
        if not isinstance(data, list) or len(data) < 20:
            return None
        highs: list[float] = []
        lows: list[float] = []
        for candle in data:
            if isinstance(candle, (list, tuple)) and len(candle) >= 5:
                hi = _safe_float(candle[2])
                lo = _safe_float(candle[3])
                if hi is not None and hi > 0:
                    highs.append(hi)
                if lo is not None and lo > 0:
                    lows.append(lo)
        if len(highs) < 20 or len(lows) < 20:
            return None
        return highs, lows
    except Exception as e:
        logger.warning("breakout_detector: fetch klines failed %s: %s", sym, e)
        return None


def get_sr_levels(symbol: str) -> dict[str, list[float]] | None:
    """
    Resistance: 3 level tertinggi (cluster), Support: 3 level terendah (cluster).
    Cache TTL 4 jam per coin.
    """
    sym = symbol.strip().upper()
    now = time.time()
    cached = _sr_cache.get(sym)
    if cached and now - cached.get("ts", 0) < SR_CACHE_TTL_SEC:
        return {
            "resistance": list(cached.get("resistance") or []),
            "support": list(cached.get("support") or []),
        }

    ohlc = _fetch_daily_high_low(sym, KLINES_LIMIT)
    if ohlc is None:
        return None
    highs, lows = ohlc
    res_levels = _cluster_level_means(highs, resistance=True, n=3)
    sup_levels = _cluster_level_means(lows, resistance=False, n=3)
    if not res_levels or not sup_levels:
        return None

    _sr_cache[sym] = {
        "resistance": res_levels,
        "support": sup_levels,
        "ts": now,
    }
    return {"resistance": res_levels, "support": sup_levels}


def check_breakout(symbol: str, current_price: float) -> dict[str, Any] | None:
    """
    Deteksi breakout UP (> resistance + 0.5%) atau DOWN (< support - 0.5%).
    Cooldown per coin; level yang sama tidak alert lagi sampai level SR berubah >0.5%.
    """
    sym = symbol.strip().upper()
    now = time.time()
    last = _last_alert_ts.get(sym)
    if last is not None and (now - last) < ALERT_COOLDOWN_SEC:
        return None

    try:
        price = float(current_price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    sr = get_sr_levels(sym)
    if sr is None:
        return None

    resistances = [r for r in sr.get("resistance") or [] if r and r > 0]
    supports = [s for s in sr.get("support") or [] if s and s > 0]
    if not resistances or not supports:
        return None

    # UP: harga di atas resistance tertinggi yang sudah ditembus dengan margin
    candidates_up = [r for r in resistances if price > r * (1 + MARGIN_BREAKOUT)]
    # DOWN: harga di bawah support terendah yang sudah ditembus dengan margin
    candidates_down = [s for s in supports if price < s * (1 - MARGIN_BREAKOUT)]

    direction = None
    level = None
    if candidates_up:
        direction = "UP"
        level = max(candidates_up)
        pct_from = (price - level) / level * 100.0
    elif candidates_down:
        direction = "DOWN"
        level = min(candidates_down)
        pct_from = (price - level) / level * 100.0
    else:
        return None

    if abs(pct_from) / 100.0 >= MAX_BREAKOUT_DISTANCE_PCT:
        return None  # harga sudah terlalu jauh, alert tidak actionable

    level_f = float(level)
    last_broken = _broken_levels.get(sym)
    if last_broken is not None and last_broken > 0:
        level_change = abs(level_f - last_broken) / last_broken
        if level_change < 0.005:
            return None

    _broken_levels[sym] = level_f
    _last_alert_ts[sym] = now
    return {
        "symbol": sym,
        "direction": direction,
        "level": level_f,
        "price": float(price),
        "pct_from_level": float(pct_from),
    }


def format_breakout_alert_message(b: dict[str, Any]) -> str:
    """Format pesan Telegram untuk satu breakout."""
    sym = b.get("symbol", "—")
    direction = b.get("direction", "")
    price = b.get("price", 0.0)
    level = b.get("level", 0.0)
    pct = b.get("pct_from_level", 0.0)

    try:
        price_f = float(price)
        level_f = float(level)
        pct_f = float(pct)
    except (TypeError, ValueError):
        price_f = level_f = pct_f = 0.0

    if direction == "UP":
        head = f"📈 {sym} menembus Resistance"
        pct_s = f"+{pct_f:.2f}%"
    else:
        head = f"📉 {sym} menembus Support"
        pct_s = f"{pct_f:.2f}%"

    if ZoneInfo is not None:
        try:
            ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        except Exception:
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    else:
        ts = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB")

    return (
        "🚨 BREAKOUT ALERT\n\n"
        f"{head}\n"
        f"Harga: ${price_f:,.2f}\n"
        f"Level: ${level_f:,.2f}\n"
        f"Jarak dari level: {pct_s}\n\n"
        f"⏰ {ts}\n"
        "——\n"
        "Aliza Engine • Pantau top 5 coins"
    )


async def run_breakout_check() -> list[dict[str, Any]]:
    """Loop watchlist; harga dari snapshot; kumpulkan breakout yang lolos cooldown + level."""
    out: list[dict[str, Any]] = []
    try:
        snap = get_market_snapshot()
        data = snap.get("data") or {}
    except Exception as e:
        logger.warning("breakout_detector: get_market_snapshot failed: %s", e)
        return []

    for symbol in WATCHLIST:
        row = data.get(symbol)
        if not row or not isinstance(row, dict):
            continue
        p = row.get("price")
        pv = _safe_float(p)
        if pv is None or pv <= 0:
            continue
        hit = check_breakout(symbol, pv)
        if hit:
            out.append(hit)
    return out
