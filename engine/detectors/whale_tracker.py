from engine.market.market_analyzer import market_signal
from engine.market.market_universe import MAJOR_COINS

# =========================
# MEMORY AGAR TIDAK SPAM
# =========================

WHALE_MEMORY = {}


def detect_whale_activity():

    alerts = []

    for coin in MAJOR_COINS:

        data = market_signal(coin)

        if not data or "error" in data:
            continue

        whale = data.get("whale_activity")
        stable = data.get("stablecoin_flow")
        oi = data.get("open_interest_level")

        # =========================
        # DETEKSI TEKANAN BELI
        # =========================

        if whale == "HIGH" and stable == "HIGH INFLOW":

            state = "WHALE_BUY"

        # =========================
        # DETEKSI TEKANAN JUAL
        # =========================

        elif whale == "HIGH" and stable == "HIGH OUTFLOW":

            state = "WHALE_SELL"

        else:
            continue

        last_state = WHALE_MEMORY.get(coin)

        if last_state == state:
            continue

        WHALE_MEMORY[coin] = state

        # =========================
        # FORMAT PESAN ALERT
        # =========================

        if state == "WHALE_BUY":

            message = (
                "🐋 AKTIVITAS WHALE TERDETEKSI\n\n"
                f"Market : {coin}\n\n"
                "Jenis Aktivitas : Whale Accumulation\n\n"
                f"Whale Activity : {whale}\n"
                f"Stablecoin Flow : {stable}\n"
                f"Open Interest : {oi}\n\n"
                "Potensi : Tekanan beli meningkat"
            )

        else:

            message = (
                "🐋 AKTIVITAS WHALE TERDETEKSI\n\n"
                f"Market : {coin}\n\n"
                "Jenis Aktivitas : Whale Distribution\n\n"
                f"Whale Activity : {whale}\n"
                f"Stablecoin Flow : {stable}\n"
                f"Open Interest : {oi}\n\n"
                "Potensi : Tekanan jual meningkat"
            )

        alerts.append(message)

    return alerts