"""
ALIZA PORTFOLIO AI ENGINE

Mengevaluasi trade sebelum eksekusi: drawdown, risk, position size.
Hanya menambah informasi (position_size); tidak mengubah data contract.
"""

import os
import logging

try:
    from engine.portfolio.drawdown_protector import check_drawdown
except ImportError:
    check_drawdown = None

try:
    from engine.portfolio.risk_manager import evaluate_trade as risk_evaluate_trade
except ImportError:
    risk_evaluate_trade = None

try:
    from engine.portfolio.position_sizer_legacy import calculate_position_size
except ImportError:
    calculate_position_size = None

DEFAULT_BALANCE = float(os.environ.get("ALIZA_PORTFOLIO_BALANCE", "10000"))
DEFAULT_RISK_PCT = float(os.environ.get("ALIZA_RISK_PCT", "0.01"))


def evaluate_trade(setup):
    """
    Evaluasi trade sebelum eksekusi: cek drawdown, risk manager, hitung position size.

    setup: dict dengan minimal entry, sl; optional balance, risk_pct.
    Return: {"allowed": bool, "position_size": float, "reason": str}
    """
    result = {"allowed": False, "position_size": 0.0, "reason": ""}
    try:
        if not setup or not isinstance(setup, dict):
            result["reason"] = "Setup tidak valid"
            return result

        entry = setup.get("entry")
        sl = setup.get("sl")
        if entry is None or sl is None:
            result["reason"] = "Entry atau SL tidak ada"
            return result

        if check_drawdown is not None:
            dd = check_drawdown()
            if not dd.get("trading_allowed", True):
                result["reason"] = "Trading ditangguhkan: loss streak ≥ 3"
                return result

        if risk_evaluate_trade is not None:
            risk_result = risk_evaluate_trade(entry, sl)
            if not risk_result.get("allowed", True):
                result["reason"] = risk_result.get("reason", "Ditolak risk manager")
                return result

        balance = setup.get("balance")
        if balance is None:
            balance = DEFAULT_BALANCE
        risk_pct = setup.get("risk_pct")
        if risk_pct is None:
            risk_pct = DEFAULT_RISK_PCT

        position_size = 0.0
        if calculate_position_size is not None:
            position_size = calculate_position_size(balance, risk_pct, entry, sl)

        result["allowed"] = True
        result["position_size"] = position_size
        result["reason"] = "OK"
        return result
    except Exception as e:
        logging.debug("portfolio_ai_engine evaluate_trade: %s", e)
        result["reason"] = "Error evaluasi"
        return result
