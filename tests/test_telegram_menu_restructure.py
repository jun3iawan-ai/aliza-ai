"""Regression tests for the user-facing Telegram menu restructuring."""

import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


def _rows():
    return [
        {"coin": "BTC", "side": "support", "price": 99.5, "level": 99.0, "distance_pct": 0.51},
        {"coin": "ETH", "side": "resistance", "price": 104.5, "level": 105.0, "distance_pct": 0.48},
    ]


def _labels(markup):
    return [getattr(button, "text", button) for row in markup.keyboard for button in row]


class TelegramMenuRestructureTests(IsolatedAsyncioTestCase):
    def _update(self, text, replies):
        async def reply_text(message, **kwargs):
            replies.append((message, kwargs.get("reply_markup")))

        message = SimpleNamespace(text=text, reply_text=reply_text)
        return SimpleNamespace(message=message, effective_message=message)

    async def test_levels_and_legacy_side_commands_share_the_single_display_path(self):
        replies = []
        context = SimpleNamespace(args=[], user_data={})
        update = self._update("ignored", replies)

        with patch.object(tb, "_authorized_chat", return_value=True), patch.object(
            tb, "_near_levels_for_display", return_value=_rows()
        ) as shared:
            await tb.levels_command(update, context)
            await tb.check_near_support_command(update, context)
            await tb.check_near_resistance_command(update, context)

        self.assertEqual(shared.call_count, 3)
        self.assertIn("BTC", replies[0][0])
        self.assertIn("ETH", replies[0][0])
        self.assertIn("BTC", replies[1][0])
        self.assertNotIn("ETH", replies[1][0])
        self.assertIn("ETH", replies[2][0])
        self.assertNotIn("BTC", replies[2][0])

    async def test_nested_back_returns_to_market_and_analysis_parents(self):
        replies = []
        context = SimpleNamespace(user_data={})

        await tb.menu_button_handler(self._update("📊 Market", replies), context)
        self.assertIn("🔔 Monitor Pasar", _labels(replies[-1][1]))
        await tb.menu_button_handler(self._update("🔔 Monitor Pasar", replies), context)
        self.assertIn("📍 Levels (S/R)", _labels(replies[-1][1]))
        await tb.menu_button_handler(self._update("⬅ Kembali", replies), context)
        self.assertIn("🔔 Monitor Pasar", _labels(replies[-1][1]))

        await tb.menu_button_handler(self._update("📈 Analisis", replies), context)
        self.assertIn("🎯 Konteks Market", _labels(replies[-1][1]))
        await tb.menu_button_handler(self._update("⬅ Kembali", replies), context)
        self.assertIn("📈 Analisis", _labels(replies[-1][1]))

    async def test_market_monitor_routes_existing_commands_from_new_location(self):
        replies = []
        context = SimpleNamespace(user_data={})
        handlers = {
            "levels_command": AsyncMock(),
            "check_big_move_command": AsyncMock(),
            "check_rsi_extreme_command": AsyncMock(),
            "check_breakout_command": AsyncMock(),
            "check_volume_spike_command": AsyncMock(),
            "snapshot_command": AsyncMock(),
        }
        routes = {
            "📍 Levels (S/R)": "levels_command",
            "💥 Cek Big Move (snapshot)": "check_big_move_command",
            "🔵 Cek RSI Ekstrem (snapshot)": "check_rsi_extreme_command",
            "🚨 Cek Breakout": "check_breakout_command",
            "📊 Cek Volume Spike": "check_volume_spike_command",
            "📌 Snapshot Market": "snapshot_command",
        }
        with patch.multiple(tb, **handlers):
            for label, handler_name in routes.items():
                await tb.menu_button_handler(self._update(label, replies), context)
                getattr(tb, handler_name).assert_awaited_once()

    async def test_post_init_registers_the_new_user_facing_slash_commands(self):
        set_commands = AsyncMock()
        application = SimpleNamespace(bot=SimpleNamespace(set_my_commands=set_commands))

        await tb._post_init_set_bot_commands(application)

        commands = set_commands.await_args.args[0]
        names = {command.command for command in commands}
        self.assertTrue(
            {
                "performance",
                "alert_stats",
                "snapshot",
                "health",
                "weekly_winrate",
                "shadow_promotion_check",
            }.issubset(names)
        )


