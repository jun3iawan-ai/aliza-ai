"""
ALIZA MARKET RADAR PRO ANALYZER

Menampilkan kondisi market semua coin dari snapshot dengan label intelligence:
Momentum, Whale Accumulation, Crash Risk, Breakdown Risk, Strong Trend, Neutral.
Data dari Market Snapshot (tanpa panggilan API langsung).
"""

import logging

try:
    from engine.market.market_snapshot_engine import get_market_snapshot, get_snapshot_timestamp_str
except ImportError:
    get_market_snapshot = None
    get_snapshot_timestamp_str = lambda: "—"

try:
    from engine.detectors.crash_detector import detect_crash_risk
except ImportError:
    detect_crash_risk = None

try:
    from engine.detectors.altseason_detector import detect_altseason
except ImportError:
    detect_altseason = None

try:
    from engine.detectors.whale_accumulation_detector import detect_whale_accumulation
except ImportError:
    detect_whale_accumulation = None

try:
    from engine.detectors.liquidation_detector import detect_liquidation_cascade
except ImportError:
    detect_liquidation_cascade = None


def _trend_arrow(trend):
    if trend == "BULLISH":
        return "↑"
    if trend == "BEARISH":
        return "↓"
    if trend == "SIDEWAYS":
        return "→"
    return ""


def generate_radar_pro():
    """
    Bangun list radar per coin dari snapshot dengan label intelligence.
    Return list of dict: {"coin": str, "trend": str, "trend_alignment": str, "label": str, "crash_risk": bool}.
    """
    radar_data = []
    if not get_market_snapshot:
        return radar_data

    snapshot = get_market_snapshot()
    markets = snapshot.get("data") or {}
    if not markets:
        return radar_data

    btc_data = markets.get("BTC")

    for coin, data in markets.items():
        if not data or data.get("error"):
            continue
        trend = data.get("trend") or "SIDEWAYS"
        alignment = data.get("trend_alignment") or "UNKNOWN"
        rsi = data.get("rsi")
        whale = data.get("whale_activity")
        risk = data.get("market_risk_score")
        phase = data.get("market_phase_prediction")

        # Default label dari kondisi existing
        if risk == "HIGH":
            label = "⚠ Crash Risk"
        elif whale in ["HIGH", "EXTREME"]:
            label = "🐋 Whale Activity"
        elif trend == "BULLISH" and rsi is not None and rsi > 60:
            label = "🚀 Momentum"
        elif trend == "BEARISH" and rsi is not None and rsi < 40:
            label = "⚡ Breakdown Risk"
        elif trend == "BULLISH":
            label = "📈 Strong Trend"
        else:
            label = "• Neutral"

        crash_risk_flag = False
        if detect_crash_risk is not None:
            try:
                crash = detect_crash_risk(data)
                crash_risk_flag = bool(crash.get("crash_risk"))
                logging.debug("Crash detector %s risk=%s", coin, crash_risk_flag)
                if crash_risk_flag:
                    label = "⚠ Crash Risk"
            except Exception as e:
                logging.debug("Crash detector error for %s: %s", coin, e)

        # Altseason detector: hanya untuk coin selain BTC, butuh btc_data
        if coin != "BTC" and btc_data and detect_altseason is not None:
            try:
                altseason = detect_altseason(coin, data, btc_data)
                if altseason.get("altseason_signal"):
                    label = "🚀 Altseason Signal"
            except Exception as e:
                logging.debug("Altseason detector error for %s: %s", coin, e)

        # Whale accumulation detector
        if detect_whale_accumulation is not None:
            try:
                whale = detect_whale_accumulation(coin, data)
                if whale.get("whale_accumulation"):
                    label = "🐋 Whale Accumulation"
            except Exception as e:
                logging.debug("Whale accumulation detector error for %s: %s", coin, e)

        # Liquidation cascade detector
        if detect_liquidation_cascade is not None:
            try:
                liq = detect_liquidation_cascade(coin, data)
                if liq.get("liquidation_signal"):
                    liq_type = liq.get("type")
                    if liq_type == "LONG_LIQUIDATION":
                        label = "⚡ Long Liquidation"
                    elif liq_type == "SHORT_SQUEEZE":
                        label = "⚡ Short Squeeze"
            except Exception as e:
                logging.debug("Liquidation detector error for %s: %s", coin, e)

        radar_data.append(
            {
                "coin": coin,
                "trend": trend,
                "trend_alignment": alignment,
                "label": label,
                "crash_risk": crash_risk_flag,
            }
        )

    return radar_data


def format_radar_pro_report(radar_data):
    """
    Format laporan Radar Pro untuk Telegram.
    Satu baris per coin: COIN  TREND arrow  label. Lalu timestamp snapshot.
    """
    if not radar_data:
        return "📡 ALIZA MARKET RADAR PRO\n\nTidak ada data market.\n\n🕒 Market Snapshot : —"

    lines = ["📡 ALIZA MARKET RADAR PRO\n"]
    for item in radar_data:
        coin = item.get("coin", "")
        trend = item.get("trend", "SIDEWAYS")
        label = item.get("label", "• Neutral")
        arrow = _trend_arrow(trend)
        trend_display = f"{trend} {arrow}".strip()
        lines.append(f"{coin:4}  {trend_display:12}  {label}")

    ts = get_snapshot_timestamp_str()
    lines.append(f"\n🕒 Market Snapshot : {ts}")
    return "\n".join(lines)
