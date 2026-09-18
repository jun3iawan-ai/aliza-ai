"""Tests for the scheduled three-state market-context transition alert."""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.market.market_context_engine import map_label_to_alert_status

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


class _Context:
    def __init__(self, chat_id=12345):
        self.bot_data = {"chat_id": chat_id}


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Bearish", "Bearish"),
        ("Weak", "Bearish"),
        ("Neutral", "Neutral"),
        ("Bullish", "Bullish"),
        ("Strong Bullish", "Bullish"),
    ],
)
def test_map_label_to_alert_status_for_all_market_score_labels(label, expected):
    assert map_label_to_alert_status(label) == expected


def test_bootstrap_persists_baseline_without_sending(monkeypatch):
    set_value = []
    dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr(tb, "calculate_market_score", lambda: {"label": "Weak", "total_score": 40})
    monkeypatch.setattr(tb.ngov, "get_value", lambda *_args: None)
    monkeypatch.setattr(tb.ngov, "set_value", lambda *args: set_value.append(args))
    monkeypatch.setattr(tb, "safe_dispatch", dispatch)

    asyncio.run(tb.market_context_alert_job(_Context()))

    assert set_value == [("market_context_alert", "status", "Bearish")]
    dispatch.assert_not_awaited()


def test_changed_status_sends_alert_filters_strong_bullish_and_persists(monkeypatch):
    set_value = []
    dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr(
        tb,
        "calculate_market_score",
        lambda: {
            "label": "Strong Bullish",
            "total_score": 82,
            "timestamp": "2026-09-18 10:15:00 WIB",
        },
    )
    monkeypatch.setattr(tb.ngov, "get_value", lambda *_args: "Bearish")
    monkeypatch.setattr(tb.ngov, "set_value", lambda *args: set_value.append(args))
    monkeypatch.setattr(
        tb,
        "generate_radar_pro",
        lambda: [
            {"coin": "BTC", "trend_alignment": "STRONG_BULLISH"},
            {"coin": "ETH", "trend_alignment": "PARTIAL"},
            {"coin": "SOL", "trend_alignment": "MIXED"},
            {"coin": "XRP", "trend_alignment": "UNKNOWN"},
            {"coin": "BNB", "trend_alignment": "STRONG_BEARISH"},
        ],
    )
    monkeypatch.setattr(tb, "safe_dispatch", dispatch)

    asyncio.run(tb.market_context_alert_job(_Context()))

    dispatch.assert_awaited_once()
    message = dispatch.await_args.args[0]
    assert "Bearish 🔴 → Bullish 🟢" in message
    assert "Skor: 82/100" in message
    assert "BTC" in message
    assert "ETH" not in message
    assert "SOL" not in message
    assert "XRP" not in message
    assert "BNB" not in message
    assert dispatch.await_args.kwargs == {"chat_id": 12345, "force": True}
    assert set_value == [("market_context_alert", "status", "Bullish")]


def test_same_status_does_not_send_or_update_state(monkeypatch):
    dispatch = AsyncMock(return_value=True)
    set_value = []
    monkeypatch.setattr(tb, "calculate_market_score", lambda: {"label": "Bullish", "total_score": 62})
    monkeypatch.setattr(tb.ngov, "get_value", lambda *_args: "Bullish")
    monkeypatch.setattr(tb.ngov, "set_value", lambda *args: set_value.append(args))
    monkeypatch.setattr(tb, "safe_dispatch", dispatch)

    asyncio.run(tb.market_context_alert_job(_Context()))

    dispatch.assert_not_awaited()
    assert set_value == []


def test_alignment_filter_returns_only_strong_matches():
    radar_data = [
        {"coin": "BTC", "trend_alignment": "STRONG_BULLISH"},
        {"coin": "ETH", "trend_alignment": "STRONG_BEARISH"},
        {"coin": "SOL", "trend_alignment": "PARTIAL"},
        {"coin": "XRP", "trend_alignment": "MIXED"},
        {"coin": "BNB", "trend_alignment": "UNKNOWN"},
    ]

    assert tb._coins_aligned_with_market_status("Bullish", radar_data) == ["BTC"]
    assert tb._coins_aligned_with_market_status("Bearish", radar_data) == ["ETH"]
    assert tb._coins_aligned_with_market_status("Neutral", radar_data) == []


def test_transition_to_neutral_has_no_coin_list(monkeypatch):
    set_value = []
    dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr(
        tb,
        "calculate_market_score",
        lambda: {
            "label": "Neutral",
            "total_score": 50,
            "timestamp": "2026-09-18 10:30:00 WIB",
        },
    )
    monkeypatch.setattr(tb.ngov, "get_value", lambda *_args: "Bullish")
    monkeypatch.setattr(tb.ngov, "set_value", lambda *args: set_value.append(args))
    monkeypatch.setattr(tb, "generate_radar_pro", lambda: pytest.fail("radar must not run for Neutral"))
    monkeypatch.setattr(tb, "safe_dispatch", dispatch)

    asyncio.run(tb.market_context_alert_job(_Context()))

    message = dispatch.await_args.args[0]
    assert "Bullish 🟢 → Neutral ⚪" in message
    assert "Coin searah" not in message
    assert "BTC" not in message
    assert set_value == [("market_context_alert", "status", "Neutral")]


def test_changed_status_without_strong_aligned_coins_still_sends(monkeypatch):
    dispatch = AsyncMock(return_value=True)
    monkeypatch.setattr(tb, "calculate_market_score", lambda: {"label": "Weak", "total_score": 31, "timestamp": "2026-09-18 10:45:00 WIB"})
    monkeypatch.setattr(tb.ngov, "get_value", lambda *_args: "Neutral")
    monkeypatch.setattr(tb.ngov, "set_value", lambda *_args: None)
    monkeypatch.setattr(tb, "generate_radar_pro", lambda: [{"coin": "BTC", "trend_alignment": "PARTIAL"}])
    monkeypatch.setattr(tb, "safe_dispatch", dispatch)

    asyncio.run(tb.market_context_alert_job(_Context()))

    message = dispatch.await_args.args[0]
    assert "Neutral ⚪ → Bearish 🔴" in message
    assert "Tidak ada coin dengan trend kuat searah saat ini." in message
    assert dispatch.await_args.kwargs == {"chat_id": 12345, "force": True}
