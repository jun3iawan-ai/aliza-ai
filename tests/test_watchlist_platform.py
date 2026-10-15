"""Format v1 Porto: platform baru (tokocrypto) dan simbol yang sama dari beberapa platform tidak boleh ditolak."""
import json

from engine.market import watchlist_source as wl

DOC = {
    "v": 1, "source": "porto-crypto-jun", "ts": "2026-10-15T10:00:00+07:00",
    "symbols": ["BTC", "JTO", "JTO", "SOL", "DOGE"],
    "coins": [
        {"key": "btc-tk", "symbol": "BTC", "platform": "tokocrypto", "venue": "Tokocrypto", "chain": "tk", "price_source": "binance", "price_symbol": "BTCUSDT"},
        {"key": "jto-sol", "symbol": "JTO", "platform": "metamask", "venue": "Solana", "chain": "sol", "price_source": "binance", "price_symbol": "JTOUSDT"},
        {"key": "jto-idx", "symbol": "JTO", "platform": "indodax", "venue": "Indodax", "chain": "idx", "price_source": "indodax", "price_symbol": "jto_idr"},
        {"key": "doge-tk", "symbol": "DOGE", "platform": "tokocrypto", "venue": "Tokocrypto", "chain": "tk", "price_source": "binance", "price_symbol": "DOGEUSDT"},
    ],
}


def test_platform_baru_dan_simbol_ganda_diterima():
    assert wl.parse_symbols(DOC) == ["BTC", "JTO", "SOL", "DOGE"]   # unik, urutan asli


def test_isi_coins_tidak_divalidasi():
    d = json.loads(json.dumps(DOC))
    d["coins"].append({"platform": "platform-masa-depan", "aneh": [1, 2]})
    d["coins"] = "bukan list"
    assert wl.parse_symbols(d) == ["BTC", "JTO", "SOL", "DOGE"]
