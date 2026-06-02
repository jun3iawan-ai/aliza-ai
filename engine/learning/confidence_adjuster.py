"""
ALIZA CONFIDENCE ADJUSTER

Menyesuaikan confidence berdasarkan performa strategy dari trade history.
Rule: winrate > 0.65 → +5; winrate < 0.40 → -10; clamp 0–100.
"""

import logging


def adjust_confidence(setup, base_confidence, strategy_stats):
    """
    Sesuaikan confidence berdasarkan strategy_stats (dari get_strategy_stats()).

    strategy_stats: dict setup_name -> { "winrate", "avg_rr", "total_trades" }.
    Rule:
      - if winrate > 0.65 → confidence +5
      - if winrate < 0.40 → confidence -10
    Clamp: 0–100.

    Return: int confidence (0–100).
    """
    try:
        if strategy_stats is None or not isinstance(strategy_stats, dict):
            return _clamp(base_confidence)
        setup_name = (setup or "").strip() or "UNKNOWN"
        stats = strategy_stats.get(setup_name)
        if not stats or stats.get("total_trades", 0) < 1:
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
