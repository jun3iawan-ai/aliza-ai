import requests

BINANCE_OI_API = "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT"

# =========================
# OPEN INTEREST
# =========================

def get_open_interest():

    try:

        res = requests.get(BINANCE_OI_API, timeout=10)

        data = res.json()

        oi = float(data["openInterest"])

        return oi

    except Exception as e:

        print("open interest error:", e)

        return None


# =========================
# OI ANALYSIS
# =========================

def analyze_open_interest(oi):

    if oi is None:
        return "UNKNOWN"

    if oi > 200000:
        return "EXTREME"

    if oi > 120000:
        return "HIGH"

    if oi > 80000:
        return "MEDIUM"

    return "LOW"


# =========================
# LIQUIDATION RISK
# =========================

def liquidation_risk(open_interest_level, funding_status):

    if open_interest_level == "EXTREME" and funding_status == "LONG OVERCROWDED":
        return "LONG SQUEEZE RISK"

    if open_interest_level == "EXTREME" and funding_status == "SHORT OVERCROWDED":
        return "SHORT SQUEEZE RISK"

    if open_interest_level == "HIGH":
        return "ELEVATED"

    return "LOW"