class TelegramMenuRetirementTests(IsolatedAsyncioTestCase):
    def _update(self, text, replies):
        async def reply_text(message, **kwargs):
            replies.append((message, kwargs.get("reply_markup")))

        message = SimpleNamespace(text=text, reply_text=reply_text)
        return SimpleNamespace(message=message, effective_message=message)

    def test_retired_buttons_absent_from_every_keyboard(self):
        keyboards = [
            tb._main_menu_keyboard(), tb._market_submenu_keyboard(), tb._trading_submenu_keyboard(),
            tb._analysis_submenu_keyboard(), tb._macro_submenu_keyboard(),
            tb._market_monitor_submenu_keyboard(),
            tb._system_submenu_keyboard(),
        ]
        shown = {label for kb in keyboards for label in _labels(kb)}
        self.assertFalse(shown & tb._RETIRED_MENU_LABELS, shown & tb._RETIRED_MENU_LABELS)

    async def test_retired_button_from_cached_keyboard_returns_main_menu(self):
        handlers = {
            "spot_signal_command": AsyncMock(), "predict": AsyncMock(),
            "shadow_stats_command": AsyncMock(), "check_whale_command": AsyncMock(),
            "portfolio": AsyncMock(),
        }
        with patch.multiple(tb, **handlers):
            for label in ("📈 Saran Spot", "🔮 Prediksi Market", "🧪 Riset Shadow E3",
                          "🐋 Monitor Whale", "📈 Open Position",
                          "📂 Posisi Aktif", "📊 Performance"):
                replies = []
                await tb.menu_button_handler(self._update(label, replies), SimpleNamespace(user_data={}))
                self.assertEqual(len(replies), 1, label)
                self.assertIn("sudah tidak tersedia", replies[0][0])
                self.assertIn("💹 Trading", _labels(replies[0][1]))
            for name in handlers:
                getattr(tb, name).assert_not_awaited()


class UnifiedRadarTests(IsolatedAsyncioTestCase):
    def _update(self, text, replies):
        async def reply_text(message, **kwargs):
            replies.append((message, kwargs.get("reply_markup")))

        message = SimpleNamespace(text=text, reply_text=reply_text)
        return SimpleNamespace(message=message, effective_message=message)

    def test_format_shows_both_timeframes_rsi_label_and_star(self):
        from engine.market import market_radar_pro_analyzer as rp
        with patch.object(rp, "get_snapshot_timestamp_str", return_value="14:02:08"):
            out = rp.format_radar_report([
                {"coin": "BTC", "trend_4h": "BEARISH", "trend_1d": "SIDEWAYS", "rsi": 25.2, "label": "⚡ Breakdown Risk"},
                {"coin": "OM", "trend_4h": "BULLISH", "trend_1d": "BULLISH", "rsi": 61, "label": "📈 Strong Trend"},
                {"coin": "ADA", "trend_4h": "BEARISH", "trend_1d": "UNKNOWN", "rsi": None, "label": "• Neutral"},
            ])
        self.assertIn("BTC    4H ↓  1D →  RSI 25  ⚡ Breakdown Risk", out)
        self.assertIn("4H ↑  1D ↑  RSI 61  📈 Strong Trend ⭐", out)
        self.assertIn("ADA    4H ↓  1D ?  RSI  —  —", out)
        self.assertNotIn("Neutral", out)
        self.assertIn("14:02:08", out)

    async def test_market_menu_has_single_radar_and_old_labels_route_to_it(self):
        self.assertIn("📡 Radar", _labels(tb._market_submenu_keyboard()))
        self.assertNotIn("📡 Radar Pro", _labels(tb._market_submenu_keyboard()))
        with patch.object(tb, "radar", AsyncMock()) as radar_mock:
            for label in ("📡 Radar", "📡 Radar Market", "📡 Radar Pro"):
                await tb.menu_button_handler(self._update(label, []), SimpleNamespace(user_data={}))
        self.assertEqual(radar_mock.await_count, 3)
