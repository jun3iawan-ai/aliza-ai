"""Radar Aliza -> field `radar` di context.json (dibaca dashboard Porto).

SATU sumber hitung dengan pesan Telegram /radar: data berasal dari
``generate_radar_pro(snapshot)`` (snapshot yang sama), jadi arah 4H/1D, RSI dan kondisi
identik dengan yang tampil di Telegram. Modul ini hanya menerjemahkan ke bentuk mesin.

Aturan nilai: t4h/t1d = up|down|side|na, rsi4h = angka 1 desimal|null,
cond = uptrend|downtrend|null, strong = bool. Semua simbol daftar pantau selalu ada
(tidak ada data -> na/null).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
INTERVAL_MIN = 1  # radar ikut siklus snapshot (60 detik)

DEFINITIONS = {
    "t4h": "Candle 4H tertutup: close terakhir > MA10 > MA30 = up; close < MA10 < MA30 = down; selain itu side "
           "(urutan murni, tanpa ambang persen). Butuh >=30 candle, kurang = na.",
    "t1d": "Candle 1D tertutup: close terakhir > MA20 > MA50 = up; close < MA20 < MA50 = down; selain itu side. "
           "Butuh >=50 candle, kurang = na.",
    "rsi4h": "RSI 14 (Wilder) dari close candle 4H yang sudah tertutup (maks 100 candle terakhir); candle berjalan tidak dipakai.",
    "cond": "uptrend/downtrend = label kondisi Telegram 'Uptrend'/'Downtrend' (4H up/down tanpa sinyal khusus lain); "
            "null = netral atau label lain (Momentum, Whale, Crash Risk, ...), teks lengkapnya ada di field label.",
    "strong": "4H dan 1D sama-sama up atau sama-sama down (tanda ⭐ di Telegram).",
}

_DIR = {"BULLISH": "up", "BEARISH": "down", "SIDEWAYS": "side"}
_COND = {"📈 Uptrend": "uptrend", "📉 Downtrend": "downtrend"}


def _snapshot_iso(ts: Any) -> str | None:
    if not isinstance(ts, datetime):
        return None
    if ts.tzinfo is None:           # snapshot memakai utcnow() (naive UTC)
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(WIB).isoformat(timespec="seconds")


def _src(coin: str) -> str | None:
    try:
        from engine.market import coin_support
        if coin_support.has_spot(coin) is False:
            fut = coin_support.futures_symbol(coin)
            return f"binance-futures:{fut}" if fut else None
    except Exception:  # noqa: BLE001
        pass
    return f"binance:{coin}USDT"


def _coin_entry(item: dict[str, Any] | None, coin: str) -> dict[str, Any]:
    if not item:
        return {"t4h": "na", "t1d": "na", "rsi4h": None, "cond": None, "strong": False, "label": None, "src": None}
    t4 = str(item.get("trend_4h") or "").upper()
    t1 = str(item.get("trend_1d") or "").upper()
    t4h, t1d = _DIR.get(t4, "na"), _DIR.get(t1, "na")
    rsi = None
    if t4h != "na":     # >=30 candle 4H terjamin -> RSI memang dari 4H
        try:
            rsi = round(float(item.get("rsi")), 1)
        except (TypeError, ValueError):
            rsi = None
    label = str(item.get("label") or "").strip()
    if label in ("", "• Neutral", "Neutral"):
        label = ""
    return {
        "t4h": t4h,
        "t1d": t1d,
        "rsi4h": rsi,
        "cond": _COND.get(label),
        "strong": t4h == t1d and t4h in ("up", "down"),
        "label": label or None,
        "src": _src(coin),
    }


def build_radar(snapshot: dict[str, Any] | None = None, coins: list[str] | None = None) -> dict[str, Any] | None:
    """Bangun blok ``radar``; None bila snapshot belum ada (pemanggil mempertahankan radar lama)."""
    from engine.market.market_radar_pro_analyzer import generate_radar_pro
    from engine.market.market_snapshot_engine import get_market_snapshot
    from engine.market.market_universe import get_polling_coins

    snap = snapshot if snapshot is not None else get_market_snapshot()
    ts = _snapshot_iso(snap.get("timestamp"))
    items = generate_radar_pro(snap) or []
    if ts is None or not items:
        return None
    by_coin = {str(i.get("coin")): i for i in items}
    symbols = list(coins) if coins is not None else list(get_polling_coins())
    return {
        "ts": ts,
        "interval_min": INTERVAL_MIN,
        "def": dict(DEFINITIONS),
        "coins": {c: _coin_entry(by_coin.get(c), c) for c in symbols},
    }
