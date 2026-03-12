"""
ALIZA MARKET INTELLIGENCE SYSTEM

Analisis kondisi market crypto secara global (BTC context, bottom zone,
crash risk, altseason, market cycle) dan menghasilkan list alert untuk Telegram.
"""

import logging

from engine.utils.market_cache import get_market_data, get_all_market_data


# =========================
# SCAN MARKET INTELLIGENCE
# =========================

def scan_market_intelligence():
    """
    Ambil data BTC dan market semua coin, terapkan detektor:
    BTC Bottom Zone, Crash Risk, Altseason Potential, Market Cycle.
    Return list string alert (untuk dikirim ke Telegram).
    """
    alerts = []

    try:
        btc = get_market_data("BTC")
    except Exception as e:
        logging.warning("market_intelligence get_market_data BTC: %s", e)
        btc = None

    if not btc or btc.get("error"):
        return alerts

    trend = btc.get("trend")
    rsi = btc.get("rsi")
    fear_greed = btc.get("fear_greed")
    dominance = btc.get("dominance")
    market_risk_score = btc.get("market_risk_score")
    liquidation_risk = btc.get("liquidation_risk")
    market_phase_prediction = btc.get("market_phase_prediction")

    # -------------------------
    # BTC BOTTOM DETECTOR
    # -------------------------
    try:
        if (
            fear_greed is not None
            and fear_greed < 20
            and rsi is not None
            and rsi < 35
            and trend == "BEARISH"
        ):
            alerts.append(
                "🧠 BTC BOTTOM ZONE\n\n"
                "Fear & Greed sangat rendah.\n"
                "Market kemungkinan mendekati fase akumulasi."
            )
    except Exception as e:
        logging.warning("market_intelligence BTC bottom: %s", e)

    # -------------------------
    # CRASH DETECTOR
    # -------------------------
    try:
        if (
            market_risk_score == "HIGH"
            and liquidation_risk == "HIGH"
        ):
            alerts.append(
                "⚠️ MARKET CRASH RISK\n\n"
                "Likuidasi besar berpotensi terjadi."
            )
    except Exception as e:
        logging.warning("market_intelligence crash: %s", e)

    # -------------------------
    # MARKET CYCLE UPDATE
    # -------------------------
    try:
        if market_phase_prediction:
            phase = market_phase_prediction
            alerts.append(
                "📊 MARKET CYCLE UPDATE\n\n"
                f"Market berada pada fase {phase}."
            )
    except Exception as e:
        logging.warning("market_intelligence cycle: %s", e)

    # -------------------------
    # ALTSEASON DETECTOR
    # -------------------------
    try:
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
                if total_alt > 0 and (bullish_count / total_alt) > 0.6:
                    alerts.append(
                        "🚀 ALTSEASON POTENTIAL\n\n"
                        "Banyak altcoin menunjukkan tren bullish."
                    )
    except Exception as e:
        logging.warning("market_intelligence altseason: %s", e)

    return alerts
