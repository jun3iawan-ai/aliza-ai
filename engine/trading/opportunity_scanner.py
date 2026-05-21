"""
ALIZA OPPORTUNITY SCANNER

Scan peluang trading dari data snapshot yang tervalidasi.
"""

import logging
from datetime import datetime

from engine.market.market_snapshot_engine import get_market_snapshot, is_snapshot_valid

try:
    from engine.brain.opportunity_ranker import rank_opportunities
except ImportError:
    rank_opportunities = None

try:
    from engine.brain.signal_quality_engine import calculate_signal_quality
except ImportError:
    calculate_signal_quality = None

# Snapshot dianggap fresh jika umur ≤ 90 detik
SNAPSHOT_MAX_AGE_SEC = 90


def _snapshot_age_seconds(snapshot):
    """Umur snapshot dalam detik; None timestamp = dianggap sangat lama."""
    ts = snapshot.get("timestamp")
    if ts is None:
        return float("inf")
    try:
        now = datetime.utcnow()
        delta = now - ts
        return delta.total_seconds()
    except Exception:
        return float("inf")


def _get_data_for_scan():
    """
    Data untuk scan selalu dari snapshot yang valid.
    Tidak ada fallback non-snapshot untuk menjaga konsistensi global.
    """
    snapshot = get_market_snapshot()
    if not is_snapshot_valid(snapshot, SNAPSHOT_MAX_AGE_SEC):
        logging.warning("GLOBAL GUARD: SNAPSHOT INVALID — ABORTING PROCESS")
        logging.warning("SNAPSHOT STALE — NO FALLBACK ALLOWED")
        return {}
    return snapshot.get("data") or {}


def scan_opportunities_from_data(market_data_dict):
    """
    Scan peluang dari dict market data (symbol -> market_data).
    Filter: trade_setup ada, risk_reward ≥ 1.3; sort by RR descending.
    """
    if not market_data_dict:
        return []

    opportunities = []
    for coin, data in market_data_dict.items():
        if not data:
            continue
        trade = data.get("trade_setup")
        if not trade:
            continue
        rr = trade.get("risk_reward")
        if rr is None:
            continue
        if rr < 1.3:
            continue
        opportunities.append({
            "coin": coin,
            "setup": trade.get("setup"),
            "entry": trade.get("entry"),
            "sl": trade.get("sl"),
            "tp1": trade.get("tp1"),
            "tp2": trade.get("tp2"),
            "rr": rr,
            "trend": data.get("trend"),
            "confidence": trade.get("confidence"),
            "risk_quality": trade.get("risk_quality"),
            "trend_alignment": data.get("trend_alignment"),
            "market_risk_score": data.get("market_risk_score"),
        })
    opportunities.sort(key=lambda x: x["rr"], reverse=True)
    if rank_opportunities is not None:
        opportunities = rank_opportunities(opportunities)
    if calculate_signal_quality is not None:
        try:
            snapshot = get_market_snapshot()
            for opp in opportunities:
                quality = calculate_signal_quality(opp, snapshot)
                opp["score"] = quality.get("score", 0)
                opp["signal_quality"] = quality.get("quality", "LOW")
        except Exception:
            pass
    return opportunities


def scan_opportunities():
    """
    Scan peluang dengan data snapshot tervalidasi.
    """
    data = _get_data_for_scan()
    return scan_opportunities_from_data(data)


def format_opportunities_message(opportunities, max_items=3):
    """Format list opportunity ke pesan Telegram."""
    if not opportunities:
        return "Tidak ada peluang trading saat ini."
    top = opportunities[:max_items]
    message = "🎯 TOP TRADING OPPORTUNITY\n\n"
    sep = "\n━━━━━━━━━━━━━━\n\n"
    for i, opp in enumerate(top, start=1):
        coin = opp.get("coin", "")
        setup = opp.get("setup", "")
        entry = opp.get("entry")
        sl = opp.get("sl")
        tp1 = opp.get("tp1")
        tp2 = opp.get("tp2")
        rr = round(opp.get("rr", 0), 2)
        trend = opp.get("trend") or "—"
        confidence = opp.get("confidence")
        risk_quality = opp.get("risk_quality") or "—"
        message += f"{i}️⃣ {coin} {setup}\n"
        message += f"Trend : {trend}\n"
        if entry is not None:
            message += f"Entry : {round(entry, 2)}\n"
        if sl is not None:
            message += f"SL : {round(sl, 2)}\n"
        if tp1 is not None:
            message += f"TP1 : {round(tp1, 2)}\n"
        if tp2 is not None:
            message += f"TP2 : {round(tp2, 2)}\n"
        message += f"RR : {rr}\n"
        if confidence is not None:
            message += f"Confidence : {confidence}\n"
        if risk_quality:
            message += f"Risk Quality : {risk_quality}\n"
        signal_quality = opp.get("signal_quality")
        trade_score = opp.get("score")
        if signal_quality is not None:
            message += f"Signal Quality : {signal_quality}\n"
        if trade_score is not None:
            message += f"Trade Score : {trade_score}\n"
        if i < len(top):
            message += sep
    return message


def opportunity_report():
    """Laporan opportunity top 3 (untuk backward compatibility)."""
    return format_opportunities_message(scan_opportunities(), max_items=3)
