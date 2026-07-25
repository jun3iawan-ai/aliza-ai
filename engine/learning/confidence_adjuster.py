"""
ALIZA CONFIDENCE ADJUSTER

Menyesuaikan confidence berdasarkan performa strategy dari trade history.
Rule: winrate > 0.65 → +5; winrate < 0.40 → -10; clamp 0–100.
"""

import logging
import os

DEFAULT_MIN_SAMPLES = 10


def _min_samples():
    """Ambang minimum total_trades per setup sebelum penyesuaian diterapkan.
    Sample sekecil 1-2 outcome per setup terlalu noisy untuk dipakai menggeser
    confidence produksi (lihat STATUS_WINRATE_REPORT.md: N=1 pada 2026-07-25)."""
    try:
        value = int(os.environ.get("LEARNING_MIN_SAMPLES", str(DEFAULT_MIN_SAMPLES)))
        return value if value > 0 else DEFAULT_MIN_SAMPLES
    except (TypeError, ValueError):
        return DEFAULT_MIN_SAMPLES


def adjust_confidence(setup, base_confidence, strategy_stats):
    """
    Sesuaikan confidence berdasarkan strategy_stats (dari get_strategy_stats()).

    strategy_stats: dict setup_name -> { "winrate", "avg_rr", "total_trades" }.
    Rule:
      - if winrate > 0.65 → confidence +5
      - if winrate < 0.40 → confidence -10
    Tidak diterapkan jika total_trades untuk setup tsb < LEARNING_MIN_SAMPLES
    (default 10) -- di bawah itu, confidence dikembalikan apa adanya.
    Clamp: 0–100.

    Return: int confidence (0–100).
    """
    try:
        if strategy_stats is None or not isinstance(strategy_stats, dict):
            return _clamp(base_confidence)
        setup_name = (setup or "").strip() or "UNKNOWN"
        stats = strategy_stats.get(setup_name)
        if not stats or stats.get("total_trades", 0) < _min_samples():
            return _clamp(base_confidence)

        winrate = stats.get("winrate")
        if winrate is None:
            return _clamp(base_confidence)

        try:
            conf = int(base_confidence) if base_confidence is not None else 50
        except (TypeError, ValueError):
            conf = 50

        if winrate > 0.65:
            conf += 5
        elif winrate < 0.40:
            conf -= 10

        return _clamp(conf)
    except Exception as e:
        logging.debug("adjust_confidence: %s", e)
        return _clamp(base_confidence if base_confidence is not None else 50)


def _clamp(confidence):
    """Clamp confidence to 0–100."""
    try:
        c = int(confidence)
        return max(0, min(100, c))
    except (TypeError, ValueError):
        return 50
