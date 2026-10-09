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
        # Label & detector memakai tren 4H yang sama dengan panah di Radar
        # (MA10/MA30, field trend_4h) supaya panah dan label tidak bertentangan.
        # Fallback ke field "trend" lama bila trend_4h tidak tersedia.
        trend_4h = str(data.get("trend_4h") or "").upper()
        label_trend = trend_4h if trend_4h in ("BULLISH", "BEARISH", "SIDEWAYS") else trend
        ctx = dict(data, trend=label_trend)
        rsi = data.get("rsi")
        whale = data.get("whale_activity")
        phase = data.get("market_phase_prediction")

        # Default label dari kondisi existing.
        # "market_risk_score" adalah nilai GLOBAL (sama untuk semua coin dalam
        # satu siklus snapshot, lihat market_radar.py + market_analyzer.py),
        # jadi tidak dipakai langsung sebagai default di sini -- itu dulu
        # membuat SEMUA coin ter-label "Crash Risk" begitu risk global HIGH,
        # walau coin ybs sedang bullish. Label "Crash Risk" sekarang hanya
        # dipasang oleh detect_crash_risk() di bawah, yang mensyaratkan risk
        # HIGH *dan* kondisi teknikal coin ybs (bearish/overbought/liquidation).
        if whale in ["HIGH", "EXTREME"]:
            label = "🐋 Whale Activity"
        elif label_trend == "BULLISH" and rsi is not None and rsi > 60:
            label = "🚀 Momentum"
        elif label_trend == "BEARISH" and rsi is not None and rsi < 40:
            label = "⚡ Breakdown Risk"
        elif label_trend == "BULLISH":
            label = "📈 Uptrend"
        elif label_trend == "BEARISH":
            label = "📉 Downtrend"
        else:
            label = "• Neutral"

        crash_risk_flag = False
        if detect_crash_risk is not None:
            try:
                crash = detect_crash_risk(ctx)
                crash_risk_flag = bool(crash.get("crash_risk"))
                logging.debug("Crash detector %s risk=%s", coin, crash_risk_flag)
                if crash_risk_flag:
                    label = "⚠ Crash Risk"
            except Exception as e:
                logging.debug("Crash detector error for %s: %s", coin, e)

        # Altseason detector: hanya untuk coin selain BTC, butuh btc_data
        if coin != "BTC" and btc_data and detect_altseason is not None:
            try:
                altseason = detect_altseason(coin, ctx, btc_data)
                if altseason.get("altseason_signal"):
                    label = "🚀 Altseason Signal"
            except Exception as e:
                logging.debug("Altseason detector error for %s: %s", coin, e)

        # Whale accumulation detector
        if detect_whale_accumulation is not None:
            try:
                whale = detect_whale_accumulation(coin, ctx)
                if whale.get("whale_accumulation"):
                    label = "🐋 Whale Accumulation"
            except Exception as e:
                logging.debug("Whale accumulation detector error for %s: %s", coin, e)

        # Liquidation cascade detector
        if detect_liquidation_cascade is not None:
            try:
                liq = detect_liquidation_cascade(coin, ctx)
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
                "trend_4h": data.get("trend_4h") or "UNKNOWN",
                "trend_1d": data.get("trend_1d") or "UNKNOWN",
                "rsi": rsi,
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


_DIR_ARROW = {"BULLISH": "↑", "BEARISH": "↓", "SIDEWAYS": "→"}


def format_radar_report(radar_data):
    """Radar gabungan (pengganti Radar Market + Radar Pro, 9 Okt 2026).

    Satu baris per coin: arah 4H (MA10/MA30), arah 1D (MA20/MA50), RSI 4H,
    dan label kondisi. ⭐ = 4H & 1D searah (tren kuat)."""
    if not radar_data:
        return "📡 ALIZA RADAR\n\nTidak ada data market.\n\n🕒 Snapshot: —"
    lines = ["📡 ALIZA RADAR", "Kolom: 4H · 1D · RSI 4H · kondisi", ""]
    for item in radar_data:
        coin = str(item.get("coin", ""))
        t4 = str(item.get("trend_4h") or "UNKNOWN").upper()
        t1 = str(item.get("trend_1d") or "UNKNOWN").upper()
        a4 = _DIR_ARROW.get(t4, "?")
        a1 = _DIR_ARROW.get(t1, "?")
        rsi = item.get("rsi")
        try:
            rsi_s = f"{float(rsi):.0f}"
        except (TypeError, ValueError):
            rsi_s = "—"
        label = str(item.get("label") or "")
        if label.strip() in ("• Neutral", "Neutral", ""):
            label = "—"
        star = " ⭐" if t4 == t1 and t4 in ("BULLISH", "BEARISH") else ""
        lines.append(f"{coin:<6} 4H {a4}  1D {a1}  RSI {rsi_s:>2}  {label}{star}")
    lines.append("")
    lines.append("↑ naik · ↓ turun · → sideways · ? data kurang")
    lines.append("⭐ 4H & 1D searah = tren kuat")
    lines.append(f"🕒 Snapshot: {get_snapshot_timestamp_str()}")
    return "\n".join(lines)
