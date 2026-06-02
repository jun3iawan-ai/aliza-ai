"""
Resolver symbol → CoinGecko ID.
Prioritas: 1) dynamic_universe.get_coin_id(symbol)  2) COINGECKO_IDS[symbol].
Agar coin dari dynamic universe dapat dianalisis dengan benar.
"""

try:
    from engine.market.dynamic_universe import get_coin_id as _dynamic_get_coin_id
except Exception:
    _dynamic_get_coin_id = None

# Mapping statis untuk coin utama (fallback bila dynamic_universe belum punya)
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "TRX": "tron",
    "TON": "the-open-network",
    "LINK": "chainlink",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "APT": "aptos",
    "ATOM": "cosmos",
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
