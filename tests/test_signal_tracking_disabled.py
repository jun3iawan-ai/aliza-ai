"""Perekaman signal_tracking dimatikan (13 Okt 2026). Data lama tidak disentuh."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from engine.trading import signal_tracker
from interfaces import telegram_bot


@pytest.fixture
def isolated_tracker_db(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    return db_path


def test_recording_flag_is_off_by_default():
    assert telegram_bot.SIGNAL_TRACKING_RECORDING_ENABLED is False


def test_parse_and_record_signals_writes_nothing(monkeypatch):
    rec = Mock()
    monkeypatch.setattr(telegram_bot, "record_signal", rec)
    telegram_bot._parse_and_record_signals("• BTC LONG entry 100 sl 99 tp 102", market_score=50)
    rec.assert_not_called()


def test_deterministic_dispatch_does_not_record(monkeypatch):
    monkeypatch.setattr(telegram_bot, "DETERMINISTIC_SIGNAL_ENABLED", True)  # uji gate rekam saja
    rec = Mock()
    monkeypatch.setattr(telegram_bot, "record_signal", rec)
    monkeypatch.setattr(telegram_bot, "process_signal", AsyncMock(return_value=True))
    signal = {"coin": "BTC", "setup": "PULLBACK LONG", "side": "LONG", "entry": 100,
              "sl": 99, "tp1": 102, "rr": 2, "confidence": 80}
    sent = asyncio.run(telegram_bot._dispatch_and_record_deterministic_signal(signal, "chat"))
    assert sent is True
    rec.assert_not_called()


def test_shadow_runner_inert(monkeypatch):
    collect = Mock(return_value=[{"coin": "BTC"}])
    rec = Mock()
    monkeypatch.setattr(telegram_bot, "collect_shadow_signals", collect)
    monkeypatch.setattr(telegram_bot, "record_signal", rec)
    assert asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, "chat")) == 0
    collect.assert_not_called()
    rec.assert_not_called()


def test_shadow_stats_command_disabled(monkeypatch):
    stats = Mock()
    monkeypatch.setattr(telegram_bot, "get_signal_stats", stats)
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    asyncio.run(telegram_bot.shadow_stats_command(update, MagicMock()))
    stats.assert_not_called()
    update.effective_message.reply_text.assert_awaited_once_with(telegram_bot.SIGNAL_TRACKING_DISABLED_TEXT)


def test_tracker_module_and_old_rows_untouched(isolated_tracker_db):
    """Gate hanya di sisi telegram_bot; fungsi tracker dan tabel lama utuh."""
    row_id = signal_tracker.record_signal({
        "coin": "ETH", "setup": "PULLBACK LONG", "side": "LONG", "entry": 100, "sl": 99,
        "tp": 102, "confidence": 80, "rr": 2, "source": "deterministic", "dispatch_status": "SENT",
        "signal_time": "2026-10-01T00:00:00+07:00"})
    assert row_id
    with signal_tracker._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM signal_tracking").fetchone()[0] == 1


def test_deterministic_scanner_flag_off_by_default():
    assert telegram_bot.DETERMINISTIC_SIGNAL_ENABLED is False


def test_scan_gate_does_not_call_scanner_when_off(monkeypatch):
    scan = Mock(return_value={"coin": "BTC"})
    monkeypatch.setattr(telegram_bot, "scan_for_signals", scan)
    assert telegram_bot._scan_for_signals_gated() is None
    scan.assert_not_called()


def test_scan_gate_calls_scanner_when_on(monkeypatch):
    scan = Mock(return_value={"coin": "BTC"})
    monkeypatch.setattr(telegram_bot, "scan_for_signals", scan)
    monkeypatch.setattr(telegram_bot, "DETERMINISTIC_SIGNAL_ENABLED", True)
    assert telegram_bot._scan_for_signals_gated() == {"coin": "BTC"}


def test_dispatch_function_refuses_when_flag_off_even_if_breaker_inactive(monkeypatch):
    process = AsyncMock(return_value=True)
    monkeypatch.setattr(telegram_bot, "process_signal", process)
    sig = {"coin": "BTC", "setup": "PULLBACK LONG", "side": "LONG", "entry": 100, "sl": 99, "tp1": 102}
    assert asyncio.run(telegram_bot._dispatch_and_record_deterministic_signal(sig, "chat")) is False
    process.assert_not_called()
