"""
ALIZA DASHBOARD API

Endpoint untuk dashboard web: market, quant, predict, signals, portfolio.
Import dilakukan di dalam handler agar server tetap start jika modul opsional belum ada.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.security import AuthenticatedUser, get_current_user
from engine.utils.market_cache import get_market_data
from engine.trading.opportunity_scanner import scan_opportunities
from engine.trading.trade_manager import get_active_trades

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/market")
def dashboard_market(
    _current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Data market BTC (Market Radar)."""
    return get_market_data("BTC") or {}


@router.get("/quant")
def dashboard_quant(
    _current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Skor dan bias market (Quant Model)."""
    try:
        from engine.intelligence.quant_market_model import calculate_market_score

        return calculate_market_score()
    except ImportError:
        return {"detail": "quant_market_model tidak tersedia di deployment ini", "status": "unavailable"}


@router.get("/predict")
def dashboard_predict(
    _current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Probabilitas prediksi market."""
    try:
        from engine.intelligence.predictive_market_ai import calculate_market_predictions

        return calculate_market_predictions()
    except ImportError:
        return {"detail": "predictive_market_ai tidak tersedia di deployment ini", "status": "unavailable"}


@router.get("/signals")
def dashboard_signals(
    _current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Daftar opportunity signals."""
    return scan_opportunities()


@router.get("/portfolio")
def dashboard_portfolio(
    _current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    """Posisi trading aktif (format mengikuti get_active_trades)."""
    rows = get_active_trades()
    out = []
    for r in rows:
        if len(r) >= 10:
            out.append({
                "coin": r[0],
                "direction": r[1],
                "setup": r[2],
                "entry": r[3],
                "stop_loss": r[4],
                "tp1": r[5],
                "tp2": r[6],
                "quantity": r[7],
                "position_value_usdt": r[8],
                "risk_usdt": r[9],
            })
        elif len(r) >= 7:
            out.append({
                "coin": r[0],
                "direction": r[1],
                "setup": r[2],
                "entry": r[3],
                "stop_loss": r[4],
                "tp1": r[5],
                "tp2": r[6],
            })
        elif len(r) >= 6:
            out.append({
                "coin": r[0],
                "setup": r[1],
                "entry": r[2],
                "stop_loss": r[3],
                "tp1": r[4],
                "tp2": r[5],
            })
    return out
