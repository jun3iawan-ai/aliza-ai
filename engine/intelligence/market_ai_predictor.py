# =========================
# MARKET AI PREDICTOR
# =========================

def market_phase(cycle_phase, funding_status, smart_money_signal):

    if cycle_phase == "ACCUMULATION" and smart_money_signal == "ACCUMULATION":
        return "EARLY BULL"

    if cycle_phase == "BULL":
        return "BULL TREND"

    if funding_status == "LONG OVERCROWDED":
        return "TOP FORMATION"

    if cycle_phase == "BEAR":
        return "BEAR TREND"

    return "SIDEWAYS"


# =========================
# BULL PROBABILITY
# =========================

def bull_probability(
    cycle_phase,
    whale_activity,
    smart_money_signal,
    stablecoin_flow
):

    score = 0

    if cycle_phase == "ACCUMULATION":
        score += 30

    if whale_activity in ["HIGH", "EXTREME"]:
        score += 20

    if smart_money_signal == "ACCUMULATION":
        score += 30

    if stablecoin_flow == "HIGH":
        score += 20

    return min(100, score)


# =========================
# MARKET RISK SCORE
# =========================

def market_risk_score(crash_probability, liquidation_risk):

    risk = crash_probability

    if liquidation_risk in ["LONG SQUEEZE RISK", "SHORT SQUEEZE RISK"]:
        risk += 20

    if risk > 80:
        return "EXTREME"

    if risk > 60:
        return "HIGH"

    if risk > 40:
        return "MEDIUM"

    return "LOW"