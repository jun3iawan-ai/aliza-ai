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


def _label_for_score(score: int) -> tuple[str, str, str]:
    if score <= 30:
        return ("Bearish", "🔴", "Tekanan turun dominan — tren harga dan konteks searah melemah.")
    if score <= 45:
        return ("Weak", "🟠", "Kondisi melemah — lebih banyak faktor negatif daripada positif.")
    if score <= 55:
        return ("Neutral", "⚪", "Seimbang — belum ada arah dominan.")
    if score <= 70:
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


def calculate_market_score() -> dict[str, Any]:
    """
    Skor konteks market 0-100 dari 5 komponen:
    tren harga 40 (BTC 4H/1D + breadth 4H semua coin), makro 20,
    Fear & Greed 15, funding 15 (keramaian posisi), BTC dominance 10.
    """
    components = _neutral_components()
    failed_components = 0

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
        logger.warning("market_context: price_trend component failed: %s", e)

    # 2) Makro (max 20)
    try:
        cpi = get_macro_data("CPIAUCSL", "pct_change_yoy")
        fed = get_macro_data("FEDFUNDS", "latest")
        cpi_change = _safe_float((cpi or {}).get("change") if isinstance(cpi, dict) else None)
        fed_rate = _safe_float((fed or {}).get("value") if isinstance(fed, dict) else None)
        fed_change = _safe_float((fed or {}).get("change") if isinstance(fed, dict) else None)
        if cpi_change is None or fed_rate is None:
            components["macro"] = {"score": 10, "cpi_change": cpi_change, "fed_rate": fed_rate,
                                   "fed_change": fed_change, "max": 20}
            failed_components += 1
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
                                   "fed_change": fed_change, "max": 20}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        logger.warning("market_context: macro component failed: %s", e)

    # 3) Fear & Greed (max 15)
    try:
        g = get_global_market_data() or {}
        fg = _safe_float(g.get("fear_greed"))
        if g.get("fear_greed_status") == "failed" or fg is None:
            failed_components += 1
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
        logger.warning("market_context: funding_rate component failed: %s", e)

    # 5) BTC dominance (max 10)
    try:
        g = get_global_market_data() or {}
        dom = _safe_float(g.get("btc_dominance"))
        if g.get("btc_dominance_status") == "failed" or dom is None:
            failed_components += 1
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
        logger.warning("market_context: btc_dominance component failed: %s", e)

    total_score = int(sum(int(v.get("score", 0)) for v in components.values()))
    if failed_components >= 5:
        components = _neutral_components()
        total_score = 50

    label, emoji, summary = _label_for_score(total_score)
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
    return {
        "total_score": total_score,
        "label": label,
        "emoji": emoji,
        "components": components,
        "summary": summary,
        "timestamp": now_wib,
    }


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
