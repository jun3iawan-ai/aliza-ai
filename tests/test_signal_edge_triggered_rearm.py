"""Regression tests for deterministic [TRADE SIGNAL] OPEN-row episode gating."""

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

    monkeypatch.setattr(
        signal_se, "save_state", lambda state: persisted.update({"state": copy.deepcopy(state)})
    )
    monkeypatch.setattr(
        signal_se, "load_state", lambda: copy.deepcopy(persisted.get("state", {}))
    )
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}
    yield persisted
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}


@pytest.fixture
def tracker_db(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    return db_path


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
        "entry": 100.0,
        "sl": 95.0,
        "tp": 110.0,
        "rr": 3.0,
        "confidence": 70,
    }


def _attempt(signal):
    key = f"{signal['coin']}|{signal['setup']}"
    if signal_se.can_send_signal(key, signal):
        signal_se.record_signal_sent(key, signal)
        return True
    return False


def _record_open(signal, **overrides):
    row = dict(signal)
    row.update(overrides)
    row.setdefault("dispatch_status", "SENT")
    row_id = signal_tracker.record_signal(row)
    assert row_id is not None
    return row_id


def _observe_valid(*signals):
    signal_se.observe_signal_validity(list(signals), {s["coin"] for s in signals})


def _observe_invalid(*coins):
    signal_se.observe_signal_validity([], set(coins))


def test_open_row_blocks_rr_oscillation_even_after_floor_ttl(tracker_db, clock, caplog):
    """Production regression: RR dips cannot re-arm an ETH row that is still OPEN."""
    eth = _signal("ETH", "OVERBOUGHT REJECTION", "SHORT")
    _record_open(eth, entry=1951.99, sl=1974.27, tp=1856.02)
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")

    # Exact production shape: invalid RR scans, then valid again after the TTL.
    for now, rr, should_attempt in (
        (60, 2.75, False),
        (120, 2.80, False),
        (180, 2.80, False),
        (1_001, 3.08, True),
    ):
        clock["now"] = now
        candidate = {**eth, "rr": rr}
        if rr >= 3:
            _observe_valid(candidate)
        else:
            _observe_invalid("ETH")
        if should_attempt:
            assert _attempt(candidate) is False

    assert signal_tracker.has_open_episode(
        coin="ETH", setup="OVERBOUGHT REJECTION", side="SHORT", source="deterministic"
    )
    assert signal_se.EDGE_SIGNAL_STATE["ETH|OVERBOUGHT REJECTION|SHORT"]["active"] is True
    assert "suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT" in caplog.text
    assert "new key=ETH|OVERBOUGHT REJECTION|SHORT" not in caplog.text


@pytest.mark.parametrize("outcome", ["WIN", "LOSS", "EXPIRED"])
def test_terminal_tracker_status_synchronously_rearms_after_floor(
    tracker_db, clock, monkeypatch, outcome, caplog
):
    signal = _signal()
    _attempt(signal)  # establishes the 900-second floor exactly as production dispatch does
    _record_open(signal)
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")

    monkeypatch.setattr(signal_tracker, "_fetch_5m_klines", lambda *_args: [])
    monkeypatch.setattr(
        signal_tracker,
        "_evaluate_outcome",
        lambda **_kwargs: (outcome, 110.0 if outcome == "WIN" else 95.0, 1.0),
    )
    closed = signal_tracker.check_open_signals()

    assert closed[0]["status"] == outcome
    assert signal_se.EDGE_SIGNAL_STATE["SUI|OVERSOLD BOUNCE|LONG"]["active"] is False
    assert "tracking_closed key=SUI|OVERSOLD BOUNCE|LONG" in caplog.text

    clock["now"] = 901
    assert _attempt(signal) is True
    assert "new key=SUI|OVERSOLD BOUNCE|LONG" in caplog.text


