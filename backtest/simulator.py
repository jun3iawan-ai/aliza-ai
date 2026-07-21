"""Event-driven, research-only simulator for TradingBrain production setups."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from engine.brain import trading_brain
from engine.brain.trading_brain import TradingBrain
from engine.intelligence.market_regime_detector import detect_market_regime
from engine.market.features import compute_features

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
    rows = [row for row in rows if int(row["open_time"]) >= position["entry_time"] and int(row["close_time"]) <= now_ms]
    for row in rows:
        high, low = float(row["high"]), float(row["low"])
        side = position["side"]
        tp, sl = float(position["tp1"]), float(position["sl"])
        if side == "LONG":
            if high >= tp and low <= sl:
                return "LOSS", sl, row["close_time"], "same_bar_tp_sl"
            if low <= sl:
                return "LOSS", sl, row["close_time"], "sl"
            if high >= tp:
                return "WIN", tp, row["close_time"], "tp1"
        else:
            if low <= tp and high >= sl:
                return "LOSS", sl, row["close_time"], "same_bar_tp_sl"
            if high >= sl:
                return "LOSS", sl, row["close_time"], "sl"
            if low <= tp:
                return "WIN", tp, row["close_time"], "tp1"
    if now_ms - position["entry_time"] >= TIME_STOP_MS:
        return "EXPIRED", position["last_close"], now_ms, "time_stop_7d"
    return None


def _trade_record(position, result, exit_price, exit_time, exit_reason, resolution, funding_history, notional):
    pnl = calculate_trade_pnl(
        position["side"],
        position["entry_price"],
        exit_price,
        notional,
        position["entry_time"],
        exit_time,
        funding_history,
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


def simulate_coin(coin, dataset, start_ms, end_ms, setups=None, production_filters=True, notional=100.0, btc_dataset=None):
    setups = set(setups or SETUPS)
    all_candles = sorted(dataset.get("4h", []), key=lambda row: int(row["open_time"]))
    candles = [row for row in all_candles if start_ms <= int(row["close_time"]) <= end_ms]
    one_day = sorted(dataset.get("1d", []), key=lambda row: int(row["close_time"]))
    lower_resolution, lower_rows = _lower_resolution(dataset)
    lower_rows = sorted(lower_rows, key=lambda row: int(row["open_time"]))
    funding = dataset.get("funding") or []
    closes_4h = [float(row["close"]) for row in all_candles]
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
            }
            pending = None

        if position:
            position["last_close"] = float(candle["close"])
            event = _exit_event(position, lower_rows, now)
            if event:
                result, exit_price, exit_time, reason = event
                trades.append(_trade_record(position, result, exit_price, exit_time, reason, lower_resolution, funding, notional))
                position = None

        if position or pending or index + 1 >= len(candles):
            continue

        closes_until = [float(row["close"]) for row in all_candles if int(row["close_time"]) <= now]
        one_day_until = [row for row in one_day if int(row["close_time"]) <= now]
        closes_1d = [float(row["close"]) for row in one_day_until]
        feature = compute_features(closes_until, closes_1d, price=float(candle["close"]))
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
        }
        signal = _call_brain(market_data, regime)
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
            "entry_index": index + 1,
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
            },
        }

    if position:
        exit_time = int(candles[-1]["close_time"])
        trades.append(_trade_record(position, "EXPIRED", position["last_close"], exit_time, "end_of_period", lower_resolution, funding, notional))
    return trades
