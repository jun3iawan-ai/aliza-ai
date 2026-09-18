"""Regression tests for neutral prediction labels and global-data fallbacks."""

import asyncio
import os
from unittest.mock import patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.market import market_context_engine as context_engine
from engine.prediction.prediction_engine import generate_market_prediction

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


class _Message:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class _Update:
    def __init__(self):
        self.message = _Message()


def _snapshot(trend="SIDEWAYS", rsi=50, regime="RANGE", whale="NEUTRAL", altseason=60):
    return {
        "data": {"BTC": {"trend": trend, "rsi": rsi}},
        "market_intelligence": {
            "market_regime": regime,
            "whale_pressure": whale,
            "altseason_probability": altseason,
        },
    }


def _quant_message(snapshot):
    update = _Update()
    with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
        tb, "get_snapshot_timestamp_str", return_value="12:00:00"
    ):
        asyncio.run(tb.quant_command(update, None))
    assert len(update.message.replies) == 1
    return update.message.replies[0]

def _predict_message(snapshot):
    update = _Update()
    with patch.object(tb, "get_market_snapshot", return_value=snapshot), patch.object(
        tb, "get_snapshot_timestamp_str", return_value="12:00:00"
    ):
        asyncio.run(tb.predict(update, None))
    assert len(update.message.replies) == 1
    return update.message.replies[0]


def test_predict_and_quant_report_neutral_for_a_genuine_zero_zero_tie():
    snapshot = _snapshot()
    prediction = generate_market_prediction(snapshot)
    predict_message = _predict_message(snapshot)
    quant_message = _quant_message(snapshot)
    assert prediction["bullish_probability"] == prediction["bearish_probability"] == 50
    assert prediction["bias"] == "NEUTRAL"
    assert "Short-term Bias : NEUTRAL" in predict_message
    assert "Market Bias : NEUTRAL" in quant_message


def test_predict_and_quant_keep_their_existing_non_tie_directions():
    for expected_bias, snapshot in (
        ("BULLISH", _snapshot("BULLISH", 65, "TREND", "BUYING", 61)),
        ("BEARISH", _snapshot("BEARISH", 35, "DOWNTREND", "SELLING", 60)),
    ):
        assert generate_market_prediction(snapshot)["bias"] == expected_bias
        assert f"Short-term Bias : {expected_bias}" in _predict_message(snapshot)
        assert f"Market Bias : {expected_bias}" in _quant_message(snapshot)


def _market_score(monkeypatch, global_data):
    monkeypatch.setattr(context_engine, "get_global_market_data", lambda: global_data)
    monkeypatch.setattr(context_engine, "get_all_funding_data", lambda: {coin: {"funding_rate": 0.0} for coin in ("BTC", "ETH", "BNB", "SOL", "XRP")})
    monkeypatch.setattr(context_engine, "get_macro_data", lambda code, _kind: {"change": -1.0} if code == "CPIAUCSL" else {"value": 5.0, "change": 0.0})
    monkeypatch.setattr(context_engine, "scan_for_signals", lambda: {"confidence": 80})
    return context_engine.calculate_market_score()


def test_failed_global_statuses_exclude_fallback_values_from_market_score(monkeypatch):
    normal = _market_score(monkeypatch, {"fear_greed": 50.0, "fear_greed_status": "ok", "btc_dominance": 55.0, "btc_dominance_status": "ok"})
    failed_fear_greed = _market_score(monkeypatch, {"fear_greed": 50.0, "fear_greed_status": "failed", "btc_dominance": 55.0, "btc_dominance_status": "ok"})
    failed_dominance = _market_score(monkeypatch, {"fear_greed": 50.0, "fear_greed_status": "ok", "btc_dominance": 55.0, "btc_dominance_status": "failed"})
    both_failed = _market_score(monkeypatch, {"fear_greed": 50.0, "fear_greed_status": "failed", "btc_dominance": 55.0, "btc_dominance_status": "failed"})
    assert normal["total_score"] == 88
    assert failed_fear_greed["total_score"] == 85
    assert failed_dominance["total_score"] == 86
    assert both_failed["total_score"] == 83
    assert failed_fear_greed["components"]["fear_greed"]["value"] is None
    assert failed_dominance["components"]["btc_dominance"]["value"] is None


def test_brief_format_is_stable_for_ok_status_and_valid_when_status_failed(monkeypatch):
    normal = _market_score(monkeypatch, {"fear_greed": 50.0, "fear_greed_status": "ok", "btc_dominance": 55.0, "btc_dominance_status": "ok"})
    normal_brief = context_engine.format_context_for_brief()
    failed = _market_score(monkeypatch, {"fear_greed": 50.0, "fear_greed_status": "failed", "btc_dominance": 55.0, "btc_dominance_status": "failed"})
    failed_brief = context_engine.format_context_for_brief()
    assert normal["total_score"] == 88
    assert "F&G    : 50 (Neutral) | BTC.D: 55.0%" in normal_brief
    assert failed["total_score"] == 83
