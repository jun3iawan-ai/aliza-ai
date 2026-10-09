"""Positioning futures: tafsiran harga vs OI, format, dan penggabungan menu."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from engine.market import positioning as pos


@pytest.mark.parametrize("price,oi,emoji", [
    (3.0, 6.0, "🟩"), (-3.0, 6.0, "🟥"), (3.0, -6.0, "🟦"), (-3.0, -6.0, "🟧"),
    (0.2, 6.0, "🟨"), (-4.0, 1.0, "▫️"), (None, 5.0, "▫️"),
])
def test_interpret(price, oi, emoji):
    assert pos.interpret(price, oi)[0] == emoji


def _row(coin, price, oi, fr=0.0001, ls=1.2):
    return {"coin": coin, "fr": fr, "next_funding": "15:00 WIB", "next_funding_ms": None,
            "oi_usd": 1e9, "oi_24h": oi, "oi_4h": 1.0, "price_24h": price, "ls": ls}


def test_headline_dominant_pattern():
    rows = [_row("A", -3, -8), _row("B", -2, -6), _row("C", 1, 1)]
    h = pos.market_headline(rows)
    assert "🟧 2/3" in h and "deleveraging" in h


def test_headline_mixed():
    rows = [_row("A", -3, -8), _row("B", 3, 6), _row("C", 1, 1)]
    assert "campuran" in pos.market_headline(rows)


def test_format_lists_extreme_funding_and_notable_oi():
    rows = [_row("BTC", 1.0, 1.0), _row("SOL", -4.0, 9.0, fr=0.0015)]
    txt = pos.format_positioning(rows, "ts", missing=["BONE"])
    assert "SOL +0.1500%" in txt and "Long terlalu padat" in txt
    assert "🟥 SOL OI +9.0%" in txt
    assert "Tidak ada di Binance Futures: BONE" in txt
    assert "bukan saran entry" in txt


def test_format_empty():
    assert "tidak tersedia" in pos.format_positioning([], "ts")


def test_collect_skips_non_futures_coins():
    with patch.object(pos, "fetch_coin", side_effect=lambda c: _row(c, 1, 1)):
        rows = pos.collect(["BTC", "BONE"])
    assert [r["coin"] for r in rows] == ["BTC"]


def test_coin_line():
    line = pos.coin_line(_row("BTC", -3.0, -6.0, fr=-0.0002, ls=0.9))
    assert "OI 24j -6.0%" in line and "FR -0.0200%" in line and "L/S 0.90" in line
    assert "🟧" in line


class TestMenus:
    def test_cfra_and_health_buttons_removed(self):
        import interfaces.telegram_bot as tb
        macro = [b for row in tb._macro_submenu_keyboard().keyboard for b in row]
        system = [b for row in tb._system_submenu_keyboard().keyboard for b in row]
        labels = [getattr(b, "text", b) for b in macro + system]
        assert "📊 CFRA" not in labels and "🏥 Health Sistem" not in labels
        assert "🔄 Funding Rate & OI" in labels and "⚙️ Status Sistem" in labels

    def test_old_cfra_label_routes_to_funding_view(self):
        import asyncio
        import interfaces.telegram_bot as tb
        msg = SimpleNamespace(text="📊 CFRA", reply_text=AsyncMock())
        upd = SimpleNamespace(message=msg, effective_message=msg)
        with patch.object(tb, "check_funding_command", AsyncMock()) as m:
            asyncio.run(tb.menu_button_handler(upd, SimpleNamespace(user_data={})))
        m.assert_awaited_once()

    def test_status_text_reports_missing_coins(self):
        import interfaces.telegram_bot as tb
        from datetime import datetime
        snap = {"data": {"BTC": {"price": 1}, "ETH": {"price": 1}}, "timestamp": datetime.utcnow()}
        with patch.object(tb, "get_market_snapshot", return_value=snap):
            txt = tb._system_status_text(None)
        assert "2/" in txt and "Tidak ada di snapshot" in txt and "WARNING" in txt


def test_tokenomics_disk_cache_fallback_after_restart():
    from engine.market import coin_info as ci
    ci.reset_cache_for_tests()
    batch = {"BTC": {"market_cap": 1.0, "fully_diluted_valuation": 1.0, "circulating_supply": 1.0,
                     "total_supply": 1.0, "max_supply": 2.0, "market_cap_rank": 1}}
    with patch.object(ci, "_fetch_tokenomics_batch", return_value=(batch, None)):
        assert ci.get_tokenomics("BTC", now=1000.0)["status"] == "ok"
    ci.reset_cache_for_tests()  # simulasi restart
    with patch.object(ci, "_fetch_tokenomics_batch", return_value=(None, "HTTP 429")):
        assert ci.get_tokenomics("BTC", now=2000.0)["status"] == "ok"
    ci.reset_cache_for_tests()
