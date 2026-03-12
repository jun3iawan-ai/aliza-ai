from engine.trading.trade_manager import get_active_trades, close_trade
from engine.utils.market_cache import get_market_data


def check_trades():

    trades = get_active_trades()

    alerts = []

    for trade in trades:

        coin, setup, entry, sl, tp1, tp2 = trade

        data = get_market_data(coin)

        if not data:
            continue

        price = data["price"]

        # =========================
        # SHORT TRADE
        # =========================

        if setup.startswith("SHORT"):

            if price <= tp1:

                close_trade(coin)

                alerts.append(
                    f"🎯 TAKE PROFIT HIT\n\n{coin}\nHarga: {price}"
                )

            elif price >= sl:

                close_trade(coin)

                alerts.append(
                    f"❌ STOP LOSS HIT\n\n{coin}\nHarga: {price}"
                )

        # =========================
        # LONG TRADE (termasuk OVERSOLD BOUNCE)
        # =========================

        if setup == "OVERSOLD BOUNCE" or setup.startswith("LONG"):

            if price >= tp1:

                close_trade(coin)

                alerts.append(
                    f"🎯 TAKE PROFIT HIT\n\n{coin}\nHarga: {price}"
                )

            elif price <= sl:

                close_trade(coin)

                alerts.append(
                    f"❌ STOP LOSS HIT\n\n{coin}\nHarga: {price}"
                )

    return alerts