"""
Market context score engine (0-100) for daily brief.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.market.funding_rate_monitor import get_all_funding_data
from engine.market.global_market_cache import get_global_market_data
from engine.market.macro_monitor import get_macro_data

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
_COINS = ("BTC", "ETH", "BNB", "SOL", "XRP")


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# Batas label (skor 0-100). Satu-satunya sumber: dipakai _label_for_score dan diekspor
# ke context.json sebagai thresholds tiga-keadaan (lihat map_label_to_alert_status).
BEARISH_MAX = 30          # skor <= 30       -> Bearish
WEAK_MAX = 45             # skor 31..45      -> Weak
NEUTRAL_MAX = 55          # skor 46..55      -> Neutral
BULLISH_MAX = 70          # skor 56..70      -> Bullish ; > 70 -> Strong Bullish
# Tiga keadaan (Bearish+Weak / Neutral / Bullish+Strong): skor < BEARISH_BELOW = bearish,
# skor > BULLISH_ABOVE = bullish, selain itu neutral.
BEARISH_BELOW = WEAK_MAX + 1
BULLISH_ABOVE = NEUTRAL_MAX


def _label_for_score(score: int) -> tuple[str, str, str]:
    if score <= BEARISH_MAX:
        return ("Bearish", "🔴", "Tekanan turun dominan — tren harga dan konteks searah melemah.")
    if score <= WEAK_MAX:
        return ("Weak", "🟠", "Kondisi melemah — lebih banyak faktor negatif daripada positif.")
    if score <= NEUTRAL_MAX:
        return ("Neutral", "⚪", "Seimbang — belum ada arah dominan.")
    if score <= BULLISH_MAX:
        return ("Bullish", "🟢", "Cenderung positif — tren harga dan konteks lebih banyak mendukung.")
    return ("Strong Bullish", "💚", "Kondisi kuat — tren harga dan konteks searah naik.")


def map_label_to_alert_status(label: str) -> str:
    """Collapse the five market-score labels into the three alert statuses."""
    normalized = str(label or "").strip()
    if normalized in {"Bearish", "Weak"}:
        return "Bearish"
    if normalized in {"Bullish", "Strong Bullish"}:
        return "Bullish"
    return "Neutral"


def _get_snapshot() -> dict[str, Any]:
    """Snapshot market (dipisah supaya mudah di-patch di test)."""
    from engine.market.market_snapshot_engine import get_market_snapshot
    return get_market_snapshot() or {}


# Bobot (9 Okt 2026): tren harga jadi komponen terbesar — versi lama tidak
# melihat arah harga sama sekali (bisa "Strong Bullish" saat semua coin turun).
_MAX = {"price_trend": 40, "macro": 20, "fear_greed": 15, "funding_rate": 15, "btc_dominance": 10}

# Lima tingkat asli (key, teks label di kode, batas atas inklusif) — dari konstanta bernama di atas.
LEVELS = (
    ("bearish", "Bearish", BEARISH_MAX),
    ("weak", "Weak", WEAK_MAX),
    ("neutral", "Neutral", NEUTRAL_MAX),
    ("bullish", "Bullish", BULLISH_MAX),
    ("strong_bullish", "Strong Bullish", sum(_MAX.values())),
)


def level_key_for_label(label_text: str, score: int | None = None) -> str:
    """Key tingkat (bearish|weak|neutral|bullish|strong_bullish) dari teks label kode."""
    for key, text, _upto in LEVELS:
        if text == label_text:
            return key
    if score is not None:  # label tak dikenal -> turunkan dari skor
        for key, _text, upto in LEVELS:
            if score <= upto:
                return key
    return "neutral"


def levels_bands() -> list[dict[str, Any]]:
    return [{"upto": upto, "key": key, "text": text} for key, text, upto in LEVELS]


def _neutral_components() -> dict[str, dict[str, Any]]:
    # Default netral = setengah bobot; total 50 bila semua sumber gagal.
    return {
        "price_trend": {"score": 20, "btc_4h": None, "btc_1d": None, "up": None, "down": None, "n": None, "max": 40},
        "macro": {"score": 10, "cpi_change": None, "fed_rate": None, "max": 20},
        "fear_greed": {"score": 8, "value": None, "max": 15},
        "funding_rate": {"score": 8, "avg_fr": None, "max": 15},
        "btc_dominance": {"score": 5, "value": None, "max": 10},
    }


_TREND_PTS = {"BULLISH": 10, "SIDEWAYS": 5, "BEARISH": 0}


def _calculate_market_score() -> dict[str, Any]:
    """
    Skor konteks market 0-100 dari 5 komponen:
    tren harga 40 (BTC 4H/1D + breadth 4H semua coin), makro 20,
    Fear & Greed 15, funding 15 (keramaian posisi), BTC dominance 10.
    """
    components = _neutral_components()
    failed_components = 0
    failed_keys: set[str] = set()

    # 1) Tren harga (max 40) = BTC 4H (10) + BTC 1D (10) + breadth 4H (20)
    try:
        data = (_get_snapshot().get("data") or {})
        btc = data.get("BTC") if isinstance(data, dict) else None
        t4 = str((btc or {}).get("trend_4h") or "").upper()
        t1 = str((btc or {}).get("trend_1d") or "").upper()
        trends = [str((md or {}).get("trend_4h") or "").upper()
                  for md in (data or {}).values() if isinstance(md, dict) and not md.get("error")]
        trends = [x for x in trends if x in _TREND_PTS]
        if not btc or not trends:
            failed_components += 1
            failed_keys.add("price_trend")
        else:
            up = sum(1 for x in trends if x == "BULLISH")
            down = sum(1 for x in trends if x == "BEARISH")
            side = len(trends) - up - down
            breadth = round(20 * (up + 0.5 * side) / len(trends))
            s = _TREND_PTS.get(t4, 5) + _TREND_PTS.get(t1, 5) + breadth
            components["price_trend"] = {
                "score": int(s), "btc_4h": t4 or None, "btc_1d": t1 or None,
                "up": up, "down": down, "n": len(trends), "max": 40,
            }
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        failed_keys.add("price_trend")
        logger.warning("market_context: price_trend component failed: %s", e)

    # 2) Makro (max 20)
    try:
        cpi = get_macro_data("CPIAUCSL", "pct_change_yoy")
        fed = get_macro_data("FEDFUNDS", "latest")
        cpi_change = _safe_float((cpi or {}).get("change") if isinstance(cpi, dict) else None)
        fed_rate = _safe_float((fed or {}).get("value") if isinstance(fed, dict) else None)
        fed_change = _safe_float((fed or {}).get("change") if isinstance(fed, dict) else None)
        # cpi_change = inflasi BULANAN (MoM); YoY ada di cpi["value"]. Skor tetap memakai MoM (lihat catatan di docs).
        cpi_d, fed_d = (cpi if isinstance(cpi, dict) else {}), (fed if isinstance(fed, dict) else {})
        ages = [d.get("age_sec") for d in (cpi_d, fed_d)
                if d.get("stale") and isinstance(d.get("age_sec"), (int, float))]
        extra = {"cpi_yoy": _safe_float(cpi_d.get("value")), "cpi_yoy_prev": _safe_float(cpi_d.get("prev_value")),
                 "stale_sec": max(ages) if ages else None}
        if cpi_change is None or fed_rate is None:
            components["macro"] = {"score": 10, "cpi_change": cpi_change, "fed_rate": fed_rate,
                                   "fed_change": fed_change, "max": 20, **extra}
            failed_components += 1
            failed_keys.add("macro")
        else:
            fed_up = fed_change is not None and fed_change > 0
            fed_stable_or_down = fed_change is None or fed_change <= 0
            if cpi_change < 0 and fed_stable_or_down:
                s = 20
            elif cpi_change < 0 and fed_up:
                s = 12
            elif cpi_change < 0.5 and not fed_up:
                s = 10
            else:
                s = 4
            components["macro"] = {"score": s, "cpi_change": cpi_change, "fed_rate": fed_rate,
                                   "fed_change": fed_change, "max": 20, **extra}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        failed_keys.add("macro")
        logger.warning("market_context: macro component failed: %s", e)

    # 3) Fear & Greed (max 15)
    try:
        g = get_global_market_data() or {}
        fg = _safe_float(g.get("fear_greed"))
        if g.get("fear_greed_status") == "failed" or fg is None:
            failed_components += 1
            failed_keys.add("fear_greed")
        else:
            if fg <= 24:
                s = 4
            elif fg <= 44:
                s = 8
            elif fg <= 55:
                s = 10
            elif fg <= 74:
                s = 13
            else:
                s = 15
            components["fear_greed"] = {"score": s, "value": fg, "max": 15}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        failed_keys.add("fear_greed")
        logger.warning("market_context: fear_greed component failed: %s", e)

    # 4) Funding (max 15) — dinilai sebagai keramaian posisi:
    #    short ramai (negatif) = bahan bakar squeeze naik; long ramai = rawan flush.
    try:
        fdata = get_all_funding_data() or {}
        rates = []
        for c in _COINS:
            row = fdata.get(c) if isinstance(fdata, dict) else None
            fr = _safe_float((row or {}).get("funding_rate"))
            if fr is not None:
                rates.append(fr)
        if not rates:
            failed_components += 1
            failed_keys.add("funding_rate")
        else:
            avg_fr_pct = (sum(rates) / len(rates)) * 100.0
            if avg_fr_pct < -0.05:
                s = 15
            elif avg_fr_pct < -0.01:
                s = 11
            elif avg_fr_pct <= 0.01:
                s = 8
            elif avg_fr_pct <= 0.05:
                s = 6
            elif avg_fr_pct <= 0.1:
                s = 3
            else:
                s = 0
            components["funding_rate"] = {"score": s, "avg_fr": avg_fr_pct, "max": 15}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        failed_keys.add("funding_rate")
        logger.warning("market_context: funding_rate component failed: %s", e)

    # 5) BTC dominance (max 10)
    try:
        g = get_global_market_data() or {}
        dom = _safe_float(g.get("btc_dominance"))
        if g.get("btc_dominance_status") == "failed" or dom is None:
            failed_components += 1
            failed_keys.add("btc_dominance")
        else:
            if dom > 60:
                s = 3
            elif dom >= 50:
                s = 6
            else:
                s = 10
            components["btc_dominance"] = {"score": s, "value": dom, "max": 10}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        failed_keys.add("btc_dominance")
        logger.warning("market_context: btc_dominance component failed: %s", e)

    total_score = int(sum(int(v.get("score", 0)) for v in components.values()))
    if failed_components >= 5:
        components = _neutral_components()
        total_score = 50

    label, emoji, summary = _label_for_score(total_score)
    now = datetime.now(WIB)
    now_wib = now.strftime("%Y-%m-%d %H:%M:%S WIB")
    return {
        "total_score": total_score,
        "label": label,
        "emoji": emoji,
        "components": components,
        "summary": summary,
        "timestamp": now_wib,
        "timestamp_iso": now.isoformat(timespec="seconds"),
        "failed_components": failed_components,
        "component_ok": {k: k not in failed_keys for k in _MAX},
    }


def calculate_market_score() -> dict[str, Any]:
    """Hitung skor, lalu ekspor hasilnya ke context.json (best-effort, tidak pernah melempar)."""
    result = _calculate_market_score()
    try:
        from engine.market.market_context_export import export_context
        export_context(result)
    except Exception as e:  # noqa: BLE001
        logger.warning("market_context: ekspor context.json gagal: %s", e)
    return result


_ARROW = {"BULLISH": "↑", "BEARISH": "↓", "SIDEWAYS": "→"}


def _stale_suffix(stale_sec: Any) -> str:
    """' | data cache N jam/hari' bila makro memakai data terakhir yang berhasil (FRED sedang gagal)."""
    try:
        sec = float(stale_sec)
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    hours = sec / 3600
    return f" | data cache {max(1, round(hours))} jam" if hours < 48 else f" | data cache {int(hours // 24)} hari"


def build_components_view(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Baris breakdown (nama, skor, max, detail) — SATU sumber untuk pesan Telegram
    /market_context dan context.json."""
    c = result.get("components", {})
    pt = c.get("price_trend") or {}
    macro = c.get("macro") or {}
    fg = c.get("fear_greed") or {}
    fr = c.get("funding_rate") or {}
    dom = c.get("btc_dominance") or {}

    if pt.get("n"):
        n, up, down = pt["n"], pt.get("up") or 0, pt.get("down") or 0
        pt_label = (f"BTC 4H {_ARROW.get(pt.get('btc_4h'), '?')} 1D {_ARROW.get(pt.get('btc_1d'), '?')}"
                    f" · {up}/{n} coin 4H naik, {down}/{n} turun")
    else:
        pt_label = "data tidak tersedia"
    cpi_change, fed_rate, fed_change = macro.get("cpi_change"), macro.get("fed_rate"), macro.get("fed_change")
    cpi_label = "—" if cpi_change is None else f"{float(cpi_change):+.2f}%"
    if cpi_change is not None and macro.get("cpi_yoy") is not None:
        cpi_label += f" (YoY {float(macro['cpi_yoy']):.2f}%)"
    fed_label = "—" if fed_rate is None else f"{float(fed_rate):.2f}%"
    if fed_change is not None:
        fed_label += " (naik)" if fed_change > 0 else " (turun)" if fed_change < 0 else " (tetap)"
    fg_val, fr_val, dom_val = fg.get("value"), fr.get("avg_fr"), dom.get("value")
    fg_label = "—" if fg_val is None else f"{float(fg_val):.0f}"
    if fr_val is None:
        fr_label = "—"
    else:
        frv = float(fr_val)
        fr_label = f"{frv:+.4f}% " + ("(short ramai)" if frv < -0.01 else "(long ramai)" if frv > 0.01 else "(seimbang)")
    dom_label = "—" if dom_val is None else f"{float(dom_val):.1f}%"
    ok = result.get("component_ok") or {}

    return [
        {"key": "trend", "name": "Tren harga", "score": pt.get("score", 0), "max": _MAX["price_trend"], "detail": pt_label,
         "ok": bool(ok.get("price_trend", True))},
        {"key": "macro", "name": "Makro", "score": macro.get("score", 0), "max": _MAX["macro"],
         "detail": f"CPI MoM: {cpi_label} | Fed: {fed_label}{_stale_suffix(macro.get('stale_sec'))}",
         "ok": bool(ok.get("macro", True))},
        {"key": "fng", "name": "Fear & Greed", "score": fg.get("score", 0), "max": _MAX["fear_greed"],
         "detail": f"nilai: {fg_label}", "ok": bool(ok.get("fear_greed", True))},
        {"key": "funding", "name": "Funding", "score": fr.get("score", 0), "max": _MAX["funding_rate"],
         "detail": f"avg: {fr_label}", "ok": bool(ok.get("funding_rate", True))},
        {"key": "dominance", "name": "BTC Dominance", "score": dom.get("score", 0), "max": _MAX["btc_dominance"],
         "detail": f"nilai: {dom_label}", "ok": bool(ok.get("btc_dominance", True))},
    ]


