"""Kartu kondisi per coin & daftar coin dekat support (decision-support, 9 Okt 2026).

Murni deskriptif: tanpa BUY/EXIT, tanpa confidence, tanpa entry/SL/TP otomatis.
Fungsi di sini tidak melakukan I/O; data (snapshot, closes, funding, label)
diberikan oleh pemanggil supaya mudah dites.
"""
from __future__ import annotations

from typing import Any

_ARROW = {"BULLISH": "↑", "BEARISH": "↓", "SIDEWAYS": "→"}
NEAR_SUPPORT_MAX_PCT = 3.0


def _f(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def fmt_price(v) -> str:
    x = _f(v)
    if x is None:
        return "—"
    a = abs(x)
    if a >= 1000:
        return f"${x:,.0f}" if a >= 10000 else f"${x:,.2f}"
    if a >= 1:
        return f"${x:,.4f}".rstrip("0").rstrip(".")
    return f"${x:.8f}".rstrip("0").rstrip(".")


def _arrow(t) -> str:
    return _ARROW.get(str(t or "").upper(), "?")


def support_distance_pct(price, support) -> float | None:
    """Jarak harga ke support dalam % harga (positif = di atas support)."""
    p, s = _f(price), _f(support)
    if not p or s is None or p <= 0:
        return None
    return (p - s) / p * 100


def resistance_distance_pct(price, resistance) -> float | None:
    p, r = _f(price), _f(resistance)
    if not p or r is None or p <= 0:
        return None
    return (r - p) / p * 100


def avg_move_pct(closes) -> float | None:
    """Rata-rata gerak absolut per candle (%) dari 14 perubahan close terakhir."""
    c = [x for x in (closes or []) if _f(x)]
    if len(c) < 15:
        return None
    c = c[-15:]
    moves = [abs(c[i] - c[i - 1]) / c[i - 1] * 100 for i in range(1, len(c))]
    return sum(moves) / len(moves)


def _trend_phrase(t4: str, t1: str) -> str:
    if t4 == t1 and t4 in ("BULLISH", "BEARISH"):
        return "searah ⭐"
    if "UNKNOWN" in (t4, t1) or not t4 or not t1:
        return "data belum lengkap"
    return "belum searah"


def _rsi_phrase(rsi: float | None) -> str:
    if rsi is None:
        return "—"
    if rsi < 30:
        return f"{rsi:.0f} — oversold"
    if rsi < 40:
        return f"{rsi:.0f} — momentum lemah, belum oversold"
    if rsi <= 60:
        return f"{rsi:.0f} — netral"
    if rsi <= 70:
        return f"{rsi:.0f} — momentum kuat"
    return f"{rsi:.0f} — overbought"


def build_coin_condition(
    symbol: str,
    md: dict[str, Any],
    *,
    funding_rate=None,
    closes_4h=None,
    closes_1d=None,
    label: str | None = None,
    snapshot_ts: str = "—",
) -> str:
    """Kartu kondisi satu coin. funding_rate = fraksi mentah (0.0001 = 0,01%)."""
    if not isinstance(md, dict) or not md:
        return f"🔍 {symbol} — data tidak tersedia."
    price = _f(md.get("price"))
    rsi = _f(md.get("rsi"))
    sup, res = _f(md.get("support")), _f(md.get("resistance"))
    t4 = str(md.get("trend_4h") or "UNKNOWN").upper()
    t1 = str(md.get("trend_1d") or "UNKNOWN").upper()

    ds = support_distance_pct(price, sup)
    dr = resistance_distance_pct(price, res)
    if ds is None:
        pos = "—"
    elif ds >= 0:
        pos = f"{ds:.1f}% di atas support {fmt_price(sup)}"
    else:
        pos = f"{abs(ds):.1f}% DI BAWAH support {fmt_price(sup)} (support jebol)"
    if dr is not None:
        pos += (f" · {dr:.1f}% di bawah resistance {fmt_price(res)}" if dr >= 0
                else f" · {abs(dr):.1f}% DI ATAS resistance {fmt_price(res)} (tembus)")

    vol = avg_move_pct(closes_4h)
    fr = _f(funding_rate)
    fr_pct = fr * 100 if fr is not None else None
    if fr_pct is None:
        fr_s = "—"
    elif fr_pct >= 0.03:
        fr_s = f"{fr_pct:+.3f}% (long ramai)"
    elif fr_pct <= -0.01:
        fr_s = f"{fr_pct:+.3f}% (short ramai)"
    else:
        fr_s = f"{fr_pct:+.3f}% (netral)"

    lbl = (label or "").strip()
    if lbl in ("", "• Neutral", "Neutral"):
        lbl = "—"

    lines = [
        f"🔍 {symbol} — Kondisi Coin",
        f"Harga   : {fmt_price(price)}",
        f"Tren    : 4H {_arrow(t4)} · 1D {_arrow(t1)}  ({_trend_phrase(t4, t1)})",
        f"RSI 4H  : {_rsi_phrase(rsi)}",
        f"Posisi  : {pos}",
        f"Gerak/candle 4H: ±{vol:.1f}% (rata-rata 14 candle)" if vol is not None else "Gerak/candle 4H: —",
        f"Funding : {fr_s}",
        f"Kondisi : {lbl}",
    ]

    notes: list[str] = []
    support_30d = None
    c1 = [x for x in (closes_1d or []) if _f(x)]
    if len(c1) >= 30:
        support_30d = min(c1[-30:])
    if ds is not None and 0 <= ds <= NEAR_SUPPORT_MAX_PCT:
        if support_30d is not None and sup is not None and support_30d < sup * 0.995:
            notes.append(f"Support dekat — kalau jebol, level 30-hari berikutnya ~{fmt_price(support_30d)}")
        else:
            notes.append("Support dekat — perhatikan reaksi harga di level ini")
    if ds is not None and ds < 0:
        notes.append("Harga sudah di bawah support jangka pendek — level lama bisa berubah jadi resistance")
    if dr is not None and 0 <= dr <= NEAR_SUPPORT_MAX_PCT:
        notes.append("Dekat resistance — ruang naik terbatas sebelum level ini tembus")
    if t4 in ("BULLISH", "BEARISH") and t1 == "SIDEWAYS":
        arah = "turun" if t4 == "BEARISH" else "naik"
        notes.append(f"Tren 1D belum ikut {arah}; konfirmasi kalau 1D ikut {_arrow(t4)}")
    elif t4 in ("BULLISH", "BEARISH") and t1 in ("BULLISH", "BEARISH") and t4 != t1:
        notes.append("4H berlawanan dengan 1D — gerak 4H bisa jadi koreksi/pantulan sementara")
    elif t4 == t1 and t4 in ("BULLISH", "BEARISH"):
        notes.append(f"4H & 1D searah {_arrow(t4)} — tren paling jelas")
    if rsi is not None and rsi < 30:
        notes.append("RSI oversold — pantulan mungkin, tapi belum ada konfirmasi pembalikan")
    elif rsi is not None and rsi > 70:
        notes.append("RSI overbought — rawan koreksi")
    if fr_pct is not None and (fr_pct >= 0.03 or fr_pct <= -0.01):
        notes.append("Funding condong ke satu sisi — rawan squeeze ke arah sebaliknya")
    if notes:
        lines.append("")
        lines.append("Yang perlu dicatat:")
        lines.extend(f"• {n}" for n in notes[:4])
    lines.append("")
    lines.append("ℹ️ Info kondisi, bukan saran entry.")
    lines.append(f"🕒 Snapshot: {snapshot_ts}")
    return "\n".join(lines)


def near_support_rows(data: dict[str, Any], max_pct: float = NEAR_SUPPORT_MAX_PCT) -> list[dict]:
    rows = []
    for sym, md in (data or {}).items():
        if not isinstance(md, dict) or md.get("error"):
            continue
        ds = support_distance_pct(md.get("price"), md.get("support"))
        if ds is None or ds < 0 or ds > max_pct:
            continue
        rows.append({
            "coin": sym, "dist": ds, "support": md.get("support"),
            "t4": str(md.get("trend_4h") or "UNKNOWN").upper(),
            "t1": str(md.get("trend_1d") or "UNKNOWN").upper(),
            "rsi": _f(md.get("rsi")),
        })
    rows.sort(key=lambda r: r["dist"])
    return rows


def format_near_support(rows: list[dict], max_pct: float = NEAR_SUPPORT_MAX_PCT, snapshot_ts: str = "—") -> str:
    head = [f"📍 DEKAT SUPPORT (≤{max_pct:.0f}% di atas support)", ""]
    if not rows:
        return "\n".join(head + ["Tidak ada coin yang dekat support saat ini.", "", f"🕒 Snapshot: {snapshot_ts}"])
    body = []
    for r in rows:
        rsi = f"{r['rsi']:.0f}" if r["rsi"] is not None else "—"
        body.append(
            f"{r['coin']:<6} {r['dist']:.1f}% di atas {fmt_price(r['support'])} · "
            f"4H {_arrow(r['t4'])} 1D {_arrow(r['t1'])} · RSI {rsi}"
        )
    tail = [
        "",
        "Support = close terendah ~3 hari (20 candle 4H).",
        "Dekat support saat tren ↓ = rawan jebol; saat tren ↑ = area pantulan.",
        "ℹ️ Daftar pantau, bukan sinyal beli. Pilih coin untuk kartu kondisinya 👇",
        f"🕒 Snapshot: {snapshot_ts}",
    ]
    return "\n".join(head + body + tail)
