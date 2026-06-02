"""
ALIZA EXPLAIN ENGINE

Menjelaskan keputusan trading: kenapa Aliza tidak memberikan trade untuk coin tertentu.
Hanya membaca snapshot dan TradingBrain; tidak memanggil API.
"""

import logging

try:
    from engine.brain.trading_brain import TradingBrain
except ImportError:
    TradingBrain = None


def explain_trade_decision(symbol, snapshot):
    """
    Analisis kenapa setup NO SETUP atau menampilkan ringkasan jika setup valid.

    Args:
        symbol: Simbol coin (BTC, ETH, ...)
        snapshot: Dict dari get_market_snapshot(), punya snapshot["data"][symbol]

    Returns:
        {
            "symbol": str,
            "trend": str,
            "rsi": float or None,
            "alignment": str,
            "setup": str,
            "rr": float or None,
            "confidence": int,
            "reason": str,
        }
        atau None jika symbol tidak ada di snapshot.
    """
    if not snapshot or not isinstance(snapshot, dict):
        return None
    data = snapshot.get("data") or {}
    if symbol not in data:
        return None

    market_data = data[symbol]
    if not market_data or not isinstance(market_data, dict):
        return None

    trend = market_data.get("trend")
    rsi = market_data.get("rsi")
    support = market_data.get("support")
    resistance = market_data.get("resistance")
    price = market_data.get("price")
    trend_alignment = (market_data.get("trend_alignment") or "").strip().upper() or "UNKNOWN"

    setup = "NO SETUP"
    risk_reward = None
    confidence = 0
    reason = "Market belum memberikan setup yang valid"

    if TradingBrain is None:
        return {
            "symbol": symbol,
            "trend": trend,
            "rsi": rsi,
            "alignment": trend_alignment or "UNKNOWN",
            "setup": setup,
            "rr": risk_reward,
            "confidence": confidence,
            "reason": "Engine tidak tersedia",
        }

    try:
        brain = TradingBrain()
        result = brain.analyze(market_data)
        if result:
            setup = result.get("setup") or "NO SETUP"
            risk_reward = result.get("risk_reward")
            confidence = result.get("confidence") or 0
    except Exception as e:
        logging.debug("explain_engine TradingBrain.analyze error: %s", e)
        reason = "Error saat analisis"

    if setup == "NO SETUP" and reason == "Market belum memberikan setup yang valid":
        reason = _infer_no_setup_reason_with_price(
            trend=trend,
            rsi=rsi,
            support=support,
            resistance=resistance,
            price=price,
            trend_alignment=trend_alignment,
            rr=risk_reward,
        )

    return {
        "symbol": symbol,
        "trend": trend,
        "rsi": rsi,
        "alignment": trend_alignment or "UNKNOWN",
        "setup": setup,
        "rr": risk_reward,
        "confidence": confidence,
        "reason": reason,
    }


def _infer_no_setup_reason_with_price(trend, rsi, support, resistance, price, trend_alignment, rr):
    """Tentukan alasan utama NO SETUP (dengan price untuk proximity)."""
    if trend_alignment in ("MIXED", "UNKNOWN"):
        return "Trend alignment lemah"
    try:
        rsi_val = float(rsi) if rsi is not None else None
    except (TypeError, ValueError):
        rsi_val = None
    if rsi_val is not None:
        if rsi_val >= 70:
            return "RSI terlalu tinggi"
        if rsi_val <= 30:
            return "RSI terlalu rendah"
    try:
        price_val = float(price) if price is not None else None
        res_val = float(resistance) if resistance is not None else None
        sup_val = float(support) if support is not None else None
        if price_val is not None and res_val is not None and res_val > 0:
            if price_val > res_val * 0.98:
                return "Harga terlalu dekat resistance"
        if price_val is not None and sup_val is not None and sup_val > 0:
            if price_val < sup_val * 1.02:
                return "Harga terlalu dekat support"
    except (TypeError, ValueError):
        pass
    if rr is not None:
        try:
            rr_val = float(rr)
            if rr_val < 2:
                return "Risk reward terlalu kecil"
        except (TypeError, ValueError):
            pass
    return "Market belum memberikan setup yang valid"
