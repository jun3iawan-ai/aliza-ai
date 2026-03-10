# =========================
# MARKET REPORT FORMATTER
# =========================

def format_market_report(data):

    price = data.get("price")
    trend = data.get("trend")

    cycle = data.get("cycle_phase")

    ai_phase = data.get("market_phase_prediction")

    bull_prob = data.get("bull_probability")

    whale = data.get("whale_activity")

    stablecoin = data.get("stablecoin_flow")

    funding = data.get("funding_status")

    oi = data.get("open_interest_level")

    liquidation = data.get("liquidation_risk")

    risk = data.get("market_risk_score")

    message = f"""
📊 INTELIJEN MARKET BTC

Harga BTC: ${price}
Trend: {trend}

Siklus Bitcoin: {cycle}
Prediksi AI: {ai_phase}

Probabilitas Bull Market: {bull_prob}%

Aktivitas Whale: {whale}
Arus Stablecoin: {stablecoin}

Funding Rate: {funding}

Open Interest: {oi}
Risiko Likuidasi: {liquidation}

Tingkat Risiko Market: {risk}
"""

    return message.strip()


# =========================
# SMART MONEY ALERT
# =========================

def smart_money_alert(data):

    if data.get("smart_money_signal") != "ACCUMULATION":
        return None

    return """
🧠 SINYAL SMART MONEY

Smart money terdeteksi
sedang mengakumulasi BTC.

Kemungkinan fase awal bull market.

Strategi:
Akumulasi BTC secara bertahap.
""".strip()


# =========================
# CRASH WARNING
# =========================

def crash_warning(data):

    if data.get("market_risk_score") not in ["HIGH", "EXTREME"]:
        return None

    crash_prob = data.get("crash_probability")

    return f"""
🚨 PERINGATAN MARKET

Probabilitas Crash: {crash_prob}%

Market menunjukkan
risiko tinggi.

Strategi:
Kurangi risiko posisi.
""".strip()