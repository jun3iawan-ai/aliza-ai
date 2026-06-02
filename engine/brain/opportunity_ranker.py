"""
ALIZA OPPORTUNITY RANKER

Ranking peluang trading berdasarkan score: RR, confidence, trend alignment, market risk.
Digunakan oleh /setfutures untuk menampilkan top 3 peluang terbaik.
"""

import logging


def _alignment_bonus(trend_alignment):
    """STRONG_BULLISH/STRONG_BEARISH +20, BULLISH/BEARISH +10, lainnya 0."""
    a = (trend_alignment or "").strip().upper()
    if a in ("STRONG_BULLISH", "STRONG_BEARISH"):
        return 20
    if a in ("BULLISH", "BEARISH"):
        return 10
    return 0


def _risk_penalty(market_risk_score):
    """HIGH -10, MEDIUM -5, LOW/lainnya 0 (dikurangi agar opportunity score tidak terlalu rendah)."""
    r = (market_risk_score or "").strip().upper()
    if r == "HIGH":
        return 10
    if r == "MEDIUM":
        return 5
    return 0


def rank_opportunities(opportunities):
    """
    Hitung score tiap opportunity, urutkan by score DESC, return top 3.

    Score = (rr * 40) * (confidence * 0.4) + alignment_bonus - risk_penalty.
    Field tambahan: opportunity["score"].
    """
    if not opportunities:
        logging.debug("Opportunity ranking completed")
        return []

    try:
        for opp in opportunities:
            rr = opp.get("rr")
            confidence = opp.get("confidence")
            trend_alignment = opp.get("trend_alignment")
            market_risk_score = opp.get("market_risk_score")

            try:
                rr_val = float(rr) if rr is not None else 0.0
            except (TypeError, ValueError):
                rr_val = 0.0
            try:
                conf_val = float(confidence) if confidence is not None else 0.0
            except (TypeError, ValueError):
                conf_val = 0.0

            base = (rr_val * 40) * (conf_val * 0.4)
            bonus = _alignment_bonus(trend_alignment)
            penalty = _risk_penalty(market_risk_score)
            opp["score"] = base + bonus - penalty
            coin = opp.get("coin", "")
            setup = opp.get("setup", "")
            logging.debug("Opportunity score %s %s = %s", coin, setup, opp["score"])

        ranked = sorted(opportunities, key=lambda x: x.get("score", 0), reverse=True)
        top3 = ranked[:3]
        logging.debug("Opportunity ranking completed")
        return top3
    except Exception as e:
        logging.debug("Opportunity ranker error: %s", e)
        return opportunities[:3] if opportunities else []
