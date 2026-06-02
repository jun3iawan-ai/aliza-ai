"""
ALIZA SPOT TRADING ENGINE v1

Memberikan sinyal BUY (akumulasi / pullback) dan EXIT untuk spot.
Modul tambahan; tidak mengubah pipeline futures (market_cache → TradingBrain → trade_setup).
"""


def analyze_spot_opportunity(symbol: str, market_data: dict, intelligence: dict) -> dict:
    """
    Analisis peluang spot: BUY (ACCUMULATION / PULLBACK) atau EXIT.

    Args:
        symbol: Simbol coin (BTC, ETH, ...).
        market_data: Dict dari snapshot["data"][symbol] (trend, rsi, support, resistance, price).
        intelligence: Dict dari snapshot["market_intelligence"] (market_regime, dll).

    Returns:
        {
            "signal": "BUY" | "WAIT" | "EXIT",
            "type": "ACCUMULATION" | "PULLBACK" | None,
            "reason": str,
            "confidence": int
        }
    """
    if not market_data or not isinstance(market_data, dict):
        return _result("WAIT", None, "Data tidak tersedia", 0)

    trend = (market_data.get("trend") or "").strip().upper()
    rsi = _safe_float(market_data.get("rsi"))
    price = _safe_float(market_data.get("price"))
    support = _safe_float(market_data.get("support"))
    resistance = _safe_float(market_data.get("resistance"))
    market_regime = (intelligence.get("market_regime") or "").strip().upper() if intelligence else ""

    # CASE 3 — EXIT (prioritas pertama)
    if rsi is not None and rsi >= 70:
        return _result("EXIT", None, "RSI overbought (≥70)", 75)
    if trend and trend != "BULLISH" and trend != "STRONG_BULLISH":
        return _result("EXIT", None, "Trend tidak bullish", 75)

    # Di bawah ini: trend bullish, RSI < 70
    if not trend or trend not in ("BULLISH", "STRONG_BULLISH"):
        return _result("WAIT", None, "Menunggu konfirmasi trend", 0)

    # CASE 2 — PULLBACK (RSI < 50, harga dekat support)
    if rsi is not None and rsi < 50 and support is not None and support > 0 and price is not None:
        near_support = price <= support * 1.02
        if near_support:
            return _result("BUY", "PULLBACK", "Market bullish + pullback ke support", 80)

    # CASE 1 — ACCUMULATION (45 <= RSI <= 65, market_regime TREND)
    if rsi is not None and 45 <= rsi <= 65 and market_regime == "TREND":
        return _result("BUY", "ACCUMULATION", "Trend bullish, RSI zona akumulasi, regime trend", 70)

    # DEFAULT
    return _result("WAIT", None, "Belum ada setup spot yang memenuhi kriteria", 0)


def _result(signal: str, type_: str | None, reason: str, confidence: int) -> dict:
    return {
        "signal": signal,
        "type": type_,
        "reason": reason,
        "confidence": confidence,
    }


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
