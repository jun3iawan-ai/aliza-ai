"""Regression tests for Fase 1 signal-integrity fixes."""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, Mock, patch

import pytest

from engine import risk_manager
from engine.alerts import auto_alert_engine
from engine.market import market_analyzer
from engine.trading import signal_tracker


@pytest.fixture
def isolated_tracker_db(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    return db_path


def _record_short(coin: str) -> int:
    row_id = signal_tracker.record_signal(
        {
            "coin": coin,
            "setup": "PULLBACK SHORT",
            "side": "SHORT",
            "source": "deterministic",
            "dispatch_status": "SENT",
            "entry": 100,
            "sl": 102,
            "tp": 96,
        }
    )
    assert row_id is not None
    return row_id


def test_pullback_short_outcome_uses_explicit_side(isolated_tracker_db, monkeypatch):
    _record_short("BTC")
    _record_short("ETH")

    candles = {
        "BTC": [{"high": 101, "low": 95}],
        "ETH": [{"high": 103, "low": 99}],
    }
    monkeypatch.setattr(
        signal_tracker,
        "_fetch_5m_klines",
        lambda coin, _created, _now: candles[coin],
    )

    closed = signal_tracker.check_open_signals()
    result = {item["coin"]: item for item in closed}
    assert result["BTC"]["status"] == "WIN"
    assert result["BTC"]["pnl_pct"] == pytest.approx(3.8)
    assert result["ETH"]["status"] == "LOSS"
    assert result["ETH"]["pnl_pct"] == pytest.approx(-2.2)


def test_same_bar_tp_and_sl_is_conservative_loss(isolated_tracker_db, monkeypatch):
    _record_short("SOL")
    monkeypatch.setattr(
        signal_tracker,
        "_fetch_5m_klines",
        lambda *_args: [{"high": 103, "low": 95}],
    )

    closed = signal_tracker.check_open_signals()
    assert len(closed) == 1
    assert closed[0]["status"] == "LOSS"
    assert closed[0]["close_price"] == 102


def test_rejected_gateway_is_not_recorded(isolated_tracker_db, monkeypatch):
    from interfaces import telegram_bot

    monkeypatch.setattr(
        telegram_bot, "process_signal", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(telegram_bot, "record_signal", signal_tracker.record_signal)
    signal = {
        "coin": "BTC",
        "setup": "PULLBACK LONG",
        "side": "LONG",
        "entry": 100,
        "sl": 99,
        "tp1": 102,
        "rr": 2,
        "confidence": 80,
    }

    sent = asyncio.run(
        telegram_bot._dispatch_and_record_deterministic_signal(signal, "test-chat")
    )
    assert sent is False
    with signal_tracker._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM signal_tracking").fetchone()[0] == 0


def test_stats_default_excludes_llm(isolated_tracker_db):
    base = {
        "coin": "BTC",
        "setup": "PULLBACK LONG",
        "side": "LONG",
        "dispatch_status": "SENT",
        "entry": 100,
        "sl": 99,
        "tp": 102,
        "signal_time": "2026-01-01T00:00:00+07:00",
    }
    assert signal_tracker.record_signal({**base, "source": "deterministic"})
    assert signal_tracker.record_signal({**base, "source": "llm"})

    stats = signal_tracker.get_signal_stats()
    assert stats["source_filter"] == "deterministic"
    assert stats["total_signals"] == 1
    assert {row["source"]: row["total"] for row in stats["by_source"]} == {
        "deterministic": 1,
        "llm": 1,
    }
    assert stats["by_side"][0]["side"] == "LONG"
    assert stats["by_setup"][0]["setup"] == "PULLBACK LONG"


def test_open_candle_removed_and_ticker_not_appended(monkeypatch):
    raw = [
        [0, "1", "2", "0.5", "1.5", "10", 999],
        [1000, "1", "3", "0.5", "2.5", "10", 2001],
    ]
    assert market_analyzer._extract_closed_kline_closes(raw, now_ms=2000) == [1.5]

    captured = []

    def capture_prices(prices):
        captured.append(list(prices))
        return min(prices[-20:]), max(prices[-20:])

    monkeypatch.setattr(market_analyzer, "_get_price_from_binance", lambda _s: 999.0)
    monkeypatch.setattr(
        market_analyzer,
        "_get_binance_klines",
        Mock(side_effect=[list(range(1, 61)), list(range(1, 61))]),
    )
    monkeypatch.setattr(
        market_analyzer,
        "get_global_market_data",
        lambda: {"fear_greed": 50, "btc_dominance": 50},
    )
    monkeypatch.setattr(market_analyzer, "_support_resistance", capture_prices)
    with patch(
        "engine.brain.trading_brain.TradingBrain.analyze",
        return_value={"setup": "NO SETUP", "side": None},
    ):
        result = market_analyzer.market_signal("TEST", radar_data={})

    assert result is not None
    assert len(captured[-1]) == 60
    assert captured[-1][-1] == 60
    assert 999.0 not in captured[-1]


def test_missing_daily_timeframe_produces_unknown_alignment(monkeypatch):
    monkeypatch.setattr(market_analyzer, "_get_price_from_binance", lambda _s: 60.0)
    monkeypatch.setattr(
        market_analyzer,
        "_get_binance_klines",
        Mock(side_effect=[list(range(1, 61)), list(range(1, 21))]),
    )
    monkeypatch.setattr(
        market_analyzer,
        "get_global_market_data",
        lambda: {"fear_greed": 50, "btc_dominance": 50},
    )
    with patch(
        "engine.brain.trading_brain.TradingBrain.analyze",
        return_value={"setup": "NO SETUP", "side": None},
    ):
        result = market_analyzer.market_signal("TEST", radar_data={})

    assert result is not None
    assert result["trend_1d"] == "UNKNOWN"
    assert result["trend_alignment"] == "UNKNOWN"


def test_validator_rejects_long_with_stop_above_entry(monkeypatch):
    monkeypatch.setattr(risk_manager, "get_active_trades", lambda: [])
    assert not risk_manager.validate_proposed_trade(100, 101, 104, "LONG")
    assert risk_manager.validate_proposed_trade(100, 99, 102, "LONG")


def test_auto_alert_score_contract_and_invalid_startup_threshold(monkeypatch):
    monkeypatch.setenv("AUTO_ALERT_MIN_SCORE", "70")
    assert auto_alert_engine._load_min_score() == 70
    monkeypatch.setattr(auto_alert_engine, "MIN_SCORE", 70)
    opportunity = {
        "coin": "BTC",
        "setup": "PULLBACK LONG",
        "side": "LONG",
        "score": 100,
        "rr": 3,
        "confidence": 80,
        "entry": 100,
        "sl": 99,
        "tp1": 103,
        "tp2": 105,
    }
    assert len(auto_alert_engine.process_auto_alerts([opportunity])) == 1

    monkeypatch.setenv("AUTO_ALERT_MIN_SCORE", "160")
    with pytest.raises(RuntimeError, match="between 0 and 100"):
        auto_alert_engine._load_min_score()


def test_tracking_migration_is_idempotent_and_backfills_legacy(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE signal_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin TEXT NOT NULL,
            setup TEXT,
            status TEXT DEFAULT 'OPEN',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO signal_tracking (coin, setup) VALUES ('BTC', 'PULLBACK SHORT')"
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))

    assert signal_tracker.init_signal_tracking_db()
    assert signal_tracker.init_signal_tracking_db()
    with signal_tracker._connect() as migrated:
        row = migrated.execute(
            "SELECT side, source, signal_id, dispatch_status FROM signal_tracking"
        ).fetchone()
    assert row["side"] == "SHORT"
    assert row["source"] == "legacy"
    assert row["signal_id"]
    assert row["dispatch_status"] == "UNKNOWN"
