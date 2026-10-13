"""Tests for the proactive weekly winrate summary job. See
WEEKLY_WINRATE_SUMMARY_REPORT.md for the design decisions this exercises.
"""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def _seed_open_signal(coin, setup="OVERSOLD BOUNCE", source="deterministic"):
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
        }
    )
    assert row_id is not None
    return row_id


class TestFormatSourceBlock:
    def test_zero_signals_shows_no_data_line(self, isolated_tracker_db):
        block = telegram_bot._format_source_block("PRODUKSI (deterministic)", "🟢", "deterministic")
        assert "Total sinyal: 0" in block
        assert "Belum ada sinyal tercatat" in block

    def test_below_threshold_shows_insufficient_data_disclaimer(self, isolated_tracker_db, monkeypatch):
        monkeypatch.setenv("LEARNING_MIN_SAMPLES", "10")
        for i in range(3):
            _seed_closed_signal(f"WIN{i}", "PULLBACK LONG", "WIN")

        block = telegram_bot._format_source_block("PRODUKSI (deterministic)", "🟢", "deterministic")

        assert "N=3 closed" in block
        assert "BELUM CUKUP DATA" in block

    def test_at_or_above_threshold_shows_winrate_without_disclaimer_plus_rr_pf(
        self, isolated_tracker_db, monkeypatch
    ):
        monkeypatch.setenv("LEARNING_MIN_SAMPLES", "10")
        for i in range(7):
            _seed_closed_signal(f"WIN{i}", "PULLBACK LONG", "WIN", rr=2.0)
        for i in range(3):
            _seed_closed_signal(f"LOSS{i}", "PULLBACK LONG", "LOSS", rr=1.0)

        block = telegram_bot._format_source_block("PRODUKSI (deterministic)", "🟢", "deterministic")

        assert "N=10 closed" in block
        assert "BELUM CUKUP DATA" not in block
        assert "Winrate: 70.0%" in block
        assert "Avg RR" in block
        assert "Profit Factor" in block


class TestNewSignalNote:
    def test_first_call_counts_all_lifetime_signals_as_new(self, isolated_tracker_db, isolated_governor_state):
        _seed_open_signal("BTC")
        _seed_open_signal("ETH")

        note = telegram_bot._weekly_summary_new_signal_note("deterministic", current_total=2)

        assert "+2 sinyal baru" in note

    def test_no_new_signals_since_last_summary(self, isolated_tracker_db, isolated_governor_state):
        ngov.set_value("weekly_winrate_summary", "last_total_deterministic", 5)

        note = telegram_bot._weekly_summary_new_signal_note("deterministic", current_total=5)

        assert note == "Tidak ada sinyal baru minggu ini."

    def test_some_new_signals_since_last_summary(self, isolated_tracker_db, isolated_governor_state):
        ngov.set_value("weekly_winrate_summary", "last_total_deterministic", 5)

        note = telegram_bot._weekly_summary_new_signal_note("deterministic", current_total=8)

        assert "+3 sinyal baru" in note


class TestFullSummaryMessage:
    def test_zero_signals_both_sources_does_not_crash(self, isolated_tracker_db, isolated_governor_state):
        message = telegram_bot.format_weekly_winrate_summary()

        assert "RINGKASAN WINRATE MINGGUAN" in message
        assert "PRODUKSI (deterministic)" in message
        assert "RISET (shadow_e3" in message
        assert "Circuit breaker" in message

    def test_repeated_call_with_no_new_data_reports_no_new_signals(
        self, isolated_tracker_db, isolated_governor_state, monkeypatch
    ):
        monkeypatch.setenv("LEARNING_MIN_SAMPLES", "10")
        _seed_closed_signal("BTC", "PULLBACK LONG", "LOSS")

        first = telegram_bot.format_weekly_winrate_summary()
        assert "+1 sinyal baru" in first  # first run: lifetime total counted as new

        second = telegram_bot.format_weekly_winrate_summary()
        assert "Tidak ada sinyal baru minggu ini." in second

    def test_breaker_active_reflected_in_message(self, isolated_tracker_db, isolated_governor_state):
        for coin in ("BTC", "ETH", "SOL"):
            _seed_closed_signal(coin, "PULLBACK LONG", "LOSS")

        message = telegram_bot.format_weekly_winrate_summary()

        assert "Circuit breaker: AKTIF" in message
        assert "loss streak 3" in message

    def test_breaker_inactive_reflected_in_message(self, isolated_tracker_db, isolated_governor_state):
        _seed_closed_signal("BTC", "PULLBACK LONG", "WIN")

        message = telegram_bot.format_weekly_winrate_summary()

        assert "Circuit breaker: tidak aktif" in message

    def test_shadow_source_independent_of_empty_deterministic(
        self, isolated_tracker_db, isolated_governor_state, monkeypatch
    ):
        """Deterministic totally empty must not crash the shadow_e3 block (or
        vice versa) -- each source is read/rendered independently."""
        monkeypatch.setenv("LEARNING_MIN_SAMPLES", "10")
        for i in range(10):
            _seed_closed_signal(f"S{i}", "OVERSOLD BOUNCE", "WIN", source="shadow_e3", rr=3.0)

        message = telegram_bot.format_weekly_winrate_summary()

        assert "Belum ada sinyal tercatat" in message  # deterministic empty
        assert "Winrate: 100.0%" in message  # shadow_e3 has data


