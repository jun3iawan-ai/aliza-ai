from fastapi import APIRouter
from engine.market_analyzer import btc_signal

router = APIRouter()

# =========================
# BTC MARKET DATA
# =========================

@router.get("/btc")
def btc_market():
    return btc_signal()


# =========================
# BTC TRADING SETUP
# =========================

@router.get("/api/trading/btc")
def btc_trading():

    market = btc_signal()

    if "trade_setup" not in market:
        return {"error": "trading setup not available"}

    return market["trade_setup"]