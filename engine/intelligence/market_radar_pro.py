"""
ALIZA MARKET RADAR PRO

Menghitung probabilitas kondisi market (BTC bottom, crash, bull run, altseason)
dari data cache dan memformat laporan radar untuk Telegram.
"""

from engine.utils.market_cache import get_market_data, get_all_market_data


# =========================
# CALCULATE PROBABILITIES
# =========================

def calculate_market_probabilities():
    """
    Ambil data BTC dan market semua coin, hitung:
    - BTC Bottom Probability (max 100)
    - Crash Probability (max 100)
    - Bull Run Probability (max 100)
    - Altseason Probability (max 100)
    Return dict dengan skor dan konteks (fear_greed, trend, phase) untuk format report.
    """
    result = {
        "bottom_probability": 0,
        "crash_probability": 0,
        "bull_probability": 0,
        "altseason_probability": 0,
        "fear_greed": None,
        "trend": None,
        "market_phase_prediction": None,
    }

    btc = get_market_data("BTC")
    if not btc or btc.get("error"):
        return result

    trend = btc.get("trend")
    rsi = btc.get("rsi")
    fear_greed = btc.get("fear_greed")
    whale_activity = btc.get("whale_activity")
    market_risk_score = btc.get("market_risk_score")
    liquidation_risk = btc.get("liquidation_risk")
    stablecoin_flow = btc.get("stablecoin_flow")
    dominance = btc.get("dominance")
    market_phase_prediction = btc.get("market_phase_prediction")

    result["fear_greed"] = fear_greed
    result["trend"] = trend
    result["market_phase_prediction"] = market_phase_prediction

    # -------------------------
    # BTC BOTTOM PROBABILITY
    # -------------------------
    bottom = 0
    if fear_greed is not None and fear_greed < 20:
        bottom += 30
    if rsi is not None and rsi < 35:
        bottom += 30
    if trend == "BEARISH":
        bottom += 20
    if whale_activity in ("HIGH", "EXTREME"):
        bottom += 20
    result["bottom_probability"] = min(bottom, 100)

    # -------------------------
    # CRASH PROBABILITY
    # -------------------------
    crash = 0
    if market_risk_score == "HIGH":
        crash += 40
    if liquidation_risk == "HIGH":
        crash += 30
    if whale_activity == "EXTREME":
        crash += 30
    result["crash_probability"] = min(crash, 100)

    # -------------------------
    # BULL RUN PROBABILITY
    # -------------------------
    bull = 0
    if trend == "BULLISH":
        bull += 40
    if stablecoin_flow == "HIGH INFLOW":
        bull += 30
    if whale_activity in ("HIGH", "EXTREME"):
        bull += 30
    result["bull_probability"] = min(bull, 100)

    # -------------------------
    # ALTSEASON PROBABILITY
    # -------------------------
    alt = 0
    markets = get_all_market_data()
    if markets:
        altcoins = [c for c in markets if c != "BTC"]
        if altcoins:
            bullish_count = sum(
                1
                for c in altcoins
                if markets.get(c) and markets[c].get("trend") == "BULLISH"
            )
            total_alt = len(altcoins)
            if total_alt > 0 and (bullish_count / total_alt) > 0.5:
                alt += 50
    if dominance is not None and dominance < 55:
        alt += 50
    result["altseason_probability"] = min(alt, 100)

    return result


# =========================
# FORMAT RADAR REPORT
# =========================

def format_radar_report(data):
    """
    Format laporan Market Radar Pro untuk Telegram (Bahasa Indonesia).
    """
    if not data:
        return "Data radar tidak tersedia."

    bottom = data.get("bottom_probability", 0)
    crash = data.get("crash_probability", 0)
    bull = data.get("bull_probability", 0)
    alt = data.get("altseason_probability", 0)
    fear = data.get("fear_greed")
    trend = data.get("trend")
    phase = data.get("market_phase_prediction")

    fear_str = fear if fear is not None else "—"
    trend_str = trend if trend else "—"
    phase_str = phase if phase else "—"

    message = (
        "📡 ALIZA MARKET RADAR PRO\n\n"
        f"BTC Bottom Probability : {bottom}%\n"
        f"Crash Probability : {crash}%\n"
        f"Bull Run Probability : {bull}%\n"
        f"Altseason Probability : {alt}%\n\n"
        "Market Context\n"
        f"Fear & Greed : {fear_str}\n"
        f"BTC Trend : {trend_str}\n"
        f"Market Phase : {phase_str}"
    )
    return message