def test_first_signal_without_open_row_dispatches_immediately(tracker_db, clock, caplog):
    signal = _signal("ARB")
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")

    assert _attempt(signal) is True
    assert signal_tracker.has_open_episode(
        coin="ARB", setup="OVERSOLD BOUNCE", side="LONG", source="deterministic"
    ) is False
    assert "new key=ARB|OVERSOLD BOUNCE|LONG" in caplog.text


def test_eth_replay_invalid_rr_then_valid_is_same_episode(tracker_db, clock, caplog):
    eth = _signal("ETH", "OVERBOUGHT REJECTION", "SHORT")
    _record_open(eth, entry=1951.99, sl=1974.2672, tp=1856.02)
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")

    for now, rr in ((60, 2.75), (120, 2.80), (180, 2.80)):
        clock["now"] = now
        _observe_invalid("ETH")
        assert signal_se.EDGE_SIGNAL_STATE["ETH|OVERBOUGHT REJECTION|SHORT"]["active"] is True

    clock["now"] = 1_001
    valid_eth = {**eth, "rr": 3.08}
    _observe_valid(valid_eth)
    assert _attempt(valid_eth) is False
    assert "suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT" in caplog.text
    assert "new key=ETH|OVERBOUGHT REJECTION|SHORT" not in caplog.text


def test_open_guard_and_edge_identity_include_side(tracker_db):
    long = _signal("BTC", "CUSTOM SETUP", "LONG")
    short = _signal("BTC", "CUSTOM SETUP", "SHORT")

    assert _record_open(long) is not None
    assert _record_open(short) is not None
    assert signal_tracker.record_signal(long) is None
    assert signal_tracker.has_open_episode(
        coin="BTC", setup="CUSTOM SETUP", side="LONG", source="deterministic"
    )
    assert signal_tracker.has_open_episode(
        coin="BTC", setup="CUSTOM SETUP", side="SHORT", source="deterministic"
    )
    assert set(signal_se.EDGE_SIGNAL_STATE) == {
        "BTC|CUSTOM SETUP|LONG", "BTC|CUSTOM SETUP|SHORT"
    }


def test_bootstrap_uses_open_row_and_suppresses_same_episode(tracker_db, monkeypatch, clock, caplog):
    eth = _signal("ETH", "OVERBOUGHT REJECTION", "SHORT")
    _record_open(eth, entry=1950, sl=1975, tp=1855)
    legacy_state = {"last_signals": {}, "edge_signal_state": {}}
    persisted = {}
    monkeypatch.setattr(signal_se, "load_state", lambda: copy.deepcopy(legacy_state))
    monkeypatch.setattr(
        signal_se, "save_state", lambda state: persisted.update({"state": copy.deepcopy(state)})
    )
    signal_se.LAST_SIGNALS = {}
    signal_se.EDGE_SIGNAL_STATE = {}
    caplog.set_level(logging.INFO, logger="engine.trading.signal_engine")

    signal_se._init_last_signals_from_disk()
    clock["now"] = 1_000
    assert _attempt(eth) is False
    assert persisted["state"]["edge_signal_state_bootstrapped"] is True
    assert "bootstrap source=signal_tracking open=1 added=1" in caplog.text
    assert "suppressed_same_episode key=ETH|OVERBOUGHT REJECTION|SHORT" in caplog.text


def test_bootstrap_marker_prevents_reseeding_on_later_restart(tracker_db, monkeypatch):
    _record_open(_signal("ETH", "OVERBOUGHT REJECTION", "SHORT"))
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


def test_shadow_and_notification_governor_cooldowns_are_untouched(monkeypatch):
    from engine.shadow import e3_shadow
    from interfaces import telegram_bot

    monkeypatch.delenv("SHADOW_SIGNAL_COOLDOWN_SEC", raising=False)
    assert e3_shadow.dispatch_cooldown_sec() == 14_400
    assert telegram_bot._SNAPSHOT_ALERT_COOLDOWN_SEC == 4 * 3600
