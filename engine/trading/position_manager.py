from engine.trading.trade_manager import get_active_trades
from engine.utils.market_cache import get_market_data


# =========================
# CALCULATE PNL
# =========================

def calculate_pnl(direction, entry, price):

    if direction == "LONG":
        pnl = ((price - entry) / entry) * 100
    else:
        pnl = ((entry - price) / entry) * 100

    return round(pnl, 2)


# =========================
# POSITION MANAGEMENT
# =========================

def analyze_positions():

    trades = get_active_trades()

    alerts = []

    if not trades:
        return alerts

    for trade in trades:

        coin = trade[0]
        setup = trade[1]
        entry = trade[2]

        direction = "LONG" if (setup and ("LONG" in setup or setup == "OVERSOLD BOUNCE")) else "SHORT"

        market = get_market_data(coin)

        if not market:
            continue

        price = market.get("price")

        if not price:
            continue

        pnl = calculate_pnl(direction, entry, price)

        recommendation = None

        if pnl >= 5:

            recommendation = "Take Partial Profit (Close 30%)"

        elif pnl >= 3:

            recommendation = "Trail Stop Loss"

        elif pnl >= 1.5:

            recommendation = "Move SL to Break Even"

        if recommendation:

            message = (
                "⚠️ POSITION MANAGEMENT\n\n"
                f"{coin} {setup}\n\n"
                f"Entry : {entry}\n"
                f"Price : {price}\n"
                f"PnL   : {pnl}%\n\n"
                f"AI Recommendation:\n"
                f"{recommendation}"
            )

            alerts.append(message)

    return alerts