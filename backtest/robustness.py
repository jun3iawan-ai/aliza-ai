"""Fase 4 robustness protocol for the frozen E3 configuration."""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from engine.market.market_universe import CORE_COINS, get_universe_exclude

from .data_loader import BinanceDataLoader, load_coin_dataset, to_ms
from .metrics import aggregate_metrics
from .simulator import SETUPS, simulate_coin

E3 = {
    "id": "E3_3x_atr_3D",
    "sl_atr_multiplier": 1.0,
    "tp_mode": "3x_atr",
    "time_stop_days": 3,
    "support_distance_filter": True,
}
HOLDOUT_START = "2026-01-21T00:00:00Z"
HOLDOUT_END = "2026-07-21T23:59:59Z"
FULL_START = "2024-07-21T00:00:00Z"
FULL_END = HOLDOUT_END


def _datasets(data_dir, start, end, coins):
    loader = BinanceDataLoader(data_dir)
    sm, em = to_ms(start), to_ms(end)
    warm = sm - 60 * 24 * 60 * 60 * 1000
    return {coin: load_coin_dataset(loader, coin, warm, em, download=False) for coin in coins}


def _run(config, datasets, start_ms, end_ms, coins):
    rows = []
    for coin in coins:
        for trade in simulate_coin(
            coin,
            datasets[coin],
            start_ms,
            end_ms,
            setups=SETUPS,
            production_filters=True,
            notional=100.0,
            btc_dataset=datasets.get("BTC"),
            experiment=config,
        ):
            trade["experiment"] = config.get("id", "experiment")
            rows.append(trade)
    return rows


def _bootstrap(rows, iterations=10000, seed=20260721):
    values = [float(row.get("pnl_pct", 0.0)) for row in rows]
    if not values:
        return {"iterations": iterations, "expectancy_pct": 0.0, "ci95": [0.0, 0.0], "seed": seed}
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        estimates.append(sum(rng.choice(values) for _ in values) / len(values))
    estimates.sort()
    lo = estimates[int(iterations * 0.025)]
    hi = estimates[int(iterations * 0.975) - 1]
    return {
        "iterations": iterations,
        "seed": seed,
        "expectancy_pct": sum(values) / len(values),
        "ci95": [round(lo, 8), round(hi, 8)],
        "lower_bound_gt_zero": lo > 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="backtest/data")
    parser.add_argument("--output-dir", default="backtest/results/fase4")
    args = parser.parse_args(argv)
    coins = [coin for coin in CORE_COINS if coin not in get_universe_exclude()]
    holdout_sm, holdout_em = to_ms(HOLDOUT_START), to_ms(HOLDOUT_END)
    full_sm, full_em = to_ms(FULL_START), to_ms(FULL_END)
    holdout_data = _datasets(args.data_dir, HOLDOUT_START, HOLDOUT_END, coins)
    full_data = _datasets(args.data_dir, FULL_START, FULL_END, coins)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    holdout_rows = _run(E3, holdout_data, holdout_sm, holdout_em, coins)
    result = {
        "protocol": {
            "holdout_start": HOLDOUT_START,
            "holdout_end": HOLDOUT_END,
            "coins": coins,
            "bootstrap_seed": 20260721,
        },
        "baseline_holdout": aggregate_metrics(holdout_rows),
        "bootstrap": _bootstrap(holdout_rows),
    }

    without_wld = [coin for coin in coins if coin != "WLD"]
    no_wld_data = {coin: holdout_data[coin] for coin in without_wld}
    no_wld_rows = _run(E3, no_wld_data, holdout_sm, holdout_em, without_wld)
    result["exclude_wld"] = aggregate_metrics(no_wld_rows)

    result["stress_slippage"] = {}
    for label, slippage in (("2x", 0.001), ("3x", 0.0015)):
        cfg = {**E3, "id": f"E3_{label}_slippage", "slippage_per_side": slippage}
        rows = _run(cfg, holdout_data, holdout_sm, holdout_em, coins)
        result["stress_slippage"][label] = aggregate_metrics(rows)

    # Eight equal chronological windows over the complete two-year sample.
    result["rolling_8"] = []
    span = (full_em - full_sm) / 8
    for index in range(8):
        start = int(full_sm + index * span)
        end = int(full_em if index == 7 else full_sm + (index + 1) * span)
        rows = _run(E3, full_data, start, end, coins)
        result["rolling_8"].append({"window": index + 1, "start_ms": start, "end_ms": end, "metrics": aggregate_metrics(rows)})

    per_coin = {}
    for coin in coins:
        per_coin[coin] = aggregate_metrics(_run(E3, {coin: holdout_data[coin]}, holdout_sm, holdout_em, [coin]))
    result["per_coin_holdout"] = per_coin

    # Post-hoc calibration only; never used for winner selection.
    result["posthoc_runner_up"] = {}
    for cfg in (
        {"id": "E3_3x_atr_7D", "sl_atr_multiplier": 1.0, "tp_mode": "3x_atr", "time_stop_days": 7, "support_distance_filter": True},
        {"id": "E1_ATR_1.5", "sl_atr_multiplier": 1.5},
    ):
        result["posthoc_runner_up"][cfg["id"]] = aggregate_metrics(_run(cfg, holdout_data, holdout_sm, holdout_em, coins))

    (output / "robustness_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    (output / "manifest.json").write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "protocol": result["protocol"]}, indent=2))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
