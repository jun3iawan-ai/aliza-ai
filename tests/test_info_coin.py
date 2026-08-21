"""
Tests for the "Info Coin" display-only feature (paket 1, no new external API).

Covers:
  1. market_signal() now exposes ma20/ma50/ma200 without changing any existing
     key/value (engine/market/market_analyzer.py).
  2. The Info Coin render path (interfaces.telegram_bot._format_info_coin_message)
     never touches the production/shadow signal pipeline -- pure display.
  3. engine.market.coin_info.get_tokenomics(): fetch fail -> "unavailable"
     (never a fabricated number), fetch success -> full fields, cache TTL honored.
  4. Message rendering: healthy fixture -> all 4 sections present; degraded
     fixture -> "tidak tersedia" shown, and a silently-defaulted 50 (dominance/
     fear&greed fetch failure) is never presented as if it were real.
  5. Telegram wiring: the "ℹ️ Info Coin" menu button builds the coin selector,
     and the "info_<COIN>" inline callback renders via _format_info_coin_message.
"""

import os
import time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import pytest

from engine.market import coin_info
from engine.market import features as market_features
from engine.market import market_analyzer

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


# ---------------------------------------------------------------------------
# 1. market_signal() exposes ma20/ma50/ma200, everything else unchanged
# ---------------------------------------------------------------------------


def _mock_trading_brain():
    return patch(
        "engine.brain.trading_brain.TradingBrain.analyze",
        return_value={"setup": "NO SETUP", "side": None},
    )


class TestMarketSignalMovingAverages:
    def test_ma_keys_present_and_match_features_module(self, monkeypatch):
        prices = list(range(1, 61))  # 60 closed candles, both 4h and 1d
        monkeypatch.setattr(market_analyzer, "_get_price_from_binance", lambda _s: 60.0)
        monkeypatch.setattr(
            market_analyzer,
            "_get_binance_klines",
            Mock(side_effect=[list(prices), list(prices)]),
        )
        monkeypatch.setattr(
            market_analyzer,
            "get_global_market_data",
            lambda: {"fear_greed": 50, "btc_dominance": 50},
        )
        with _mock_trading_brain():
            result = market_analyzer.market_signal("TEST", radar_data={})

        assert result is not None
        # New keys present
        assert "ma20" in result and "ma50" in result and "ma200" in result
        # 60 candles: ma20/ma50 computable, ma200 needs >=200 -> None
        assert result["ma20"] == market_features.moving_average(prices, 20)
        assert result["ma50"] == market_features.moving_average(prices, 50)
        assert result["ma200"] is None
        assert result["ma20"] == pytest.approx(50.5)
        assert result["ma50"] == pytest.approx(35.5)

    def test_existing_keys_and_values_unchanged(self, monkeypatch):
        """Byte-identical old behavior: every pre-existing key keeps the exact
        value it had before ma20/ma50/ma200 were added (only new keys appear)."""
        prices = list(range(1, 61))
        monkeypatch.setattr(market_analyzer, "_get_price_from_binance", lambda _s: 60.0)
        monkeypatch.setattr(
            market_analyzer,
            "_get_binance_klines",
            Mock(side_effect=[list(prices), list(prices)]),
        )
        monkeypatch.setattr(
            market_analyzer,
            "get_global_market_data",
            lambda: {"fear_greed": 50, "btc_dominance": 50},
        )
        with _mock_trading_brain():
            result = market_analyzer.market_signal("TEST", radar_data={})

        assert result is not None
        pre_existing_keys = {
            "symbol", "price", "trend", "rsi", "support", "resistance",
            "fear_greed", "dominance", "trend_4h", "trend_1d", "trend_alignment",
            "cycle_phase", "funding_status", "whale_activity", "stablecoin_flow",
            "open_interest_level", "liquidation_risk", "market_phase_prediction",
            "bull_probability", "market_risk_score", "trade_setup",
            "data_coverage", "timestamp",
        }
        assert pre_existing_keys.issubset(result.keys())
        assert result["symbol"] == "TEST"
        assert result["price"] == 60.0
        assert result["trend"] in ("BULLISH", "BEARISH", "SIDEWAYS")
        assert result["fear_greed"] == 50
        assert result["dominance"] == 50

    def test_fallback_market_data_has_ma_keys_as_none(self):
        fallback = market_analyzer._fallback_market_data("TEST", "boom")
        assert fallback["ma20"] is None
        assert fallback["ma50"] is None
        assert fallback["ma200"] is None
        assert fallback["error"] == "boom"


# ---------------------------------------------------------------------------
# 2. Info Coin render path never touches the signal/shadow pipeline
# ---------------------------------------------------------------------------


