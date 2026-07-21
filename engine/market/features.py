"""Pure historical feature calculations shared by runtime and backtester."""

from engine.indicators.constants import MIN_REQUIRED_DATA
from engine.market.multi_timeframe_analyzer import analyze_multi_timeframe


def moving_average(prices, period):
    if not prices or len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def calculate_rsi(prices, period=14):
    if not prices or len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for index in range(1, len(prices)):
        change = prices[index] - prices[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return round(100 - (100 / (1 + relative_strength)), 2)


def calculate_rsi_series(prices, period=14):
    """Return RSI at each prefix using the same Wilder recurrence as calculate_rsi."""
    values = [None] * len(prices or [])
    if not prices or len(prices) < period + 1:
        return values
    gains = []
    losses = []
    for index in range(1, len(prices)):
        change = prices[index] - prices[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    values[period] = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + avg_gain / avg_loss)), 2)
    for index in range(period + 1, len(prices)):
        gain = gains[index - 1]
        loss = losses[index - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        values[index] = 100.0 if avg_loss == 0 else round(100 - (100 / (1 + avg_gain / avg_loss)), 2)
    return values


def support_resistance(prices):
    if not prices or len(prices) < 20:
        return None, None
    recent = prices[-20:]
    return min(recent), max(recent)


def trend_from_ma(price, ma_short, ma_long):
    if ma_short is None or ma_long is None:
        return "SIDEWAYS"
    if price > ma_short > ma_long:
        return "BULLISH"
    if price < ma_short < ma_long:
        return "BEARISH"
    return "SIDEWAYS"


def compute_features(closes_4h, closes_1d, price=None, price_series=None, rsi_value=None):
    """Compute exactly the close-based feature contract used by market_signal()."""
    closes_4h = list(closes_4h or [])
    closes_1d = list(closes_1d or [])
    if price_series is not None:
        prices = list(price_series or [])
    elif closes_4h and len(closes_4h) >= 20:
        prices = list(closes_4h)
    elif closes_1d and len(closes_1d) >= 20:
        prices = list(closes_1d)
    else:
        prices = []

    if price is None and prices:
        price = prices[-1]
    if not prices or len(prices) < MIN_REQUIRED_DATA:
        return {
            "valid": False,
            "prices": prices,
            "reason": "insufficient_price_series",
            "trend": None,
            "rsi": None,
            "support": None,
            "resistance": None,
            "trend_4h": "UNKNOWN",
            "trend_1d": "UNKNOWN",
            "trend_alignment": "UNKNOWN",
        }

    mtf_4h = closes_4h if len(closes_4h) >= 30 else []
    mtf_1d = closes_1d if len(closes_1d) >= 50 else []
    mtf = analyze_multi_timeframe(mtf_4h, mtf_1d)

    ma20 = moving_average(prices, 20)
    ma50 = moving_average(prices, 50)
    ma200 = moving_average(prices, 200)
    if ma50 and ma200:
        trend = trend_from_ma(price, ma50, ma200)
    elif ma20 and ma50:
        trend = trend_from_ma(price, ma20, ma50)
    else:
        trend = "SIDEWAYS"

    rsi_prices = (
        closes_4h if closes_4h and len(closes_4h) >= 15
        else closes_1d if closes_1d and len(closes_1d) >= 15
        else prices
    )
    rsi = rsi_value if rsi_value is not None else calculate_rsi(rsi_prices)
    support, resistance = support_resistance(prices)
    if rsi is None:
        return {
            "valid": False,
            "prices": prices,
            "reason": "insufficient_rsi_data",
            "trend": trend,
            "rsi": None,
            "support": support,
            "resistance": resistance,
            "trend_4h": mtf["trend_4h"],
            "trend_1d": mtf["trend_1d"],
            "trend_alignment": mtf["alignment"],
        }
    return {
        "valid": True,
        "prices": prices,
        "reason": "ok",
        "trend": trend,
        "rsi": float(rsi),
        "support": support,
        "resistance": resistance,
        "trend_4h": mtf["trend_4h"],
        "trend_1d": mtf["trend_1d"],
        "trend_alignment": mtf["alignment"],
        "ma20": ma20,
        "ma50": ma50,
        "ma200": ma200,
    }
