"""Tests for the drawdown circuit breaker gating production [TRADE SIGNAL]
broadcast (deterministic source only). See DRAWDOWN_BROADCAST_GATE_REPORT.md
for the design decisions this exercises.
"""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest

from engine import signal_engine as gateway
from engine.alerts import notification_governor as ngov
from engine.trading import signal_tracker
from interfaces import telegram_bot


@pytest.fixture
def isolated_tracker_db(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    return db_path


@pytest.fixture
def isolated_governor_state(tmp_path, monkeypatch):
    state_path = tmp_path / "alert_cooldown_state.json"
    monkeypatch.setattr(ngov, "STATE_FILE", str(state_path))
    ngov.reset_state_for_tests()
    yield state_path


@pytest.fixture(autouse=True)
def _clear_signal_dedup_cache():
    """scan_for_signals()'s 15-min TTL dedup cache (engine.trading.signal_engine.
    LAST_SIGNALS) is a bare module dict shared across the whole test process --
    reset it so one test's dispatch doesn't dedup-block the next."""
    from engine.trading import signal_engine as trading_se

    trading_se.LAST_SIGNALS = {}
    yield
    trading_se.LAST_SIGNALS = {}


def _seed_closed_signal(coin, setup, result, source="deterministic", rr=2.0, confidence=60):
    row_id = signal_tracker.record_signal(
        {
            "coin": coin,
            "setup": setup,
            "side": "LONG",
            "source": source,
            "dispatch_status": "SENT",
            "entry": 100,
            "sl": 95,
            "tp": 110,
            "rr": rr,
            "confidence": confidence,
        }
    )
    assert row_id is not None
    conn = sqlite3.connect(signal_tracker.DB_PATH)
    conn.execute(
        "UPDATE signal_tracking SET status=?, close_price=?, "
        "close_time=datetime('now'), pnl_pct=? WHERE id=?",
        (result, 110 if result == "WIN" else 95, 5.0 if result == "WIN" else -5.0, row_id),
    )
    conn.commit()
    conn.close()
    return row_id


def _make_trade_signal(coin, setup="OVERSOLD BOUNCE"):
    return {
        "coin": coin,
        "setup": setup,
        "side": "LONG",
        "entry": 100,
        "sl": 95,
        "tp1": 110,
        "rr": 3.0,
        "confidence": 70,
    }


@pytest.fixture(autouse=True)
def _bypass_risk_and_macro_gates(monkeypatch):
    """Isolate the breaker behaviour from unrelated gates (risk_manager/macro
    calendar) that these tests don't exercise."""
    monkeypatch.setattr(gateway, "validate_signal_risk", lambda signal: True)
    monkeypatch.setattr(gateway, "get_upcoming_high_impact_events", None)


class TestProcessSignalSuppressDispatch:
    def test_suppress_dispatch_skips_safe_dispatch_but_returns_true(self, monkeypatch):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)
        signal = {**_make_trade_signal("BTC"), "source": "deterministic", "signal_type": gateway.SIGNAL_TYPE_TRADE}

        result = asyncio.run(
            gateway.process_signal(
                "BTC|OVERSOLD BOUNCE", signal, "body", chat_id="test-chat", suppress_dispatch=True
            )
        )

        assert result is True
        dispatch_mock.assert_not_called()

    def test_normal_dispatch_still_calls_safe_dispatch(self, monkeypatch):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)
        signal = {**_make_trade_signal("ETH"), "source": "deterministic", "signal_type": gateway.SIGNAL_TYPE_TRADE}

        result = asyncio.run(
            gateway.process_signal(
                "ETH|OVERSOLD BOUNCE", signal, "body", chat_id="test-chat", suppress_dispatch=False
            )
        )

        assert result is True
        dispatch_mock.assert_called_once()


