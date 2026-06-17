"""
ALIZA MARKET UNIVERSE
Daftar crypto yang dianalisa oleh Aliza.
Fixed watchlist 20 coin.
"""

# Fixed watchlist — tidak berubah secara dynamic
CORE_COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP",
    "ADA", "SUI", "ARB", "PEPE", "JTO",
    "ETHFI", "WLD", "OM", "ASTER", "XPL",
    "TAO", "BONE", "FARTCOIN", "HYPE", "ZEREBRO",
]

# Tidak dipakai lagi — dynamic universe dinonaktifkan
DEFAULT_DYNAMIC_COINS = []

TRADABLE_COINS = list(CORE_COINS)

MAJOR_COINS = list(CORE_COINS)
