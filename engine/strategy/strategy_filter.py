"""
ALIZA STRATEGY FILTER

Memfilter setup berdasarkan regime: hanya setup yang ada di STRATEGY_MAP[regime] yang diizinkan.
Regime tidak dikenal → allow setup (fallback).
"""

import logging

from engine.strategy.strategy_regime_map import STRATEGY_MAP


def is_strategy_allowed(setup, regime):
    """
    Jika setup ada dalam STRATEGY_MAP[regime] → True.
    Jika tidak → False.
    Jika regime tidak ditemukan → True (allow setup).
    """
    if not regime or not isinstance(regime, str):
        logging.debug("Strategy filter regime=%s setup=%s allowed=True (no regime)", regime, setup)
        return True
    regime = regime.strip().upper()
    if regime not in STRATEGY_MAP:
        logging.debug("Strategy filter regime=%s setup=%s allowed=True (regime unknown)", regime, setup)
        return True
    allowed_list = STRATEGY_MAP[regime]
    if not setup or not isinstance(setup, str):
        logging.debug("Strategy filter regime=%s setup=%s allowed=True (no setup)", regime, setup)
        return True
    setup = setup.strip()
    allowed = setup in allowed_list
    logging.debug("Strategy filter regime=%s setup=%s allowed=%s", regime, setup, allowed)
    return allowed
