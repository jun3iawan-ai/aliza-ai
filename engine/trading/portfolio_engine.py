import requests

from engine.trading.trade_manager import get_active_trades
from engine.utils.market_cache import get_market_data


# =========================
# GET PRICE
# =========================

def get_price(symbol):

    symbol = symbol.upper()

    # TRY MARKET CACHE
    try:

        data = get_market_data(symbol)

        if data:
            price = data.get("price")

            if price:
                return float(price)

    except:
        pass

    # FALLBACK BINANCE API
    try:

        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"

        r = requests.get(url, timeout=5)

        data = r.json()

        if "price" in data:
            return float(data["price"])

    except:
        pass

    return None


# =========================
# CALCULATE PNL
# =========================

def calculate_pnl(entry, price, direction):

    if price is None:
        return None

    if direction == "LONG":
        pnl = ((price - entry) / entry) * 100
    else:
        pnl = ((entry - price) / entry) * 100

    return round(pnl, 2)


# =========================
# BUILD PORTFOLIO REPORT
# =========================

def portfolio_report():

    trades = get_active_trades()

    if not trades:
        return "Tidak ada posisi trading aktif."

    message = "📊 ALIZA PORTFOLIO\n\n"

    for trade in trades:

        coin = trade[0]
        setup = trade[1]
        entry = trade[2]

        direction = "LONG" if (setup and ("LONG" in setup or setup == "OVERSOLD BOUNCE")) else "SHORT"

        price = get_price(coin)

        pnl = calculate_pnl(entry, price, direction)

        if price is None:
            price_text = "N/A"
        else:
            price_text = round(price, 2)

        if pnl is None:
            pnl_text = "N/A"
        else:
            pnl_text = f"{pnl}%"

        message += (
            f"{coin} {setup}\n"
            f"Entry : {entry}\n"
            f"Price : {price_text}\n"
            f"PnL   : {pnl_text}\n\n"
        )

    message += f"Total Active Trades : {len(trades)}"

    return message