"""⚡ Scan Pasar — laporan gabungan on-demand (9 Okt 2026).

Read-only: TIDAK mencatat cooldown alert dan TIDAK mengirim alert, jadi
memakai tombol ini tidak menahan alert otomatis. Fungsi format murni; data
(perubahan 1 jam, level S/R, rata-rata volume) diberikan pemanggil.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

import requests

from engine.market.breakout_detector import evaluate_breakout
from engine.market.coin_condition import fmt_price, resistance_distance_pct

logger = logging.getLogger(__name__)

BIG_MOVE_PCT = 3.0
SPIKE_MULTIPLIER = 4.0
NEAR_RES_PCT = 3.0
TICKER_URL = "https://api.binance.com/api/v3/ticker"


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def fetch_1h_changes(coins: list[str]) -> dict[str, float]:
    """% perubahan rolling 1 jam dari Binance (satu request untuk semua coin)."""
    out: dict[str, float] = {}
    if not coins:
        return out
    syms = [f"{c}USDT" for c in coins]
    try:
        r = requests.get(
            TICKER_URL,
            params={"symbols": json.dumps(syms, separators=(",", ":")), "windowSize": "1h", "type": "MINI"},
            timeout=10,
        )
        r.raise_for_status()
        for row in r.json():
            sym = str(row.get("symbol", ""))
            o, last = _f(row.get("openPrice")), _f(row.get("lastPrice"))
            if sym.endswith("USDT") and o and last:
                out[sym[:-4]] = (last - o) / o * 100
    except Exception as e:  # noqa: BLE001
        logger.warning("market_scan: ticker 1h gagal: %s", e)
    return out


def collect_scan(
    data: dict[str, Any],
    changes_1h: dict[str, float],
    sr_fn: Callable[[str], Any],
    avg_vol_fn: Callable[[str], Any],
    levels_map: dict | None = None,
) -> dict[str, Any]:
    breakouts, vol_ratios, oversold, overbought, near_res = [], [], [], [], []
    for coin, md in (data or {}).items():
        if not isinstance(md, dict) or md.get("error"):
            continue
        price = _f(md.get("price"))
        try:
            hit = evaluate_breakout(price, sr_fn(coin)) if price else None
        except Exception as e:  # noqa: BLE001
            logger.warning("market_scan: breakout %s: %s", coin, e)
            hit = None
        if hit:
            breakouts.append(dict(hit, coin=coin))
        vol, avg = _f(md.get("volume_24h")), None
        try:
            avg = _f(avg_vol_fn(coin))
        except Exception as e:  # noqa: BLE001
            logger.warning("market_scan: avg volume %s: %s", coin, e)
        if vol and avg:
            vol_ratios.append((coin, vol / avg))
        rsi = _f(md.get("rsi"))
        if rsi is not None and rsi < 30:
            oversold.append((coin, rsi))
        elif rsi is not None and rsi > 70:
            overbought.append((coin, rsi))
        res_v = (levels_map.get(coin) or {}).get("resistance") if levels_map and levels_map.get(coin) else md.get("resistance")
        dr = resistance_distance_pct(price, res_v)
        if dr is not None and 0 <= dr <= NEAR_RES_PCT:
            near_res.append((coin, dr, res_v))
    vol_ratios.sort(key=lambda x: -x[1])
    oversold.sort(key=lambda x: x[1])
    overbought.sort(key=lambda x: -x[1])
    near_res.sort(key=lambda x: x[1])
    return {
        "changes": changes_1h, "breakouts": breakouts, "vol_ratios": vol_ratios,
        "oversold": oversold, "overbought": overbought, "near_res": near_res,
    }


def format_market_scan(scan: dict[str, Any], snapshot_ts: str = "—") -> str:
    ch = scan.get("changes") or {}
    lines = [f"⚡ SCAN PASAR — {snapshot_ts}", ""]

    lines.append("🏃 Gerak 1 jam terbesar")
    if ch:
        ups = sorted([(c, v) for c, v in ch.items() if v > 0], key=lambda x: -x[1])[:3]
        downs = sorted([(c, v) for c, v in ch.items() if v < 0], key=lambda x: x[1])[:3]
        lines.append("▲ " + (" · ".join(f"{c} {v:+.1f}%" for c, v in ups) if ups else "—"))
        lines.append("▼ " + (" · ".join(f"{c} {v:+.1f}%" for c, v in downs) if downs else "—"))
        big = [f"{c} {v:+.1f}%" for c, v in sorted(ch.items(), key=lambda x: -abs(x[1])) if abs(v) >= BIG_MOVE_PCT]
        lines.append(f"💥 Big move (≥{BIG_MOVE_PCT:.0f}%): " + (", ".join(big) if big else "tidak ada"))
    else:
        lines.append("Data perubahan 1 jam tidak tersedia")
    lines.append("")

    bo = scan.get("breakouts") or []
    lines.append("🚨 Tembus level hari ini (vs close kemarin)")
    if bo:
        for b in bo:
            if b["direction"] == "UP":
                txt = f"tembus ke atas {fmt_price(b['level'])} ({b['pct_from_level']:+.1f}%)"
            else:
                txt = f"jebol ke bawah {fmt_price(b['level'])} ({b['pct_from_level']:+.1f}%)"
            lines.append(f"• {b['coin']} {txt}")
        lines.append("  (level: pivot harian 90 hari — sama dengan menu lain)")
    else:
        lines.append("• tidak ada")
    lines.append("")

    vr = scan.get("vol_ratios") or []
    spikes = [(c, r) for c, r in vr if r >= SPIKE_MULTIPLIER]
    lines.append("📊 Volume 24j vs rata-rata 14 hari")
    if spikes:
        lines.append("• Spike: " + ", ".join(f"{c} {r:.1f}×" for c, r in spikes))
    else:
        top = ", ".join(f"{c} {r:.1f}×" for c, r in vr[:3]) if vr else "—"
        lines.append(f"• Spike (≥{SPIKE_MULTIPLIER:.0f}×): tidak ada · tertinggi: {top}")
    lines.append("")

    os_, ob = scan.get("oversold") or [], scan.get("overbought") or []
    lines.append("🔵 RSI 4H ekstrem")
    lines.append("• Oversold (<30): " + (", ".join(f"{c} {r:.0f}" for c, r in os_) if os_ else "—"))
    lines.append("• Overbought (>70): " + (", ".join(f"{c} {r:.0f}" for c, r in ob) if ob else "—"))
    lines.append("")

    nr = scan.get("near_res") or []
    lines.append(f"🔺 Dekat resistance (≤{NEAR_RES_PCT:.0f}%)")
    shown = ", ".join(f"{c} {d:.1f}% → {fmt_price(r)}" for c, d, r in nr[:6])
    more = f" (+{len(nr) - 6} lagi, lihat 📍 Dekat S/R)" if len(nr) > 6 else ""
    lines.append("• " + (shown + more if nr else "tidak ada"))
    lines.append("")
    lines.append("ℹ️ Pemantauan, bukan sinyal. Detail per coin: 🔍 Analisis Coin")
    return "\n".join(lines)
