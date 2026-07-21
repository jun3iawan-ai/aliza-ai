"""Aggregate backtest metrics, confidence intervals, and walk-forward slices."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import median


def wilson_interval(wins, total, z=1.959963984540054):
    if total <= 0:
        return [0.0, 0.0]
    p = wins / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [round(max(0.0, centre - margin), 6), round(min(1.0, centre + margin), 6)]


def _max_drawdown(values):
    peak = 0.0
    drawdown = 0.0
    equity = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return round(drawdown, 8)


def aggregate_metrics(trades):
    trades = list(trades or [])
    wins = [trade for trade in trades if trade.get("result") == "WIN"]
    losses = [trade for trade in trades if trade.get("result") == "LOSS"]
    pnls = [float(trade.get("pnl_pct", 0)) for trade in trades]
    win_pnls = [float(trade.get("pnl_pct", 0)) for trade in wins]
    loss_pnls = [float(trade.get("pnl_pct", 0)) for trade in losses]
    gross_win = sum(value for value in win_pnls if value > 0)
    gross_loss = abs(sum(value for value in loss_pnls if value < 0))
    durations = [float(trade.get("duration_hours", 0)) for trade in trades]
    total = len(trades)
    result = {
        "n": total,
        "wins": len(wins),
        "losses": len(losses),
        "winrate": round(len(wins) / total, 6) if total else 0.0,
        "winrate_wilson_95": wilson_interval(len(wins), total),
        "expectancy_pct": round(sum(pnls) / total, 8) if total else 0.0,
        "profit_factor": round(gross_win / gross_loss, 8) if gross_loss else (round(gross_win, 8) if gross_win else 0.0),
        "avg_win_pct": round(sum(win_pnls) / len(win_pnls), 8) if win_pnls else 0.0,
        "avg_loss_pct": round(sum(loss_pnls) / len(loss_pnls), 8) if loss_pnls else 0.0,
        "max_drawdown_pct": _max_drawdown(pnls),
        "median_duration_hours": round(median(durations), 8) if durations else 0.0,
        "pnl_distribution_pct": {
            "min": round(min(pnls), 8) if pnls else 0.0,
            "p25": round(sorted(pnls)[max(0, int(len(pnls) * 0.25) - 1)], 8) if pnls else 0.0,
            "median": round(median(pnls), 8) if pnls else 0.0,
            "p75": round(sorted(pnls)[max(0, int(len(pnls) * 0.75) - 1)], 8) if pnls else 0.0,
            "max": round(max(pnls), 8) if pnls else 0.0,
        },
        "sample_small": total < 30,
    }
    if result["sample_small"]:
        result["sample_note"] = "sampel kecil — tidak konklusif"
    return result


def group_trades(trades, keys=("setup", "coin", "regime", "side")):
    grouped = defaultdict(list)
    for trade in trades or []:
        grouped[tuple(trade.get(key, "UNKNOWN") for key in keys)].append(trade)
    return grouped


def metrics_by_group(trades, keys=("setup", "coin", "regime", "side")):
    result = {}
    for group, rows in sorted(group_trades(trades, keys).items()):
        result["|".join(str(part) for part in group)] = aggregate_metrics(rows)
    return result


def quarter_label(timestamp_ms, start_ms, end_ms):
    span = max(1, end_ms - start_ms)
    quarter = min(4, int((timestamp_ms - start_ms) / span * 4) + 1)
    return f"Q{quarter}"


def walk_forward_metrics(trades, start_ms, end_ms):
    quarters = defaultdict(list)
    for trade in trades or []:
        quarters[quarter_label(int(trade["entry_time"]), start_ms, end_ms)].append(trade)
    return {quarter: metrics_by_group(rows, keys=("setup", "coin", "regime", "side")) for quarter, rows in sorted(quarters.items())}
