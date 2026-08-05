"""Regression tests for the real 1h Big Move snapshot enrichment."""

from unittest import TestCase
from unittest.mock import Mock, patch

from engine.market import market_snapshot_engine as mse

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


class OneHourSnapshotEnrichmentTests(TestCase):
    def setUp(self):
        mse._one_hour_close_cache.clear()

    def tearDown(self):
        mse._one_hour_close_cache.clear()

    def test_price_change_from_closed_1h_reference_handles_up_and_down(self):
        self.assertAlmostEqual(mse._price_change_from_1h_close(110.0, 100.0), 10.0)
        self.assertAlmostEqual(mse._price_change_from_1h_close(90.0, 100.0), -10.0)
        self.assertIsNone(mse._price_change_from_1h_close(0, 100.0))
        self.assertIsNone(mse._price_change_from_1h_close(100.0, None))

    def test_enrichment_writes_priority_1h_field(self):
        collected = {
            "UP": {"price": 105.0},
            "DOWN": {"price": 95.0},
            "MISSING": {"price": 100.0},
        }
        with patch.object(mse, "_latest_closed_1h_close", side_effect=[100.0, 100.0, None]):
            mse._enrich_collected_with_binance_1h(collected)
        self.assertAlmostEqual(collected["UP"]["price_change_1h"], 5.0)
        self.assertAlmostEqual(collected["DOWN"]["price_change_1h"], -5.0)
        self.assertEqual(collected["UP"]["price_change_pct_1h"], collected["UP"]["price_change_1h"])
        self.assertNotIn("price_change_1h", collected["MISSING"])

    def test_closed_candle_reference_is_cached_until_next_hour_boundary(self):
        response = Mock(status_code=200)
        response.json.return_value = [
            [0, "0", "0", "0", "100", "0", 3_599_999],
            [3_600_000, "0", "0", "0", "101", "0", 7_199_999],
        ]
        with patch.object(mse.requests, "get", return_value=response) as get:
            self.assertEqual(mse._latest_closed_1h_close("BTCUSDT", now=3_600.0), 100.0)
            self.assertEqual(mse._latest_closed_1h_close("BTCUSDT", now=3_900.0), 100.0)
        self.assertEqual(get.call_count, 1)


class BigMoveFieldPriorityTests(TestCase):
    def test_big_move_prefers_real_1h_field_over_24h_fallback(self):
        row = {"price_change_1h": -3.25, "price_change_percentage_24h": 18.0}
        self.assertEqual(tb._snapshot_big_move_pct(row), -3.25)

    def test_big_move_retains_24h_fallback_when_1h_unavailable(self):
        self.assertEqual(tb._snapshot_big_move_pct({"price_change_percentage_24h": 4.5}), 4.5)

