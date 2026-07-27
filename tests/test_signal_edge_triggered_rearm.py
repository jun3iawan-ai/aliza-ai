"""Regression tests for deterministic [TRADE SIGNAL] edge-triggered re-arm."""

from __future__ import annotations

import copy
import logging

import pytest

from engine.trading import signal_engine as signal_se
from engine.trading import signal_tracker


@pytest.fixture(autouse=True)
def isolated_edge_state(monkeypatch):
    """Keep persisted signal state and wall clock deterministic per test."""
    persisted: dict = {}

    def save_state(state):
        persisted["state"] = copy.deepcopy(state)

    def load_state():
        return copy.deepcopy(persisted.get("state", {}))

    monkeypatch.setattr(signal_se, "save_state", save_state)
    monkeypatch.setattr(signal_se, "load_state", load_state)
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}
    yield persisted
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}


@pytest.fixture
def clock(monkeypatch):
    value = {"now": 0.0}
    monkeypatch.setattr(signal_se.time, "time", lambda: value["now"])
    return value


def _signal(coin="SUI", setup="OVERSOLD BOUNCE", side="LONG"):
    return {
        "coin": coin,
        "setup": setup,
        "side": side,
        "source": "deterministic",
        "signal_type": "trade_signal",
    }


def _attempt(signal):
    key = f"{signal['coin']}|{signal['setup']}"
    if signal_se.can_send_signal(key, signal):
        signal_se.record_signal_sent(key, signal)
        return True
    return False


def _observe_valid(*signals):
    coins = {signal["coin"] for signal in signals}
    signal_se.observe_signal_validity(list(signals), coins)


def _observe_invalid(*coins):
    signal_se.observe_signal_validity([], set(coins))


def test_continuously_valid_setup_dispatches_once_even_after_ttl(clock, caplog):
    signal = _signal()
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")
    sent = 0

    # Twenty 60-second snapshots cross the old 15-minute TTL floor twice.
    for _ in range(20):
        _observe_valid(signal)
        sent += _attempt(signal)
        clock["now"] += 60

    assert sent == 1
    assert "suppressed_same_episode key=SUI|OVERSOLD BOUNCE|LONG" in caplog.text
    assert "new key=SUI|OVERSOLD BOUNCE|LONG" in caplog.text


def test_short_invalid_flicker_does_not_rearm(clock, caplog):
    signal = _signal()
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")
    _observe_valid(signal)
    assert _attempt(signal) is True

    # Two scans is below the default three-scan debounce.
    _observe_invalid("SUI")
    _observe_invalid("SUI")
    clock["now"] = 1_000
    _observe_valid(signal)

    assert _attempt(signal) is False
    assert signal_se.EDGE_SIGNAL_STATE["SUI|OVERSOLD BOUNCE|LONG"]["active"] is True
    assert "suppressed_same_episode key=SUI|OVERSOLD BOUNCE|LONG" in caplog.text


def test_reset_after_debounce_dispatches_new_when_floor_has_elapsed(clock, caplog):
    signal = _signal()
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")
    _observe_valid(signal)
    assert _attempt(signal) is True

    for now in (60, 120, 180):
        clock["now"] = now
        _observe_invalid("SUI")

    clock["now"] = 901
    _observe_valid(signal)
    assert _attempt(signal) is True
    assert "reset key=SUI|OVERSOLD BOUNCE|LONG invalid_scans=3 debounce=3" in caplog.text


def test_reset_inside_floor_cooldown_is_suppressed(clock, caplog):
    signal = _signal()
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")
    _observe_valid(signal)
    assert _attempt(signal) is True

    for now in (60, 120, 180):
        clock["now"] = now
        _observe_invalid("SUI")

    clock["now"] = 240
    _observe_valid(signal)
    assert _attempt(signal) is False
    assert "suppressed_floor_cooldown key=SUI|OVERSOLD BOUNCE|LONG" in caplog.text


def test_keys_are_independent_by_coin_setup_and_side(clock):
    sui = _signal("SUI")
    arb = _signal("ARB")
    _observe_valid(sui, arb)
    assert _attempt(sui) is True
    assert _attempt(arb) is True

    clock["now"] = 1_000
    _observe_invalid("SUI")
    _observe_invalid("SUI")
    _observe_invalid("SUI")
    _observe_valid(sui, arb)

    assert _attempt(sui) is True
    assert _attempt(arb) is False


def test_active_episode_persists_across_simulated_restart(clock, isolated_edge_state):
    signal = _signal()
    _observe_valid(signal)
    assert _attempt(signal) is True
    assert "edge_signal_state" in isolated_edge_state["state"]

    # Drop module memory; loading must recover the active episode from persisted
    # state, so an unchanged valid setup is not treated as new after restart.
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}
    signal_se._init_last_signals_from_disk()
    clock["now"] = 1_000
    _observe_valid(signal)

    assert _attempt(signal) is False


def test_shadow_and_notification_governor_cooldowns_are_untouched(monkeypatch):
    from engine.shadow import e3_shadow
    from interfaces import telegram_bot

    monkeypatch.delenv("SHADOW_SIGNAL_COOLDOWN_SEC", raising=False)
    assert e3_shadow.dispatch_cooldown_sec() == 14_400
    assert telegram_bot._SNAPSHOT_ALERT_COOLDOWN_SEC == 4 * 3600

def test_first_bootstrap_uses_open_deterministic_tracking_rows(tmp_path, monkeypatch, clock, caplog):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    assert signal_tracker.record_signal({
        "coin": "ETH",
        "setup": "OVERBOUGHT REJECTION",
        "side": "SHORT",
        "source": "deterministic",
        "dispatch_status": "SENT",
        "entry": 1950,
        "sl": 1975,
        "tp": 1855,
    })

    legacy_state = {"last_signals": {}, "edge_signal_state": {}}
    persisted = {}
    monkeypatch.setattr(signal_se, "load_state", lambda: copy.deepcopy(legacy_state))
    monkeypatch.setattr(
        signal_se,
        "save_state",
        lambda state: persisted.update({"state": copy.deepcopy(state)}),
    )
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")

    signal_se._init_last_signals_from_disk()
    eth = _signal("ETH", "OVERBOUGHT REJECTION", "SHORT")
    _observe_valid(eth)

    assert signal_se.EDGE_SIGNAL_STATE["ETH|OVERBOUGHT REJECTION|SHORT"] == {
        "active": True,
        "inactive_scans": 0,
    }
    assert persisted["state"]["edge_signal_state_bootstrapped"] is True
    assert _attempt(eth) is False
    assert "bootstrap source=signal_tracking open=1 added=1" in caplog.text
    assert "suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT" in caplog.text


def test_bootstrap_marker_prevents_reseeding_on_later_restart(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    assert signal_tracker.record_signal({
        "coin": "ETH",
        "setup": "OVERBOUGHT REJECTION",
        "side": "SHORT",
        "source": "deterministic",
        "dispatch_status": "SENT",
        "entry": 1950,
        "sl": 1975,
        "tp": 1855,
    })

    initialized_state = {
        "last_signals": {},
        "edge_signal_state": {},
        "edge_signal_state_bootstrapped": True,
    }
    monkeypatch.setattr(signal_se, "load_state", lambda: copy.deepcopy(initialized_state))
    monkeypatch.setattr(signal_se, "save_state", lambda _state: None)
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}

    signal_se._init_last_signals_from_disk()
    assert signal_se.EDGE_SIGNAL_STATE == {}