def _healthy_snapshot():
    return {
        "data": {
            "BTC": {
                "price": 65000.1234,
                "price_change_percentage_24h": 2.5,
                "price_change_1h": 0.3,
                "trend": "BULLISH",
                "trend_4h": "BULLISH",
                "trend_1d": "BULLISH",
                "trend_alignment": "STRONG_BULLISH",
                "rsi": 61.2,
                "ma20": 64000.0,
                "ma50": 62000.0,
                "ma200": 58000.0,
                "support": 63000.0,
                "resistance": 67000.0,
                "volume_24h": 1_234_567_890.0,
                "whale_activity": "MEDIUM",
            }
        },
        "timestamp": None,
    }


def _healthy_tokenomics(symbol=None, now=None):
    return {
        "status": "ok",
        "message": None,
        "market_cap": 1_280_000_000_000.0,
        "fully_diluted_valuation": 1_365_000_000_000.0,
        "circulating_supply": 19_700_000.0,
        "total_supply": 21_000_000.0,
        "max_supply": 21_000_000.0,
        "market_cap_rank": 1,
    }


def _healthy_macro(series_id=None, transform=None, bypass_cache=False):
    return {"value": 5.33, "date": "2026-07-01", "prev_value": 5.33, "prev_date": "2026-06-01", "change": 0.0}


def _healthy_global_market_data():
    return {
        "fear_greed": 62.0,
        "btc_dominance": 54.3,
        "fear_greed_status": "ok",
        "btc_dominance_status": "ok",
        "timestamp": time.time(),
    }


@pytest.fixture
def _patched_getters(monkeypatch):
    """Wire every getter _format_info_coin_message reads to safe fixtures, and
    make get_sr_levels() report unavailable so the naive-fallback path is used
    (keeps the test independent from breakout_detector internals)."""
    monkeypatch.setattr(tb, "get_market_snapshot", _healthy_snapshot)
    monkeypatch.setattr(tb, "get_sr_levels", lambda symbol: None)
    monkeypatch.setattr(tb, "get_tokenomics", _healthy_tokenomics)
    monkeypatch.setattr(tb, "get_macro_data", _healthy_macro)
    monkeypatch.setattr(tb, "get_global_market_data", _healthy_global_market_data)


class TestInfoCoinDoesNotTouchSignalPipeline:
    def test_forbidden_functions_never_called(self, monkeypatch, _patched_getters):
        process_signal_mock = Mock()
        record_signal_mock = Mock()
        queue_alert_mock = Mock()
        collect_shadow_mock = Mock()

        monkeypatch.setattr(tb, "process_signal", process_signal_mock)
        monkeypatch.setattr(tb, "record_signal", record_signal_mock)
        monkeypatch.setattr(tb.ngov, "queue_alert", queue_alert_mock)
        monkeypatch.setattr(tb, "collect_shadow_signals", collect_shadow_mock)

        text, err = tb._format_info_coin_message("BTC")

        assert err is None
        assert text is not None
        process_signal_mock.assert_not_called()
        record_signal_mock.assert_not_called()
        queue_alert_mock.assert_not_called()
        collect_shadow_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 3. engine.market.coin_info.get_tokenomics(): fail-open-but-honest + cache TTL
# ---------------------------------------------------------------------------


class FakeCgResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or []

    def json(self):
        return self._json_data


@pytest.fixture(autouse=True)
def _clean_coin_info_cache():
    coin_info.reset_cache_for_tests()
    yield
    coin_info.reset_cache_for_tests()


