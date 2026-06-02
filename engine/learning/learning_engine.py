"""
ALIZA LEARNING ENGINE

Membaca trade history dan menyediakan strategy stats untuk TradingBrain.
Hanya membaca data/trade_history.json; tidak mengubah database.
"""

import logging

try:
    from engine.learning.trade_history_tracker import get_closed_history
except ImportError:
    get_closed_history = None

try:
    from engine.learning.strategy_performance import analyze_strategy_performance
except ImportError:
    analyze_strategy_performance = None


def get_strategy_stats():
    """
    Load trade_history.json, analisis performa per setup, return stats.

    Return: {
        setup_name: {
            "winrate": float,
            "avg_rr": float,
            "total_trades": int,
        }
    }
    """
    if get_closed_history is None or analyze_strategy_performance is None:
        return {}
    try:
        history = get_closed_history()
        return analyze_strategy_performance(history)
    except Exception as e:
        logging.debug("learning_engine get_strategy_stats: %s", e)
        return {}
