"""Tests for connecting the learning loop (confidence_adjuster / drawdown_protector)
to live signal_tracking outcomes instead of the frozen data/trade_history.json seed
file. See LEARNING_LOOP_LIVE_DATA_REPORT.md for the decision rationale.
"""

from __future__ import annotations

import sqlite3

import pytest

from engine.learning import confidence_adjuster, learning_engine, trade_history_tracker
from engine.portfolio import drawdown_protector
from engine.trading import signal_tracker


@pytest.fixture
def isolated_tracker_db(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    return db_path


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


class TestGetClosedHistoryLiveData:
    def test_reads_from_signal_tracking_not_json_seed(self, isolated_tracker_db, monkeypatch, tmp_path):
        # Point HISTORY_PATH at a nonexistent file to prove the JSON seed is not consulted.
        monkeypatch.setattr(
            trade_history_tracker, "HISTORY_PATH", str(tmp_path / "nonexistent_seed.json")
        )
        _seed_closed_signal("BTC", "PULLBACK LONG", "WIN")
        _seed_closed_signal("ETH", "PULLBACK LONG", "LOSS")

        closed = trade_history_tracker.get_closed_history()
        assert len(closed) == 2
        results = {c["coin"]: c["result"] for c in closed}
        assert results == {"BTC": "WIN", "ETH": "LOSS"}

    def test_excludes_shadow_e3_by_default(self, isolated_tracker_db):
        _seed_closed_signal("BTC", "PULLBACK LONG", "WIN", source="deterministic")
        _seed_closed_signal("SUI", "PULLBACK LONG", "WIN", source="shadow_e3")

        closed = trade_history_tracker.get_closed_history()
        assert len(closed) == 1
        assert closed[0]["coin"] == "BTC"

    def test_can_explicitly_query_shadow_e3(self, isolated_tracker_db):
        _seed_closed_signal("SUI", "PULLBACK LONG", "LOSS", source="shadow_e3")

        closed = trade_history_tracker.get_closed_history(source="shadow_e3")
        assert len(closed) == 1
        assert closed[0]["coin"] == "SUI"

    def test_excludes_open_signals(self, isolated_tracker_db):
        _seed_closed_signal("BTC", "PULLBACK LONG", "WIN")
        signal_tracker.record_signal(
            {
                "coin": "ETH",
                "setup": "PULLBACK LONG",
                "side": "LONG",
                "source": "deterministic",
                "entry": 100,
                "sl": 95,
                "tp": 110,
            }
        )  # left OPEN, never closed

        closed = trade_history_tracker.get_closed_history()
        assert len(closed) == 1
        assert closed[0]["coin"] == "BTC"

    def test_chronological_order_oldest_first(self, isolated_tracker_db):
        _seed_closed_signal("BTC", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("ETH", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("SOL", "PULLBACK LONG", "WIN")

        closed = trade_history_tracker.get_closed_history()
        assert [c["coin"] for c in closed] == ["BTC", "ETH", "SOL"]


class TestConfidenceAdjusterMinSamples:
    def test_below_default_threshold_no_adjustment(self):
        stats = {"PULLBACK LONG": {"winrate": 1.0, "avg_rr": 2.0, "total_trades": 3}}
        result = confidence_adjuster.adjust_confidence("PULLBACK LONG", 50, stats)
        assert result == 50

    def test_at_default_threshold_applies_high_winrate_bonus(self):
        stats = {"PULLBACK LONG": {"winrate": 0.70, "avg_rr": 2.0, "total_trades": 10}}
        result = confidence_adjuster.adjust_confidence("PULLBACK LONG", 50, stats)
        assert result == 55

    def test_at_default_threshold_applies_low_winrate_penalty(self):
        stats = {"PULLBACK LONG": {"winrate": 0.30, "avg_rr": 1.0, "total_trades": 10}}
        result = confidence_adjuster.adjust_confidence("PULLBACK LONG", 50, stats)
        assert result == 40

    def test_env_override_lowers_threshold(self, monkeypatch):
        monkeypatch.setenv("LEARNING_MIN_SAMPLES", "3")
        stats = {"PULLBACK LONG": {"winrate": 0.70, "avg_rr": 2.0, "total_trades": 3}}
        result = confidence_adjuster.adjust_confidence("PULLBACK LONG", 50, stats)
        assert result == 55

    def test_env_override_raises_threshold(self, monkeypatch):
        monkeypatch.setenv("LEARNING_MIN_SAMPLES", "20")
        stats = {"PULLBACK LONG": {"winrate": 0.70, "avg_rr": 2.0, "total_trades": 10}}
        result = confidence_adjuster.adjust_confidence("PULLBACK LONG", 50, stats)
        assert result == 50


class TestDrawdownProtectorLiveTrigger:
    def test_three_consecutive_live_losses_blocks_trading(self, isolated_tracker_db):
        _seed_closed_signal("BTC", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("ETH", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("SOL", "PULLBACK LONG", "LOSS")

        result = drawdown_protector.check_drawdown()
        assert result["trading_allowed"] is False
        assert result["loss_streak"] == 3

    def test_win_breaks_streak_allows_trading(self, isolated_tracker_db):
        _seed_closed_signal("BTC", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("ETH", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("SOL", "PULLBACK LONG", "WIN")

        result = drawdown_protector.check_drawdown()
        assert result["trading_allowed"] is True

    def test_two_losses_does_not_block(self, isolated_tracker_db):
        _seed_closed_signal("BTC", "PULLBACK LONG", "LOSS")
        _seed_closed_signal("ETH", "PULLBACK LONG", "LOSS")

        result = drawdown_protector.check_drawdown()
        assert result["trading_allowed"] is True

    def test_no_closed_trades_allows_trading(self, isolated_tracker_db):
        result = drawdown_protector.check_drawdown()
        assert result["trading_allowed"] is True


class TestLearningEngineIntegration:
    def test_get_strategy_stats_reflects_live_outcomes(self, isolated_tracker_db):
        for i in range(6):
            _seed_closed_signal(f"WCOIN{i}", "PULLBACK LONG", "WIN", rr=2.0)
        for i in range(4):
            _seed_closed_signal(f"LCOIN{i}", "PULLBACK LONG", "LOSS", rr=1.0)

        stats = learning_engine.get_strategy_stats()
        assert stats["PULLBACK LONG"]["total_trades"] == 10
        assert stats["PULLBACK LONG"]["winrate"] == pytest.approx(0.6)

    def test_confidence_adjuster_end_to_end_with_live_data(self, isolated_tracker_db):
        """10 outcomes at 70% winrate for PULLBACK LONG -> +5 confidence bonus,
        entirely driven by rows in signal_tracking (no trade_history.json)."""
        for i in range(7):
            _seed_closed_signal(f"WCOIN{i}", "PULLBACK LONG", "WIN", rr=2.0)
        for i in range(3):
            _seed_closed_signal(f"LCOIN{i}", "PULLBACK LONG", "LOSS", rr=1.0)

        stats = learning_engine.get_strategy_stats()
        adjusted = confidence_adjuster.adjust_confidence("PULLBACK LONG", 50, stats)
        assert adjusted == 55
