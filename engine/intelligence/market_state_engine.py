"""
ALIZA MARKET STATE ENGINE

Menggabungkan hasil Market Radar, Predictive AI, dan Quant Model
menjadi satu kesimpulan kondisi market. Data dari snapshot (tanpa panggilan API langsung).
"""

try:
    from engine.market.market_snapshot_engine import get_market_snapshot
except ImportError:
    get_market_snapshot = None

try:
    from engine.intelligence.predictive_market_ai import calculate_market_predictions
except ImportError:
    calculate_market_predictions = None

try:
    from engine.intelligence.quant_market_model import calculate_market_score
except ImportError:
    calculate_market_score = None


def calculate_market_state():
    """
    Gabungkan analisis dari snapshot BTC, Predictive AI, dan Quant Model.
    Return dict: market_bias, market_risk, crash_probability, bull_probability, trend, whale_activity.
    """
    state = {
        "market_bias": "NEUTRAL",
        "market_risk": "UNKNOWN",
        "crash_probability": 0,
        "bull_probability": None,
        "trend": "UNKNOWN",
        "whale_activity": "UNKNOWN",
    }

    if not get_market_snapshot:
        return state

    snapshot = get_market_snapshot()
    data = snapshot.get("data") or {}
    btc = data.get("BTC")
    if not btc or btc.get("error"):
        return state

    predictive = {}
    if calculate_market_predictions:
        try:
            predictive = calculate_market_predictions(btc_data=btc) or {}
        except Exception:
            pass

    quant = {}
    if calculate_market_score:
        try:
            quant = calculate_market_score(btc_data=btc) or {}
        except Exception:
            pass

    quant_score = quant.get("market_score")
    if quant_score is not None:
        try:
            q = int(quant_score)
            if q >= 65:
                state["market_bias"] = "BULLISH"
            elif q <= 40:
                state["market_bias"] = "BEARISH"
            else:
                state["market_bias"] = "NEUTRAL"
        except (TypeError, ValueError):
            pass

    state["market_risk"] = btc.get("market_risk_score") or quant.get("market_risk_score") or "UNKNOWN"
    state["crash_probability"] = predictive.get("crash_probability", 0)
    state["bull_probability"] = btc.get("bull_probability") or quant.get("bull_probability")
    state["trend"] = btc.get("trend") or "UNKNOWN"
    state["whale_activity"] = btc.get("whale_activity") or "UNKNOWN"

    return state


def format_market_state_report(state):
    """Format laporan Market State untuk Telegram."""
    if not state:
        return "Data market state tidak tersedia."

    bias = state.get("market_bias") or "—"
    trend = state.get("trend") or "—"
    risk = state.get("market_risk") or "—"
    crash = state.get("crash_probability")
    crash_str = f"{crash}%" if crash is not None else "—"
    bull = state.get("bull_probability")
    bull_str = f"{bull}%" if bull is not None else "—"
    whale = state.get("whale_activity") or "—"

    return (
        "🧠 ALIZA MARKET STATE\n\n"
        f"Bias : {bias}\n"
        f"Trend : {trend}\n\n"
        f"Risk Level : {risk}\n"
        f"Crash Probability : {crash_str}\n\n"
        f"Bull Probability : {bull_str}\n\n"
        f"Whale Activity : {whale}"
    )
