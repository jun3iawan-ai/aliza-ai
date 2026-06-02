"""
ALIZA STRATEGY ENGINE

Memfilter setup berdasarkan market_regime dari snapshot (market_intelligence).
Hanya memfilter setelah TradingBrain; tidak mengubah pipeline.
"""

import logging

try:
    from engine.strategy.strategy_filter import is_strategy_allowed
except ImportError:
    is_strategy_allowed = None


def filter_setup(setup, snapshot):
    """
    Ambil regime dari snapshot["market_intelligence"]["market_regime"],
    cek is_strategy_allowed(setup, regime).
    Jika False → return "NO SETUP".
    Jika True → return setup.
    """
    if not setup or setup == "NO SETUP":
        return setup
    if is_strategy_allowed is None:
        return setup
    try:
        if not snapshot or not isinstance(snapshot, dict):
            return setup
        mi = snapshot.get("market_intelligence")
        if not mi or not isinstance(mi, dict):
            return setup
        regime = mi.get("market_regime")
        if not is_strategy_allowed(setup, regime):
            return "NO SETUP"
        return setup
    except Exception as e:
        logging.debug("strategy_engine filter_setup: %s", e)
        return setup
