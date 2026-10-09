"""Watchlist 9 Okt 2026 + fallback candle futures untuk coin yang histori spotnya pendek."""
from unittest.mock import patch

from engine.market import market_analyzer as ma
from engine.market.market_universe import CORE_COINS


def test_watchlist_cleanup():
    assert "HYPE" in CORE_COINS
    for c in ("BONE", "FARTCOIN", "ZEREBRO"):
        assert c not in CORE_COINS


def _resp(n):
    rows = [[i * 1000, "1", "2", "0.5", str(1 + i), "0", i * 1000 + 999] for i in range(n)]

    class R:
        status_code = 200

        def json(self):
            return rows
    return R()


def test_short_spot_history_falls_back_to_futures():
    with patch.object(ma, "_get_binance_spot_klines", return_value=[1.0] * 15), \
         patch.object(ma, "_extract_closed_kline_closes", side_effect=lambda d: [float(x[4]) for x in d]), \
         patch.object(ma, "set_cached_klines") as cache, \
         patch.object(ma.requests, "get", return_value=_resp(100)) as get:
        out = ma._get_binance_klines("HYPEUSDT", "1d", 100)
    assert len(out) == 100
    assert get.call_args.args[0] == ma.BINANCE_FUTURES_KLINES_URL
    cache.assert_called_once()


def test_full_spot_history_no_futures_call():
    with patch.object(ma, "_get_binance_spot_klines", return_value=[1.0] * 100), \
         patch.object(ma.requests, "get") as get:
        assert len(ma._get_binance_klines("BTCUSDT", "4h", 100)) == 100
    get.assert_not_called()
