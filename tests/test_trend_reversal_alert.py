"""Tests for edge-triggered per-coin strong-alignment reversal alerts."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from engine.alerts import notification_governor as ngov
from interfaces import telegram_bot as tb


class _Context:
    def __init__(self, chat_id=12345):
        self.bot_data = {"chat_id": chat_id}


@pytest.fixture
def isolated_governor_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ngov, "STATE_FILE", str(tmp_path / "alert_cooldown_state.json"))
    ngov.reset_state_for_tests()
    yield
    ngov.reset_state_for_tests()


def _snapshot(alignment, *, price=100.0, volume_24h=100.0):
    return {
        "data": {
            "BTC": {
                "trend_alignment": alignment,
                "price": price,
                "volume_24h": volume_24h,
            }
        }
    }


def _run_checker(monkeypatch, snapshot, dispatch, avg_volume=100.0):
    monkeypatch.setattr(tb, "get_market_snapshot", lambda: snapshot)
    monkeypatch.setattr(tb, "get_avg_volume", lambda _coin: avg_volume)
    monkeypatch.setattr(tb, "safe_dispatch", dispatch)
    asyncio.run(tb.trend_reversal_checker(_Context()))


def test_bootstrap_stores_strong_baseline_without_alert(isolated_governor_state, monkeypatch):
    dispatch = AsyncMock(return_value=True)

    _run_checker(monkeypatch, _snapshot("STRONG_BULLISH"), dispatch)

    assert ngov.get_value("trend_reversal_state", "BTC") == "BULLISH"
    dispatch.assert_not_awaited()


@pytest.mark.parametrize("alignment", ("PARTIAL", "MIXED", "UNKNOWN"))
def test_transitional_alignments_preserve_baseline_without_alert(
    isolated_governor_state, monkeypatch, alignment
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(return_value=True)

    _run_checker(monkeypatch, _snapshot(alignment), dispatch)

    assert ngov.get_value("trend_reversal_state", "BTC") == "BULLISH"
    dispatch.assert_not_awaited()


def test_reversal_survives_mixed_and_partial_before_opposite_strong(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(return_value=True)

    _run_checker(monkeypatch, _snapshot("MIXED"), dispatch)
    _run_checker(monkeypatch, _snapshot("PARTIAL"), dispatch)
    assert ngov.get_value("trend_reversal_state", "BTC") == "BULLISH"
    dispatch.assert_not_awaited()

    _run_checker(
        monkeypatch,
        _snapshot("STRONG_BEARISH", volume_24h=20.0),
        dispatch,
        avg_volume=100.0,
    )

    dispatch.assert_awaited_once()
    message = dispatch.await_args.args[0]
    assert "REVERSAL TREN TERDETEKSI" in message
    assert "BTC: BULLISH → BEARISH" in message
    assert dispatch.await_args.kwargs == {"chat_id": 12345, "force": True}
    assert ngov.get_value("trend_reversal_state", "BTC") == "BEARISH"


def test_simple_alert_sends_when_volume_is_anomalously_low(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(return_value=True)

    _run_checker(
        monkeypatch,
        _snapshot("STRONG_BEARISH", volume_24h=49.0),
        dispatch,
        avg_volume=100.0,
    )

    dispatch.assert_awaited_once()
    assert "REVERSAL TREN TERDETEKSI" in dispatch.await_args.args[0]
    assert "TERKONFIRMASI" not in dispatch.await_args.args[0]
    assert ngov.get_value("trend_reversal_state", "BTC") == "BEARISH"


def test_strict_alert_sends_only_when_volume_meets_half_of_average(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(return_value=True)

    _run_checker(
        monkeypatch,
        _snapshot("STRONG_BEARISH", price=91.25, volume_24h=50.0),
        dispatch,
        avg_volume=100.0,
    )

    assert dispatch.await_count == 2
    simple_message = dispatch.await_args_list[0].args[0]
    strict_message = dispatch.await_args_list[1].args[0]
    assert "REVERSAL TREN TERDETEKSI" in simple_message
    assert "REVERSAL TREN TERKONFIRMASI" in strict_message
    assert "Volume 24h: 50.00 USDT (avg 14D: 100.00 USDT)" in strict_message
    assert all(call.kwargs == {"chat_id": 12345, "force": True} for call in dispatch.await_args_list)
    assert ngov.get_value("trend_reversal_state", "BTC") == "BEARISH"


def test_same_strong_direction_does_not_refire_after_reversal(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(return_value=True)
    bearish_snapshot = _snapshot("STRONG_BEARISH", volume_24h=100.0)

    _run_checker(monkeypatch, bearish_snapshot, dispatch, avg_volume=100.0)
    assert dispatch.await_count == 2

    _run_checker(monkeypatch, bearish_snapshot, dispatch, avg_volume=100.0)

    assert dispatch.await_count == 2
    assert ngov.get_value("trend_reversal_state", "BTC") == "BEARISH"

def test_simple_dispatch_false_keeps_baseline_for_retry(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(return_value=False)
    bearish_snapshot = _snapshot("STRONG_BEARISH", volume_24h=100.0)

    _run_checker(monkeypatch, bearish_snapshot, dispatch, avg_volume=100.0)

    dispatch.assert_awaited_once()
    assert ngov.get_value("trend_reversal_state", "BTC") == "BULLISH"

    dispatch.return_value = True
    _run_checker(monkeypatch, bearish_snapshot, dispatch, avg_volume=100.0)

    assert dispatch.await_count == 3
    assert ngov.get_value("trend_reversal_state", "BTC") == "BEARISH"


def test_simple_dispatch_exception_keeps_baseline_for_retry(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(side_effect=RuntimeError("Telegram unavailable"))

    _run_checker(
        monkeypatch,
        _snapshot("STRONG_BEARISH", volume_24h=100.0),
        dispatch,
        avg_volume=100.0,
    )

    dispatch.assert_awaited_once()
    assert ngov.get_value("trend_reversal_state", "BTC") == "BULLISH"


def test_strict_dispatch_failure_does_not_block_baseline_update(
    isolated_governor_state, monkeypatch
):
    ngov.set_value("trend_reversal_state", "BTC", "BULLISH")
    dispatch = AsyncMock(side_effect=[True, RuntimeError("strict dispatch failed")])

    _run_checker(
        monkeypatch,
        _snapshot("STRONG_BEARISH", volume_24h=100.0),
        dispatch,
        avg_volume=100.0,
    )

    assert dispatch.await_count == 2
    assert ngov.get_value("trend_reversal_state", "BTC") == "BEARISH"
