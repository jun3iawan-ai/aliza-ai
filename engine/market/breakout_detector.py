"""
Breakout detector: level support/resistance dari 90 candle daily Binance,
deteksi tembus dengan margin 0.5%, cooldown 8 jam per coin.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import requests

from engine.alerts import notification_governor as ngov
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

# Cooldown timestamp + terakhir level yang memicu alert breakout: persisted via
# notification_governor (data/alert_cooldown_state.json) — dulu dict in-memory,
# hilang tiap restart proses (lihat NOTIFIKASI_MITIGASI_REPORT.md).
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


def get_sr_levels(symbol: str) -> dict[str, Any] | None:
    """Level S/R untuk breakout — kini dari mesin level terpadu (pivot harian
    90 hari, engine/market/key_levels.py). Fallback ke cluster ekstrem lama."""
    try:
        from engine.market.key_levels import levels_for
        unified = levels_for(symbol)
        if unified:
            return {"levels": unified["levels"], "prev_close": unified["prev_close"],
                    "resistance": unified["levels"], "support": unified["levels"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("breakout_detector: key_levels %s gagal: %s", symbol, e)
    return _legacy_sr_levels(symbol)


def _legacy_sr_levels(symbol: str) -> dict[str, list[float]] | None:
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


def evaluate_breakout(price: float, sr: dict[str, Any] | None) -> dict[str, Any] | None:
    """Inti deteksi breakout TANPA state (tanpa cooldown/level memory).

    Format terpadu (key_levels): {"levels": [...], "prev_close": c} →
    UP bila close harian kemarin DI BAWAH level dan harga kini > level*(1+margin);
    DOWN bila close kemarin DI ATAS level dan harga kini < level*(1-margin).
    Format lama {"resistance","support"} tetap didukung.
    Diabaikan bila harga sudah >= MAX_BREAKOUT_DISTANCE_PCT dari level."""
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price <= 0 or not sr:
        return None
    if sr.get("levels") is not None and sr.get("prev_close"):
        prev = float(sr["prev_close"])
        lv = [float(x) for x in sr["levels"] if x and x > 0]
        ups = [L for L in lv if prev < L and price > L * (1 + MARGIN_BREAKOUT)]
        downs = [L for L in lv if prev > L and price < L * (1 - MARGIN_BREAKOUT)]
        if ups:
            direction, level = "UP", max(ups)
        elif downs:
            direction, level = "DOWN", min(downs)
        else:
            return None
        pct_from = (price - level) / level * 100.0
        if abs(pct_from) / 100.0 >= MAX_BREAKOUT_DISTANCE_PCT:
            return None
        return {"direction": direction, "level": float(level), "price": price, "pct_from_level": float(pct_from)}
    resistances = [r for r in sr.get("resistance") or [] if r and r > 0]
    supports = [s for s in sr.get("support") or [] if s and s > 0]
    if not resistances or not supports:
        return None
    candidates_up = [r for r in resistances if price > r * (1 + MARGIN_BREAKOUT)]
    candidates_down = [s for s in supports if price < s * (1 - MARGIN_BREAKOUT)]
    if candidates_up:
        direction, level = "UP", max(candidates_up)
    elif candidates_down:
        direction, level = "DOWN", min(candidates_down)
    else:
        return None
    pct_from = (price - level) / level * 100.0
    if abs(pct_from) / 100.0 >= MAX_BREAKOUT_DISTANCE_PCT:
        return None
    return {"direction": direction, "level": float(level), "price": price, "pct_from_level": float(pct_from)}


def check_breakout(symbol: str, current_price: float) -> dict[str, Any] | None:
    """
    Deteksi breakout UP (> resistance + 0.5%) atau DOWN (< support - 0.5%).
    Cooldown per coin; level yang sama tidak alert lagi sampai level SR berubah >0.5%.
    """
    sym = symbol.strip().upper()
    now = time.time()
    if not ngov.is_cooldown_allowed("breakout", sym, ALERT_COOLDOWN_SEC, now=now):
        return None

    try:
        price = float(current_price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    sr = get_sr_levels(sym)
    hit = evaluate_breakout(price, sr)
    if hit is None:
        return None
    direction, level, pct_from = hit["direction"], hit["level"], hit["pct_from_level"]

    level_f = float(level)
    last_broken = ngov.get_value("breakout_level", sym)
    if last_broken is not None and last_broken > 0:
        level_change = abs(level_f - float(last_broken)) / float(last_broken)
        if level_change < 0.005:
            return None

    ngov.set_value("breakout_level", sym, level_f)
    ngov.record_cooldown("breakout", sym, now=now)
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

    # Semua coin di snapshot (dulu hanya WATCHLIST 5 coin). Level S/R di-cache
    # 4 jam per coin, jadi tambahan coin = tambahan request ringan per 4 jam.
    for symbol in list(data.keys()):
        row = data.get(symbol)
        if not row or not isinstance(row, dict):
            continue
        if not ngov.is_coin_snapshot_fresh(row):
            logger.warning("breakout_detector: skip %s — stale snapshot data", symbol)
            ngov.record_skipped_stale("breakout")
            continue
        p = row.get("price")
        pv = _safe_float(p)
        if pv is None or pv <= 0:
            continue
        hit = check_breakout(symbol, pv)
        if hit:
            out.append(hit)
    return out