class TestGetTokenomics:
    def test_fetch_failure_returns_unavailable_not_a_fabricated_number(self, monkeypatch):
        monkeypatch.setattr(
            coin_info, "resolve_coin_id", lambda sym: {"BTC": "bitcoin"}.get(sym)
        )
        with patch("engine.market.coin_info.requests.get", return_value=FakeCgResponse(status_code=500)):
            result = coin_info.get_tokenomics("BTC")
        assert result["status"] == "unavailable"
        assert result["market_cap"] is None
        assert result["message"] is not None

    def test_fetch_success_returns_full_fields(self, monkeypatch):
        monkeypatch.setattr(
            coin_info, "resolve_coin_id", lambda sym: {"BTC": "bitcoin"}.get(sym)
        )
        rows = [
            {
                "id": "bitcoin",
                "market_cap": 1_200_000_000_000,
                "fully_diluted_valuation": 1_300_000_000_000,
                "circulating_supply": 19_700_000,
                "total_supply": 21_000_000,
                "max_supply": 21_000_000,
                "market_cap_rank": 1,
            }
        ]
        with patch("engine.market.coin_info.requests.get", return_value=FakeCgResponse(json_data=rows)) as mock_get:
            result = coin_info.get_tokenomics("BTC")
        assert result["status"] == "ok"
        assert result["market_cap"] == 1_200_000_000_000
        assert result["market_cap_rank"] == 1
        assert result["max_supply"] == 21_000_000
        mock_get.assert_called_once()

    def test_cache_ttl_two_calls_within_window_hit_http_once(self, monkeypatch):
        monkeypatch.setattr(
            coin_info, "resolve_coin_id", lambda sym: {"BTC": "bitcoin"}.get(sym)
        )
        rows = [{"id": "bitcoin", "market_cap": 1.0, "fully_diluted_valuation": 1.0,
                  "circulating_supply": 1.0, "total_supply": 1.0, "max_supply": 1.0,
                  "market_cap_rank": 1}]
        with patch("engine.market.coin_info.requests.get", return_value=FakeCgResponse(json_data=rows)) as mock_get:
            now = time.time()
            coin_info.get_tokenomics("BTC", now=now)
            coin_info.get_tokenomics("BTC", now=now + 10)
        assert mock_get.call_count == 1

    def test_cache_expiry_refetches_after_ttl(self, monkeypatch):
        monkeypatch.setattr(
            coin_info, "resolve_coin_id", lambda sym: {"BTC": "bitcoin"}.get(sym)
        )
        rows = [{"id": "bitcoin", "market_cap": 1.0, "fully_diluted_valuation": 1.0,
                  "circulating_supply": 1.0, "total_supply": 1.0, "max_supply": 1.0,
                  "market_cap_rank": 1}]
        with patch("engine.market.coin_info.requests.get", return_value=FakeCgResponse(json_data=rows)) as mock_get:
            now = time.time()
            coin_info.get_tokenomics("BTC", now=now)
            coin_info.get_tokenomics("BTC", now=now + coin_info.TOKENOMICS_CACHE_SEC + 1)
        assert mock_get.call_count == 2

    def test_unknown_symbol_not_in_response_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            coin_info, "resolve_coin_id", lambda sym: {"BTC": "bitcoin", "ETH": "ethereum"}.get(sym)
        )
        rows = [{"id": "bitcoin", "market_cap": 1.0, "fully_diluted_valuation": 1.0,
                  "circulating_supply": 1.0, "total_supply": 1.0, "max_supply": 1.0,
                  "market_cap_rank": 1}]
        with patch("engine.market.coin_info.requests.get", return_value=FakeCgResponse(json_data=rows)):
            result = coin_info.get_tokenomics("ETH")
        assert result["status"] == "unavailable"


# ---------------------------------------------------------------------------
# 4. Message rendering: healthy vs degraded fixtures
# ---------------------------------------------------------------------------


class TestFormatInfoCoinMessage:
    def test_healthy_fixture_all_sections_populated(self, _patched_getters):
        text, err = tb._format_info_coin_message("BTC")
        assert err is None
        assert "TEKNIKAL" in text
        assert "TOKENOMICS" in text
        assert "ON-CHAIN" in text
        assert "MAKRO & SENTIMEN" in text
        assert "tidak tersedia" not in text
        assert "Fed Funds Rate: 5.33%" in text
        assert "BTC Dominance: 54.30%" in text
        assert "Fear & Greed: 62 (Greed)" in text

    def test_degraded_fixture_shows_unavailable_not_fake_numbers(self, monkeypatch):
        monkeypatch.setattr(tb, "get_market_snapshot", _healthy_snapshot)
        monkeypatch.setattr(tb, "get_sr_levels", lambda symbol: None)
        monkeypatch.setattr(
            tb, "get_tokenomics",
            lambda symbol, now=None: {
                "status": "unavailable", "message": "gagal fetch",
                "market_cap": None, "fully_diluted_valuation": None,
                "circulating_supply": None, "total_supply": None,
                "max_supply": None, "market_cap_rank": None,
            },
        )
        monkeypatch.setattr(tb, "get_macro_data", lambda *a, **k: None)
        monkeypatch.setattr(
            tb, "get_global_market_data",
            lambda: {
                "fear_greed": 50.0, "btc_dominance": 50.0,
                "fear_greed_status": "failed", "btc_dominance_status": "failed",
                "timestamp": time.time(),
            },
        )

        text, err = tb._format_info_coin_message("BTC")
        assert err is None
        assert "Tokenomics: tidak tersedia" in text
        assert "Fed Funds Rate: tidak tersedia" in text
        # The silently-defaulted 50 must never be presented as a real reading --
        # it must always carry the "fetch gagal" annotation next to it.
        assert "(fetch gagal, nilai default)" in text
        assert text.count("(fetch gagal, nilai default)") == 2

    def test_unknown_coin_returns_error_not_crash(self, _patched_getters):
        text, err = tb._format_info_coin_message("NOTACOIN")
        assert text is None
        assert err == "Coin tidak tersedia."

    def test_coin_missing_from_snapshot_returns_error(self, monkeypatch):
        monkeypatch.setattr(tb, "get_market_snapshot", lambda: {"data": {}, "timestamp": None})
        text, err = tb._format_info_coin_message("BTC")
        assert text is None
        assert "tidak tersedia" in err

    def test_sideways_trend_from_insufficient_ma_is_tagged(self, monkeypatch):
        snap = _healthy_snapshot()
        snap["data"]["BTC"]["trend"] = "SIDEWAYS"
        snap["data"]["BTC"]["ma20"] = None
        snap["data"]["BTC"]["ma50"] = None
        snap["data"]["BTC"]["ma200"] = None
        monkeypatch.setattr(tb, "get_market_snapshot", lambda: snap)
        monkeypatch.setattr(tb, "get_sr_levels", lambda symbol: None)
        monkeypatch.setattr(tb, "get_tokenomics", _healthy_tokenomics)
        monkeypatch.setattr(tb, "get_macro_data", _healthy_macro)
        monkeypatch.setattr(tb, "get_global_market_data", _healthy_global_market_data)

        text, err = tb._format_info_coin_message("BTC")
        assert err is None
        assert "SIDEWAYS (data terbatas)" in text

    def test_genuine_sideways_with_full_ma_is_not_tagged(self, monkeypatch):
        # SIDEWAYS trend but ma20/ma50/ma200 are all present -> this is a real
        # sideways reading, not a silent fallback, so it must NOT be tagged.
        snap = _healthy_snapshot()
        snap["data"]["BTC"]["trend"] = "SIDEWAYS"
        monkeypatch.setattr(tb, "get_market_snapshot", lambda: snap)
        monkeypatch.setattr(tb, "get_sr_levels", lambda symbol: None)
        monkeypatch.setattr(tb, "get_tokenomics", _healthy_tokenomics)
        monkeypatch.setattr(tb, "get_macro_data", _healthy_macro)
        monkeypatch.setattr(tb, "get_global_market_data", _healthy_global_market_data)

        text, err = tb._format_info_coin_message("BTC")
        assert err is None
        assert "(data terbatas)" not in text


