from engine.market_cache import get_all_market_data


# =========================
# MARKET RADAR PRO
# =========================

def analyze_market():

    market_data = get_all_market_data()

    alerts = []

    if not market_data:
        return alerts

    # =========================
    # BTC DATA
    # =========================

    btc = market_data.get("BTC")

    if btc:

        rsi = btc.get("rsi")
        fear = btc.get("fear_greed")
        dominance = btc.get("dominance")
        trend = btc.get("trend")

        # =========================
        # BTC BOTTOM DETECTOR
        # =========================

        if rsi and fear:

            if rsi < 30 and fear <= 20:

                alerts.append(

                    "🟢 BTC BOTTOM DETECTOR\n\n"
                    f"RSI : {rsi}\n"
                    f"Fear & Greed : {fear}\n\n"
                    "Market sangat oversold.\n"
                    "Potensi reversal mulai terbentuk."

                )

        # =========================
        # BTC CRASH ALERT
        # =========================

        if rsi and trend:

            if rsi >= 70 and trend == "BULLISH":

                alerts.append(

                    "⚠️ BTC CRASH ALERT\n\n"
                    f"RSI : {rsi}\n"
                    f"Trend : {trend}\n\n"
                    "Market overbought.\n"
                    "Potensi koreksi besar."

                )

    # =========================
    # WHALE TRACKER
    # =========================

    for coin, data in market_data.items():

        whale = data.get("whale_activity")

        if whale == "HIGH":

            alerts.append(

                "🐋 WHALE ACTIVITY\n\n"
                f"{coin} mengalami aktivitas whale tinggi.\n"
                "Pergerakan besar kemungkinan terjadi."

            )

    # =========================
    # ALTSEASON DETECTOR
    # =========================

    if btc:

        dominance = btc.get("dominance")

        if dominance and dominance < 45:

            alerts.append(

                "🚀 ALTSEASON SIGNAL\n\n"
                f"BTC Dominance : {dominance}%\n\n"
                "Dominance rendah.\n"
                "Altcoin berpotensi outperform."

            )

    # =========================
    # ELITE TRADE SCANNER
    # =========================

    for coin, data in market_data.items():

        trade = data.get("trade_setup")

        if not trade:
            continue

        rr = trade.get("risk_reward")

        if rr and rr >= 3:

            alerts.append(

                "🔥 ELITE TRADE SETUP\n\n"
                f"{coin} {trade.get('setup')}\n\n"
                f"Entry : {trade.get('entry')}\n"
                f"SL : {trade.get('sl')}\n"
                f"TP1 : {trade.get('tp1')}\n"
                f"TP2 : {trade.get('tp2')}\n"
                f"RR : {round(rr,2)}"

            )

    return alerts