def format_context_for_brief() -> str:
    """Format regime-based market context section for morning brief."""
    r = calculate_market_score()
    score = r.get('total_score', 50)
    label = r.get('label', 'Neutral')

    # Selaras dengan batas label di _label_for_score (≤30/≤45/≤55/≤70).
    regime, risk = {
        "Strong Bullish": ("Trending Bullish", "Low"),
        "Bullish": ("Neutral-Bullish", "Moderate"),
        "Neutral": ("Ranging", "Neutral"),
        "Weak": ("Neutral-Bearish", "Elevated"),
        "Bearish": ("Risk-Off", "High"),
    }.get(label, ("Ranging", "Neutral"))

    c = r.get('components', {})
    fg_val = (c.get('fear_greed') or {}).get('value', 50)
    dom_val = (c.get('btc_dominance') or {}).get('value', 50)
    fr_avg = (c.get('funding_rate') or {}).get('avg_fr', 0)

    try:
        fg_int = int(round(float(fg_val)))
    except (TypeError, ValueError):
        fg_int = 50
    try:
        dom_f = float(dom_val)
    except (TypeError, ValueError):
        dom_f = 50.0
    try:
        fr_f = float(fr_avg)
    except (TypeError, ValueError):
        fr_f = 0.0

    return (
        "🎯 KONDISI MARKET\n"
        f"Regime : {regime} | Risk: {risk}\n"
        f"F&G    : {fg_int} ({'Extreme Fear' if fg_int <= 25 else 'Fear' if fg_int <= 46 else 'Neutral' if fg_int <= 54 else 'Greed' if fg_int <= 75 else 'Extreme Greed'}) | BTC.D: {dom_f:.1f}%\n"
        f"FR avg : {fr_f:+.4f}%\n"
        f"📌 {r.get('summary', 'Seimbang — belum ada arah dominan.')}"
    )