# ---------------------------------------------------------------------------
# 5. Telegram wiring: menu button -> coin selector -> inline callback
# ---------------------------------------------------------------------------


def _labels(markup):
    return [getattr(button, "text", button) for row in markup.inline_keyboard]


class TestInfoCoinTelegramWiring(IsolatedAsyncioTestCase):
    async def test_menu_button_shows_coin_selector_with_info_prefix(self):
        replies = []

        async def reply_text(message, **kwargs):
            replies.append((message, kwargs.get("reply_markup")))

        message = SimpleNamespace(text="ℹ️ Info Coin", reply_text=reply_text)
        update = SimpleNamespace(message=message, effective_message=message)
        context = SimpleNamespace(user_data={})

        await tb.menu_button_handler(update, context)

        assert len(replies) == 1
        _, markup = replies[0]
        assert markup is not None
        callback_datas = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "info_BTC" in callback_datas

    async def test_info_coin_button_reachable_from_market_submenu(self):
        labels = [
            getattr(btn, "text", btn)
            for row in tb._market_submenu_keyboard().keyboard
            for btn in row
        ]
        assert "ℹ️ Info Coin" in labels

    async def test_callback_info_prefix_calls_formatter_and_replies(self):
        with patch.object(tb, "_authorized_chat", return_value=True), patch.object(
            tb, "_format_info_coin_message", return_value=("PESAN INFO COIN BTC", None)
        ) as mock_fmt:
            reply_mock = AsyncMock()
            callback_query = SimpleNamespace(
                data="info_BTC",
                answer=AsyncMock(),
                message=SimpleNamespace(reply_text=reply_mock),
            )
            update = SimpleNamespace(callback_query=callback_query)
            context = SimpleNamespace()

            await tb.coin_selector_callback(update, context)

        mock_fmt.assert_called_once_with("BTC")
        reply_mock.assert_awaited_once_with("PESAN INFO COIN BTC")

    async def test_callback_info_prefix_shows_error_without_crashing(self):
        with patch.object(tb, "_authorized_chat", return_value=True), patch.object(
            tb, "_format_info_coin_message", return_value=(None, "Coin tidak tersedia.")
        ):
            reply_mock = AsyncMock()
            callback_query = SimpleNamespace(
                data="info_NOPE",
                answer=AsyncMock(),
                message=SimpleNamespace(reply_text=reply_mock),
            )
            update = SimpleNamespace(callback_query=callback_query)
            context = SimpleNamespace()

            await tb.coin_selector_callback(update, context)

        reply_mock.assert_awaited_once_with("Coin tidak tersedia.")
