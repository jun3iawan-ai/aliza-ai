"""
ALIZA PERFORMANCE ANALYTICS

Menghitung performa trading dari trade history (closed trades).
Hanya membaca data; tidak mengubah pipeline atau trade_history.
"""

import logging


def analyze_performance(trades):
    """
    Hitung total_trades, wins, losses, winrate, avg_rr, profit_factor.

    trades: list of closed trade dicts (coin, setup, entry, exit, result, rr, confidence, timestamp).
    profit_factor = sum(rr positif) / abs(sum(rr negatif)); jika tidak ada rr negatif, return 0.

    Return: {
        "total_trades": int,
        "wins": int,
        "losses": int,
        "winrate": float,
        "avg_rr": float,
        "profit_factor": float,
    }
    """
    result = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
        "avg_rr": 0.0,
        "profit_factor": 0.0,
    }
    try:
        if not trades or not isinstance(trades, list):
            return result

        total = len(trades)
        wins = 0
        losses = 0
        rr_sum = 0.0
        rr_positive_sum = 0.0
        rr_negative_sum = 0.0

        for t in trades:
            if not isinstance(t, dict):
                continue
            res = str(t.get("result", "")).upper()
            if res == "WIN":
                wins += 1
            elif res == "LOSS":
                losses += 1
            rr = t.get("rr")
            if rr is not None:
                try:
                    r = float(rr)
                    rr_sum += r
                    if r > 0:
                        rr_positive_sum += r
                    elif r < 0:
                        rr_negative_sum += r
                except (TypeError, ValueError):
                    pass

        result["total_trades"] = total
        result["wins"] = wins
        result["losses"] = losses
        result["winrate"] = round((wins / total), 4) if total > 0 else 0.0
        result["avg_rr"] = round(rr_sum / total, 2) if total > 0 else 0.0
        if rr_negative_sum != 0:
            result["profit_factor"] = round(rr_positive_sum / abs(rr_negative_sum), 2)
        else:
            result["profit_factor"] = round(rr_positive_sum, 2) if rr_positive_sum > 0 else 0.0
        return result
    except Exception as e:
        logging.debug("performance_analyzer: %s", e)
        return result


def analyze_strategy_stats(trades):
    """
    Per-setup stats: trades count dan winrate.

    Return: {
        "strategy_name": {"trades": int, "winrate": float},
        ...
    }
    """
    result = {}
    try:
        if not trades or not isinstance(trades, list):
            return result

        by_setup = {}
        for t in trades:
            if not isinstance(t, dict):
                continue
            setup = (t.get("setup") or "").strip() or "UNKNOWN"
            if setup not in by_setup:
                by_setup[setup] = {"wins": 0, "total": 0}
            by_setup[setup]["total"] += 1
            if str(t.get("result", "")).upper() == "WIN":
                by_setup[setup]["wins"] += 1

        for name, agg in by_setup.items():
            total = agg["total"]
            wins = agg["wins"]
            result[name] = {
                "trades": total,
                "winrate": round((wins / total), 4) if total > 0 else 0.0,
            }
        return result
    except Exception as e:
        logging.debug("analyze_strategy_stats: %s", e)
        return result
