"""
Tests for the breaking-news mitigation (see BERITA_MITIGASI_REPORT.md):
- breaking_news_job dedup migrated from an in-memory dict to
  notification_governor (ngov), namespace "news_title", so it survives a
  process restart the same way the checkers fixed in
  NOTIFIKASI_MITIGASI_REPORT.md do.
- FMP_CALENDAR_ENABLED flag in engine/market/economic_calendar.py: FMP is
  skipped by default (its configured key returns HTTP 403), falling back to
  Investing.com / rule-based, and can be re-enabled via env.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.alerts import notification_governor as ngov
from engine.market import economic_calendar as ecal

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot


def _news_item(title: str, snippet: str = "Dampak signifikan ke market crypto hari ini.", hours_ago: float = 0.5) -> dict:
    pub = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return {
        "title": title,
        "snippet": snippet,
        "source": "TestSource",
        "link": "https://example.com/a",
        "time": pub.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class BreakingNewsDedupTests(IsolatedAsyncioTestCase):
    """Item 1 / test 1 & 2: news-title dedup, persisted via ngov."""

    def setUp(self):
        ngov.reset_state_for_tests()

    def _patches(self, item):
        return (
            patch.object(telegram_bot, "_fetch_crypto_news", return_value=[item]),
            patch.object(telegram_bot, "_fetch_macro_news", return_value=[]),
            patch.object(telegram_bot, "_translate_news_to_id", side_effect=lambda t, s: (t, s)),
            patch.object(telegram_bot, "safe_dispatch", new=AsyncMock(return_value=True)),
            patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"),
        )

    async def test_same_title_within_24h_is_not_resent(self):
        item = _news_item("Bitcoin ETF approved by SEC today")
        p1, p2, p3, p4, p5 = self._patches(item)
        with p1, p2, p3, p4 as mock_dispatch, p5:
            ctx = SimpleNamespace(bot_data={})
            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 1)

            # same title shows up again in the very next hourly scan
            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 1)

    async def test_same_title_is_sent_again_after_24h(self):
        item = _news_item("Bitcoin ETF approved by SEC today")
        p1, p2, p3, p4, p5 = self._patches(item)
        with p1, p2, p3, p4 as mock_dispatch, p5:
            ctx = SimpleNamespace(bot_data={})
            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 1)

            # fast-forward the recorded dedup timestamp past the 24h window
            key = item["title"][:400]
            old_ts = time.time() - (telegram_bot._NEWS_TITLE_DEDUP_SEC + 10)
            ngov.set_value("cooldown:news_title", key, old_ts)

            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 2)

    async def test_dedup_survives_simulated_process_restart(self):
        """The bug this fixes: SENT_NEWS_TITLES was a module dict, wiped on
        every process restart. Simulate a restart by dropping ngov's
        in-memory cache and re-reading from disk."""
        item = _news_item("Exchange hack drains millions in crypto overnight")
        p1, p2, p3, p4, p5 = self._patches(item)
        with p1, p2, p3, p4 as mock_dispatch, p5:
            ctx = SimpleNamespace(bot_data={})
            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 1)

            # simulate a fresh process
            ngov._state_cache = None

            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 1)  # still 1, not resent

    async def test_different_titles_are_independent(self):
        item_a = _news_item("Bitcoin ETF approved by SEC today")
        item_b = _news_item("Ethereum ETF approved by SEC today")
        with patch.object(telegram_bot, "_fetch_crypto_news", return_value=[item_a, item_b]), \
             patch.object(telegram_bot, "_fetch_macro_news", return_value=[]), \
             patch.object(telegram_bot, "_translate_news_to_id", side_effect=lambda t, s: (t, s)), \
             patch.object(telegram_bot, "safe_dispatch", new=AsyncMock(return_value=True)) as mock_dispatch, \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            ctx = SimpleNamespace(bot_data={})
            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 2)

    async def test_non_breaking_item_is_not_dispatched_or_deduped(self):
        item = _news_item("What is bitcoin? A beginner guide to crypto")
        with patch.object(telegram_bot, "_fetch_crypto_news", return_value=[item]), \
             patch.object(telegram_bot, "_fetch_macro_news", return_value=[]), \
             patch.object(telegram_bot, "safe_dispatch", new=AsyncMock(return_value=True)) as mock_dispatch, \
             patch.object(telegram_bot, "DEFAULT_CHAT_ID", "12345"):
            ctx = SimpleNamespace(bot_data={})
            await telegram_bot.breaking_news_job(ctx)
            self.assertEqual(mock_dispatch.call_count, 0)
            self.assertIsNone(ngov.get_value("cooldown:news_title", item["title"][:400]))


class BreakingNewsPruneTests(TestCase):
    """news_title keys are unbounded (one per article title, unlike the small
    fixed per-coin key space other checkers use) — must be prunable."""

    def setUp(self):
        ngov.reset_state_for_tests()

    def test_prune_removes_entries_older_than_ttl_keeps_recent(self):
        now = time.time()
        ngov.record_cooldown("news_title", "old headline", now=now - telegram_bot._NEWS_TITLE_DEDUP_SEC - 10)
        ngov.record_cooldown("news_title", "recent headline", now=now)
        removed = ngov.prune_cooldown_namespace("news_title", telegram_bot._NEWS_TITLE_DEDUP_SEC, now=now)
        self.assertEqual(removed, 1)
        self.assertIsNone(ngov.get_value("cooldown:news_title", "old headline"))
        self.assertIsNotNone(ngov.get_value("cooldown:news_title", "recent headline"))


class FmpCalendarFlagTests(TestCase):
    """Item 3 / test 3 & 4: FMP_CALENDAR_ENABLED gates the FMP call."""

    def setUp(self):
        ecal._fmp_calendar_cache = {"ts": 0.0, "days": 0, "events": None}
        ecal._events_cache = {"ts": 0.0, "days": 0, "events": []}

    def test_fmp_disabled_by_default_skips_fmp_and_falls_back_to_investing(self):
        fake_investing_events = [
            {
                "name": "CPI",
                "datetime_utc": "2026-01-02T12:30:00+00:00",
                "datetime_wib": "2026-01-02T19:30:00+07:00",
                "impact": "HIGH",
                "country": "US",
                "previous": "-",
                "forecast": "-",
            }
        ]
        with patch.dict(os.environ, {"FMP_API_KEY": "testkey123"}, clear=False), \
             patch.dict(os.environ, {"FMP_CALENDAR_ENABLED": "false"}, clear=False), \
             patch("engine.market.economic_calendar._fetch_from_fmp") as mock_fmp, \
             patch(
                 "engine.market.investing_calendar.fetch_investing_calendar",
                 return_value=fake_investing_events,
             ) as mock_investing, \
             patch.object(ecal, "_fetch_serper_events", return_value=[]):
            events = ecal.get_upcoming_events(days_ahead=2)
        mock_fmp.assert_not_called()
        mock_investing.assert_called_once()
        self.assertTrue(any(e["name"] == "CPI" for e in events))

    def test_fmp_enabled_is_still_called_when_flag_true(self):
        fake_fmp_events = [
            {
                "name": "NFP",
                "datetime_utc": "2026-01-02T12:30:00+00:00",
                "datetime_wib": "2026-01-02T19:30:00+07:00",
                "impact": "HIGH",
                "country": "US",
                "previous": "-",
                "forecast": "-",
            }
        ]
        with patch.dict(os.environ, {"FMP_API_KEY": "testkey123"}, clear=False), \
             patch.dict(os.environ, {"FMP_CALENDAR_ENABLED": "true"}, clear=False), \
             patch(
                 "engine.market.economic_calendar._fetch_from_fmp",
                 return_value=fake_fmp_events,
             ) as mock_fmp, \
             patch.object(ecal, "_fetch_serper_events", return_value=[]):
            events = ecal.get_upcoming_events(days_ahead=2)
        mock_fmp.assert_called_once()
        self.assertTrue(any(e["name"] == "NFP" for e in events))

    def test_fmp_not_called_when_key_missing_even_if_flag_true(self):
        with patch.dict(os.environ, {"FMP_API_KEY": ""}, clear=False), \
             patch.dict(os.environ, {"FMP_CALENDAR_ENABLED": "true"}, clear=False), \
             patch("engine.market.economic_calendar._fetch_from_fmp") as mock_fmp, \
             patch(
                 "engine.market.investing_calendar.fetch_investing_calendar",
                 return_value=[],
             ), \
             patch.object(ecal, "_fetch_serper_events", return_value=[]):
            ecal.get_upcoming_events(days_ahead=2)
        mock_fmp.assert_not_called()
