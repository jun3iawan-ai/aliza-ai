"""Backtest-driven Fase 3 experiment runner; no live/runtime imports beyond TradingBrain."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from engine.market.market_universe import CORE_COINS, get_universe_exclude

from .data_loader import BinanceDataLoader, load_coin_dataset, to_ms
from .metrics import aggregate_metrics, metrics_by_group
from .simulator import SETUPS, simulate_coin


COINS = [coin for coin in CORE_COINS if coin not in get_universe_exclude()]
TUNE_START = "2024-07-21T00:00:00Z"
TUNE_END = "2026-01-20T23:59:59Z"
HOLDOUT_START = "2026-01-21T00:00:00Z"
HOLDOUT_END = "2026-07-21T23:59:59Z"


def experiment_grid(phase, base_atr=2.0):
    if phase == "e1":
        return [{"id": "E1_ATR_1.0", "sl_atr_multiplier": 1.0},
                {"id": "E1_ATR_1.5", "sl_atr_multiplier": 1.5},
                {"id": "E1_ATR_2.0", "sl_atr_multiplier": base_atr},
                {"id": "E1_ATR_2.5", "sl_atr_multiplier": 2.5}]
    if phase == "e2":
        return [
            {"id": "E2_CONFIRM", "sl_atr_multiplier": base_atr, "confirmation": True},
            {"id": "E2_SUPPORT_DISTANCE", "sl_atr_multiplier": base_atr, "support_distance_filter": True},
            {"id": "E2_NO_OVERSOLD", "sl_atr_multiplier": base_atr, "disable_setup": "OVERSOLD BOUNCE"},
            {"id": "E2_NO_OVERBOUGHT", "sl_atr_multiplier": base_atr, "disable_setup": "OVERBOUGHT REJECTION"},
        ]
    if phase == "e3":
        return [
            {"id": f"E3_{tp}_{days}D", "sl_atr_multiplier": base_atr, "tp_mode": tp, "time_stop_days": days, "support_distance_filter": True}
            for tp in ("resistance", "2x_atr", "3x_atr") for days in (3, 7)
        ]
    if phase == "e4":
        return [
            {"id": "E4_FUNDING_POSITIVE", "sl_atr_multiplier": base_atr, "funding_positive_only": True, "support_distance_filter": True},
            {"id": "E4_RR2_CONF60", "sl_atr_multiplier": base_atr, "rr_min": 2, "confidence_min": 60, "support_distance_filter": True},
            {"id": "E4_RR2_CONF70", "sl_atr_multiplier": base_atr, "rr_min": 2, "confidence_min": 70, "support_distance_filter": True},
            {"id": "E4_RR3_CONF60", "sl_atr_multiplier": base_atr, "rr_min": 3, "confidence_min": 60, "support_distance_filter": True},
            {"id": "E4_RR3_CONF70", "sl_atr_multiplier": base_atr, "rr_min": 3, "confidence_min": 70, "support_distance_filter": True},
        ]
    if phase == "baseline":
        return [{"id": "baseline_5m", "baseline": True}]
    raise ValueError(phase)


def _write_csv(path, rows):
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        if not fields:
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_phase(phase, start=TUNE_START, end=TUNE_END, data_dir="backtest/data", output_dir="backtest/results/fase3", base_atr=2.0):
    loader = BinanceDataLoader(data_dir)
    start_ms, end_ms = to_ms(start), to_ms(end)
    warmup = start_ms - 60 * 24 * 60 * 60 * 1000
    datasets = {coin: load_coin_dataset(loader, coin, warmup, end_ms, download=False) for coin in COINS}
    output = Path(output_dir) / phase
    output.mkdir(parents=True, exist_ok=True)
    all_rows = []
    summaries = {}
    for config in experiment_grid(phase, base_atr):
        rows = []
        for coin in COINS:
            trades = simulate_coin(
                coin, datasets[coin], start_ms, end_ms, setups=SETUPS,
                production_filters=True, notional=100.0,
                btc_dataset=datasets.get("BTC"), experiment={} if config.get("baseline") else config,
            )
            for trade in trades:
                trade["experiment"] = config["id"]
            rows.extend(trades)
        all_rows.extend(rows)
        summaries[config["id"]] = {
            "config": config,
            "metrics": aggregate_metrics(rows),
            "by_setup_regime_side": metrics_by_group(rows, keys=("setup", "regime", "side")),
        }
    _write_csv(output / "trades.csv", all_rows)
    (output / "summaries.json").write_text(json.dumps(summaries, indent=2, sort_keys=True))
    (output / "manifest.json").write_text(json.dumps({
        "phase": phase, "start": start, "end": end, "coins": COINS,
        "criteria": {"expectancy_pct_gt": 0.10, "profit_factor_gt": 1.15, "n_gte": 80, "coin_profit_share_lt": 0.50},
    }, indent=2, sort_keys=True))
    return summaries


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "e1", "e2", "e3", "e4"))
    parser.add_argument("--start", default=TUNE_START)
    parser.add_argument("--end", default=TUNE_END)
    parser.add_argument("--data-dir", default="backtest/data")
    parser.add_argument("--base-atr", type=float, default=2.0)
    parser.add_argument("--output-dir", default="backtest/results/fase3")
    args = parser.parse_args(argv)
    summaries = run_phase(args.phase, args.start, args.end, args.data_dir, args.output_dir, args.base_atr)
    print(json.dumps({key: value["metrics"] for key, value in summaries.items()}, indent=2))


if __name__ == "__main__":
    main()
