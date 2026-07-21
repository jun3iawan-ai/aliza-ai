import copy
import json

import pytest

from backtest.costs import calculate_trade_pnl
from backtest.metrics import aggregate_metrics
from backtest.simulator import _exit_event, simulate_coin
from engine.market.features import compute_features


def _row(index, open_price, high=None, low=None, close=None, step=4 * 60 * 60 * 1000):
    open_time = index * step
    return {
        "open_time": open_time,
        "open": float(open_price),
        "high": float(high if high is not None else open_price + 1),
        "low": float(low if low is not None else open_price - 1),
        "close": float(close if close is not None else open_price),
        "volume": 1.0,
        "close_time": open_time + step - 1,
    }


def _dataset(count=80):
    rows = [_row(index, 100 + index * 0.1, close=100 + index * 0.1) for index in range(count)]
    daily = [_row(index, 100 + index * 0.1, close=100 + index * 0.1, step=24 * 60 * 60 * 1000) for index in range(count)]
    lower = []
    for index, row in enumerate(rows):
        lower.append({
            "open_time": row["open_time"],
            "open": row["open"],
            "high": row["open"] + 0.2,
            "low": row["open"] - 0.2,
            "close": row["close"],
            "volume": 1.0,
            "close_time": row["close_time"],
        })
    return {"4h": rows, "1d": daily, "5m": lower, "1h": [], "funding": []}


def test_feature_parity_runtime_vs_backtester(monkeypatch):
    from engine.market import market_analyzer as analyzer

    closes_4h = [100 + (index % 7) for index in range(80)]
    closes_1d = [100 + (index % 9) for index in range(60)]
    feature = compute_features(closes_4h, closes_1d, price=105.0)
    monkeypatch.setattr(analyzer, "_get_price_from_binance", lambda symbol: 105.0)
    monkeypatch.setattr(analyzer, "_get_binance_klines", lambda symbol, interval, limit=100: closes_4h if interval == "4h" else closes_1d)
    monkeypatch.setattr(analyzer, "get_global_market_data", lambda: {"fear_greed": 50, "btc_dominance": 50})
    monkeypatch.setattr(analyzer, "market_radar", lambda fear, dominance: {})
    result = analyzer.market_signal("BTC", radar_data={})
    assert result["trend"] == feature["trend"]
    assert result["rsi"] == feature["rsi"]
    assert result["support"] == feature["support"]
    assert result["resistance"] == feature["resistance"]
    assert result["trend_alignment"] == feature["trend_alignment"]


def test_anti_lookahead_feature_prefix_is_unchanged():
    closes = [100 + index * 0.2 for index in range(80)]
    daily = [100 + index * 0.1 for index in range(60)]
    before = compute_features(closes[:60], daily[:50], price=111.8)
    after = compute_features(closes[:60], daily[:50], price=111.8)
    assert before == after


def test_entry_uses_next_candle_open(monkeypatch):
    import backtest.simulator as simulator

    dataset = _dataset()
    monkeypatch.setattr(
        simulator,
        "_call_brain",
        lambda market_data, regime: {
            "setup": "PULLBACK LONG",
            "side": "LONG",
            "entry": market_data["price"],
            "sl": market_data["price"] - 1,
            "tp1": market_data["price"] + 3,
            "risk_reward": 3,
            "confidence": 80,
        },
    )
    trades = simulate_coin("BTC", dataset, 0, dataset["4h"][-1]["close_time"], production_filters=True)
    assert trades
    assert trades[0]["entry_price"] == dataset["4h"][20]["open"]
    assert trades[0]["entry_price"] != dataset["4h"][19]["close"]


def test_same_bar_tp_sl_is_loss_and_short_direction():
    long_position = {"side": "LONG", "tp1": 110, "sl": 90, "entry_time": 0, "last_close": 100}
    row = _row(0, 100, high=111, low=89)
    assert _exit_event(long_position, [row], row["close_time"])[:2] == ("LOSS", 90)

    short_position = {"side": "SHORT", "tp1": 90, "sl": 110, "entry_time": 0, "last_close": 100}
    assert _exit_event(short_position, [_row(0, 100, high=100, low=89)], row["close_time"])[:2] == ("WIN", 90)
    assert _exit_event(short_position, [_row(0, 100, high=111, low=100)], row["close_time"])[:2] == ("LOSS", 110)


def test_fee_slippage_and_funding_manual():
    result = calculate_trade_pnl(
        "SHORT", 100, 90, 100, 0, 8 * 60 * 60 * 1000,
        funding_history=[{"timestamp": 8 * 60 * 60 * 1000, "funding_rate": 0.0002}],
    )
    # Entry 99.95, exit 90.045, gross ~11%, less 0.2% fees, 0.1% slippage, 0.02% funding.
    assert result["funding_method"] == "binance_history"
    assert result["funding_pct"] == 0.02
    assert result["pnl_pct"] > 10.5


def test_reproducibility():
    dataset = _dataset()
    first = simulate_coin("BTC", copy.deepcopy(dataset), 0, dataset["4h"][-1]["close_time"], production_filters=False)
    second = simulate_coin("BTC", copy.deepcopy(dataset), 0, dataset["4h"][-1]["close_time"], production_filters=False)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_metrics_wilson_and_small_sample():
    metrics = aggregate_metrics([
        {"result": "WIN", "pnl_pct": 1, "duration_hours": 4},
        {"result": "LOSS", "pnl_pct": -1, "duration_hours": 8},
    ])
    assert metrics["n"] == 2
    assert metrics["sample_small"] is True
    assert len(metrics["winrate_wilson_95"]) == 2


def test_rsi_stream_matches_runtime_formula():
    from engine.market.features import calculate_rsi, calculate_rsi_series

    prices = [100 + (index % 9) - index * 0.03 for index in range(300)]
    stream = calculate_rsi_series(prices)
    assert all(calculate_rsi(prices[:index + 1]) == stream[index] for index in range(len(prices)))
