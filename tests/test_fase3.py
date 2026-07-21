import copy

from backtest.simulator import _mae_pct, simulate_coin
from engine.market.features import average_true_range


def _row(index, open_price, high, low, close, step=4 * 60 * 60 * 1000):
    start = index * step
    return {
        "open_time": start,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1,
        "close_time": start + step - 1,
    }


def test_atr14_manual_and_future_candle_invariance():
    rows = [_row(index, 100, 102, 98, 100) for index in range(16)]
    rows[14]["high"] = 110
    rows[14]["low"] = 90
    values = average_true_range(rows, 14)
    expected = ((13 * 4) + 20) / 14
    assert values[14] == expected
    extended = rows + [_row(16, 1000, 1010, 990, 1005)]
    assert average_true_range(extended, 14)[14] == values[14]


def test_mae_manual():
    position = {"side": "LONG", "entry_time": 0, "entry_price": 100}
    rows = [_row(0, 100, 101, 98, 100)]
    assert _mae_pct(position, rows, rows[0]["close_time"]) == -2.0


def test_confirmation_uses_next_candle_close_only(monkeypatch):
    import backtest.simulator as simulator

    rows = [_row(index, 100, 101, 99, 100) for index in range(35)]
    rows[20]["open"] = 100
    rows[20]["close"] = 99
    daily = [_row(index, 100, 101, 99, 100, step=24 * 60 * 60 * 1000) for index in range(55)]
    dataset = {"4h": rows, "1d": daily, "5m": rows, "1h": [], "funding": []}
    monkeypatch.setattr(
        simulator,
        "_call_brain",
        lambda market_data, regime: {
            "setup": "OVERSOLD BOUNCE",
            "side": "LONG",
            "entry": market_data["price"],
            "sl": market_data["price"] * 0.985,
            "tp1": market_data["price"] * 1.05,
            "risk_reward": 3,
            "confidence": 80,
        },
    )
    trades = simulate_coin(
        "BTC", dataset, 0, rows[-1]["close_time"],
        production_filters=False, experiment={"confirmation": True},
    )
    assert all(trade["setup"] != "OVERSOLD BOUNCE" or trade["entry_time"] != rows[20]["open_time"] for trade in trades)
