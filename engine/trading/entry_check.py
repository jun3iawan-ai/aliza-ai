"""/cek — validasi rencana entry user terhadap kondisi market (9 Okt 2026).

Murni deterministik, tanpa I/O: semua data (snapshot coin, level terpadu,
volatilitas, funding, event) diberikan pemanggil. Bukan sinyal: menilai
RENCANA user, keputusan tetap di user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.market.coin_condition import avg_move_pct, fmt_price

MMR = 0.005            # perkiraan maintenance margin (likuidasi isolated)
WIB = timezone(timedelta(hours=7))
OK, WARN, BAD, INFO = "✅", "⚠️", "❌", "ℹ️"

USAGE = (
    "Format:\n"
    "/cek <COIN> <long|short> <entry|now> sl <harga> [tp <harga>] [lev <x>] [risk <%>]\n\n"
    "Contoh:\n"
    "/cek BTC long 82500 sl 81000 tp 86000 lev 5\n"
    "cek sol short now sl 113 tp 104\n\n"
    "• tanpa lev = spot · tanpa tp = target ke level terdekat\n"
    "• atur modal sekali: /modal 1000 (risiko default 1%)"
)


@dataclass
class Plan:
    coin: str
    side: str            # LONG / SHORT
    entry: float | None  # None = harga sekarang
    sl: float
    tp: float | None = None
    lev: float | None = None
    risk_pct: float | None = None
    raw_entry_now: bool = False


@dataclass
class Check:
    lines: list[tuple[str, str]] = field(default_factory=list)

    def add(self, mark: str, text: str) -> None:
        self.lines.append((mark, text))

    def count(self, mark: str) -> int:
        return sum(1 for m, _ in self.lines if m == mark)


def _num(tok: str) -> float:
    t = tok.strip().lower().replace(",", "").replace("$", "")
    mult = 1000.0 if t.endswith("k") else 1.0
    t = t[:-1] if t.endswith("k") else t
    return float(t) * mult


def parse_plan(text: str) -> tuple[Plan | None, str | None]:
    """'BTC long 82500 sl 81000 tp 86000 lev 5 risk 1' → Plan atau pesan error."""
    toks = [t for t in re.split(r"\s+", (text or "").strip()) if t]
    if toks and toks[0].lower().lstrip("/") in ("cek", "check"):
        toks = toks[1:]
    if len(toks) < 5:
        return None, "Data kurang.\n\n" + USAGE
    coin = toks[0].upper()
    side_map = {"long": "LONG", "buy": "LONG", "beli": "LONG", "short": "SHORT", "sell": "SHORT", "jual": "SHORT"}
    side = side_map.get(toks[1].lower())
    if not side:
        return None, f"Arah harus long/short, bukan '{toks[1]}'.\n\n" + USAGE
    try:
        now = toks[2].lower() in ("now", "sekarang", "market", "mkt")
        entry = None if now else _num(toks[2])
    except ValueError:
        return None, f"Entry '{toks[2]}' bukan angka.\n\n" + USAGE
    kv: dict[str, float] = {}
    rest = toks[3:]
    i = 0
    while i < len(rest):
        key = rest[i].lower()
        if key in ("sl", "tp", "lev", "x", "risk", "r") and i + 1 < len(rest):
            try:
                kv[{"x": "lev", "r": "risk"}.get(key, key)] = _num(rest[i + 1].rstrip("x%"))
            except ValueError:
                return None, f"Nilai '{rest[i + 1]}' untuk {key} bukan angka.\n\n" + USAGE
            i += 2
        else:
            return None, f"Bagian '{rest[i]}' tidak dikenali.\n\n" + USAGE
    if "sl" not in kv:
        return None, "Stop loss wajib diisi (sl <harga>).\n\n" + USAGE
    lev = kv.get("lev")
    if lev is not None and not (1 <= lev <= 125):
        return None, "Leverage harus 1–125."
    risk = kv.get("risk")
    if risk is not None and not (0 < risk <= 10):
        return None, "Risiko per trade harus 0–10%."
    return Plan(coin, side, entry, kv["sl"], kv.get("tp"), lev, risk, now), None


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def evaluate(plan: Plan, ctx: dict[str, Any]) -> dict[str, Any]:
    """ctx: price, trend_4h, trend_1d, rsi, levels{support,support2,resistance,resistance2},
    closes_4h, funding_rate (fraksi), label, events[list], calendar_live(bool),
    capital(float|None), risk_pct_default(float), now(datetime)."""
    price = _f(ctx.get("price"))
    entry = plan.entry if plan.entry is not None else price
    if not price or not entry:
        return {"error": "Harga coin tidak tersedia."}
    long_ = plan.side == "LONG"
    sl, tp = plan.sl, plan.tp
    if (long_ and sl >= entry) or (not long_ and sl <= entry):
        return {"error": f"SL {fmt_price(sl)} harus {'di bawah' if long_ else 'di atas'} entry {fmt_price(entry)} untuk {plan.side}."}
    if tp is not None and ((long_ and tp <= entry) or (not long_ and tp >= entry)):
        return {"error": f"TP {fmt_price(tp)} harus {'di atas' if long_ else 'di bawah'} entry untuk {plan.side}."}

    c = Check()
    lv = ctx.get("levels") or {}
    s1, s2, r1, r2 = (_f(lv.get(k)) for k in ("support", "support2", "resistance", "resistance2"))
    sl_pct = abs(entry - sl) / entry * 100

    # 1) Posisi entry vs harga sekarang
    gap = (entry - price) / price * 100
    vol = avg_move_pct(ctx.get("closes_4h"))
    if plan.entry is not None and abs(gap) > 0.3:
        need = "turun" if gap < 0 else "naik"
        far = vol is not None and abs(gap) > 3 * vol
        c.add(WARN if far else INFO,
              f"Entry {abs(gap):.1f}% dari harga sekarang (harga perlu {need} dulu) — order limit belum tentu terisi"
              + (" ; jauh (>3× gerak candle 4H)" if far else ""))

    # 2) SL vs volatilitas
    if vol:
        ratio = sl_pct / vol
        if ratio < 1:
            high_lev = bool(plan.lev and plan.lev >= 10)
            c.add(BAD if high_lev else WARN,
                  f"SL {sl_pct:.1f}% < gerak rata-rata 1 candle 4H (±{vol:.1f}%) — rawan kena noise"
                  + (f", kritis dengan leverage {plan.lev:g}×" if high_lev else ""))
        elif ratio > 6:
            c.add(INFO, f"SL lebar ({sl_pct:.1f}% ≈ {ratio:.0f}× gerak candle 4H) — ukuran posisi jadi kecil")
        else:
            c.add(OK, f"Jarak SL {sl_pct:.1f}% ≈ {ratio:.1f}× gerak candle 4H (wajar)")

    # 3) SL vs level struktur
    if long_ and s1 is not None and s1 < entry:
        if sl > s1:
            c.add(WARN, f"SL di atas support {fmt_price(s1)} — bisa kena sebelum support diuji")
        else:
            c.add(OK, f"SL di bawah support {fmt_price(s1)}")
    if not long_ and r1 is not None and r1 > entry:
        if sl < r1:
            c.add(WARN, f"SL di bawah resistance {fmt_price(r1)} — bisa kena sebelum resistance diuji")
        else:
            c.add(OK, f"SL di atas resistance {fmt_price(r1)}")

    # 4) Target & RR
    obstacle = r1 if long_ else s1
    target, target_src = tp, "TP"
    if target is None:
        if obstacle is not None and ((long_ and obstacle > entry) or (not long_ and obstacle < entry)):
            target, target_src = obstacle, f"level {'resistance' if long_ else 'support'} terdekat"
    rr = None
    if target is not None:
        rr = abs(target - entry) / abs(entry - sl)
        mark = BAD if rr < 1 else WARN if rr < 1.5 else OK
        c.add(mark, f"RR {rr:.1f} ke {target_src} {fmt_price(target)}")
        if tp is not None and obstacle is not None:
            blocks = (entry < obstacle < tp * 0.997) if long_ else (tp * 1.003 < obstacle < entry)
            if blocks:
                rr_obs = abs(obstacle - entry) / abs(entry - sl)
                c.add(WARN, f"{'Resistance' if long_ else 'Support'} {fmt_price(obstacle)} menghalangi sebelum TP (RR ke level itu {rr_obs:.1f})")
    else:
        c.add(INFO, "Tidak ada level di arah target dalam 90 hari — tentukan TP sendiri")

    # 5) Tren
    t4 = str(ctx.get("trend_4h") or "").upper()
    t1 = str(ctx.get("trend_1d") or "").upper()
    against = "BEARISH" if long_ else "BULLISH"
    with_ = "BULLISH" if long_ else "BEARISH"
    arrow = {"BULLISH": "↑", "BEARISH": "↓", "SIDEWAYS": "→"}
    tr = f"4H {arrow.get(t4, '?')} · 1D {arrow.get(t1, '?')}"
    if t4 == against and t1 == against:
        c.add(BAD, f"Melawan tren 4H & 1D ({tr})")
    elif against in (t4, t1):
        c.add(WARN, f"Melawan tren {'4H' if t4 == against else '1D'} ({tr})")
    elif t4 == with_ and t1 == with_:
        c.add(OK, f"Searah tren 4H & 1D ({tr})")
    elif with_ in (t4, t1):
        c.add(OK, f"Searah tren {'4H' if t4 == with_ else '1D'} ({tr})")
    else:
        c.add(INFO, f"Market range ({tr}) — tren belum memberi arah")

    # 6) Momentum & lokasi
    rsi = _f(ctx.get("rsi"))
    if rsi is not None:
        if long_ and rsi > 70:
            c.add(WARN, f"RSI 4H {rsi:.0f} overbought — rawan koreksi setelah entry")
        elif not long_ and rsi < 30:
            c.add(WARN, f"RSI 4H {rsi:.0f} oversold — rawan pantulan setelah entry")
    if long_ and r1 is not None and 0 < (r1 - entry) / entry * 100 < 1:
        c.add(WARN, f"Entry tepat di bawah resistance {fmt_price(r1)} (<1%)")
    if not long_ and s1 is not None and 0 < (entry - s1) / entry * 100 < 1:
        c.add(WARN, f"Entry tepat di atas support {fmt_price(s1)} (<1%)")

    # 7) Funding (keramaian)
    fr = _f(ctx.get("funding_rate"))
    if fr is not None:
        frp = fr * 100
        if long_ and frp >= 0.03:
            c.add(WARN, f"Funding {frp:+.3f}% — long ramai, rawan long squeeze")
        elif not long_ and frp <= -0.01:
            c.add(WARN, f"Funding {frp:+.3f}% — short ramai, rawan short squeeze")

    # 8) Event ekonomi 24 jam
    now = ctx.get("now") or datetime.now(timezone.utc)
    if not ctx.get("calendar_live", True):
        c.add(WARN, "Data kalender ekonomi live tidak tersedia — cek manual event 24 jam ke depan")
    for e in ctx.get("events") or []:
        try:
            dt = datetime.fromisoformat(str(e.get("datetime_utc")))
        except ValueError:
            continue
        hrs = (dt - now).total_seconds() / 3600
        if not (0 <= hrs <= 24):
            continue
        jam = dt.astimezone(WIB).strftime("%d/%m %H:%M WIB")
        if e.get("impact") == "HIGH":
            mark = BAD if (plan.lev and hrs <= 2) else WARN
            c.add(mark, f"Event HIGH {e.get('name')} {jam} ({hrs:.0f} jam lagi)")
        else:
            c.add(INFO, f"Event {e.get('name')} {jam}")

    # 9) Leverage & likuidasi
    liq = None
    if plan.lev:
        liq = entry * (1 - 1 / plan.lev + MMR) if long_ else entry * (1 + 1 / plan.lev - MMR)
        liq_before_sl = (liq >= sl) if long_ else (liq <= sl)
        if liq_before_sl:
            c.add(BAD, f"Likuidasi ±{fmt_price(liq)} terjadi SEBELUM SL — leverage terlalu tinggi")
        else:
            buffer = abs(liq - sl) / entry * 100
            c.add(OK if buffer >= 1 else WARN, f"Likuidasi ±{fmt_price(liq)} ({buffer:.1f}% di luar SL)")

    # Ukuran posisi
    sizing = None
    cap = _f(ctx.get("capital"))
    risk_pct = plan.risk_pct or _f(ctx.get("risk_pct_default")) or 1.0
    if cap:
        risk_usd = cap * risk_pct / 100
        notional = risk_usd / (sl_pct / 100)
        sizing = {
            "capital": cap, "risk_pct": risk_pct, "risk_usd": risk_usd, "notional": notional,
            "qty": notional / entry, "margin": notional / plan.lev if plan.lev else notional,
        }
        if not plan.lev and long_ and notional > cap:
            c.add(WARN, f"Ukuran posisi {fmt_price(notional)} > modal {fmt_price(cap)} — SL terlalu dekat untuk spot dengan risiko {risk_pct:g}%")
        if plan.lev and sizing["margin"] > cap:
            c.add(BAD, f"Margin {fmt_price(sizing['margin'])} > modal {fmt_price(cap)} — naikkan leverage atau perlebar SL")

    bad, warn = c.count(BAD), c.count(WARN)
    if bad:
        verdict = f"🔴 BERTENTANGAN — {bad} hal kritis"
    elif warn >= 2:
        verdict = f"🟡 NETRAL — {warn} hal perlu diperhatikan"
    elif warn == 1:
        verdict = "🟢 MENDUKUNG — 1 catatan"
    else:
        verdict = "🟢 MENDUKUNG"
    return {"entry": entry, "price": price, "sl_pct": sl_pct, "rr": rr, "target": target,
            "liq": liq, "sizing": sizing, "checks": c.lines, "verdict": verdict}


def format_result(plan: Plan, res: dict[str, Any], label: str | None = None, snapshot_ts: str = "—") -> str:
    if res.get("error"):
        return "❌ " + res["error"]
    if plan.lev:
        mode = f"futures {plan.lev:g}×"
    elif plan.side == "SHORT":
        mode = "futures, leverage belum diisi"
    else:
        mode = "spot"
    entry, price = res["entry"], res["price"]
    tp_s = ""
    if plan.tp is not None:
        tp_pct = (plan.tp - entry) / entry * 100
        tp_s = f" · TP {fmt_price(plan.tp)} ({tp_pct:+.1f}%)"
    sl_signed = (plan.sl - entry) / entry * 100
    lines = [
        f"🧭 CEK RENCANA — {plan.coin} {plan.side} ({mode})",
        f"Harga {fmt_price(price)} · entry {fmt_price(entry)}{' (harga sekarang)' if plan.entry is None else ''}"
        f" · SL {fmt_price(plan.sl)} ({sl_signed:+.1f}%){tp_s}",
        "",
        f"Penilaian: {res['verdict']}",
        "",
    ]
    order = {BAD: 0, WARN: 1, OK: 2, INFO: 3}
    for mark, text in sorted(res["checks"], key=lambda x: order.get(x[0], 9)):
        lines.append(f"{mark} {text}")
    if label and label.strip() not in ("", "• Neutral", "Neutral"):
        lines.append(f"{INFO} Kondisi coin: {label.strip()}")
    sz = res.get("sizing")
    lines.append("")
    if sz:
        lines.append(f"📐 Ukuran posisi (modal {fmt_price(sz['capital'])} · risiko {sz['risk_pct']:g}%)")
        lines.append(f"Risiko {fmt_price(sz['risk_usd'])} · nilai posisi {fmt_price(sz['notional'])} · qty {sz['qty']:.6g} {plan.coin}")
        if plan.lev:
            lines.append(f"Margin {plan.lev:g}×: {fmt_price(sz['margin'])}")
    else:
        lines.append("📐 Atur modal sekali untuk hitung ukuran posisi: /modal 1000")
    lines += ["", "ℹ️ Penilaian rencana terhadap kondisi saat ini — bukan sinyal. Likuidasi = perkiraan isolated.",
              f"🕒 Snapshot: {snapshot_ts}"]
    return "\n".join(lines)
