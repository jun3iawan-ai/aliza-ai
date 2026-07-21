"""
ALIZA TRADING BRAIN

Menghasilkan trade_setup (setup, entry, sl, tp1, tp2, risk_reward, confidence)
dari market_data. TP dibatasi maksimal ±8% dari entry agar RR realistis.
Confidence dapat disesuaikan oleh learning system (strategy stats dari trade history).
"""

import logging

# Batas maksimum jarak TP dari entry (±8%)
TP_MAX_PCT = 0.08
MIN_STOP_DISTANCE_PCT = 0.005

try:
    from engine.learning.confidence_adjuster import adjust_confidence
except ImportError:
    adjust_confidence = None

try:
    from engine.learning.learning_engine import get_strategy_stats
except ImportError:
    get_strategy_stats = None

try:
    from engine.strategy.strategy_engine import filter_setup
except ImportError:
    filter_setup = None

try:
    from engine.market.market_snapshot_engine import get_market_snapshot
except ImportError:
    get_market_snapshot = None

try:
    from engine.risk_manager import validate_proposed_trade
except ImportError:
    validate_proposed_trade = None


def _cap_tp_long(entry, tp1, tp2):
    """Untuk LONG: TP tidak boleh melebihi entry * 1.08."""
    if entry is None or entry <= 0:
        return tp1, tp2
    max_tp = entry * (1 + TP_MAX_PCT)
    if tp1 is not None and tp1 > max_tp:
        tp1 = max_tp
    if tp2 is not None and tp2 > max_tp:
        tp2 = max_tp
    return tp1, tp2


def _cap_tp_short(entry, tp1, tp2):
    """Untuk SHORT: TP tidak boleh di bawah entry * 0.92."""
    if entry is None or entry <= 0:
        return tp1, tp2
    min_tp = entry * (1 - TP_MAX_PCT)
    if tp1 is not None and tp1 < min_tp:
        tp1 = min_tp
    if tp2 is not None and tp2 < min_tp:
        tp2 = min_tp
    return tp1, tp2


def _risk_reward(entry, sl, tp1):
    """Hitung risk/reward ratio (berdasarkan jarak ke TP1)."""
    if entry is None or sl is None or tp1 is None or entry == 0:
        return None
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    reward = abs(tp1 - entry)
    return round(reward / risk, 2)


def _confidence_from_rr(rr, rsi):
    """Confidence sederhana dari RR dan RSI."""
    base = 50
    if rr is not None:
        if rr >= 3:
            base += 25
        elif rr >= 2:
            base += 15
        elif rr >= 1.5:
            base += 5
    if rsi is not None and 30 <= rsi <= 70:
        base += 10
    return min(85, base)


