"""
ALIZA SIGNAL QUALITY ENGINE

Menghitung Trade Score (0–100) dan quality label untuk setiap opportunity.
Layer tambahan; tidak mengubah pipeline.
"""

import logging


def _trend_alignment_points(trend_alignment):
    """Trend Alignment: STRONG_* → 25, BULLISH/BEARISH → 18, PARTIAL → 12, MIXED → 5."""
    a = (trend_alignment or "").strip().upper()
    if a in ("STRONG_BULLISH", "STRONG_BEARISH"):
        return 25
    if a in ("BULLISH", "BEARISH"):
        return 18
    if a == "PARTIAL":
        return 12
    if a == "MIXED":
        return 5
    return 0


def _rr_points(rr):
    """Risk Reward: rr ≥ 3 → 20, ≥ 2 → 15, ≥ 1.5 → 10, else 5."""
    if rr is None:
        return 5
    try:
        r = float(rr)
        if r >= 3:
            return 20
        if r >= 2:
            return 15
        if r >= 1.5:
            return 10
    except (TypeError, ValueError):
        pass
    return 5


def _confidence_points(confidence):
    """Confidence: score += confidence * 0.2 (max 20 if confidence 100)."""
    if confidence is None:
        return 0
    try:
        c = float(confidence)
        return min(20, c * 0.2)
    except (TypeError, ValueError):
        return 0


def _regime_points(market_regime):
    """Market Regime: TREND → 15, RANGE → 8, DOWNTREND → 10, VOLATILE → 5."""
    r = (market_regime or "").strip().upper()
    if r == "TREND":
        return 15
    if r == "RANGE":
        return 8
    if r == "DOWNTREND":
        return 10
    if r == "VOLATILE":
        return 5
    return 0


def _whale_points(whale_pressure):
    """Whale Pressure: BUYING → 10, SELLING → 5, NEUTRAL → 3."""
    w = (whale_pressure or "").strip().upper()
    if w == "BUYING":
        return 10
    if w == "SELLING":
        return 5
    if w == "NEUTRAL":
        return 3
    return 0


def _market_risk_points(market_risk_score):
    """Market Risk: HIGH → -10, MEDIUM → -5, LOW → 0."""
    r = (market_risk_score or "").strip().upper()
    if r == "HIGH":
        return -10
    if r == "MEDIUM":
        return -5
    return 0


def calculate_signal_quality(opportunity, snapshot):
    """
    Hitung Trade Score (0–100) dan quality label.

    opportunity: dict dengan coin, setup, rr, confidence, trend_alignment, market_risk_score.
    snapshot: dari get_market_snapshot(); dipakai untuk market_intelligence (regime, whale_pressure).

    Bobot: Trend Alignment 25, RR 20, Confidence 20, Market Regime 15, Whale 10, Market Risk 10.
    quality: score ≥ 80 ELITE, ≥ 70 HIGH, ≥ 60 GOOD, ≥ 50 MEDIUM, else LOW.

    Return: {"score": int, "quality": str}
    """
    result = {"score": 0, "quality": "LOW"}
    try:
        if not opportunity or not isinstance(opportunity, dict):
            return result

        score = 0.0
        score += _trend_alignment_points(opportunity.get("trend_alignment"))
        score += _rr_points(opportunity.get("rr"))
        score += _confidence_points(opportunity.get("confidence"))

        mi = (snapshot or {}).get("market_intelligence") or {}
        if isinstance(mi, dict):
            score += _regime_points(mi.get("market_regime"))
            score += _whale_points(mi.get("whale_pressure"))
        score += _market_risk_points(opportunity.get("market_risk_score"))

        score = max(0, min(100, round(score)))
        result["score"] = int(score)

        if score >= 80:
            result["quality"] = "ELITE"
        elif score >= 70:
            result["quality"] = "HIGH"
        elif score >= 60:
            result["quality"] = "GOOD"
        elif score >= 50:
            result["quality"] = "MEDIUM"
        else:
            result["quality"] = "LOW"

        return result
    except Exception as e:
        logging.debug("signal_quality_engine: %s", e)
        return result
