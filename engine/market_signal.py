"""
Layer signal publik: generate_signal memanggil analyzer.
Jika data tidak valid (RSI tidak terhitung, harga/kurang candle) → None — jangan perlakukan sebagai sinyal.
Log peringatan ada di market_analyzer.market_signal saat mengembalikan None.
"""

from engine.market.market_analyzer import market_signal as _market_signal


def generate_signal(symbol, radar_data=None):
    signal = _market_signal(symbol, radar_data)
    if signal is None:
        return None
    return signal
