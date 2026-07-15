"""
ALIZA MULTI TIMEFRAME ANALYZER

Analyzes trend alignment across 4H and 1D using close-price series from
Binance klines. No external API calls; uses only the lists passed in.
"""

import logging


def _ma(values, period):
    """Moving average over last `period` values. Returns None if insufficient data."""
    if not values or len(values) < period:
        return None
    return sum(values[-period:]) / period


def _trend_from_mas(price, ma_short, ma_long):
    """price > ma_short > ma_long -> BULLISH; price < ma_short < ma_long -> BEARISH; else SIDEWAYS."""
    if ma_short is None or ma_long is None or price is None:
        return "UNKNOWN"
    if price > ma_short > ma_long:
        return "BULLISH"
    if price < ma_short < ma_long:
        return "BEARISH"
    return "SIDEWAYS"


def analyze_multi_timeframe(prices_4h=None, prices_1d=None):
    """
    Determine trend alignment from 4h and 1d close-price series (oldest → newest).

    - trend_4h: from prices_4h (ma10 vs ma30), needs at least 30 candles.
    - trend_1d: from prices_1d (ma20 vs ma50), needs at least 50 candles.
    - alignment: STRONG_BULLISH / STRONG_BEARISH when both align; MIXED otherwise; UNKNOWN if either missing.
    """
    prices_4h = prices_4h or []
    prices_1d = prices_1d or []

    # 4H trend: ma10 vs ma30, last close as price
    if len(prices_4h) >= 30:
        price_4h = prices_4h[-1]
        ma10 = _ma(prices_4h, 10)
        ma30 = _ma(prices_4h, 30)
        trend_4h = _trend_from_mas(price_4h, ma10, ma30)
    else:
        trend_4h = "UNKNOWN"

    # 1D trend: ma20 vs ma50, last close as price
    if len(prices_1d) >= 50:
        price_1d = prices_1d[-1]
        ma20 = _ma(prices_1d, 20)
        ma50 = _ma(prices_1d, 50)
        trend_1d = _trend_from_mas(price_1d, ma20, ma50)
    else:
        trend_1d = "UNKNOWN"

    # Alignment
    if trend_4h == "UNKNOWN" or trend_1d == "UNKNOWN":
        alignment = "UNKNOWN"
    elif trend_4h == "BULLISH" and trend_1d == "BULLISH":
        alignment = "STRONG_BULLISH"
    elif trend_4h == "BEARISH" and trend_1d == "BEARISH":
        alignment = "STRONG_BEARISH"
    elif (
        trend_4h in ("BULLISH", "BEARISH") and trend_1d == "SIDEWAYS"
    ) or (
        trend_4h == "SIDEWAYS" and trend_1d in ("BULLISH", "BEARISH")
    ):
        alignment = "PARTIAL"
    else:
        alignment = "MIXED"

    return {
        "trend_4h": trend_4h,
        "trend_1d": trend_1d,
        "alignment": alignment,
    }
