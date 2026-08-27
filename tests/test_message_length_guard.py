"""Tests for the Telegram message-length guard.

Regression coverage for the "Message is too long" dispatch failures seen in
morning_brief / evening_summary (see MESSAGE_TOO_LONG_FIX_REPORT.md).
Telegram's sendMessage endpoint hard-caps messages at 4096 characters; these
tests verify that oversized content is split into multiple sequential
messages by the centralized dispatcher instead of raising an exception.
"""

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
        }
    }


class FakeBot:
    """Minimal stand-in for telegram.Bot — records every send_message call."""

    def __init__(self):
        self.sent: list[str] = []

    async def send_message(self, chat_id, text):
        self.sent.append(text)


class SplitMessageHelperTests(TestCase):
    """Unit tests for _split_message_for_telegram()."""

    def test_short_message_returned_unchanged(self):
        short = "Pesan pendek yang jelas muat dalam satu bubble Telegram."
        self.assertEqual(tb._split_message_for_telegram(short), [short])

    def test_message_at_exact_limit_is_not_split(self):
        exact = "A" * tb.TELEGRAM_MESSAGE_LIMIT
        parts = tb._split_message_for_telegram(exact)
        self.assertEqual(parts, [exact])

    def test_long_message_splits_into_multiple_parts_within_limit(self):
        long_text = ("Kalimat analisis market untuk banyak coin. " * 60 + "\n\n") * 6
        self.assertGreater(len(long_text), tb.TELEGRAM_MESSAGE_LIMIT)

        parts = tb._split_message_for_telegram(long_text)

        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), tb.TELEGRAM_MESSAGE_LIMIT)

    def test_split_prefers_paragraph_or_word_boundary_over_mid_word_cut(self):
        # Build text where a long run of words straddles the split point —
        # the cut must land on a space/newline, never inside a word.
        word = "kata"
        text = ((word + " ") * 2000).strip()
        self.assertGreater(len(text), tb.TELEGRAM_MESSAGE_LIMIT)

        parts = tb._split_message_for_telegram(text)

        for part in parts[:-1]:
            # strip the "[lanjutan i/n]" suffix before checking the boundary
            body = part.rsplit("\n\n[lanjutan", 1)[0]
            self.assertFalse(body.endswith(word[:-1]))  # not cut mid-word
            self.assertTrue(body.endswith(word) or body == "")

    def test_multi_part_messages_get_lanjutan_suffix(self):
        long_text = ("Baris penting. " * 400)
        parts = tb._split_message_for_telegram(long_text)
        self.assertGreater(len(parts), 1)
        n = len(parts)
        for i, part in enumerate(parts, start=1):
            self.assertIn(f"[lanjutan {i}/{n}]", part)

    def test_empty_string_handled_without_error(self):
        self.assertEqual(tb._split_message_for_telegram(""), [""])


class DispatchAlertMessageSplittingTests(IsolatedAsyncioTestCase):
    """dispatch_alert_message() must split, not crash, on oversized text."""

    async def test_long_message_sent_in_multiple_parts_without_exception(self):
        fake_bot = FakeBot()
        long_message = ("Analisis mendalam untuk setiap coin di watchlist. " * 120 + "\n\n") * 4
        self.assertGreater(len(long_message), tb.TELEGRAM_MESSAGE_LIMIT)

        with patch.multiple(
            tb,
            get_bot=lambda: fake_bot,
            IS_PRIMARY_DISPATCHER=True,
            DEFAULT_CHAT_ID="123",
        ):
            result = await tb.dispatch_alert_message(long_message, chat_id="123", force=True)

        self.assertTrue(result)
        self.assertGreater(len(fake_bot.sent), 1)
        for sent_text in fake_bot.sent:
            self.assertLessEqual(len(sent_text), tb.TELEGRAM_MESSAGE_LIMIT)

    async def test_short_message_still_sent_as_single_call(self):
        fake_bot = FakeBot()
        short_message = "Ringkasan singkat."

        with patch.multiple(
            tb,
            get_bot=lambda: fake_bot,
            IS_PRIMARY_DISPATCHER=True,
            DEFAULT_CHAT_ID="123",
        ):
            result = await tb.dispatch_alert_message(short_message, chat_id="123", force=True)

        self.assertTrue(result)
        self.assertEqual(fake_bot.sent, [short_message])


class MorningBriefEveningSummaryOversizedContentTests(IsolatedAsyncioTestCase):
    """End-to-end: oversized morning_brief/evening_summary content must not
    raise "Message is too long" and must reach the (mocked) Telegram bot in
    split form."""

    async def _run_job_with_oversized_sections(self, job):
        fake_bot = FakeBot()

        # Oversized funding section (mirrors real production: one line per
        # watchlist coin, unbounded) and oversized LLM analysis text — both
        # independently exceed the 4096-char sendMessage limit, matching the
        # two failure modes seen in production logs ("dispatch header" and
        # "dispatch analysis").
        oversized_funding_section = "🔄 Funding Rate & OI\n" + (
            "BTC FR: +0.0810% | OI: $152.34M (+3.2% 24h) | L/S: 1.08  —\n" * 80
        )
        oversized_analysis = "Analisis market mendalam per coin. " * 300

        patches = {
            "DEFAULT_CHAT_ID": "123",
            "IS_PRIMARY_DISPATCHER": True,
            "get_bot": lambda: fake_bot,
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
            "format_funding_section_for_brief": lambda: oversized_funding_section,
            "_format_macro_section_for_brief_with_data_per": lambda: "Macro",
            "_format_cross_asset_section": lambda: "Cross asset",
            "_format_market_intelligence_section": lambda: "Intel",
            "_generate_brief_analysis": AsyncMock(return_value=oversized_analysis),
            "_parse_and_record_signals": lambda *a, **k: None,
        }
        with patch.multiple(tb, **patches):
            # sanity: confirm our fixture is actually oversized before
            # asserting the fix handles it
            self.assertGreater(len(oversized_funding_section), tb.TELEGRAM_MESSAGE_LIMIT)
            self.assertGreater(len(oversized_analysis), tb.TELEGRAM_MESSAGE_LIMIT)
            await job(SimpleNamespace(bot_data={"chat_id": "123"}))

        return fake_bot

    async def test_morning_brief_oversized_content_sent_without_exception(self):
        fake_bot = await self._run_job_with_oversized_sections(tb.morning_brief_job)

        # header + analysis together must have produced more than 2 raw
        # dispatch calls once split (proves splitting actually engaged)
        self.assertGreater(len(fake_bot.sent), 2)
        for sent_text in fake_bot.sent:
            self.assertLessEqual(len(sent_text), tb.TELEGRAM_MESSAGE_LIMIT)

    async def test_evening_summary_oversized_content_sent_without_exception(self):
        fake_bot = await self._run_job_with_oversized_sections(tb.evening_summary_job)

        self.assertGreater(len(fake_bot.sent), 2)
        for sent_text in fake_bot.sent:
            self.assertLessEqual(len(sent_text), tb.TELEGRAM_MESSAGE_LIMIT)
