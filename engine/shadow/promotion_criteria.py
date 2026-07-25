"""Read-only evaluator for the shadow_e3 -> production promotion criteria
defined in FASE4_REPORT.md ("Kriteria promosi"):

    expectancy >+0.3%/trade, profit factor >1.2, bootstrap CI95 lower bound
    >-0.1%, no single coin >50% of total positive PnL, and >=60 closed
    outcomes OR >=6 weeks of observation (whichever is longer).

This module ONLY reads engine.trading.signal_tracker (via signal_tracker.DB_PATH,
so it respects the same DB the rest of the live pipeline/tests use) and NEVER
writes to signal_tracking, .env, or any SHADOW_E3_* flag. It does not decide
anything -- it reports PASS/FAIL per criterion with the real numbers so a human
can decide. See SHADOW_PROMOTION_CHECKLIST_REPORT.md for the methodology
decisions (especially the bootstrap CI and coin-concentration definitions,
neither of which had a prior live-data implementation to match).

The bootstrap CI here reimplements backtest/robustness.py::_bootstrap()'s exact
percentile-bootstrap formula (same 10000 iterations / seed 20260721 convention)
rather than importing it, so this production-facing module does not depend on
the offline `backtest/` package (which REPO_CLEANUP_REPORT.md flags "JANGAN
SENTUH" and pulls in heavier data-loading/simulation dependencies not needed
here).
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timezone
from typing import Any

from engine.trading import signal_tracker

EXPECTANCY_THRESHOLD_PCT = 0.3
PROFIT_FACTOR_THRESHOLD = 1.2
CI_LOWER_BOUND_THRESHOLD_PCT = -0.1
COIN_PROFIT_SHARE_THRESHOLD = 0.50
MIN_OUTCOMES = 60
MIN_WEEKS = 6.0

# Below this many closed outcomes, a percentile bootstrap is not meaningful
# (e.g. N=1 always yields a zero-width CI, which is misleading, not precise).
# Reused as the same convention as LEARNING_MIN_SAMPLES (engine/learning/
# confidence_adjuster.py, default 10) for "is there enough data to say
# anything statistically" -- documented in Langkah 0 of the report rather
# than invented as a new unrelated number.
BOOTSTRAP_MIN_N = 10
BOOTSTRAP_ITERATIONS = 10000
BOOTSTRAP_SEED = 20260721


def _closed_rows(source: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(signal_tracker.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT coin, pnl_pct, signal_time
        FROM signal_tracking
        WHERE source = ? AND status IN ('WIN', 'LOSS') AND pnl_pct IS NOT NULL
        """,
        (source,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _first_signal_time(source: str) -> str | None:
    conn = sqlite3.connect(signal_tracker.DB_PATH)
    row = conn.execute(
        "SELECT MIN(signal_time) FROM signal_tracking WHERE source = ?", (source,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def _expectancy_pct(pnls: list[float]) -> float:
    return sum(pnls) / len(pnls) if pnls else 0.0


def _profit_factor(pnls: list[float]) -> float:
    """Mirrors backtest/metrics.py::aggregate_metrics() -- gross win / gross
    loss computed from realized pnl_pct, NOT engine.analytics.performance_
    analyzer.analyze_performance() (which computes profit_factor from the
    *planned* `rr` field at signal time, a different and unsuitable basis for
    a promotion decision that must be based on realized outcomes)."""
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    if gross_loss:
        return gross_win / gross_loss
    return gross_win if gross_win > 0 else 0.0


def _bootstrap_ci95_lower(pnls: list[float]) -> float | None:
    if len(pnls) < BOOTSTRAP_MIN_N:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    estimates = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        estimates.append(sum(rng.choice(pnls) for _ in pnls) / len(pnls))
    estimates.sort()
    return estimates[int(BOOTSTRAP_ITERATIONS * 0.025)]


def _coin_profit_shares(rows: list[dict[str, Any]]) -> tuple[dict[str, float], str | None, float]:
    """Share of TOTAL POSITIVE pnl_pct contributed by each coin -- how
    concentrated the strategy's winning trades are in a single coin. No prior
    codified formula exists for "coin_profit_share" in this codebase: the term
    only appears as an undocumented threshold label in
    backtest/run_experiments.py's manifest ("coin_profit_share_lt": 0.50,
    written for human review, never computed by code). This definition
    mirrors the intent of the "Exclude-WLD" leave-one-out sensitivity check in
    ROBUSTNESS_RESULTS.md (does the result depend on one coin's contribution)
    but as a direct share formula instead of a leave-one-out re-run."""
    by_coin: dict[str, float] = {}
    for row in rows:
        pnl = float(row["pnl_pct"])
        if pnl > 0:
            by_coin[row["coin"]] = by_coin.get(row["coin"], 0.0) + pnl
    total_positive = sum(by_coin.values())
    if total_positive <= 0:
        return {}, None, 0.0
    shares = {coin: value / total_positive for coin, value in by_coin.items()}
    top_coin = max(shares, key=shares.get)
    return shares, top_coin, shares[top_coin]


def _weeks_since(first_signal_time: str | None) -> float:
    if not first_signal_time:
        return 0.0
    try:
        first = datetime.fromisoformat(str(first_signal_time))
    except ValueError:
        return 0.0
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta_days = (now - first.astimezone(timezone.utc)).total_seconds() / 86400.0
    return max(0.0, delta_days / 7.0)


def evaluate_promotion_criteria(source: str = "shadow_e3", now: datetime | None = None) -> dict[str, Any]:
    """Read-only. Never mutates signal_tracking, .env, or any SHADOW_E3_* flag."""
    rows = _closed_rows(source)
    pnls = [float(row["pnl_pct"]) for row in rows]
    n_closed = len(pnls)

    expectancy = _expectancy_pct(pnls)
    profit_factor = _profit_factor(pnls)
    ci_lower = _bootstrap_ci95_lower(pnls)
    shares, top_coin, top_share = _coin_profit_shares(rows)

    first_signal_time = _first_signal_time(source)
    weeks = _weeks_since(first_signal_time)
    observation_met = n_closed >= MIN_OUTCOMES or weeks >= MIN_WEEKS

    checks = {
        "expectancy": {
            "value": expectancy,
            "threshold": EXPECTANCY_THRESHOLD_PCT,
            "passed": n_closed > 0 and expectancy > EXPECTANCY_THRESHOLD_PCT,
        },
        "profit_factor": {
            "value": profit_factor,
            "threshold": PROFIT_FACTOR_THRESHOLD,
            "passed": n_closed > 0 and profit_factor > PROFIT_FACTOR_THRESHOLD,
        },
        "ci_lower_bound": {
            "value": ci_lower,
            "threshold": CI_LOWER_BOUND_THRESHOLD_PCT,
            "computable": ci_lower is not None,
            "passed": ci_lower is not None and ci_lower > CI_LOWER_BOUND_THRESHOLD_PCT,
        },
        "coin_concentration": {
            "top_coin": top_coin,
            "top_share": top_share,
            "threshold": COIN_PROFIT_SHARE_THRESHOLD,
            "passed": n_closed > 0 and top_share <= COIN_PROFIT_SHARE_THRESHOLD,
        },
        "observation": {
            "n_closed": n_closed,
            "weeks": round(weeks, 2),
            "min_outcomes": MIN_OUTCOMES,
            "min_weeks": MIN_WEEKS,
            "first_signal_time": first_signal_time,
            "passed": observation_met,
        },
    }

    return {
        "source": source,
        "n_closed": n_closed,
        "checks": checks,
        "all_passed": all(check["passed"] for check in checks.values()),
    }


def _fmt_pct(value: float | None) -> str:
    return f"{value:+.4f}%" if value is not None else "—"


def format_promotion_check_message(result: dict[str, Any]) -> str:
    checks = result["checks"]
    lines = [
        "🔍 SHADOW E3 → PRODUKSI: CEK KRITERIA PROMOSI",
        "(read-only, TIDAK mengubah SHADOW_E3_ENABLED/SHADOW_E3_DISPATCH apa pun)",
        "",
        f"N closed outcome: {result['n_closed']}",
        "",
    ]

    exp = checks["expectancy"]
    mark = "✅" if exp["passed"] else "❌"
    lines.append(
        f"{mark} Expectancy: {_fmt_pct(exp['value'])} (ambang >+{exp['threshold']:.1f}%)"
    )

    pf = checks["profit_factor"]
    mark = "✅" if pf["passed"] else "❌"
    lines.append(
        f"{mark} Profit Factor: {pf['value']:.2f} (ambang >{pf['threshold']:.1f})"
    )

    ci = checks["ci_lower_bound"]
    mark = "✅" if ci["passed"] else "❌"
    if ci["computable"]:
        lines.append(
            f"{mark} Batas bawah bootstrap CI95: {_fmt_pct(ci['value'])} (ambang >{ci['threshold']:.1f}%)"
        )
    else:
        lines.append(
            f"{mark} Batas bawah bootstrap CI95: belum bisa dihitung "
            f"(N={result['n_closed']} < {BOOTSTRAP_MIN_N} closed outcome minimum untuk bootstrap bermakna)"
        )

    conc = checks["coin_concentration"]
    mark = "✅" if conc["passed"] else "❌"
    if conc["top_coin"] is not None:
        lines.append(
            f"{mark} Konsentrasi profit: {conc['top_coin']} = {conc['top_share'] * 100:.1f}% "
            f"dari total profit (ambang <={conc['threshold'] * 100:.0f}%)"
        )
    else:
        lines.append(f"{mark} Konsentrasi profit: belum ada trade profit untuk dihitung")

    obs = checks["observation"]
    mark = "✅" if obs["passed"] else "❌"
    lines.append(
        f"{mark} Observasi: N={obs['n_closed']} closed (ambang ≥{obs['min_outcomes']}) ATAU "
        f"{obs['weeks']:.1f} minggu sejak sinyal pertama (ambang ≥{obs['min_weeks']:.0f} minggu)"
    )

    lines.append("")
    if result["all_passed"]:
        lines.append("✅ MEMENUHI SEMUA KRITERIA — siap dipertimbangkan untuk promosi.")
    else:
        failed = [name for name, check in checks.items() if not check["passed"]]
        label_map = {
            "expectancy": "expectancy",
            "profit_factor": "profit factor",
            "ci_lower_bound": "batas bawah bootstrap CI",
            "coin_concentration": "konsentrasi profit per coin",
            "observation": "observasi (N/minggu)",
        }
        failed_labels = ", ".join(label_map.get(name, name) for name in failed)
        lines.append(f"❌ BELUM MEMENUHI — kriteria yang belum: {failed_labels}.")
    lines.append("")
    lines.append("Keputusan promosi tetap manual — command ini tidak mengubah apa pun.")

    return "\n".join(lines)
