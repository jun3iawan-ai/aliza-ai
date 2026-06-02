"""
ALIZA STRATEGY REGIME MAP

Mapping regime market ke daftar setup yang diizinkan.
Strategy switch memfilter setup berdasarkan market_regime.
"""

STRATEGY_MAP = {
    "TREND": [
        "PULLBACK LONG",
        "PULLBACK SHORT",
        "MOMENTUM LONG",
        "MOMENTUM SHORT",
        "BREAKOUT LONG",
    ],
    "RANGE": [
        "OVERSOLD BOUNCE",
        "OVERBOUGHT REJECTION",
    ],
    "DOWNTREND": [
        "PULLBACK SHORT",
        "OVERBOUGHT REJECTION",
    ],
    "VOLATILE": [],
}
