"""
ALIZA MARKET UNIVERSE
Daftar crypto yang dianalisa oleh Aliza.
Hybrid: CORE_COINS (tetap) + dynamic opportunity coins.
"""

# Core coins selalu dimonitor (market leader)
CORE_COINS = [
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
]

# Fallback ketika dynamic universe belum tersedia
DEFAULT_DYNAMIC_COINS = [
    "ADA",
    "DOGE",
    "AVAX",
    "TRX",
    "TON",
    "LINK",
    "DOT",
    "LTC",
    "APT",
    "ATOM",
]

TRADABLE_COINS = CORE_COINS + DEFAULT_DYNAMIC_COINS

MAJOR_COINS = [
"BTC",
"ETH",
"BNB",
"SOL",
"XRP",
"ADA",
"DOGE",
"AVAX",
"TRX",
"TON",
"LINK",
"DOT",
"LTC",
"APT",
"ATOM"
]
