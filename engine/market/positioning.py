"""Positioning derivatif per coin: funding, open interest (Δ 24 jam / 4 jam),
rasio long/short, dan tafsiran harga vs OI.

Read-only: tidak mengirim alert, tidak menyentuh cooldown. Dipakai menu
"🔄 Funding Rate & OI" (yang juga menggantikan CFRA) dan kartu Analisis Coin.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from engine.market import funding_rate_monitor as frm

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "AlizaAI"}
TIMEOUT = 8
CACHE_TTL_SEC = 5 * 60
OI_FLAT_PCT = 2.0      # |ΔOI 24j| di bawah ini dianggap stabil
PRICE_FLAT_PCT = 0.5   # |Δharga 24j| di bawah ini dianggap datar
OI_NOTABLE_PCT = 5.0   # |ΔOI 24j| minimal untuk masuk "yang menonjol"
FR_EXTREME = frm.FUNDING_ALERT_THRESHOLD  # 0.001 = 0.1%

_cache: dict[str, dict[str, Any]] = {}


def interpret(price_pct: float | None, oi_pct: float | None) -> tuple[str, str]:
    """Tafsiran klasik harga vs open interest (jendela 24 jam)."""
    if price_pct is None or oi_pct is None:
        return "▫️", "data OI tidak lengkap"
    if abs(oi_pct) < OI_FLAT_PCT:
        return "▫️", "OI stabil — tidak ada penumpukan posisi"
    if abs(price_pct) < PRICE_FLAT_PCT:
        if oi_pct > 0:
            return "🟨", "posisi menumpuk saat harga datar — siap gerak kencang"
        return "▫️", "posisi dikurangi, harga datar"
    if price_pct > 0 and oi_pct > 0:
        return "🟩", "long baru masuk — kenaikan didukung posisi baru"
    if price_pct > 0 and oi_pct < 0:
        return "🟦", "short covering — naik tanpa posisi baru (rapuh)"
    if price_pct < 0 and oi_pct > 0:
        return "🟥", "short baru masuk — tekanan jual didukung posisi"
    return "🟧", "long keluar/likuidasi — turun karena posisi ditutup"


def _oi_hist(sym: str) -> tuple[float | None, float | None, float | None]:
    """(oi_usd_now, Δ% 24 jam, Δ% 4 jam) dari openInterestHist 1h."""
    try:
        r = requests.get(frm.OPEN_INTEREST_HIST_URL,
                         params={"symbol": sym, "period": "1h", "limit": 25},
                         headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None, None, None
        rows = sorted(r.json() or [], key=lambda x: int(x.get("timestamp") or 0))
        vals = [frm._safe_float(x.get("sumOpenInterestValue")) for x in rows]
        vals = [v for v in vals if v is not None and v > 0]
        if len(vals) < 2:
            return None, None, None
        now = vals[-1]
        d24 = (now - vals[0]) / vals[0] * 100.0
        d4 = (now - vals[-5]) / vals[-5] * 100.0 if len(vals) >= 5 else None
        return now, d24, d4
    except Exception as e:  # noqa: BLE001
        logger.debug("positioning oi_hist %s: %s", sym, e)
        return None, None, None


def _ls_ratio(sym: str) -> float | None:
    try:
        r = requests.get(frm.GLOBAL_LS_RATIO_URL,
                         params={"symbol": sym, "period": "1h", "limit": 1},
                         headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        rows = r.json() or []
        return frm._safe_float(rows[-1].get("longShortRatio")) if rows else None
    except Exception as e:  # noqa: BLE001
        logger.debug("positioning ls %s: %s", sym, e)
        return None


def _price_change_24h(sym: str) -> float | None:
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr",
                         params={"symbol": sym}, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return frm._safe_float(r.json().get("priceChangePercent"))
    except Exception as e:  # noqa: BLE001
        logger.debug("positioning ticker %s: %s", sym, e)
        return None


def fetch_coin(coin: str) -> dict[str, Any] | None:
    """Data positioning satu coin (cache 5 menit). None jika tidak ada di futures."""
    coin = str(coin).strip().upper()
    sym = frm.SYMBOL_MAP.get(coin)
    if not sym:
        return None
    now = time.time()
    c = _cache.get(coin)
    if c and now - c["ts"] < CACHE_TTL_SEC:
        return dict(c["row"])
    fd = frm.get_funding_rate_data(coin) or {}
    oi_usd, d24, d4 = _oi_hist(sym)
    price_pct = _price_change_24h(sym)
    if not fd and oi_usd is None:
        return None
    row = {
        "coin": coin,
        "fr": fd.get("funding_rate"),
        "next_funding": fd.get("next_funding_time") or "—",
        "next_funding_ms": fd.get("next_funding_time_ms"),
        "oi_usd": oi_usd,
        "oi_24h": d24,
        "oi_4h": d4,
        "price_24h": price_pct,
        "ls": _ls_ratio(sym),
    }
    _cache[coin] = {"ts": now, "row": row}
    return dict(row)


def collect(coins: list[str]) -> list[dict[str, Any]]:
    """Ambil positioning paralel untuk coin yang tersedia di Binance Futures."""
    eligible = [c for c in coins if c in frm.SYMBOL_MAP]
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(fetch_coin, eligible))
    return [r for r in rows if r]


def _pct(v: float | None, nd: int = 1) -> str:
    return "—" if v is None else f"{v:+.{nd}f}%"


def coin_line(row: dict[str, Any]) -> str:
    """Ringkasan satu baris untuk kartu Analisis Coin."""
    emoji, text = interpret(row.get("price_24h"), row.get("oi_24h"))
    fr = row.get("fr")
    fr_s = "—" if fr is None else f"{fr * 100:+.4f}%"
    ls = row.get("ls")
    ls_s = "—" if ls is None else f"{ls:.2f}"
    return (f"OI 24j {_pct(row.get('oi_24h'))} (4j {_pct(row.get('oi_4h'))}) · "
            f"harga 24j {_pct(row.get('price_24h'))} · FR {fr_s} · L/S {ls_s}\n"
            f"{emoji} {text}")


_HEADLINES = {
    "🟩": "long baru masuk — kenaikan didukung posisi baru",
    "🟥": "short baru masuk — tekanan jual didukung posisi",
    "🟦": "short covering — kenaikan tanpa posisi baru",
    "🟧": "deleveraging — harga turun karena long menutup posisi, bukan short agresif",
    "🟨": "posisi menumpuk saat harga datar",
    "▫️": "OI stabil — positioning belum berubah berarti",
}


def market_headline(rows: list[dict[str, Any]]) -> str:
    """Pola dominan di seluruh coin (≥ separuh coin dengan data)."""
    cats = [interpret(r.get("price_24h"), r.get("oi_24h"))[0] for r in rows
            if r.get("price_24h") is not None and r.get("oi_24h") is not None]
    if not cats:
        return ""
    top = max(set(cats), key=cats.count)
    n = cats.count(top)
    if n * 2 < len(cats):
        return f"Gambaran umum: campuran — tidak ada pola positioning dominan ({len(cats)} coin)."
    return f"Gambaran umum: {top} {n}/{len(cats)} coin {_HEADLINES[top]}."


def _minutes_to(ms: Any, now: float | None = None) -> int | None:
    try:
        return int((float(ms) - (now or time.time()) * 1000) / 60000)
    except (TypeError, ValueError):
        return None


def format_positioning(rows: list[dict[str, Any]], ts_label: str, missing: list[str] | None = None) -> str:
    if not rows:
        return "🔄 Funding & Open Interest\nData tidak tersedia (Binance Futures tidak merespons)."
    lines = ["🔄 FUNDING & OPEN INTEREST (24 jam)", "",
             "Coin     Harga   OI      FR        L/S"]
    for r in rows:
        emoji, _ = interpret(r.get("price_24h"), r.get("oi_24h"))
        fr = r.get("fr")
        fr_s = "   —    " if fr is None else f"{fr * 100:+.4f}%"
        ls = r.get("ls")
        ls_s = "—" if ls is None else f"{ls:.2f}"
        lines.append(f"{r['coin']:<8} {_pct(r.get('price_24h')):>6} {_pct(r.get('oi_24h')):>6}  {fr_s}  {ls_s} {emoji}")

    head = market_headline(rows)
    if head:
        lines[1:1] = [head, ""]

    extreme = [r for r in rows if r.get("fr") is not None and abs(r["fr"]) > FR_EXTREME]
    lines += ["", "⚠️ Funding ekstrem (|FR| > 0.1%):"]
    if extreme:
        for r in extreme:
            z = frm.classify_fr_zone(r["fr"])
            mins = _minutes_to(r.get("next_funding_ms"))
            when = f"{r['next_funding']}" + (f", {mins} mnt lagi" if mins is not None and mins >= 0 else "")
            lines.append(f"{z['emoji']} {r['coin']} {r['fr'] * 100:+.4f}% — {z['action']} (funding berikut {when})")
    else:
        lines.append("Tidak ada — funding semua coin di zona normal.")

    notable = [r for r in rows if r.get("oi_24h") is not None and abs(r["oi_24h"]) >= OI_NOTABLE_PCT]
    notable.sort(key=lambda r: -abs(r["oi_24h"]))
    lines += ["", f"📌 Perubahan OI menonjol (≥{OI_NOTABLE_PCT:.0f}%):"]
    if notable:
        for r in notable[:6]:
            emoji, text = interpret(r.get("price_24h"), r.get("oi_24h"))
            lines.append(f"{emoji} {r['coin']} OI {_pct(r['oi_24h'])}, harga {_pct(r.get('price_24h'))} → {text}")
    else:
        lines.append("Tidak ada — OI semua coin relatif stabil.")

    lines += [
        "",
        "Cara baca (harga vs OI):",
        "🟩 harga↑ OI↑ long baru masuk · 🟥 harga↓ OI↑ short baru masuk",
        "🟦 harga↑ OI↓ short covering · 🟧 harga↓ OI↓ long keluar",
        "🟨 OI↑ saat harga datar = posisi menumpuk",
        "▫️ OI berubah < 2% (stabil)",
        "FR positif = long bayar short. L/S = rasio akun long:short (bukan volume).",
    ]
    if missing:
        lines.append(f"Tidak ada di Binance Futures: {', '.join(missing)}")
    lines += ["", "ℹ️ Info positioning, bukan saran entry.", f"⏰ {ts_label}"]
    return "\n".join(lines)
