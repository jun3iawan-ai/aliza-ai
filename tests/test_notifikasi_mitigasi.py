"""
Tests for the Telegram notification-noise mitigation (see
NOTIFIKASI_MITIGASI_REPORT.md): persisted cooldowns, per-coin data
freshness, burst digesting, per-hour rate limiting, and the unified
volume-spike threshold.
"""

import os
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.alerts import notification_governor as ngov
from engine.market import volume_spike_detector as vsd

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot


def setUpModule():
    ngov.reset_state_for_tests()


class SnapshotAlertCooldownTests(TestCase):
    """Item 1 / test 1: near_support/near_resistance/rsi cooldown (4h), persisted."""

    def setUp(self):
        ngov.reset_state_for_tests()

    def test_second_alert_within_4h_suppressed_then_allowed_after(self):
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        self.assertTrue(telegram_bot._snapshot_alert_allowed("BTC", "near_resistance", t0))
        # same coin+condition, 1h later — still within the 4h cooldown
        self.assertFalse(
            telegram_bot._snapshot_alert_allowed("BTC", "near_resistance", t0 + timedelta(hours=1))
        )
        # just under 4h
        self.assertFalse(
            telegram_bot._snapshot_alert_allowed(
                "BTC", "near_resistance", t0 + timedelta(hours=3, minutes=59)
            )
        )
        # 4h+ later — allowed again
        self.assertTrue(
            telegram_bot._snapshot_alert_allowed(
                "BTC", "near_resistance", t0 + timedelta(hours=4, seconds=1)
            )
        )

    def test_cooldown_survives_simulated_process_restart(self):
        """The bug this fixes: cooldown state used to live in a module dict that
        was wiped on every process restart. Simulate a restart by dropping the
        in-memory cache and re-reading from disk."""
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        self.assertTrue(telegram_bot._snapshot_alert_allowed("ETH", "near_support", t0))

        # simulate a fresh process: drop the in-memory cache
        ngov._state_cache = None

        self.assertFalse(
            telegram_bot._snapshot_alert_allowed("ETH", "near_support", t0 + timedelta(minutes=5))
        )

    def test_recorded_cooldown_timestamp_matches_real_utc_epoch(self):
        """Regression: datetime.utcnow().timestamp() (naive) is interpreted by
        Python as LOCAL time, not UTC — on a server whose local tz isn't UTC
        (this VPS runs Asia/Jakarta, UTC+7) that silently stores cooldown
        epochs offset by the local UTC delta. Caught live during restart
        verification by inspecting data/alert_cooldown_state.json and finding
        recorded timestamps ~7h off from the real wall clock. Elapsed-time
        cooldown math still happened to cancel out (same bias on write and
        read), but this guards the stored absolute epoch directly."""
        real_now = time.time()
        telegram_bot._snapshot_alert_allowed("TZCOIN", "tz_regression", datetime.utcnow())
        recorded = ngov.get_value("cooldown:snapshot_alert", "TZCOIN:tz_regression")
        self.assertIsNotNone(recorded)
        self.assertLess(abs(recorded - real_now), 5)

    def test_cooldown_is_scoped_per_coin_and_condition(self):
        t0 = datetime(2026, 1, 1, 0, 0, 0)
        self.assertTrue(telegram_bot._snapshot_alert_allowed("SOL", "near_resistance", t0))
        # different coin — independent cooldown
        self.assertTrue(telegram_bot._snapshot_alert_allowed("XRP", "near_resistance", t0))
        # same coin, different condition — independent cooldown
        self.assertTrue(telegram_bot._snapshot_alert_allowed("SOL", "near_support", t0))