class TestDeterministicDispatchSuppression:
    def test_three_live_losses_suppresses_dispatch_but_still_records(
        self, isolated_tracker_db, monkeypatch
    ):
        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")

        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        signal = _make_trade_signal("ARB")
        sent = asyncio.run(
            telegram_bot._dispatch_and_record_deterministic_signal(signal, "test-chat")
        )

        assert sent is True  # processed/recorded, even though not user-visible
        dispatch_mock.assert_not_called()

        conn = sqlite3.connect(signal_tracker.DB_PATH)
        row = conn.execute(
            "SELECT dispatch_status, status, source FROM signal_tracking WHERE coin='ARB'"
        ).fetchone()
        conn.close()
        assert row == ("SUPPRESSED", "OPEN", "deterministic")

    def test_no_losses_dispatches_normally(self, isolated_tracker_db, monkeypatch):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        signal = _make_trade_signal("XPL")
        sent = asyncio.run(
            telegram_bot._dispatch_and_record_deterministic_signal(signal, "test-chat")
        )

        assert sent is True
        dispatch_mock.assert_called_once()

        conn = sqlite3.connect(signal_tracker.DB_PATH)
        row = conn.execute(
            "SELECT dispatch_status FROM signal_tracking WHERE coin='XPL'"
        ).fetchone()
        conn.close()
        assert row == ("SENT",)

    def test_two_losses_does_not_suppress(self, isolated_tracker_db, monkeypatch):
        for coin in ("BTC", "ETH"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        signal = _make_trade_signal("SUI")
        asyncio.run(telegram_bot._dispatch_and_record_deterministic_signal(signal, "test-chat"))

        dispatch_mock.assert_called_once()


class TestBreakerTransitionNotifications:
    def test_no_transition_when_never_active(self, isolated_tracker_db, isolated_governor_state, monkeypatch):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))

        dispatch_mock.assert_not_called()

    def test_activation_sends_exactly_one_warning_and_no_repeat(
        self, isolated_tracker_db, isolated_governor_state, monkeypatch
    ):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")

        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        assert dispatch_mock.call_count == 1
        sent_text = dispatch_mock.call_args.args[0]
        assert "Circuit breaker aktif" in sent_text

        # Subsequent cycles, still active, no new WIN -> no repeated warning.
        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        assert dispatch_mock.call_count == 1

    def test_reset_sends_exactly_one_confirmation_and_resumes_dispatch(
        self, isolated_tracker_db, isolated_governor_state, monkeypatch
    ):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")
        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        assert dispatch_mock.call_count == 1  # activation notice

        dispatch_mock.reset_mock()
        _seed_closed_signal("XRP", "PULLBACK LONG", "WIN")  # breaks the streak

        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        assert dispatch_mock.call_count == 1
        assert "nonaktif" in dispatch_mock.call_args.args[0]

        # No repeat once reset is already notified.
        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        assert dispatch_mock.call_count == 1

        dispatch_mock.reset_mock()
        signal = _make_trade_signal("ADA")
        sent = asyncio.run(
            telegram_bot._dispatch_and_record_deterministic_signal(signal, "chat")
        )
        assert sent is True
        dispatch_mock.assert_called_once()  # normal [TRADE SIGNAL] dispatch resumed

    def test_state_persists_across_simulated_restart(
        self, isolated_tracker_db, isolated_governor_state, monkeypatch
    ):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")
        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        assert dispatch_mock.call_count == 1

        # Simulate a process restart: drop the in-memory notification_governor
        # cache so the next read must come from disk (STATE_FILE).
        ngov._state_cache = None
        dispatch_mock.reset_mock()

        asyncio.run(telegram_bot._notify_drawdown_breaker_transition("chat"))
        dispatch_mock.assert_not_called()  # still active, already notified pre-"restart"


class TestShadowAndLlmUnaffectedByBreaker:
    def test_llm_source_signal_dispatches_via_process_signal_unaffected_by_breaker(
        self, isolated_tracker_db, monkeypatch
    ):
        """llm/SPOT-FUTURES advisory signals go through the same process_signal()
        gateway as deterministic trade signals, but only _dispatch_and_record_
        deterministic_signal ever passes suppress_dispatch=True (confirmed by
        `grep -rn suppress_dispatch` -- single call site, hardcoded to the
        deterministic path). Calling process_signal() directly for an llm signal,
        exactly as morning/evening summary code does, must dispatch normally
        even while the deterministic breaker is active."""
        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")  # breaker active

        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        llm_signal = {
            **_make_trade_signal("BONE"),
            "source": "llm",
            "signal_type": gateway.SIGNAL_TYPE_TRADE,
        }
        sent = asyncio.run(
            gateway.process_signal("BONE|llm-advisory", llm_signal, "SARAN SPOT/FUTURES body", chat_id="chat")
        )

        assert sent is True
        dispatch_mock.assert_called_once()

    def test_shadow_e3_dispatch_ignores_breaker_state(
        self, isolated_tracker_db, monkeypatch
    ):
        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")  # breaker active

        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)
        monkeypatch.setattr(
            telegram_bot,
            "collect_shadow_signals",
            lambda snapshot: [
                {
                    "coin": "SUI",
                    "setup": "OVERSOLD BOUNCE",
                    "side": "LONG",
                    "entry": 1.0,
                    "sl": 0.9,
                    "tp1": 1.3,
                    "atr_14": 0.033,
                    "source": "shadow_e3",
                }
            ],
        )
        monkeypatch.setattr(telegram_bot, "shadow_dispatch_enabled", lambda: True)
        monkeypatch.setattr(telegram_bot, "_shadow_signal_allowed", lambda *a, **k: True)

        recorded = asyncio.run(telegram_bot._run_shadow_e3({}, "chat"))

        assert recorded == 1
        dispatch_mock.assert_called_once()  # shadow dispatch unaffected by breaker

        conn = sqlite3.connect(signal_tracker.DB_PATH)
        row = conn.execute(
            "SELECT source, dispatch_status FROM signal_tracking WHERE coin='SUI'"
        ).fetchone()
        conn.close()
        assert row == ("shadow_e3", "SENT")
