"""
Resolver symbol → CoinGecko ID.
Prioritas: 1) dynamic_universe.get_coin_id(symbol)  2) COINGECKO_IDS[symbol].
Agar coin dari dynamic universe dapat dianalisis dengan benar.
"""

try:
    from engine.market.dynamic_universe import get_coin_id as _dynamic_get_coin_id
except Exception:
    _dynamic_get_coin_id = None

# Mapping statis untuk semua 20 coin watchlist
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "SUI": "sui",
    "ARB": "arbitrum",
    "PEPE": "pepe",
    "JTO": "jito-governance-token",
    "ETHFI": "ether-fi",
    "WLD": "worldcoin-wld",
    "OM": "mantra-dao",
    "ASTER": "aster-2",
    "XPL": "xenon-pay",
    "TAO": "bittensor",
    "BONE": "bone-shibaswap",
    "FARTCOIN": "fartcoin",
    "HYPE": "hyperliquid",
    "ZEREBRO": "zerebro",
    "XAUT": "tether-gold",
}


def resolve_coin_id(symbol):
    """
    Resolve symbol (e.g. BTC, ETH) ke CoinGecko coin_id.
    Prioritas: 1) dynamic_universe.get_coin_id(symbol)  2) COINGECKO_IDS.get(symbol).
    Return str coin_id atau None jika tidak ditemukan.
    """
    if not symbol:
        return None
    sym = (symbol or "").strip().upper()
    if _dynamic_get_coin_id:
        try:
            coin_id = _dynamic_get_coin_id(sym)
            if coin_id:
                return coin_id
        except Exception:
            pass
    return COINGECKO_IDS.get(sym)
