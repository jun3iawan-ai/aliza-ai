"""CLI entry point for deterministic research backtests."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.market.market_universe import CORE_COINS, get_universe_exclude

from .data_loader import BinanceDataLoader, load_coin_dataset, to_ms
from .metrics import aggregate_metrics, metrics_by_group, walk_forward_metrics
from .simulator import SETUPS, simulate_coin


def _git_hash():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "UNKNOWN"


def _write_csv(path, rows):
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        if not fields:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(config):
    end = to_ms(config["end"])
    start = to_ms(config["start"])
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    loader = BinanceDataLoader(config["data_dir"])
    warmup_start = start - 60 * 24 * 60 * 60 * 1000
    coins = config["coins"] or [coin for coin in CORE_COINS if coin not in get_universe_exclude()]
    datasets = {}
    for coin in coins:
        datasets[coin] = load_coin_dataset(loader, coin, warmup_start, end, download=config["download"])
    all_trades = []
    for filtered in (True, False):
        variant = "production_filters" if filtered else "no_rr_conf_filters"
        for coin in coins:
            trades = simulate_coin(
                coin,
                datasets[coin],
                start,
                end,
                setups=config["setups"],
                production_filters=filtered,
                notional=config["notional"],
                btc_dataset=datasets.get("BTC"),
            )
            for trade in trades:
                trade["variant"] = variant
            all_trades.extend(trades)
    _write_csv(output / "trades.csv", all_trades)
    filtered_trades = [trade for trade in all_trades if trade["variant"] == "production_filters"]
    metrics = {
        "all": aggregate_metrics(filtered_trades),
        "by_setup_coin_regime_side": metrics_by_group(filtered_trades),
        "variants": {
            "production_filters": aggregate_metrics(filtered_trades),
            "no_rr_conf_filters": aggregate_metrics([trade for trade in all_trades if trade["variant"] == "no_rr_conf_filters"]),
        },
    }
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True))
    (output / "quarterly_metrics.json").write_text(json.dumps(walk_forward_metrics(filtered_trades, start, end), indent=2, sort_keys=True))
    (output / "config.json").write_text(json.dumps({**config, "commit": _git_hash(), "coins": coins}, indent=2, sort_keys=True))
    return output, metrics, all_trades


def build_parser():
    parser = argparse.ArgumentParser(description="Aliza AI research-only event-driven backtester")
    parser.add_argument("--coins", default="", help="comma-separated symbols; default universe minus UNIVERSE_EXCLUDE")
    parser.add_argument("--start", default=None, help="ISO date/time or epoch; default 2 years ago")
    parser.add_argument("--end", default=None, help="ISO date/time or epoch; default now")
    parser.add_argument("--setups", default=",".join(SETUPS))
    parser.add_argument("--data-dir", default="backtest/data")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--notional", type=float, default=100.0)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    now = datetime.now(timezone.utc)
    end = args.end or now.isoformat()
    start = args.start or (now - timedelta(days=730)).isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    config = {
        "start": start,
        "end": end,
        "data_dir": args.data_dir,
        "output_dir": args.output_dir or f"backtest/results/{stamp}",
        "download": not args.no_download,
        "coins": [coin.strip().upper() for coin in args.coins.split(",") if coin.strip()],
        "setups": [setup.strip().upper() for setup in args.setups.split(",") if setup.strip()],
        "notional": args.notional,
        "fee_per_side": 0.001,
        "slippage_per_side": 0.0005,
        "funding_fallback_per_8h": 0.0001,
        "entry": "next_4h_open",
        "same_bar_tp_sl": "LOSS",
        "time_stop_days": 7,
    }
    output, metrics, trades = run(config)
    print(json.dumps({"output": str(output), "trades": len(trades), "metrics": metrics["all"]}, indent=2))


if __name__ == "__main__":
    main()