class BigMoveCooldownTests(IsolatedAsyncioTestCase):
    """Item 2 / test 2: big_move_checker cooldown per (coin, direction),
    BIG_MOVE_COOLDOWN_SEC, persisted."""

    def setUp(self):
        ngov.reset_state_for_tests()

    async def test_repeat_big_move_within_cooldown_is_suppressed(self):
        fresh_ts = time.time()
        snapshot = {
            "data": {
                "OM": {
                    "price": 0.0669,
                    "price_change_percentage_24h": -5.11,
                    "timestamp": fresh_ts,
                }
            }
        }
        ctx = SimpleNamespace(bot_data={})
        with patch.object(telegram_bot, "get_market_snapshot", return_value=snapshot), \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            await telegram_bot.big_move_checker(ctx)
            self.assertEqual(ngov.pending_count(), 1)
            ngov.flush_pending()

            # second run shortly after (e.g. next 5-min tick, or right after a
            # process restart) with fresh-looking data but same direction/coin
            snapshot["data"]["OM"]["timestamp"] = time.time()
            await telegram_bot.big_move_checker(ctx)
            self.assertEqual(ngov.pending_count(), 0)

    async def test_recorded_cooldown_timestamp_matches_real_utc_epoch(self):
        """Same regression as SnapshotAlertCooldownTests, for big_move_checker's
        own now_utc.replace(tzinfo=timezone.utc).timestamp() conversion."""
        real_now = time.time()
        snapshot = {"data": {"OM": {"price": 0.0669, "price_change_percentage_24h": -5.11, "timestamp": real_now}}}
        ctx = SimpleNamespace(bot_data={})
        with patch.object(telegram_bot, "get_market_snapshot", return_value=snapshot), \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            await telegram_bot.big_move_checker(ctx)
        recorded = ngov.get_value("cooldown:big_move", "OM:down")
        self.assertIsNotNone(recorded)
        self.assertLess(abs(recorded - real_now), 5)

    async def test_opposite_direction_is_not_blocked_by_cooldown(self):
        fresh_ts = time.time()
        snapshot = {"data": {"OM": {"price": 0.0669, "price_change_percentage_24h": -5.11, "timestamp": fresh_ts}}}
        ctx = SimpleNamespace(bot_data={})
        with patch.object(telegram_bot, "get_market_snapshot", return_value=snapshot), \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            await telegram_bot.big_move_checker(ctx)
            ngov.flush_pending()

            # opposite direction for the same coin should still be allowed
            snapshot["data"]["OM"] = {"price": 0.075, "price_change_percentage_24h": 6.0, "timestamp": time.time()}
            await telegram_bot.big_move_checker(ctx)
            self.assertEqual(ngov.pending_count(), 1)

    async def test_cooldown_duration_is_configurable_via_env(self):
        self.assertEqual(ngov.BIG_MOVE_COOLDOWN_SEC, int(os.getenv("BIG_MOVE_COOLDOWN_SEC", "7200")))


class FreshnessCheckTests(IsolatedAsyncioTestCase):
    """Item 3 / test 3: stale per-coin data produces no alert, for near_resistance
    and big_move (representative of the checker family sharing the snapshot)."""

    def setUp(self):
        ngov.reset_state_for_tests()

    async def test_stale_data_skips_near_resistance_and_big_move(self):
        stale_ts = time.time() - (ngov.SNAPSHOT_MAX_AGE_SEC + 120)
        snapshot = {
            "data": {
                "BTC": {"price": 101000.0, "resistance": 101300.0, "support": 90000.0, "timestamp": stale_ts},
                "OM": {"price": 0.0669, "price_change_percentage_24h": -5.11, "timestamp": stale_ts},
            }
        }
        ctx = SimpleNamespace(bot_data={})
        with patch.object(telegram_bot, "get_market_snapshot", return_value=snapshot), \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            await telegram_bot.near_resistance_checker(ctx)
            await telegram_bot.big_move_checker(ctx)
        self.assertEqual(ngov.pending_count(), 0)

    async def test_fresh_data_is_not_blocked(self):
        fresh_ts = time.time()
        snapshot = {
            "data": {
                "BTC": {"price": 101000.0, "resistance": 101300.0, "support": 90000.0, "timestamp": fresh_ts},
                "OM": {"price": 0.0669, "price_change_percentage_24h": -5.11, "timestamp": fresh_ts},
            }
        }
        ctx = SimpleNamespace(bot_data={})
        with patch.object(telegram_bot, "get_market_snapshot", return_value=snapshot), \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            await telegram_bot.near_resistance_checker(ctx)
            await telegram_bot.big_move_checker(ctx)
        self.assertEqual(ngov.pending_count(), 2)

    def test_freshness_helper_epoch_float_handles_missing_and_unparseable(self):
        # missing timestamp -> can't prove staleness -> treated as fresh
        self.assertTrue(ngov.is_coin_snapshot_fresh({"price": 1}))
        # the exact float-epoch shape market_analyzer.py actually stores
        self.assertTrue(ngov.is_coin_snapshot_fresh({"timestamp": time.time()}))
        self.assertFalse(
            ngov.is_coin_snapshot_fresh({"timestamp": time.time() - 99999}, max_age_sec=300)
        )


