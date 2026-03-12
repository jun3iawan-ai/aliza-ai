"""
ALIZA DASHBOARD API

Endpoint untuk dashboard web: market, quant, predict, signals, portfolio.
"""

from fastapi import APIRouter

from engine.utils.market_cache import get_market_data
from engine.intelligence.quant_market_model import calculate_market_score
from engine.intelligence.predictive_market_ai import calculate_market_predictions
from engine.trading.opportunity_scanner import scan_opportunities
from engine.trading.trade_manager import get_active_trades


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/market")
def dashboard_market():
    """Data market BTC (Market Radar)."""
    return get_market_data("BTC") or {}


@router.get("/quant")
def dashboard_quant():
    """Skor dan bias market (Quant Model)."""
    return calculate_market_score()


@router.get("/predict")
def dashboard_predict():
    """Probabilitas prediksi market."""
    return calculate_market_predictions()


@router.get("/signals")
def dashboard_signals():
    """Daftar opportunity signals."""
    return scan_opportunities()


@router.get("/portfolio")
def dashboard_portfolio():
    """Posisi trading aktif. Setiap item: coin, setup, entry, stop_loss, tp1, tp2."""
    rows = get_active_trades()
    return [
        {
            "coin": r[0],
            "setup": r[1],
            "entry": r[2],
            "stop_loss": r[3],
            "tp1": r[4],
            "tp2": r[5],
        }
        for r in rows
    ]
