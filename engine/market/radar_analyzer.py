from engine.market.market_analyzer import multi_market_scan


def classify_trend(coin, trend):

    """
    Upgrade radar intelligence
    """

    if trend == "BULLISH":

        if coin in ["SOL", "AVAX", "APT"]:
            return "BREAKOUT"

        if coin in ["DOGE", "LINK"]:
            return "MOMENTUM"

        return "BULLISH"

    if trend == "BEARISH":

        if coin in ["BTC", "ETH"]:
            return "REVERSAL"

        return "BEARISH"

    return "SIDEWAYS"


def market_radar_report():

    data = multi_market_scan()

    bullish = 0
    bearish = 0
    sideways = 0

    report_lines = []

    for coin, trend in data.items():

        status = classify_trend(coin, trend)

        report_lines.append(f"{coin} → {status}")

        if status in ["BULLISH", "BREAKOUT", "MOMENTUM"]:
            bullish += 1

        elif status in ["BEARISH", "REVERSAL"]:
            bearish += 1

        else:
            sideways += 1

    # =========================
    # MARKET BIAS
    # =========================

    if bullish >= 6:
        bias = "ALTCOIN STRENGTH"

    elif bearish >= 6:
        bias = "MARKET WEAKNESS"

    else:
        bias = "NEUTRAL"

    report = "\n".join(report_lines)

    summary = f"""

Market Insight

Bullish : {bullish}
Bearish : {bearish}
Sideways : {sideways}

Market Bias : {bias}
"""

    return report + summary