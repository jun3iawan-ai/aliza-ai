"""Regression coverage for 15m/30m/1h Big Move alerts."""

import time
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock, patch

from engine.alerts import notification_governor as ngov
from engine.market import market_snapshot_engine as mse

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


class ShortWindowSnapshotEnrichmentTests(TestCase):
    def setUp(self):
        mse._short_interval_close_cache.clear()

    def tearDown(self):
        mse._short_interval_close_cache.clear()

    def test_enrichment_writes_correct_15m_and_30m_fields(self):
        collected = {"MOVE": {"price": 105.0}}
        with patch.object(
            mse,
            "_latest_closed_short_interval_close",
            side_effect=[100.0, 102.0],
        ):
            mse._enrich_collected_with_binance_short_intervals(collected)

        self.assertAlmostEqual(collected["MOVE"]["price_change_15m"], 5.0)
        self.assertAlmostEqual(
            collected["MOVE"]["price_change_30m"], (105.0 / 102.0 - 1.0) * 100.0
        )

    def test_15m_and_30m_caches_refresh_only_after_their_boundaries(self):
        cases = (
            ("15m", 15 * 60, 900.0, 1_200.0, 1_801.0, 899_999, 900_000),
            ("30m", 30 * 60, 1_800.0, 2_400.0, 3_601.0, 1_799_999, 1_800_000),
        )
        for interval, interval_sec, at_boundary, in_window, after_boundary, first_close, second_open in cases:
            with self.subTest(interval=interval):
                mse._short_interval_close_cache.clear()
                response = Mock(status_code=200)
                response.json.return_value = [
                    [0, "0", "0", "0", "100", "0", first_close],
                    [second_open, "0", "0", "0", "101", "0", second_open + interval_sec - 1],
                ]
                with patch.object(mse.requests, "get", return_value=response) as get:
                    self.assertEqual(
                        mse._latest_closed_short_interval_close(
                            "BTCUSDT", interval, interval_sec, now=at_boundary
                        ),
                        100.0,
                    )
                    self.assertEqual(
                        mse._latest_closed_short_interval_close(
                            "BTCUSDT", interval, interval_sec, now=in_window
                        ),
                        100.0,
                    )
                    self.assertEqual(
                        mse._latest_closed_short_interval_close(
                            "BTCUSDT", interval, interval_sec, now=after_boundary
                        ),
                        101.0,
                    )
                self.assertEqual(get.call_count, 2)


class BigMoveMultiTimeframeTests(IsolatedAsyncioTestCase):
    def setUp(self):
        ngov.reset_state_for_tests()
        self.context = SimpleNamespace(bot_data={})

    async def test_three_qualifying_windows_queue_three_independent_alerts(self):
        snapshot = {
            "data": {
                "MOVE": {
                    "price": 105.0,
                    "price_change_15m": 3.1,
                    "price_change_30m": 3.2,
                    "price_change_1h": 3.3,
                    "timestamp": time.time(),
                }
            }
        }
        with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
            tb, "DEFAULT_CHAT_ID", "12345"
        ):
            await tb.big_move_checker(self.context)

        self.assertEqual(ngov.pending_count(), 3)
        messages = ngov.flush_pending()
        self.assertEqual(len(messages), 3)
        self.assertTrue(any("dalam 15 menit!" in message for message in messages))
        self.assertTrue(any("dalam 30 menit!" in message for message in messages))
        self.assertTrue(any("dalam 1 jam!" in message for message in messages))
        for timeframe in ("15m", "30m", "1h"):
            self.assertIsNotNone(
                ngov.get_value("cooldown:big_move", f"MOVE:up:{timeframe}")
            )

    async def test_short_window_cooldown_does_not_block_other_windows(self):
        now = time.time()
        ngov.record_cooldown("big_move", "MOVE:up:15m", now=now)
        ngov.record_value("big_move", "MOVE:up:15m", 3.1)
        snapshot = {
            "data": {
                "MOVE": {
                    "price": 105.0,
                    "price_change_15m": 3.1,
                    "price_change_30m": 3.2,
                    "price_change_1h": 3.3,
                    "timestamp": now,
                }
            }
        }
        with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
            tb, "DEFAULT_CHAT_ID", "12345"
        ):
            await tb.big_move_checker(self.context)

        messages = ngov.flush_pending()
        self.assertEqual(len(messages), 2)
        self.assertFalse(any("dalam 15 menit!" in message for message in messages))
        self.assertTrue(any("dalam 30 menit!" in message for message in messages))
        self.assertTrue(any("dalam 1 jam!" in message for message in messages))

    async def test_15m_and_30m_do_not_fall_back_to_24h_but_1h_does(self):
        snapshot = {
            "data": {
                "FALLBACK": {
                    "price": 105.0,
                    "price_change_percentage_24h": 4.5,
                    "timestamp": time.time(),
                }
            }
        }
        with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
            tb, "DEFAULT_CHAT_ID", "12345"
        ):
            await tb.big_move_checker(self.context)

        messages = ngov.flush_pending()
        self.assertEqual(len(messages), 1)
        self.assertIn("dalam 1 jam!", messages[0])
        self.assertNotIn("15 menit", messages[0])
        self.assertNotIn("30 menit", messages[0])