class DigestBatchingTests(TestCase):
    """Item 4 / tests 4 & 5: burst -> one combined message; normal volume -> unchanged."""

    def setUp(self):
        ngov.reset_state_for_tests()

    def test_six_alerts_in_one_cycle_become_one_digest_message(self):
        for i in range(6):
            ngov.queue_alert("near_resistance", "NEAR RESISTANCE", f"COIN{i} line", f"full message {i}")
        messages = ngov.flush_pending()
        self.assertEqual(len(messages), 1)
        self.assertIn("6 sinyal", messages[0])
        for i in range(6):
            self.assertIn(f"COIN{i}", messages[0])

    def test_four_alerts_below_threshold_stay_individual(self):
        for i in range(4):
            ngov.queue_alert("near_resistance", "NEAR RESISTANCE", f"COIN{i} line", f"full message {i}")
        messages = ngov.flush_pending()
        self.assertEqual(len(messages), 4)
        self.assertEqual(set(messages), {f"full message {i}" for i in range(4)})

    def test_flush_drains_the_buffer(self):
        ngov.queue_alert("big_move", "BIG MOVE", "line", "msg")
        self.assertEqual(ngov.pending_count(), 1)
        ngov.flush_pending()
        self.assertEqual(ngov.pending_count(), 0)
        self.assertEqual(ngov.flush_pending(), [])


class RateLimitTests(TestCase):
    """Item 5 / test 6: MAX_ALERTS_PER_HOUR caps dispatch within a clock hour."""

    def setUp(self):
        ngov.reset_state_for_tests()

    def test_alerts_beyond_max_per_hour_are_suppressed(self):
        now = time.time()
        results = [ngov.allow_rate_limited_dispatch(now) for _ in range(20)]
        allowed = sum(1 for r in results if r)
        suppressed = sum(1 for r in results if not r)
        self.assertEqual(allowed, ngov.MAX_ALERTS_PER_HOUR)
        self.assertEqual(suppressed, 20 - ngov.MAX_ALERTS_PER_HOUR)
        self.assertEqual(
            ngov.get_value("rate_limit_suppressed", ngov._hour_bucket(now)),
            20 - ngov.MAX_ALERTS_PER_HOUR,
        )

    def test_rate_limit_is_configurable_via_env(self):
        self.assertEqual(ngov.MAX_ALERTS_PER_HOUR, int(os.getenv("MAX_ALERTS_PER_HOUR", "15")))

    def test_previous_hour_summary_reported_once(self):
        hour0 = 1_753_000_000.0  # arbitrary fixed epoch, hour-aligned enough for the test
        for _ in range(ngov.MAX_ALERTS_PER_HOUR + 3):
            ngov.allow_rate_limited_dispatch(hour0)
        next_hour = hour0 + 3600
        summary = ngov.pop_previous_hour_summary(next_hour)
        self.assertIsNotNone(summary)
        self.assertIn("+3", summary)
        # idempotent: asking again for the same boundary returns nothing new
        self.assertIsNone(ngov.pop_previous_hour_summary(next_hour + 1))


class VolumeSpikeThresholdTests(TestCase):
    """Item 6 / test 7: single threshold shared by detector and dispatch."""

    def setUp(self):
        ngov.reset_state_for_tests()
        vsd._avg_vol_cache.clear()

    def test_detector_threshold_is_4x(self):
        self.assertEqual(vsd.SPIKE_MULTIPLIER, 4.0)

    def test_dispatch_no_longer_has_a_second_stricter_threshold(self):
        self.assertFalse(hasattr(telegram_bot, "_VOLUME_SPIKE_MIN_MULTIPLIER"))
        self.assertFalse(hasattr(telegram_bot, "_volume_spike_last_sent"))

    def test_spike_below_threshold_does_not_trigger(self):
        vsd._avg_vol_cache["BTC"] = {"avg": 100.0, "ts": time.time()}
        self.assertIsNone(vsd.check_volume_spike("BTC", 399.0))  # 3.99x

    def test_spike_at_or_above_threshold_triggers(self):
        vsd._avg_vol_cache["ETH"] = {"avg": 100.0, "ts": time.time()}
        hit = vsd.check_volume_spike("ETH", 401.0)  # 4.01x
        self.assertIsNotNone(hit)
        self.assertGreaterEqual(hit["multiplier"], vsd.SPIKE_MULTIPLIER)

    def test_volume_spike_cooldown_persists_across_simulated_restart(self):
        vsd._avg_vol_cache["SOL"] = {"avg": 100.0, "ts": time.time()}
        self.assertIsNotNone(vsd.check_volume_spike("SOL", 500.0))
        ngov._state_cache = None  # simulate restart: drop in-memory cache
        self.assertIsNone(vsd.check_volume_spike("SOL", 500.0))
