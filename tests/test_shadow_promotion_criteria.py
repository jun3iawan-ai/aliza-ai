"""Tests for the read-only shadow_e3 -> production promotion criteria checker.
See SHADOW_PROMOTION_CHECKLIST_REPORT.md for the methodology decisions
(bootstrap CI minimum N, coin-concentration definition, observation window
start) these scenarios are built to exercise.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.shadow import promotion_criteria as pc
from engine.trading import signal_tracker
from interfaces import telegram_bot


@pytest.fixture
def isolated_tracker_db(tmp_path, monkeypatch):
    db_path = tmp_path / "signals.db"
    monkeypatch.setattr(signal_tracker, "DB_PATH", str(db_path))
    assert signal_tracker.init_signal_tracking_db()
    return db_path


def _bulk_seed_closed(rows, source="shadow_e3", signal_time=None):
    """rows: list of (coin, pnl_pct) tuples. Inserts directly via executemany
    (bypassing signal_tracker.record_signal's per-row dedup SELECTs) so
    large-N scenarios (needed to keep the bootstrap CI narrow) stay fast."""
    ts = signal_time or datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(signal_tracker.DB_PATH)
    conn.executemany(
        """
        INSERT INTO signal_tracking
            (coin, setup, side, source, status, pnl_pct, signal_time, close_time, dispatch_status)
        VALUES (?, 'PULLBACK LONG', 'LONG', ?, ?, ?, ?, ?, 'SENT')
        """,
        [
            (coin, source, "WIN" if pnl > 0 else "LOSS", pnl, ts, ts)
            for coin, pnl in rows
        ],
    )
    conn.commit()
    conn.close()


def _unique_coin_pnls(pnls, prefix="C"):
    """Pair each pnl value with a unique coin label so no single coin ever
    accidentally dominates total positive PnL (keeps concentration well under
    50% unless a scenario deliberately wants otherwise)."""
    return [(f"{prefix}{i}", pnl) for i, pnl in enumerate(pnls)]


OLD_SIGNAL_TIME = (datetime.now(timezone.utc) - timedelta(weeks=10)).isoformat()
RECENT_SIGNAL_TIME = datetime.now(timezone.utc).isoformat()


class TestAllCriteriaPass:
    def test_all_pass(self, isolated_tracker_db):
        pnls = [1.0] * 50 + [-0.3] * 20  # N=70 >= 60 (observation via N)
        _bulk_seed_closed(_unique_coin_pnls(pnls))

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["all_passed"] is True
        for name, check in result["checks"].items():
            assert check["passed"] is True, f"{name} unexpectedly failed: {check}"

        message = pc.format_promotion_check_message(result)
        assert "MEMENUHI SEMUA KRITERIA" in message
        assert "✅" in message
        assert "❌" not in message


class TestEachCriterionFailsInIsolation:
    def test_expectancy_fails_others_pass(self, isolated_tracker_db):
        pnls = [0.35] * 40 + [-0.20] * 30  # N=70, exp=0.114%, pf=2.33, ci~+0.05
        _bulk_seed_closed(_unique_coin_pnls(pnls))

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["checks"]["expectancy"]["passed"] is False
        assert result["checks"]["profit_factor"]["passed"] is True
        assert result["checks"]["ci_lower_bound"]["passed"] is True
        assert result["checks"]["coin_concentration"]["passed"] is True
        assert result["checks"]["observation"]["passed"] is True
        assert result["all_passed"] is False

        message = pc.format_promotion_check_message(result)
        assert "BELUM MEMENUHI" in message
        assert "expectancy" in message
        assert f"{result['checks']['expectancy']['value']:+.4f}%" in message

    def test_profit_factor_fails_others_pass(self, isolated_tracker_db):
        # Same per-trade magnitudes replicated to N=1000 to keep the bootstrap
        # CI narrow (see report: variance, not just the mean, drives the CI;
        # smaller N with this spread also fails CI, which would contaminate
        # this "PF only" scenario).
        pnls = [5.325] * 200 + [-3.0] * 300  # N=500... replicate once more
        pnls = [5.325] * 400 + [-3.0] * 600  # N=1000, exp=0.33%, pf=1.1833
        _bulk_seed_closed(_unique_coin_pnls(pnls))

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["checks"]["expectancy"]["passed"] is True
        assert result["checks"]["profit_factor"]["passed"] is False
        assert result["checks"]["ci_lower_bound"]["passed"] is True
        assert result["checks"]["coin_concentration"]["passed"] is True
        assert result["checks"]["observation"]["passed"] is True
        assert result["all_passed"] is False

        message = pc.format_promotion_check_message(result)
        assert "profit factor" in message

    def test_ci_lower_bound_fails_others_pass(self, isolated_tracker_db):
        # Few large wins + many small losses: positive mean and PF, but high
        # variance drags the 2.5th-percentile bootstrap estimate below -0.1%.
        pnls = [20.0] * 5 + [-1.0] * 25  # N=30 < 60 -> back-date for observation
        _bulk_seed_closed(_unique_coin_pnls(pnls), signal_time=OLD_SIGNAL_TIME)

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["checks"]["expectancy"]["passed"] is True
        assert result["checks"]["profit_factor"]["passed"] is True
        assert result["checks"]["ci_lower_bound"]["passed"] is False
        assert result["checks"]["ci_lower_bound"]["computable"] is True
        assert result["checks"]["coin_concentration"]["passed"] is True
        assert result["checks"]["observation"]["passed"] is True
        assert result["all_passed"] is False

        message = pc.format_promotion_check_message(result)
        assert "batas bawah bootstrap CI" in message

    def test_coin_concentration_fails_others_pass(self, isolated_tracker_db):
        # One coin ("WHALE") contributes the vast majority of total positive PnL.
        rows = [("WHALE", 50.0)] + _unique_coin_pnls([1.0] * 20, prefix="W")
        rows += _unique_coin_pnls([-0.5] * 10, prefix="L")
        _bulk_seed_closed(rows, signal_time=OLD_SIGNAL_TIME)  # N=31 -> back-date

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["checks"]["expectancy"]["passed"] is True
        assert result["checks"]["profit_factor"]["passed"] is True
        assert result["checks"]["ci_lower_bound"]["passed"] is True
        assert result["checks"]["coin_concentration"]["passed"] is False
        assert result["checks"]["coin_concentration"]["top_coin"] == "WHALE"
        assert result["checks"]["observation"]["passed"] is True
        assert result["all_passed"] is False

        message = pc.format_promotion_check_message(result)
        assert "konsentrasi profit" in message
        assert "WHALE" in message

    def test_observation_fails_others_pass(self, isolated_tracker_db):
        pnls = [1.0] * 11 + [-0.3] * 4  # N=15 < 60
        _bulk_seed_closed(_unique_coin_pnls(pnls), signal_time=RECENT_SIGNAL_TIME)

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["checks"]["expectancy"]["passed"] is True
        assert result["checks"]["profit_factor"]["passed"] is True
        assert result["checks"]["ci_lower_bound"]["passed"] is True
        assert result["checks"]["coin_concentration"]["passed"] is True
        assert result["checks"]["observation"]["passed"] is False
        assert result["all_passed"] is False

        message = pc.format_promotion_check_message(result)
        assert "observasi" in message.lower()


class TestTinySampleDoesNotCrash:
    def test_n_one_reports_not_computable_instead_of_fake_number(self, isolated_tracker_db):
        """Mirrors the actual current production shadow_e3 state (N=1, 1 LOSS,
        per STATUS_WINRATE_REPORT.md / SHADOW_SIGNAL_SPAM_REPORT.md)."""
        _bulk_seed_closed([("ARB", -1.7)])

        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["n_closed"] == 1
        assert result["checks"]["ci_lower_bound"]["computable"] is False
        assert result["checks"]["ci_lower_bound"]["value"] is None
        assert result["checks"]["ci_lower_bound"]["passed"] is False
        assert result["all_passed"] is False

        message = pc.format_promotion_check_message(result)
        assert "belum bisa dihitung" in message
        assert "None" not in message  # no raw None leaking into user-facing text

    def test_zero_closed_signals_does_not_crash(self, isolated_tracker_db):
        result = pc.evaluate_promotion_criteria(source="shadow_e3")

        assert result["n_closed"] == 0
        assert result["all_passed"] is False
        message = pc.format_promotion_check_message(result)
        assert "belum bisa dihitung" in message
        assert "belum ada trade profit" in message


class TestReadOnly:
    def test_evaluate_does_not_modify_signal_tracking(self, isolated_tracker_db):
        _bulk_seed_closed(_unique_coin_pnls([1.0] * 5 + [-0.5] * 3))

        conn = sqlite3.connect(signal_tracker.DB_PATH)
        before = conn.execute(
            "SELECT COUNT(*), IFNULL(SUM(id), 0) FROM signal_tracking"
        ).fetchone()
        conn.close()

        pc.evaluate_promotion_criteria(source="shadow_e3")
        pc.evaluate_promotion_criteria(source="shadow_e3")  # call twice for good measure

        conn = sqlite3.connect(signal_tracker.DB_PATH)
        after = conn.execute(
            "SELECT COUNT(*), IFNULL(SUM(id), 0) FROM signal_tracking"
        ).fetchone()
        conn.close()

        assert before == after

    def test_module_source_contains_no_write_statements(self):
        """Static confirmation to complement the dynamic row-count check:
        the module never issues INSERT/UPDATE/DELETE SQL at all."""
        import inspect

        source = inspect.getsource(pc)
        for keyword in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
            assert keyword not in source, f"unexpected write statement: {keyword}"

    def test_command_does_not_touch_shadow_env_flags(self, isolated_tracker_db, monkeypatch):
        monkeypatch.setenv("SHADOW_E3_ENABLED", "true")
        monkeypatch.setenv("SHADOW_E3_DISPATCH", "true")
        _bulk_seed_closed(_unique_coin_pnls([1.0] * 5))

        reply_mock = AsyncMock()
        update = MagicMock()
        update.effective_message = MagicMock(reply_text=reply_mock)
        monkeypatch.setattr(telegram_bot, "_authorized_chat", lambda _update: True)

        asyncio.run(telegram_bot.shadow_promotion_check_command(update, MagicMock()))

        assert os.environ.get("SHADOW_E3_ENABLED") == "true"
        assert os.environ.get("SHADOW_E3_DISPATCH") == "true"
        reply_mock.assert_called_once()


class TestCommandAuthorization:
    def test_unauthorized_chat_gets_rejected(self, monkeypatch):
        reply_mock = AsyncMock()
        update = MagicMock()
        update.effective_message = MagicMock(reply_text=reply_mock)
        monkeypatch.setattr(telegram_bot, "_authorized_chat", lambda _update: False)

        asyncio.run(telegram_bot.shadow_promotion_check_command(update, MagicMock()))

        reply_mock.assert_called_once_with("⛔ Unauthorized.")

    def test_authorized_chat_receives_report(self, isolated_tracker_db, monkeypatch):
        _bulk_seed_closed(_unique_coin_pnls([1.0] * 5))
        reply_mock = AsyncMock()
        update = MagicMock()
        update.effective_message = MagicMock(reply_text=reply_mock)
        monkeypatch.setattr(telegram_bot, "_authorized_chat", lambda _update: True)

        asyncio.run(telegram_bot.shadow_promotion_check_command(update, MagicMock()))

        reply_mock.assert_called_once()
        sent_text = reply_mock.call_args.args[0]
        assert "KRITERIA PROMOSI" in sent_text
