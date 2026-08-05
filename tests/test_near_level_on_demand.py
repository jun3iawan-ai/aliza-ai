"""Tests for the on-demand near support/resistance presentation path."""

import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


def _snapshot():
    return {
        "data": {
            "BTC": {"price": 99.5, "support": 99.0, "resistance": 105.0},
            "ETH": {"price": 104.5, "support": 95.0, "resistance": 105.0},
            "OUT": {"price": 102.0, "support": 99.0, "resistance": 107.0},
        }
    }


class NearLevelHelperTests(TestCase):
    def test_matches_side_and_custom_tolerance_without_duplicate_logic(self):
        rows = tb.get_coins_near_levels(1.0, snapshot=_snapshot())
        self.assertEqual([(row["coin"], row["side"]) for row in rows], [("BTC", "support"), ("ETH", "resistance")])
        self.assertEqual(tb.get_coins_near_levels(1.0, snapshot={"data": {"BTC": {"price": 100.8, "support": 99.0, "resistance": 105.0}}}), [])
        wider = tb.get_coins_near_levels(2.0, snapshot={"data": {"BTC": {"price": 100.8, "support": 99.0, "resistance": 105.0}}})
        self.assertEqual([(row["coin"], row["side"]) for row in wider], [("BTC", "support")])

    def test_section_is_explicit_for_empty_and_contains_both_groups_when_matched(self):
        empty = tb._format_near_levels_section([])
        self.assertIn("Tidak ada coin dekat level saat ini.", empty)
        text = tb._format_near_levels_section(tb.get_coins_near_levels(1.0, snapshot=_snapshot()))
        self.assertIn("🔻 Dekat Support", text)
        self.assertIn("🔺 Dekat Resistance", text)
        self.assertIn("BTC", text)
        self.assertIn("ETH", text)


class NearLevelCommandAndPushTests(IsolatedAsyncioTestCase):
    async def test_disabled_push_does_not_queue_individual_alert(self):
        original_pending = tb.ngov._pending
        tb.ngov._pending = []
        try:
            with patch.object(tb, "get_market_snapshot", return_value=_snapshot()), patch.object(tb, "NEAR_LEVEL_PUSH_ENABLED", False):
                await tb.near_support_checker(SimpleNamespace(bot_data={"chat_id": "123"}))
            self.assertEqual(tb.ngov.pending_count(), 0)
        finally:
            tb.ngov._pending = original_pending

    async def test_levels_command_uses_default_and_custom_tolerance(self):
        replies = []

        async def reply_text(text):
            replies.append(text)

        update = SimpleNamespace(
            effective_message=SimpleNamespace(reply_text=reply_text),
            effective_chat=SimpleNamespace(id=123),
        )
        with patch.object(tb, "_authorized_chat", return_value=True), patch.object(tb, "get_coins_near_levels", return_value=[]):
            await tb.levels_command(update, SimpleNamespace(args=[]))
            self.assertIn("±1.00%", replies[-1])
            await tb.levels_command(update, SimpleNamespace(args=["1.5"]))
            self.assertIn("±1.50%", replies[-1])


class NearLevelScheduledSummaryTests(IsolatedAsyncioTestCase):
    async def _assert_summary_contains_section(self, job):
        sent = []

        async def fake_dispatch(message, **_kwargs):
            sent.append(message)
            return True

        patches = {
            "DEFAULT_CHAT_ID": "123",
            "get_market_snapshot": lambda: _snapshot(),
            "get_snapshot_timestamp_str": lambda: "12:00:00",
            "get_global_market_data": lambda: {"fear_greed": 50, "btc_dominance": 50},
            "get_all_funding_data": lambda: {},
            "calculate_market_score": lambda: {},
            "get_events_tomorrow": lambda: [],
            "scan_for_signals": lambda: None,
            "_top_coins_analysis_dict": lambda _data: {},
            "_macro_for_analysis_prompt": lambda: {},
            "_format_events_for_display": lambda _events: "Tidak ada",
            "format_context_for_brief": lambda: "Context",
            "format_funding_section_for_brief": lambda: "Funding",
            "_format_macro_section_for_brief_with_data_per": lambda: "Macro",
            "_format_cross_asset_section": lambda: "Cross asset",
            "_format_market_intelligence_section": lambda: "Intel",
            "_generate_brief_analysis": AsyncMock(return_value="Analisis"),
            "safe_dispatch": fake_dispatch,
        }
        with patch.multiple(tb, **patches):
            await job(SimpleNamespace(bot_data={"chat_id": "123"}))
        self.assertIn("📍 LEVEL TERDEKAT", sent[0])
        self.assertIn("BTC", sent[0])
        self.assertIn("ETH", sent[0])

    async def test_morning_summary_contains_near_level_section(self):
        await self._assert_summary_contains_section(tb.morning_brief_job)

    async def test_evening_summary_contains_near_level_section(self):
        await self._assert_summary_contains_section(tb.evening_summary_job)