class TestWeeklyWinrateSummaryJob:
    def test_job_dispatches_with_force_true_to_resolved_chat_id(
        self, isolated_tracker_db, isolated_governor_state, monkeypatch
    ):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)
        _seed_closed_signal("BTC", "PULLBACK LONG", "WIN")

        context = MagicMock()
        context.bot_data = {"chat_id": "test-chat-id"}
        asyncio.run(telegram_bot.weekly_winrate_summary_job(context))

        dispatch_mock.assert_called_once()
        args, kwargs = dispatch_mock.call_args
        assert kwargs["chat_id"] == "test-chat-id"
        assert kwargs["force"] is True
        assert "RINGKASAN WINRATE MINGGUAN" in args[0]

    def test_job_skips_dispatch_when_no_chat_id(self, isolated_tracker_db, isolated_governor_state, monkeypatch):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)
        monkeypatch.setattr(telegram_bot, "DEFAULT_CHAT_ID", None)

        context = MagicMock()
        context.bot_data = {}
        asyncio.run(telegram_bot.weekly_winrate_summary_job(context))

        dispatch_mock.assert_not_called()

    def test_command_replies_disabled_and_sends_nothing(self, isolated_tracker_db, isolated_governor_state, monkeypatch):
        dispatch_mock = AsyncMock(return_value=True)
        monkeypatch.setattr(telegram_bot, "safe_dispatch", dispatch_mock)

        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        context.bot_data = {"chat_id": "test-chat-id"}
        asyncio.run(telegram_bot.weekly_winrate_summary_command(update, context))

        dispatch_mock.assert_not_called()
        update.effective_message.reply_text.assert_awaited_once_with(telegram_bot.SIGNAL_TRACKING_DISABLED_TEXT)
        assert "NONAKTIF" in telegram_bot.SIGNAL_TRACKING_DISABLED_TEXT

    def test_signal_stats_command_disabled_and_does_not_read_stats(self, monkeypatch):
        stats_mock = MagicMock()
        monkeypatch.setattr(telegram_bot, "get_signal_stats", stats_mock)
        update = MagicMock()
        update.effective_message.reply_text = AsyncMock()
        asyncio.run(telegram_bot.signal_stats_command(update, MagicMock()))

        stats_mock.assert_not_called()
        update.effective_message.reply_text.assert_awaited_once_with(telegram_bot.SIGNAL_TRACKING_DISABLED_TEXT)


class TestJobScheduling:
    @staticmethod
    def _weekly_calls(monkeypatch):
        app_mock = MagicMock()
        builder_mock = MagicMock()
        builder_mock.token.return_value = builder_mock
        builder_mock.post_init.return_value = builder_mock
        builder_mock.post_shutdown.return_value = builder_mock
        builder_mock.build.return_value = app_mock
        monkeypatch.setattr(telegram_bot, "BOT_TOKEN", "fake-token-for-test")
        monkeypatch.setattr(telegram_bot, "ApplicationBuilder", MagicMock(return_value=builder_mock))
        monkeypatch.setattr(telegram_bot, "GracefulShutdownController", MagicMock())
        monkeypatch.setattr(telegram_bot, "init_trade_db", MagicMock())
        monkeypatch.setattr(telegram_bot, "init_signal_tracking_db", MagicMock())
        monkeypatch.setattr(telegram_bot, "update_market_snapshot", MagicMock())
        telegram_bot.main()
        return [
            call
            for call in app_mock.job_queue.run_daily.call_args_list
            if call.args and call.args[0] is telegram_bot.weekly_winrate_summary_job
        ]

    def test_weekly_job_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("WEEKLY_WINRATE_SCHEDULE_ENABLED", raising=False)
        assert self._weekly_calls(monkeypatch) == []

    def test_weekly_job_never_scheduled_even_if_env_true(self, monkeypatch):
        monkeypatch.setenv("WEEKLY_WINRATE_SCHEDULE_ENABLED", "true")
        assert self._weekly_calls(monkeypatch) == []
