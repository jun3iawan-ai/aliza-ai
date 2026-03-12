# engine/ai_trade_guardian.py

from engine.trading.trade_manager import get_active_trades
from engine.utils.market_cache import get_market_data
from engine.market.market_analyzer import market_signal

# =========================
# ALERT MEMORY (GLOBAL)
# =========================
# Menyimpan status alert terakhir per trade
# contoh key: "BTC_SHORT"
ALERT_MEMORY = {}


def get_alert_state(pnl):
    """
    Menentukan status alert berdasarkan PnL
    """

    if pnl >= 8:
        return "SECURE_PROFIT"

    elif pnl >= 4:
        return "PARTIAL_PROFIT"

    elif pnl >= 2:
        return "BREAK_EVEN"

    elif pnl <= -4:
        return "CLOSE_WARNING"

    elif pnl <= -2:
        return "RISK_WARNING"

    else:
        return None


def get_alert_message(state):
    """
    Mapping state ke pesan Bahasa Indonesia
    """

    mapping = {

        "SECURE_PROFIT": "Amankan profit",

        "PARTIAL_PROFIT": "Ambil profit sebagian",

        "BREAK_EVEN": "Pindahkan Stop Loss ke Break Even",

        "RISK_WARNING": "Risiko meningkat",

        "CLOSE_WARNING": "Pertimbangkan menutup posisi",
    }

    return mapping.get(state)


def analyze_trades():

    alerts = []

    trades = get_active_trades()

    if not trades:
        return alerts

    for trade in trades:

        coin = trade[0]
        setup = trade[1]
        entry = trade[2]

        direction = "LONG" if (setup and ("LONG" in setup or setup == "OVERSOLD BOUNCE")) else "SHORT"
        trade_key = f"{coin}_{direction}"

        market = get_market_data(coin)

        if not market or market.get("price") is None:
            market = market_signal(coin)

        if not market:
            continue

        price = market.get("price")

        if price is None:
            continue

        # =========================
        # HITUNG PNL
        # =========================

        if direction == "LONG":
            pnl = ((price - entry) / entry) * 100
        else:
            pnl = ((entry - price) / entry) * 100

        pnl = round(pnl, 2)

        state = get_alert_state(pnl)

        if not state:
            continue

        last_state = ALERT_MEMORY.get(trade_key)

        # =========================
        # SMART MEMORY CHECK
        # =========================

        if last_state == state:
            # status sama → jangan kirim alert lagi
            continue

        ALERT_MEMORY[trade_key] = state

        insight = get_alert_message(state)

        message = (
            f"⚠️ UPDATE POSISI\n\n"
            f"{coin} {setup}\n\n"
            f"Harga Masuk : {entry}\n"
            f"Harga Sekarang : {price}\n\n"
            f"Profit/Loss : {pnl}%\n\n"
            f"Saran AI:\n{insight}"
        )

        alerts.append(message)

    return alerts