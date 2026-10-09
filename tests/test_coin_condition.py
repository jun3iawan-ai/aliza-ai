"""Kartu kondisi coin & Dekat Support (decision-support, 9 Okt 2026)."""
import os
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.market import coin_condition as cc

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb

BTC = {"price": 82525.42, "rsi": 38.6, "support": 81037.99, "resistance": 86242.01,
       "trend_4h": "BEARISH", "trend_1d": "SIDEWAYS", "trend": "BEARISH"}


def test_card_is_descriptive_without_signal_confidence_or_entry():
    closes_4h = [100 + (i % 3) for i in range(30)]
    closes_1d = [90000 - i * 100 for i in range(40)] + [78500]
    out = cc.build_coin_condition("BTC", BTC, funding_rate=0.000069, closes_4h=closes_4h,
                                  closes_1d=closes_1d, label="⚡ Breakdown Risk", snapshot_ts="14:27:58")
    assert "4H ↓ · 1D →  (belum searah)" in out
    assert "1.8% di atas support $81,038" in out
    assert "4.5% di bawah resistance $86,242" in out
    assert "momentum lemah, belum oversold" in out
    assert "Kondisi : ⚡ Breakdown Risk" in out
    assert "🗺️ Skenario level" in out
    assert "▲ Tembus resistance $86,242 → level 30-hari berikutnya ~$88,900" in out
    assert "▼ Jebol support $81,038 → level 30-hari berikutnya ~$78,500" in out
    assert "Tren 1D belum ikut turun" in out
    for banned in ("EXIT", "BUY", "Confidence", "Entry", "SL ", "Target", "RR"):
        assert banned not in out, banned


def test_card_flags_broken_support():
    md = dict(BTC, price=80000.0)
    out = cc.build_coin_condition("BTC", md)
    assert "DI BAWAH support" in out and "support jebol" in out


def test_near_support_rows_filter_and_sort():
    data = {
        "BTC": BTC,                                                         # 1.8%
        "SOL": {"price": 110.0, "support": 109.0, "trend_4h": "BEARISH"},  # 0.9%
        "ETH": {"price": 2500.0, "support": 2300.0},                        # 8% → keluar
        "XRP": {"price": 1.30, "support": 1.35},                            # di bawah → keluar
        "BAD": {"error": "x"},
    }
    rows = cc.near_support_rows(data)
    assert [r["coin"] for r in rows] == ["SOL", "BTC"]
    text = cc.format_near_support(rows, snapshot_ts="t")
    assert "SOL" in text and "bukan sinyal beli" in text
    assert "Tidak ada coin" in cc.format_near_support([], snapshot_ts="t")


class MenuRoutingTests(IsolatedAsyncioTestCase):
    def _update(self, text, replies):
        async def reply_text(message, **kwargs):
            replies.append((message, kwargs.get("reply_markup")))
        message = SimpleNamespace(text=text, reply_text=reply_text)
        return SimpleNamespace(message=message, effective_message=message)

    async def test_trading_menu_uses_new_buttons_and_old_label_routes(self):
        labels = [b for row in tb._trading_submenu_keyboard().keyboard for b in row]
        labels = [getattr(b, "text", b) for b in labels]
        assert "📍 Dekat S/R" in labels and "🟢 Peluang Spot" not in labels
        with patch.object(tb, "near_support_command", AsyncMock()) as m:
            for label in ("📍 Dekat S/R", "📍 Dekat Support", "🟢 Peluang Spot"):
                await tb.menu_button_handler(self._update(label, []), SimpleNamespace(user_data={}))
        assert m.await_count == 3

    async def test_analisis_coin_selector_uses_cond_prefix(self):
        replies = []
        await tb.menu_button_handler(self._update("🔍 Analisis Coin", replies), SimpleNamespace(user_data={}))
        markup = replies[-1][1]
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert datas and all(d.startswith("cond_") for d in datas)


def test_near_levels_has_both_sides():
    data = {"BTC": BTC, "OM": {"price": 100.0, "resistance": 102.0, "trend_4h": "BULLISH"}}
    text = cc.format_near_levels(cc.near_support_rows(data), cc.near_resistance_rows(data), snapshot_ts="t")
    assert "🔻 Dekat support" in text and "BTC" in text
    assert "🔺 Dekat resistance" in text and "OM     2.0% di bawah $102" in text


def test_card_scenario_when_support_already_broken():
    out = cc.build_coin_condition("BTC", dict(BTC, price=80000.0), closes_1d=[78000.0 + i for i in range(40)])
    assert "▲ Kembali di atas $81,038 → support pulih" in out
    assert "▼ Lanjut turun → level 30-hari ~$78,010" in out


def test_both_sideways_reads_as_range_not_misaligned():
    out = cc.build_coin_condition("BTC", dict(BTC, trend_4h="SIDEWAYS", trend_1d="SIDEWAYS"))
    assert "4H → · 1D →  (sama-sama sideways — range)" in out
