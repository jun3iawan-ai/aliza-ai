"""Event-driven, research-only simulator for TradingBrain production setups."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from engine.brain import trading_brain
from engine.brain.trading_brain import TradingBrain
from engine.intelligence.market_regime_detector import detect_market_regime
from engine.market.features import compute_features, calculate_rsi_series, average_true_range

from .costs import calculate_trade_pnl

logger = logging.getLogger(__name__)

SETUPS = (
    "OVERSOLD BOUNCE",
    "OVERBOUGHT REJECTION",
    "PULLBACK LONG",
    "PULLBACK SHORT",
)
TIME_STOP_MS = 7 * 24 * 60 * 60 * 1000


def _closed(rows, cutoff):
    return [row for row in rows or [] if int(row["close_time"]) <= cutoff]


def _regime_snapshot(regime):
    return {"market_intelligence": {"market_regime": regime}}


@contextmanager
def _historical_regime(regime):
    original = trading_brain.get_market_snapshot
    trading_brain.get_market_snapshot = lambda: _regime_snapshot(regime)
    try:
        yield
    finally:
        trading_brain.get_market_snapshot = original


def _call_brain(market_data, regime):
    with _historical_regime(regime):
        return TradingBrain().analyze(market_data)


def _lower_resolution(dataset):
    if dataset.get("5m"):
        return "5m", dataset["5m"]
    return "1h", dataset.get("1h") or []


def _exit_event(position, rows, now_ms):
    has_cursor = "lower_cursor" in position
    cursor = int(position.get("lower_cursor", 0))
    side = position["side"]
    tp, sl = float(position["tp1"]), float(position["sl"])
    while cursor < len(rows):
        row = rows[cursor]
        if int(row["close_time"]) > now_ms:
            break
        cursor += 1
        if int(row["open_time"]) < int(position["entry_time"]):
            continue
        high, low = float(row["high"]), float(row["low"])
        if side == "LONG":
            if high >= tp and low <= sl:
                if has_cursor:
                    position["lower_cursor"] = cursor
                return "LOSS", sl, row["close_time"], "same_bar_tp_sl"
            if low <= sl:
                if has_cursor:
                    position["lower_cursor"] = cursor
                return "LOSS", sl, row["close_time"], "sl"
            if high >= tp:
                if has_cursor:
                    position["lower_cursor"] = cursor
                return "WIN", tp, row["close_time"], "tp1"
        else:
            if low <= tp and high >= sl:
                if has_cursor:
                    position["lower_cursor"] = cursor
                return "LOSS", sl, row["close_time"], "same_bar_tp_sl"
            if high >= sl:
                if has_cursor:
                    position["lower_cursor"] = cursor
                return "LOSS", sl, row["close_time"], "sl"
            if low <= tp:
                if has_cursor:
                    position["lower_cursor"] = cursor
                return "WIN", tp, row["close_time"], "tp1"
    if has_cursor:
        position["lower_cursor"] = cursor
    if now_ms - position["entry_time"] >= position.get("time_stop_ms", TIME_STOP_MS):
        return "EXPIRED", position["last_close"], now_ms, "time_stop_7d"
    return None


def _mae_pct(position, rows, exit_time):
    observed = [row for row in rows if int(row["open_time"]) >= position["entry_time"] and int(row["close_time"]) <= exit_time]
    if not observed:
        return 0.0
    entry = float(position["entry_price"])
    if position["side"] == "LONG":
        return round((min(float(row["low"]) for row in observed) / entry - 1) * 100, 8)
    return round((entry / max(float(row["high"]) for row in observed) - 1) * 100, 8)

def _trade_record(position, result, exit_price, exit_time, exit_reason, resolution, funding_history, notional, observed_rows=None):
    pnl = calculate_trade_pnl(
        position["side"],
        position["entry_price"],
        exit_price,
        notional,
        position["entry_time"],
        exit_time,
        funding_history,
        fee_per_side=float(position.get("fee_per_side", 0.001)),
        slippage_per_side=float(position.get("slippage_per_side", 0.0005)),
    )
    entry_dt = datetime.fromtimestamp(position["entry_time"] / 1000, tz=timezone.utc)
    exit_dt = datetime.fromtimestamp(exit_time / 1000, tz=timezone.utc)
    return {
        "coin": position["coin"],
        "setup": position["setup"],
        "side": position["side"],
        "regime": position["regime"],
        "signal_time": position["signal_time"],
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "entry_price": position["entry_price"],
        "signal_price": position["signal_price"],
        "exit_price": exit_price,
        "mae_pct": _mae_pct(position, observed_rows or [], exit_time),
        "sl": position["sl"],
        "tp1": position["tp1"],
        "rr": position.get("risk_reward"),
        "confidence": position.get("confidence"),
        "result": result,
        "exit_reason": exit_reason,
        "resolution": resolution,
        "funding_method": pnl["funding_method"],
        "gross_pnl_pct": pnl["gross_pnl_pct"],
        "fee_pct": pnl["fee_pct"],
        "slippage_pct": pnl["slippage_pct"],
        "funding_pct": pnl["funding_pct"],
        "pnl_pct": pnl["pnl_pct"],
        "pnl_usdt": pnl["pnl_usdt"],
        "duration_hours": round((exit_time - position["entry_time"]) / 3600000, 8),
        "entry_iso": entry_dt.isoformat(),
        "exit_iso": exit_dt.isoformat(),
    }


def simulate_coin(coin, dataset, start_ms, end_ms, setups=None, production_filters=True, notional=100.0, btc_dataset=None, experiment=None):
    setups = set(setups or SETUPS)
    experiment = dict(experiment or {})
    all_candles = sorted(dataset.get("4h", []), key=lambda row: int(row["open_time"]))
    candles = [row for row in all_candles if start_ms <= int(row["close_time"]) <= end_ms]
    one_day = sorted(dataset.get("1d", []), key=lambda row: int(row["close_time"]))
    lower_resolution, lower_rows = _lower_resolution(dataset)
    lower_rows = sorted(lower_rows, key=lambda row: int(row["open_time"]))
    funding = dataset.get("funding") or []
    closes_4h = [float(row["close"]) for row in all_candles]
    rsi_series = calculate_rsi_series(closes_4h)
    atr_series = average_true_range(all_candles, 14)
    position = None
    pending = None
    trades = []
    btc_dataset = btc_dataset or dataset
    btc_4h = sorted(btc_dataset.get("4h", []), key=lambda row: int(row["close_time"]))
    btc_1d = sorted(btc_dataset.get("1d", []), key=lambda row: int(row["close_time"]))

    for index, candle in enumerate(candles):
        now = int(candle["close_time"])
        if pending and pending["entry_index"] == index:
            position = {
                **pending["trade"],
                "entry_price": float(candle["open"]),
                "entry_time": int(candle["open_time"]),
                "last_close": float(candle["close"]),
                "lower_cursor": 0,
            }
            pending = None

        if position:
            position["last_close"] = float(candle["close"])
            event = _exit_event(position, lower_rows, now)
            if event:
                result, exit_price, exit_time, reason = event
                trades.append(_trade_record(position, result, exit_price, exit_time, reason, lower_resolution, funding, notional, lower_rows))
                position = None

        if position or pending or index + 1 >= len(candles):
            continue

        closes_until = [float(row["close"]) for row in all_candles if int(row["close_time"]) <= now]
        rsi_index = max(0, len(closes_until) - 1)
        one_day_until = [row for row in one_day if int(row["close_time"]) <= now]
        closes_1d = [float(row["close"]) for row in one_day_until]
        feature = compute_features(closes_until[-200:], closes_1d[-50:], price=float(candle["close"]), rsi_value=rsi_series[rsi_index])
        if not feature.get("valid"):
            continue

        btc_until_4h = [row for row in btc_4h if int(row["close_time"]) <= now]
        btc_until_1d = [row for row in btc_1d if int(row["close_time"]) <= now]
        btc_feature = compute_features(
            [float(row["close"]) for row in btc_until_4h],
            [float(row["close"]) for row in btc_until_1d],
            price=float(btc_until_4h[-1]["close"]) if btc_until_4h else None,
        )
        regime = detect_market_regime(btc_feature if btc_feature.get("valid") else feature).get("market_regime", "UNKNOWN")
        market_data = {
            "symbol": coin,
            "price": float(candle["close"]),
            "trend": feature["trend"],
            "rsi": feature["rsi"],
            "support": feature["support"],
            "resistance": feature["resistance"],
            "trend_alignment": feature["trend_alignment"],
            "open": float(candle["open"]),
        }
        signal = _call_brain(market_data, regime)
        if not signal or signal.get("setup") not in setups:
            continue
        atr = atr_series[rsi_index] if rsi_index < len(atr_series) else None
        if experiment.get("disable_setup") == signal.get("setup"):
            continue
        if experiment.get("funding_positive_only") and signal.get("setup") == "PULLBACK SHORT":
            funding_rows = [item for item in funding if int(item.get("timestamp", 0)) <= now]
            if not funding_rows or float(funding_rows[-1].get("funding_rate", 0)) <= 0:
                continue
        if experiment.get("support_distance_filter") and signal.get("setup") == "OVERSOLD BOUNCE":
            support = feature.get("support")
            if support is None or float(candle["close"]) > float(support) * 1.01:
                continue
        entry_offset = 1
        if experiment.get("confirmation") and signal.get("setup") in ("OVERSOLD BOUNCE", "OVERBOUGHT REJECTION"):
            next_candle = candles[index + 1] if index + 1 < len(candles) else None
            if next_candle is None:
                continue
            bullish = signal.get("side") == "LONG"
            next_open = float(next_candle["open"])
            next_close = float(next_candle["close"])
            if (bullish and next_close <= next_open) or ((not bullish) and next_close >= next_open):
                continue
            entry_offset = 2
        if atr and experiment.get("sl_atr_multiplier"):
            distance = float(experiment["sl_atr_multiplier"]) * float(atr)
            signal["sl"] = float(signal["entry"]) - distance if signal.get("side") == "LONG" else float(signal["entry"]) + distance
        if atr and experiment.get("tp_mode") in ("2x_atr", "3x_atr"):
            multiple = 2.0 if experiment["tp_mode"] == "2x_atr" else 3.0
            signal["tp1"] = float(signal["entry"]) + multiple * float(atr) if signal.get("side") == "LONG" else float(signal["entry"]) - multiple * float(atr)
        if signal.get("entry") and signal.get("sl") and signal.get("tp1"):
            signal["risk_reward"] = round(abs(float(signal["tp1"]) - float(signal["entry"])) / abs(float(signal["entry"]) - float(signal["sl"])), 2)
        if experiment.get("rr_min") is not None and (signal.get("risk_reward") is None or float(signal.get("risk_reward")) < float(experiment["rr_min"])):
            continue
        if experiment.get("confidence_min") is not None and float(signal.get("confidence") or 0) < float(experiment["confidence_min"]):
            continue
        if not signal or signal.get("setup") not in setups:
            continue
        if production_filters and (
            signal.get("risk_reward") is None
            or float(signal.get("risk_reward")) < 3
            or float(signal.get("confidence") or 0) < 70
        ):
            continue
        if signal.get("side") not in ("LONG", "SHORT") or signal.get("sl") is None or signal.get("tp1") is None:
            continue
        pending = {
            "entry_index": index + entry_offset,
            "trade": {
                "coin": coin,
                "setup": signal["setup"],
                "side": signal["side"],
                "regime": regime,
                "signal_time": now,
                "signal_price": float(candle["close"]),
                "sl": float(signal["sl"]),
                "tp1": float(signal["tp1"]),
                "risk_reward": signal.get("risk_reward"),
                "confidence": signal.get("confidence"),
                "time_stop_ms": int(experiment.get("time_stop_days", 7)) * 24 * 60 * 60 * 1000,
                "fee_per_side": float(experiment.get("fee_per_side", 0.001)),
                "slippage_per_side": float(experiment.get("slippage_per_side", 0.0005)),
            },
        }

    if position:
        exit_time = int(candles[-1]["close_time"])
        trades.append(_trade_record(position, "EXPIRED", position["last_close"], exit_time, "end_of_period", lower_resolution, funding, notional, lower_rows))
    return trades
