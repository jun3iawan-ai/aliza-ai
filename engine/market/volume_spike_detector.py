"""
Volume spike detector: bandingkan volume 24j (USDT) dari snapshot dengan
rata-rata quote volume harian 14 hari dari Binance daily klines.
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
# Single source of truth for the spike threshold (was 2.0 here but the Telegram
# dispatch site required >=4.0 on top of this — two thresholds for one signal,
# see NOTIFIKASI_MITIGASI_REPORT.md item 6). 4.0 is what was actually effective
# in production, so that's the value kept.
SPIKE_MULTIPLIER = 4.0
# Was 4h here; the Telegram dispatch site additionally re-gated with its own
# 8h cooldown. That second gate is now removed (this is the sole cooldown
# authority), so COOLDOWN_HOURS is set to 8 to preserve prior effective cadence.
COOLDOWN_HOURS = 8

# Cache avg quote volume per symbol: {"avg": float, "ts": float}
_avg_vol_cache: dict[str, dict[str, Any]] = {}
AVG_VOL_CACHE_TTL_SEC = 4 * 3600

ALERT_COOLDOWN_SEC = COOLDOWN_HOURS * 3600

KLINES_LIMIT = 14
# Binance kline: index 7 = quote asset volume (USDT untuk pasangan USDT)
QUOTE_VOL_INDEX = 7


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fmt_usd_compact(v: float) -> str:
    """Format ringkas seperti morning brief: 1.97B, 296.23M."""
    ax = abs(v)
    if ax >= 1e9:
        return f"{v / 1e9:.2f}B"
    if ax >= 1e6:
        return f"{v / 1e6:.2f}M"
    if ax >= 1e3:
        return f"{v / 1e3:.2f}K"
    return f"{v:.2f}"


def _fetch_daily_quote_volumes(symbol: str, limit: int = KLINES_LIMIT) -> list[float] | None:
    """Ambil quote volume per candle daily (USDT)."""
    sym = f"{symbol.strip().upper()}USDT"
    try:
        r = requests.get(
            BINANCE_KLINES_URL,
            params={"symbol": sym, "interval": "1d", "limit": min(limit, 1000)},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning(
                "volume_spike_detector: Binance klines HTTP %s for %s",
                r.status_code,
                sym,
            )
            return None
        data = r.json()
        if not isinstance(data, list) or len(data) < 10:
            return None
        out: list[float] = []
        for candle in data:
            if isinstance(candle, (list, tuple)) and len(candle) > QUOTE_VOL_INDEX:
                qv = _safe_float(candle[QUOTE_VOL_INDEX])
                if qv is not None and qv >= 0:
                    out.append(qv)
        if len(out) < 10:
            return None
        return out
    except Exception as e:
        logger.warning("volume_spike_detector: fetch klines failed %s: %s", sym, e)
        return None


def get_avg_volume(symbol: str) -> float | None:
    """
    Rata-rata quote volume (USDT) dari 14 candle daily.
    Cache TTL 4 jam per coin.
    """
    sym = symbol.strip().upper()
    now = time.time()
    cached = _avg_vol_cache.get(sym)
    if cached and now - cached.get("ts", 0) < AVG_VOL_CACHE_TTL_SEC:
        avg = cached.get("avg")
        if isinstance(avg, (int, float)) and avg > 0:
            return float(avg)

    vols = _fetch_daily_quote_volumes(sym, KLINES_LIMIT)
    if vols is None or not vols:
        return None
    avg = sum(vols) / len(vols)
    if avg <= 0:
        return None
    _avg_vol_cache[sym] = {"avg": avg, "ts": now}
    return float(avg)


def check_volume_spike(symbol: str, current_volume: float) -> dict[str, Any] | None:
    """
    Spike jika current_volume > avg_volume * SPIKE_MULTIPLIER.
    Cooldown 4 jam per coin.
    """
    sym = symbol.strip().upper()
    now = time.time()
    if not ngov.is_cooldown_allowed("volume_spike", sym, ALERT_COOLDOWN_SEC, now=now):
        return None

    try:
        cv = float(current_volume)
    except (TypeError, ValueError):
        return None
    if cv <= 0:
        return None

    avg = get_avg_volume(sym)
    if avg is None or avg <= 0:
        return None

    if cv <= avg * SPIKE_MULTIPLIER:
        return None

    mult = cv / avg
    ngov.record_cooldown("volume_spike", sym, now=now)
    return {
        "symbol": sym,
        "current_volume": float(cv),
        "avg_volume": float(avg),
        "multiplier": float(mult),
    }


def format_volume_spike_alert_message(b: dict[str, Any]) -> str:
    """Format pesan Telegram untuk satu volume spike."""
    sym = b.get("symbol", "—")
    cur = b.get("current_volume", 0.0)
    avg = b.get("avg_volume", 0.0)
    mult = b.get("multiplier", 0.0)
    try:
        cur_f = float(cur)
        avg_f = float(avg)
        mult_f = float(mult)
    except (TypeError, ValueError):
        cur_f = avg_f = mult_f = 0.0

    cur_s = _fmt_usd_compact(cur_f)
    avg_s = _fmt_usd_compact(avg_f)

    if ZoneInfo is not None:
        try:
            ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        except Exception:
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    else:
        ts = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB")

    return (
        "📊 VOLUME SPIKE ALERT\n\n"
        f"⚡ {sym} volume meledak!\n"
        f"Volume 24j: ${cur_s}\n"
        f"Rata-rata: ${avg_s}\n"
        f"Multiplier: {mult_f:.2f}x dari normal\n\n"
        "💡 Volume spike sering mendahului pergerakan besar.\n"
        "Pantau price action dan konfirmasi arah.\n\n"
        f"⏰ {ts}\n"
        "——\n"
        "Aliza Engine • Volume Monitor"
    )


async def run_volume_spike_check() -> list[dict[str, Any]]:
    """Loop watchlist; volume_24h dari snapshot; kumpulkan spike yang lolos cooldown."""
    out: list[dict[str, Any]] = []
    try:
        snap = get_market_snapshot()
        data = snap.get("data") or {}
    except Exception as e:
        logger.warning("volume_spike_detector: get_market_snapshot failed: %s", e)
        return []

    for symbol in WATCHLIST:
        row = data.get(symbol)
        if not row or not isinstance(row, dict):
            continue
        if not ngov.is_coin_snapshot_fresh(row):
            logger.warning("volume_spike_detector: skip %s — stale snapshot data", symbol)
            ngov.record_skipped_stale("volume_spike")
            continue
        vol = row.get("volume_24h")
        if vol is None:
            continue
        v = _safe_float(vol)
        if v is None or v <= 0:
            continue
        hit = check_volume_spike(symbol, v)
        if hit:
            out.append(hit)
    return out
