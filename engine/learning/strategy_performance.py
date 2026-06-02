"""
ALIZA STRATEGY PERFORMANCE ANALYZER

Menganalisis performa per setup dari trade history (closed trades).
"""

import logging


def analyze_strategy_performance(history):
    """
    Hitung winrate, average_rr, total_trades per setup.

    history: list of closed trade dicts dengan keys coin, setup, entry, exit, result, rr, confidence, timestamp.
    Return: {
        setup_name: {
            "winrate": float,
            "avg_rr": float,
            "total_trades": int,
        }
    }
    """
    result = {}
    try:
        if not history or not isinstance(history, list):
            return result

        by_setup = {}
        for t in history:
            if not isinstance(t, dict):
                continue
            setup = (t.get("setup") or "").strip() or "UNKNOWN"
            if setup not in by_setup:
                by_setup[setup] = {"wins": 0, "total": 0, "rr_sum": 0.0}
            rec = by_setup[setup]
            rec["total"] += 1
            if str(t.get("result", "")).upper() == "WIN":
                rec["wins"] += 1
            rr = t.get("rr")
            if rr is not None:
                try:
                    rec["rr_sum"] += float(rr)
                except (TypeError, ValueError):
                    pass

        for setup_name, agg in by_setup.items():
            total = agg["total"]
            wins = agg["wins"]
            winrate = (wins / total) if total > 0 else 0.0
            avg_rr = (agg["rr_sum"] / total) if total > 0 else 0.0
            result[setup_name] = {
                "winrate": round(winrate, 4),
                "avg_rr": round(avg_rr, 2),
                "total_trades": total,
            }
        return result
    except Exception as e:
        logging.debug("analyze_strategy_performance: %s", e)
        return result