class TradingBrain:
    def analyze(self, market_data):
        """
        Dari market_data (price, trend, rsi, support, resistance) hasilkan trade_setup.
        TP1/TP2 dibatasi maksimal ±8% dari entry.
        """
        if not market_data:
            return None
        coin = market_data.get("symbol") or market_data.get("coin") or "?"
        reject_reason = None
        price = market_data.get("price")
        trend = market_data.get("trend")
        rsi = market_data.get("rsi")
        support = market_data.get("support")
        resistance = market_data.get("resistance")
        alignment = market_data.get("trend_alignment")
        entry = price
        if entry is None:
            return None

        # Smart Trend Filter: jangan buka trade jika alignment lemah
        if alignment in ("MIXED", "UNKNOWN") or alignment is None:
            reject_reason = "alignment_weak"
            logging.info("TradingBrain %s NO SETUP reason=%s", coin, reject_reason or "no_condition_met")
            return {
                "setup": "NO SETUP",
                "entry": entry if entry is not None else 0,
                "sl": None,
                "tp1": None,
                "tp2": None,
                "risk_reward": None,
                "confidence": 0,
                "risk_quality": "POOR",
            }

        # Batasi arah trade berdasarkan alignment
        allow_long = alignment in ("STRONG_BULLISH", "BULLISH", "PARTIAL")
        allow_short = alignment in ("STRONG_BEARISH", "BEARISH", "PARTIAL")

        setup = "NO SETUP"
        sl = None
        tp1 = None
        tp2 = None

        # RSI ekstrem dulu
        if rsi is not None and rsi < 30:
            setup = "OVERSOLD BOUNCE"
            # SL 1.5% di bawah ENTRY: buffer deterministik, tahan noise wick, tetap di bawah
            # MAX_RISK_PERCENT=2% (risk_manager). Eksperimen 21 Juli (n=3 JTO stop-out di ~1%).
            if entry:
                sl = entry * 0.985
            elif support:
                sl = support * 0.985  # fallback bila entry None
            if resistance:
                tp1 = resistance
                tp2 = resistance * 1.02
        elif rsi is not None and rsi > 70:
            setup = "OVERBOUGHT REJECTION"
            if resistance:
                sl = resistance * 1.01
            if support:
                tp1 = support
                tp2 = support * 0.98
        elif trend == "BULLISH":
            setup = "PULLBACK LONG"
            if support:
                sl = support * 0.99
            if resistance:
                tp1 = resistance
                tp2 = resistance * 1.02
        elif trend == "BEARISH":
            setup = "PULLBACK SHORT"
            if resistance:
                sl = resistance * 1.01
            if support:
                tp1 = support
                tp2 = support * 0.98

        # Filter arah: tolak LONG jika alignment tidak izinkan long, tolak SHORT jika tidak izinkan short
        is_long = "LONG" in setup or setup == "OVERSOLD BOUNCE"
        is_short = "SHORT" in setup or setup == "OVERBOUGHT REJECTION"
        if is_long and not allow_long:
            reject_reason = "direction_blocked"
            setup = "NO SETUP"
            sl = tp1 = tp2 = None
        elif is_short and not allow_short:
            reject_reason = "direction_blocked"
            setup = "NO SETUP"
            sl = tp1 = tp2 = None

        # Validasi SL/TP: nilai <= 0 dianggap invalid
        if sl is not None and sl <= 0:
            reject_reason = "invalid_sl_tp"
            setup = "NO SETUP"
            sl = tp1 = tp2 = None
        if tp1 is not None and tp1 <= 0:
            reject_reason = "invalid_sl_tp"
            setup = "NO SETUP"
            sl = tp1 = tp2 = None

        # RSI filter: LONG tidak boleh jika rsi >= 70, SHORT tidak boleh jika rsi <= 30
        if setup != "NO SETUP" and rsi is not None:
            try:
                rsi_val = float(rsi)
                if is_long and rsi_val >= 70:
                    logging.debug("RSI filter triggered")
                    reject_reason = "rsi_filter"
                    setup = "NO SETUP"
                    sl = tp1 = tp2 = None
                elif is_short and rsi_val <= 30:
                    logging.debug("RSI filter triggered")
                    reject_reason = "rsi_filter"
                    setup = "NO SETUP"
                    sl = tp1 = tp2 = None
            except (TypeError, ValueError):
                pass

        # Resistance / support proximity filter: hanya untuk PULLBACK LONG (momentum/breakout boleh dekat resistance)
        if setup != "NO SETUP" and entry is not None:
            try:
                price_val = float(entry)
                if is_long and setup == "PULLBACK LONG" and resistance is not None:
                    res_val = float(resistance)
                    if res_val > 0 and price_val > res_val * 0.98:
                        logging.debug("Resistance proximity filter applied for pullback setup")
                        reject_reason = "proximity_filter"
                        setup = "NO SETUP"
                        sl = tp1 = tp2 = None
                elif is_short and support is not None:
                    sup_val = float(support)
                    if sup_val > 0 and price_val < sup_val * 1.02:
                        logging.debug("Support proximity filter triggered")
                        reject_reason = "proximity_filter"
                        setup = "NO SETUP"
                        sl = tp1 = tp2 = None
            except (TypeError, ValueError):
                pass

        # Minimum stop distance: hindari RR palsu karena SL terlalu dekat
        if setup != "NO SETUP" and entry is not None and sl is not None:
            try:
                entry_val = float(entry)
                sl_val = float(sl)
                if entry_val > 0:
                    minimum_stop_distance = entry_val * MIN_STOP_DISTANCE_PCT
                    if abs(entry_val - sl_val) < minimum_stop_distance:
                        logging.debug("Minimum stop distance filter triggered")
                        reject_reason = "min_stop_distance"
                        setup = "NO SETUP"
                        sl = tp1 = tp2 = None
            except (TypeError, ValueError):
                pass

        # Strategy switch: filter setup by market_regime (snapshot market_intelligence)
        if setup != "NO SETUP" and filter_setup is not None and get_market_snapshot is not None:
            try:
                snapshot = get_market_snapshot()
                setup = filter_setup(setup, snapshot)
                if setup == "NO SETUP":
                    reject_reason = "regime_filter"
                    sl = tp1 = tp2 = None
            except Exception:
                pass

        if setup == "NO SETUP" or sl is None or tp1 is None:
            logging.info("TradingBrain %s NO SETUP reason=%s", coin, reject_reason or "no_condition_met")
            return {
                "setup": setup,
                "entry": entry,
                "sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "risk_reward": None,
                "confidence": 0,
                "risk_quality": "POOR",
            }

        # Batas maksimum TP: ±8% dari entry
        if "LONG" in setup or setup == "OVERSOLD BOUNCE":
            tp1, tp2 = _cap_tp_long(entry, tp1, tp2)
        else:
            tp1, tp2 = _cap_tp_short(entry, tp1, tp2)

        rr = _risk_reward(entry, sl, tp1)
        if validate_proposed_trade is not None and not validate_proposed_trade(entry, sl, tp1):
            return None
        confidence = _confidence_from_rr(rr, rsi)
        if adjust_confidence is not None and get_strategy_stats is not None:
            try:
                strategy_stats = get_strategy_stats()
                confidence = adjust_confidence(setup, confidence, strategy_stats)
            except Exception:
                pass
        risk_quality = "EXCELLENT" if (rr and rr >= 3) else "GOOD" if (rr and rr >= 2) else "MEDIUM" if (rr and rr >= 1.5) else "POOR"

        return {
            "setup": setup,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "risk_reward": rr,
            "confidence": confidence,
            "risk_quality": risk_quality,
        }
