"""
ALIZA SYSTEM MONITOR

Lightweight internal monitoring to detect system problems automatically.
Reads snapshot data only; does not modify any engine state.
"""

import logging
from datetime import datetime

from engine.market.market_snapshot_engine import get_market_snapshot

SNAPSHOT_MIN_COINS = 5
SNAPSHOT_MAX_AGE_SEC = 300


def check_system_health():
    """
    Check snapshot health, timestamp freshness, and presence of BTC.
    Returns a list of alert strings; empty list if system is healthy.
    """
    alerts = []

    try:
        snapshot = get_market_snapshot()
    except Exception as e:
        logging.error("ALIZA ERROR: failed to get market snapshot: %s", e)
        alerts.append("🚨 ALIZA ERROR: Failed to read snapshot")
        return alerts

    data = snapshot.get("data") or {}
    ts = snapshot.get("timestamp")

    # 1. Snapshot health: empty or too few coins
    num_coins = len(data)
    if num_coins == 0 or num_coins < SNAPSHOT_MIN_COINS:
        logging.warning("ALIZA WARNING: snapshot contains very few coins (count=%d)", num_coins)
        alerts.append("⚠ ALIZA WARNING: Snapshot data very small")

    # 2. Snapshot timestamp: stale if older than 300 seconds
    if ts is not None:
        try:
            now = datetime.utcnow()
            delta = now - ts
            age_sec = delta.total_seconds()
            if age_sec > SNAPSHOT_MAX_AGE_SEC:
                logging.warning("ALIZA WARNING: snapshot is stale (age=%.0fs)", age_sec)
                alerts.append("⚠ ALIZA WARNING: Market snapshot not updating")
        except (TypeError, ValueError, AttributeError) as e:
            logging.warning("ALIZA WARNING: could not compute snapshot age: %s", e)
            alerts.append("⚠ ALIZA WARNING: Market snapshot not updating")
    else:
        logging.warning("ALIZA WARNING: snapshot is stale (no timestamp)")
        alerts.append("⚠ ALIZA WARNING: Market snapshot not updating")

    # 3. BTC must exist in snapshot
    if "BTC" not in data or not data.get("BTC"):
        logging.error("ALIZA ERROR: BTC missing from snapshot")
        alerts.append("🚨 ALIZA ERROR: BTC market data missing")

    return alerts
