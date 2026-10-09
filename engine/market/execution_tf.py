"""Timeframe eksekusi (1H / 15m) untuk timing entry.

4H/1D menentukan arah & level besar; 1H/15m dipakai untuk *kapan* masuk:
tren & momentum jangka pendek, volatilitas (ATR) dan swing high/low terdekat
sebagai acuan konfirmasi dan penempatan SL. Read-only, cache 60 detik.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

SPOT_URL = "https://api.binance.com/api/v3/klines"
FUT_URL = "https://fapi.binance.com/fapi/v1/klines"
LIMIT = 150
CACHE_SEC = 60
SWING_K = 2
SWING_LOOKBACK = 48
_cache: dict[tuple[str, str], dict[str, Any]] = {}
ARROW = {"BULLISH": "↑", "BEARISH": "↓", "SIDEWAYS": "→"}


def _get(url: str, sym: str, interval: str) -> list:
    try:
        r = requests.get(url, params={"symbol": sym, "interval": interval, "limit": LIMIT}, timeout=10)
        if r.status_code == 200 and isinstance(r.json(), list):
            return r.json()
    except Exception as e:  # noqa: BLE001
        logger.debug("execution_tf %s %s %s: %s", url, sym, interval, e)
    return []


def fetch_ohlc(symbol: str, interval: str) -> dict[str, list[float]] | None:
    """OHLC candle tertutup; fallback futures bila histori spot pendek."""
    sym = f"{symbol.strip().upper()}USDT"
    key = (sym, interval)
    hit = _cache.get(key)
    if hit and time.time() - hit["ts"] < CACHE_SEC:
        return hit["data"]
    rows = _get(SPOT_URL, sym, interval)
    if len(rows) < 60:
        fut = _get(FUT_URL, sym, interval)
        if len(fut) > len(rows):
            rows = fut
    now_ms = time.time() * 1000
    rows = [x for x in rows if isinstance(x, (list, tuple)) and len(x) >= 7 and float(x[6]) < now_ms]
    if len(rows) < 30:
        return None
    data = {k: [float(x[i]) for x in rows] for k, i in (("high", 2), ("low", 3), ("close", 4))}
    _cache[key] = {"ts": time.time(), "data": data}
    return data


def _ema(xs: list[float], n: int) -> float | None:
    if len(xs) < n:
        return None
    k = 2 / (n + 1)
    e = sum(xs[:n]) / n
    for x in xs[n:]:
        e = x * k + e * (1 - k)
    return e


def _rsi(xs: list[float], n: int = 14) -> float | None:
    if len(xs) < n + 1:
        return None
    g = [max(b - a, 0.0) for a, b in zip(xs, xs[1:])]
    l_ = [max(a - b, 0.0) for a, b in zip(xs, xs[1:])]
    ag, al = sum(g[:n]) / n, sum(l_[:n]) / n
    for i in range(n, len(g)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l_[i]) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def _atr_pct(h: list[float], lo: list[float], c: list[float], n: int = 14) -> float | None:
    if len(c) < n + 1:
        return None
    trs = [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, len(c))]
    return sum(trs[-n:]) / n / c[-1] * 100


def _swings(h: list[float], lo: list[float], price: float) -> tuple[float | None, float | None]:
    """Swing high terdekat di atas harga & swing low terdekat di bawah harga (pivot k=2)."""
    k, n = SWING_K, len(h)
    start = max(k, n - SWING_LOOKBACK)
    highs = [h[i] for i in range(start, n - k) if h[i] == max(h[i - k:i + k + 1])]
    lows = [lo[i] for i in range(start, n - k) if lo[i] == min(lo[i - k:i + k + 1])]
    above = [x for x in highs if x > price]
    below = [x for x in lows if x < price]
    return (min(above) if above else None), (max(below) if below else None)


def analyze(ohlc: dict[str, list[float]] | None, price: float | None = None) -> dict[str, Any] | None:
    if not ohlc:
        return None
    c = ohlc["close"]
    p = float(price) if price else c[-1]
    e20, e50 = _ema(c, 20), _ema(c, 50)
    if e20 is None or e50 is None:
        trend = "SIDEWAYS"
    elif p > e20 > e50:
        trend = "BULLISH"
    elif p < e20 < e50:
        trend = "BEARISH"
    else:
        trend = "SIDEWAYS"
    sh, sl = _swings(ohlc["high"], ohlc["low"], p)
    return {"trend": trend, "rsi": _rsi(c), "atr_pct": _atr_pct(ohlc["high"], ohlc["low"], c),
            "ema20": e20, "ema50": e50, "swing_high": sh, "swing_low": sl}


def execution_view(symbol: str, price: float | None) -> dict[str, Any]:
    return {tf: analyze(fetch_ohlc(symbol, tf), price) for tf in ("1h", "15m")}


def timing_notes(t4: str | None, ex: dict[str, Any], fmt=lambda v: f"{v:g}") -> list[str]:
    h1, m15 = ex.get("1h"), ex.get("15m")
    if not h1:
        return []
    t4 = str(t4 or "").upper()
    a, b = h1["trend"], (m15 or {}).get("trend")
    notes: list[str] = []
    sh, sl = h1.get("swing_high"), h1.get("swing_low")
    if t4 == "BULLISH" and a == "BEARISH":
        notes.append("Koreksi di dalam tren 4H naik — timing long lebih aman setelah 1H berbalik"
                     + (f" (close 1H di atas swing high {fmt(sh)})" if sh else ""))
    elif t4 == "BEARISH" and a == "BULLISH":
        notes.append("Pantulan di dalam tren 4H turun — timing short lebih aman setelah 1H melemah"
                     + (f" (close 1H di bawah swing low {fmt(sl)})" if sl else ""))
    elif t4 == "BEARISH" and a == "BEARISH":
        notes.append("1H searah 4H turun — long masih melawan arus; belum ada tanda pembalikan")
    elif t4 == "BULLISH" and a == "BULLISH":
        notes.append("1H searah 4H naik — momentum sejalan; risiko utama entry terlalu tinggi")
    elif a == "SIDEWAYS":
        notes.append("1H belum punya arah — tunggu harga keluar dari swing range 1H"
                     + (f" ({fmt(sl)} – {fmt(sh)})" if sh and sl else ""))
    if b and a in ("BULLISH", "BEARISH") and b != a and b != "SIDEWAYS":
        notes.append(f"15m sudah berbalik {ARROW[b]} — tanda awal, belum terkonfirmasi di 1H")
    r15 = (m15 or {}).get("rsi")
    if r15 is not None and r15 >= 75:
        notes.append(f"RSI 15m {r15:.0f} — jangka pendek panas, entry long rawan dikejar di pucuk")
    elif r15 is not None and r15 <= 25:
        notes.append(f"RSI 15m {r15:.0f} — jangka pendek jenuh jual, short rawan masuk di dasar")
    return notes


def format_section(t4: str | None, ex: dict[str, Any], fmt) -> str | None:
    rows = []
    for tf, name in (("1h", "1H "), ("15m", "15m")):
        d = ex.get(tf)
        if not d:
            continue
        rsi = "—" if d["rsi"] is None else f"{d['rsi']:.0f}"
        atr = "—" if d["atr_pct"] is None else f"±{d['atr_pct']:.2f}%"
        sw = f"swing {fmt(d['swing_low']) if d['swing_low'] else '—'} / {fmt(d['swing_high']) if d['swing_high'] else '—'}"
        rows.append(f"{name}: {ARROW.get(d['trend'], '?')} · RSI {rsi} · ATR {atr} · {sw}")
    if not rows:
        return None
    out = ["━ ⏱ Timing eksekusi (1H / 15m)"] + rows
    out += [f"• {n}" for n in timing_notes(t4, ex, fmt)]
    out.append("swing = low terdekat di bawah / high terdekat di atas harga (48 candle)")
    return "\n".join(out)
