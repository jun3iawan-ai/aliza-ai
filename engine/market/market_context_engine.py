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
from engine.trading.signal_engine import scan_for_signals

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
        return ("Bearish", "🔴", "Hindari buka posisi baru — tunggu konfirmasi reversal.")
    if score <= 45:
        return ("Weak", "🟠", "Kondisi lemah — jika entry, sizing kecil dan SL ketat.")
    if score <= 55:
        return ("Neutral", "⚪", "Pasar sideways — tunggu breakout atau sinyal yang jelas.")
    if score <= 70:
        return ("Bullish", "🟢", "Kondisi mendukung — pertimbangkan entry dengan manajemen risiko normal.")
    return ("Strong Bullish", "💚", "Kondisi sangat baik — peluang swing terbuka, pantau entry di pullback.")


def _neutral_components() -> dict[str, dict[str, Any]]:
    # Balanced neutral defaults; total = 50 when all data sources fail.
    return {
        "fear_greed": {"score": 10, "value": None, "max": 20},
        "btc_dominance": {"score": 8, "value": None, "max": 15},
        "funding_rate": {"score": 12, "avg_fr": None, "max": 25},
        "macro": {"score": 12, "cpi_change": None, "fed_rate": None, "max": 25},
        "technical": {"score": 8, "has_signal": False, "max": 15},
    }


def calculate_market_score() -> dict[str, Any]:
    """
    Calculate aggregate market context score from 5 components.
    """
    components = _neutral_components()
    failed_components = 0

    # 1) Fear & Greed (max 20)
    try:
        g = get_global_market_data() or {}
        fg = _safe_float(g.get("fear_greed"))
        if fg is None:
            failed_components += 1
        else:
            if fg <= 24:
                s = 5
            elif fg <= 44:
                s = 10
            elif fg <= 55:
                s = 13
            elif fg <= 74:
                s = 17
            else:
                s = 20
            components["fear_greed"] = {"score": s, "value": fg, "max": 20}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        logger.warning("market_context: fear_greed component failed: %s", e)

    # 2) BTC Dominance (max 15)
    try:
        g = get_global_market_data() or {}
        dom = _safe_float(g.get("btc_dominance"))
        if dom is None:
            failed_components += 1
        else:
            if dom > 60:
                s = 5
            elif dom >= 50:
                s = 10
            else:
                s = 15
            components["btc_dominance"] = {"score": s, "value": dom, "max": 15}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        logger.warning("market_context: btc_dominance component failed: %s", e)

    # 3) Funding Rate (max 25)
    try:
        data = get_all_funding_data() or {}
        rates = []
        for c in _COINS:
            row = data.get(c) if isinstance(data, dict) else None
            fr = _safe_float((row or {}).get("funding_rate"))
            if fr is not None:
                rates.append(fr)
        if not rates:
            failed_components += 1
        else:
            avg_fr_pct = (sum(rates) / len(rates)) * 100.0
            if avg_fr_pct < -0.05:
                s = 20
            elif avg_fr_pct <= 0.05:
                s = 25
            elif avg_fr_pct <= 0.1:
                s = 15
            else:
                s = 5
            components["funding_rate"] = {"score": s, "avg_fr": avg_fr_pct, "max": 25}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        logger.warning("market_context: funding_rate component failed: %s", e)

    # 4) Macro (max 25)
    try:
        cpi = get_macro_data("CPIAUCSL", "pct_change_yoy")
        fed = get_macro_data("FEDFUNDS", "latest")
        cpi_change = _safe_float((cpi or {}).get("change") if isinstance(cpi, dict) else None)
        fed_rate = _safe_float((fed or {}).get("value") if isinstance(fed, dict) else None)
        fed_change = _safe_float((fed or {}).get("change") if isinstance(fed, dict) else None)

        if cpi_change is None or fed_rate is None:
            # Neutral when macro data unavailable.
            components["macro"] = {"score": 12, "cpi_change": cpi_change, "fed_rate": fed_rate, "max": 25}
            failed_components += 1
        else:
            fed_up = fed_change is not None and fed_change > 0
            fed_stable_or_down = fed_change is None or fed_change <= 0
            if cpi_change < 0 and fed_stable_or_down:
                s = 25
            elif cpi_change < 0 and fed_up:
                s = 15
            elif cpi_change < 0.5 and not fed_up:
                s = 12
            else:
                s = 5
            components["macro"] = {"score": s, "cpi_change": cpi_change, "fed_rate": fed_rate, "max": 25}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        logger.warning("market_context: macro component failed: %s", e)

    # 5) Technical Signal (max 15)
    try:
        sig = scan_for_signals()
        if not sig or not isinstance(sig, dict):
            components["technical"] = {"score": 5, "has_signal": False, "max": 15}
        else:
            conf = _safe_float(sig.get("confidence")) or 0.0
            if conf > 70:
                s = 15
            elif conf >= 50:
                s = 10
            else:
                s = 7
            components["technical"] = {"score": s, "has_signal": True, "max": 15}
    except Exception as e:  # noqa: BLE001
        failed_components += 1
        logger.warning("market_context: technical component failed: %s", e)

    total_score = int(sum(int(v.get("score", 0)) for v in components.values()))

    # If all sources fail, enforce neutral 50 by spec.
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

    if score >= 70:
        regime, risk = 'Trending Bullish', 'Low'
    elif score >= 55:
        regime, risk = 'Neutral-Bullish', 'Moderate'
    elif score >= 45:
        regime, risk = 'Ranging', 'Neutral'
    elif score >= 30:
        regime, risk = 'Neutral-Bearish', 'Elevated'
    else:
        regime, risk = 'Risk-Off', 'High'

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
        f"📌 {r.get('summary', 'Pasar sideways — tunggu breakout atau sinyal yang jelas.')}"
    )
