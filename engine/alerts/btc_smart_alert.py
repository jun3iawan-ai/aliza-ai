"""
BTC SMART ALERT SYSTEM

Memberikan sinyal khusus BTC berdasarkan snapshot (read-only).
Tidak membuka posisi dan tidak mengubah trade_setup / TradingBrain.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

MAX_REASONS = 5
TRADING_MODE = os.getenv("TRADING_MODE", "INTRADAY").strip().upper()


def compute_layered_btc_score(
    trend: str,
    rsi: float | None,
    price: float | None,
    support: float | None,
    resistance: float | None,
    structure: str,
    zone: str,
    candles: List[Dict[str, float]],
    volume_spike: bool,
    healthy_pullback: bool,
    whale: str,
    market_regime: str,
    last_candle: Dict[str, float] | None,
) -> Dict[str, Any]:
    """
    3-layer score: exactly one BASE, independent CONFIRMATION, CONTEXT (can be negative).
    final_score = base_score + confirmation_score + context_score
    """
    base_signal: str | None = None
    base_score = 0

    breakout_detected = (
        price is not None
        and resistance is not None
        and resistance > 0
        and price > resistance * 1.01
    )
    market_regime_detected = "UNKNOWN"

    volume_valid = volume_spike
    strong_close = False
    low_wick = False
    if last_candle:
        o = last_candle.get("open")
        cl = last_candle.get("close")
        high = last_candle.get("high")
        low = last_candle.get("low")
        if o is not None and cl is not None and o > 0:
            strong_close = cl > o and (abs(cl - o) / o) >= 0.005
        if o is not None and cl is not None and high is not None and low is not None and high > low:
            body_top = max(o, cl)
            lower_wick = min(o, cl) - low
            total_range = high - low
            low_wick = total_range > 0 and (lower_wick / total_range) <= 0.35

    breakout_quality = 0
    if volume_valid:
        breakout_quality += 1
    if strong_close:
        breakout_quality += 1
    if low_wick:
        breakout_quality += 1

    breakout_valid = False
    if breakout_detected:
        if volume_valid and strong_close and breakout_quality >= 2:
            breakout_valid = True

    strong_trend = trend == "BULLISH" and structure == "bullish_structure"
    volatility_high = False
    volatility_normal = True
    if candles:
        ranges = []
        for c in candles[-5:]:
            h = c.get("high")
            l = c.get("low")
            cl = c.get("close")
            if h is not None and l is not None and cl is not None and cl > 0 and h >= l:
                ranges.append((h - l) / cl)
        if ranges:
            avg_range = sum(ranges) / len(ranges)
            volatility_high = avg_range >= 0.03
            volatility_normal = not volatility_high

    if strong_trend and volatility_normal:
        market_regime_detected = "TRENDING"
    elif volatility_high:
        market_regime_detected = "VOLATILE"
    else:
        market_regime_detected = "SIDEWAYS"
    pullback_valid = healthy_pullback
    reversal_signal = (
        rsi is not None
        and rsi <= 40
        and zone == "near_support"
        and trend != "BEARISH"
    )

    if breakout_valid:
        base_signal = "BREAKOUT"
        base_score = 25
    elif strong_trend and pullback_valid:
        base_signal = "TREND_CONTINUATION"
        base_score = 20
    elif reversal_signal:
        base_signal = "REVERSAL"
        base_score = 18

    confirmation_score = 0
    confirmations: List[str] = []
    if volume_valid:
        confirmation_score += 5
        confirmations.append("Confirmed by volume")
    if strong_close:
        confirmation_score += 5
        confirmations.append("Strong close")

    structure_clean = (
        support is not None
        and resistance is not None
        and price is not None
        and zone == "near_support"
    )
    if structure_clean:
        confirmation_score += 5
        confirmations.append("Structure support (S/R zone)")
    if market_regime_detected == "TRENDING" and base_signal == "TREND_CONTINUATION":
        confirmation_score += 5
        confirmations.append("Trending regime continuation boost")

    context_score = 0
    penalties: List[str] = []
    force_wait = False
    near_resistance = zone == "near_resistance"

    confirmation_passed = True
    if base_signal == "BREAKOUT":
        if not volume_valid:
            confirmation_passed = False
        if not strong_close:
            confirmation_passed = False
    if base_signal == "BREAKOUT" and not confirmation_passed:
        reason = (
            "Base: BREAKOUT_INVALID | breakout_valid=invalid | "
            f"breakout_quality={breakout_quality}/3 | "
            "confirmation_passed=failed | force_wait_triggered=False"
        )
        return {
            "signal": "WAIT",
            "confidence": 40,
            "base_signal": base_signal,
            "base_score": base_score,
            "confirmation_score": 0,
            "context_score": 0,
            "final_score": 0,
            "reason": reason,
            "confirmations": confirmations,
            "penalties": penalties,
        }

    if near_resistance:
        context_score -= 10
        penalties.append("Penalty: near resistance")
    if zone == "mid_zone":
        context_score -= 5
        penalties.append("Penalty: mid zone")

    exhaustion_detected = False
    if last_candle:
        o = last_candle.get("open")
        cl = last_candle.get("close")
        high = last_candle.get("high")
        if o is not None and cl is not None and high is not None and o > 0:
            body = abs(cl - o) / o
            if body > 0.04:
                exhaustion_detected = True
                context_score -= 8
                penalties.append("Penalty: exhaustion")

    conflicting_signal = False
    if trend == "BULLISH" and structure == "bearish_structure":
        conflicting_signal = True
    if breakout_detected and exhaustion_detected:
        conflicting_signal = True
    if conflicting_signal:
        context_score -= 10
        penalties.append("Penalty: conflicting signal")

    if whale == "SELLING":
        context_score -= 10
        penalties.append("Penalty: whale selling")

    if market_regime == "DOWNTREND" and trend == "BULLISH":
        context_score -= 5
        penalties.append("Penalty: regime vs trend mismatch")

    regime_penalty = 0
    if market_regime_detected == "SIDEWAYS":
        if base_signal == "BREAKOUT":
            regime_penalty -= 10
        if base_signal == "TREND_CONTINUATION":
            regime_penalty -= 8
    if market_regime_detected == "VOLATILE":
        regime_penalty -= 5
    if regime_penalty != 0:
        context_score += regime_penalty
        penalties.append(f"Penalty: market regime ({market_regime_detected}) {regime_penalty}")

    volatility_type = "NORMAL"
    if market_regime_detected == "VOLATILE":
        if strong_trend:
            volatility_type = "TRENDING_VOLATILE"
        else:
            volatility_type = "CHAOTIC"
            force_wait = True
            penalties.append("Force WAIT: chaotic volatility")

    near_strong_resistance = (
        price is not None
        and resistance is not None
        and resistance > 0
        and price >= resistance * 0.995
    )
    conflicting_signal_strong = (
        (trend == "BULLISH" and structure == "bearish_structure")
        or (base_signal == "BREAKOUT" and market_regime == "DOWNTREND")
    )
    if near_strong_resistance and base_signal == "BREAKOUT":
        force_wait = True
        penalties.append("Force WAIT: breakout near strong resistance")
    if exhaustion_detected and base_signal == "BREAKOUT":
        force_wait = True
        penalties.append("Force WAIT: breakout exhaustion")
    if conflicting_signal_strong:
        force_wait = True
        penalties.append("Force WAIT: strong conflicting signal")
    if market_regime_detected == "SIDEWAYS" and breakout_quality < 2:
        force_wait = True
        penalties.append("Force WAIT: sideways extreme breakout quality")
    if market_regime_detected == "SIDEWAYS" and breakout_quality < 3:
        force_wait = True
        penalties.append("Force WAIT: sideways hard filter")

    trading_mode = TRADING_MODE if TRADING_MODE in ("SCALPING", "INTRADAY", "SWING") else "INTRADAY"

    # Mode-based context penalty scaling (keeps base/confirmation/context structure intact).
    if trading_mode == "SCALPING":
        context_score = int(round(context_score * 0.7))
    elif trading_mode == "SWING":
        context_score = int(round(context_score * 1.2))

    # Mode-based force-wait policy.
    if trading_mode == "SCALPING":
        # More permissive: only halt on chaotic volatility.
        force_wait = volatility_type == "CHAOTIC"
    elif trading_mode == "SWING":
        # More selective: halt on additional risk contexts.
        if market_regime_detected == "SIDEWAYS" or exhaustion_detected or near_resistance:
            force_wait = True

    final_score = base_score + confirmation_score + context_score

    if force_wait:
        final_score = 0
        signal = "WAIT"
    elif final_score >= (28 if trading_mode == "SCALPING" else 32 if trading_mode == "SWING" else 30):
        signal = "STRONG BUY"
    elif final_score >= (18 if trading_mode == "SCALPING" else 22 if trading_mode == "SWING" else 20):
        signal = "BUY"
    elif final_score >= 10:
        signal = "WEAK BUY"
    else:
        signal = "WAIT"

    base_part = f"Base: {base_signal}" if base_signal else "Base: NONE"
    confidence = 50
    if confirmation_passed:
        confidence += 10
    if breakout_quality == 3:
        confidence += 10
    if market_regime_detected == "TRENDING":
        confidence += 10
    if market_regime_detected == "SIDEWAYS":
        confidence -= 15
    if near_resistance:
        confidence -= 10
    if exhaustion_detected:
        confidence -= 10
    if conflicting_signal:
        confidence -= 15
    if force_wait:
        confidence = 30
    if trading_mode == "SCALPING":
        confidence += 5
    elif trading_mode == "SWING":
        confidence -= 5
    confidence = int(max(10, min(95, confidence)))

    reason_bits: List[str] = [
        base_part,
        f"score_layers={base_score}+{confirmation_score}+{context_score}",
        f"trading_mode={trading_mode}",
        f"market_regime={market_regime_detected}",
        f"volatility_type={volatility_type}",
        f"confidence={confidence}",
    ]
    reason_bits.append(f"breakout_valid={'valid' if breakout_valid else 'invalid'}")
    reason_bits.append(f"confirmation_passed={'passed' if confirmation_passed else 'failed'}")
    reason_bits.append(f"force_wait_triggered={'true' if force_wait else 'false'}")
    if breakout_detected:
        reason_bits.append(f"breakout_quality={breakout_quality}/3")
    reason_bits.extend(confirmations[:3])
    reason_bits.extend(penalties[:5])
    reason = " | ".join(reason_bits[: MAX_REASONS + 4])

    return {
        "signal": signal,
        "confidence": confidence,
        "base_signal": base_signal,
        "base_score": base_score,
        "confirmation_score": confirmation_score,
        "context_score": context_score,
        "final_score": final_score,
        "reason": reason,
        "confirmations": confirmations,
        "penalties": penalties,
        "market_regime_detected": market_regime_detected,
        "volatility_type": volatility_type,
        "trading_mode": trading_mode,
    }


def enrich_btc_market_row(market_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optional fields for BTC market row (monitor / tooling): layered score only.
    Does not alter indicators or trade_setup.
    """
    if not market_row or not isinstance(market_row, dict):
        return {}
    trend = (market_row.get("trend") or "").strip().upper()
    rsi = _safe_float(market_row.get("rsi"))
    support = _safe_float(market_row.get("support"))
    resistance = _safe_float(market_row.get("resistance"))
    price = _safe_float(market_row.get("price"))
    candles = _extract_recent_candles(market_row)
    structure = detect_market_structure(candles)
    zone = detect_zone(price, support, resistance)
    volume_spike = is_volume_spike(candles)
    healthy_pullback = is_healthy_pullback(candles, trend)
    last_candle = candles[-1] if candles else None
    layered = compute_layered_btc_score(
        trend=trend,
        rsi=rsi,
        price=price,
        support=support,
        resistance=resistance,
        structure=structure,
        zone=zone,
        candles=candles,
        volume_spike=volume_spike,
        healthy_pullback=healthy_pullback,
        whale="UNKNOWN",
        market_regime="UNKNOWN",
        last_candle=last_candle,
    )
    conf_list = "; ".join(layered.get("confirmations") or [])
    pen_list = "; ".join(layered.get("penalties") or [])
    analysis = (
        f"{layered['reason']} | structure={structure}, zone={zone} | "
        f"confirmations=[{conf_list}] | context=[{pen_list}] | final={layered['final_score']}"
    )
    return {
        "market_score": layered["final_score"],
        "signal": layered["signal"],
        "analysis": analysis,
        "score_base_signal": layered.get("base_signal"),
        "score_confirmations": layered.get("confirmations"),
        "score_penalties": layered.get("penalties"),
    }


def analyze_btc_signal(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze smart BTC signal from market snapshot.

    Returns:
        {
            "signal": str,
            "confidence": int,
            "phase": str,
            "reason": str,
            "recommendation": str
        }
    """
    if not snapshot or not isinstance(snapshot, dict):
        return {
            "signal": "WAIT",
            "confidence": 0,
            "phase": "—",
            "reason": "Snapshot tidak tersedia",
            "recommendation": "Tunggu snapshot BTC tersedia",
        }

    btc = ((snapshot.get("data") or {}).get("BTC")) or {}
    trend = (btc.get("trend") or "").strip().upper()
    rsi = _safe_float(btc.get("rsi"))
    support = _safe_float(btc.get("support"))
    resistance = _safe_float(btc.get("resistance"))
    price = _safe_float(btc.get("price"))

    intelligence = snapshot.get("market_intelligence") or {}
    market_regime = (intelligence.get("market_regime") or "").strip().upper()
    whale = (intelligence.get("whale_pressure") or "").strip().upper()
    candles = _extract_recent_candles(btc)
    structure = detect_market_structure(candles)
    zone = detect_zone(price, support, resistance)
    phase = _resolve_phase(structure, zone, trend)

    # 1) TAKE PROFIT
    if rsi is not None and rsi >= 75:
        return {
            "signal": "TAKE PROFIT",
            "confidence": 80,
            "phase": phase,
            "reason": "RSI >= 75 (overbought)",
            "recommendation": "Ambil profit sebagian",
        }

    # 2) CRASH WARNING
    if (
        trend == "BEARISH"
        and market_regime in ("DOWNTREND", "VOLATILE")
        and (
            whale == "SELLING"
            or (rsi is not None and rsi < 40)
        )
    ):
        return {
            "signal": "CRASH WARNING",
            "confidence": 90,
            "phase": phase,
            "reason": "Tekanan jual kuat + potensi penurunan lanjutan",
            "recommendation": "Exit semua posisi",
        }

    # 3) Layered score (BASE + CONFIRMATION + CONTEXT) — no double-counted bullish factors
    healthy_pullback = is_healthy_pullback(candles, trend)
    volume_spike = is_volume_spike(candles)
    last_candle = candles[-1] if candles else None

    layered = compute_layered_btc_score(
        trend=trend,
        rsi=rsi,
        price=price,
        support=support,
        resistance=resistance,
        structure=structure,
        zone=zone,
        candles=candles,
        volume_spike=volume_spike,
        healthy_pullback=healthy_pullback,
        whale=whale,
        market_regime=market_regime,
        last_candle=last_candle,
    )

    sig = layered["signal"]
    confidence = layered["confidence"]
    final_score = layered["final_score"]
    reason_detail = layered["reason"]
    conf_list = "; ".join(layered.get("confirmations") or [])
    pen_list = "; ".join(layered.get("penalties") or [])
    reason = (
        f"{reason_detail} | structure={structure}, zone={zone} | "
        f"confirmations=[{conf_list}] | context=[{pen_list}] | final={final_score}"
    )

    if sig == "STRONG BUY":
        return {
            "signal": "STRONG BUY",
            "confidence": confidence,
            "phase": phase,
            "reason": reason,
            "recommendation": "Entry bertahap 30% - 50%",
        }
    if sig == "BUY":
        return {
            "signal": "BUY",
            "confidence": confidence,
            "phase": phase,
            "reason": reason,
            "recommendation": "Boleh akumulasi bertahap dengan risk management ketat",
        }
    if sig == "WEAK BUY":
        return {
            "signal": "WEAK BUY",
            "confidence": confidence,
            "phase": phase,
            "reason": reason,
            "recommendation": "Tunggu konfirmasi tambahan sebelum tambah ukuran posisi",
        }
    return {
        "signal": "WAIT",
        "confidence": confidence,
        "phase": phase,
        "reason": reason,
        "recommendation": "Tunggu setup high probability berikutnya",
    }


def should_alert_btc(signal: str) -> bool:
    """
    Only send BTC auto-alert for high-impact signals.
    """
    return signal in ("STRONG BUY", "CRASH WARNING")


def detect_market_structure(candles: List[Dict[str, float]]) -> str:
    """
    Market structure dari 5 candle terakhir:
    bullish_structure = higher high + higher low
    bearish_structure = lower high + lower low
    selain itu = sideways
    """
    if len(candles) < 3:
        return "sideways"
    recent = candles[-5:]
    highs = [c.get("high") for c in recent if c.get("high") is not None]
    lows = [c.get("low") for c in recent if c.get("low") is not None]
    if len(highs) < 3 or len(lows) < 3:
        return "sideways"
    bullish_highs = all(highs[i] > highs[i - 1] for i in range(1, len(highs)))
    bullish_lows = all(lows[i] > lows[i - 1] for i in range(1, len(lows)))
    bearish_highs = all(highs[i] < highs[i - 1] for i in range(1, len(highs)))
    bearish_lows = all(lows[i] < lows[i - 1] for i in range(1, len(lows)))
    if bullish_highs and bullish_lows:
        return "bullish_structure"
    if bearish_highs and bearish_lows:
        return "bearish_structure"
    return "sideways"


def detect_zone(price: float | None, support: float | None, resistance: float | None) -> str:
    """
    Deteksi zona harga: near_support, near_resistance, mid_zone, neutral.
    """
    if price is None or support is None or resistance is None or resistance <= support:
        return "neutral"
    mid = (support + resistance) / 2
    width = resistance - support
    if price <= support * 1.02:
        return "near_support"
    if price >= resistance * 0.98:
        return "near_resistance"
    if abs(price - mid) < width * 0.15:
        return "mid_zone"
    return "neutral"


def _resolve_phase(structure: str, zone: str, trend: str) -> str:
    """
    Dynamic phase mapping.
    """
    if structure == "bullish_structure":
        return "TREND"
    if zone == "near_support":
        return "ACCUMULATION"
    if trend == "BEARISH":
        return "DOWNTREND"
    return "NEUTRAL"


def is_healthy_pullback(candles: List[Dict[str, float]], trend: str) -> bool:
    """
    Pullback sehat:
    - max 2 candle merah
    - volume menurun
    - tidak ada penurunan tajam
    """
    # Pullback sehat tidak valid pada trend bearish, namun boleh untuk sideways (early reversal).
    if trend == "BEARISH":
        return False
    if len(candles) < 3:
        return True
    recent = candles[-5:]
    red_count = 0
    sharp_drop = False
    volumes: List[float] = []

    for c in recent:
        o = c.get("open")
        cl = c.get("close")
        v = c.get("volume")
        if o is not None and cl is not None:
            if cl < o:
                red_count += 1
            if o > 0 and ((o - cl) / o) > 0.03:
                sharp_drop = True
        if v is not None:
            volumes.append(v)

    volume_desc = True
    if len(volumes) >= 2:
        volume_desc = volumes[-1] <= volumes[-2]

    return red_count <= 2 and volume_desc and (not sharp_drop)


def is_volume_spike(candles: List[Dict[str, float]]) -> bool:
    if len(candles) < 3:
        return False
    recent = candles[-5:]
    vols = [c.get("volume") for c in recent if c.get("volume") is not None]
    if len(vols) < 3:
        return False
    last = vols[-1]
    base = sum(vols[:-1]) / max(1, len(vols) - 1)
    if base <= 0:
        return False
    return last >= base * 1.2


def _extract_recent_candles(btc: Dict[str, Any]) -> List[Dict[str, float]]:
    """
    Coba ekstrak candle dari beberapa key umum agar backward compatible.
    """
    source = (
        btc.get("candles")
        or btc.get("recent_candles")
        or btc.get("klines")
        or btc.get("last_5_candles")
        or []
    )
    out: List[Dict[str, float]] = []
    if not isinstance(source, list):
        return out
    for row in source[-5:]:
        if isinstance(row, dict):
            out.append(
                {
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "close": _safe_float(row.get("close")),
                    "volume": _safe_float(row.get("volume")),
                }
            )
        elif isinstance(row, (list, tuple)) and len(row) >= 6:
            # format umum kline: [ts, open, high, low, close, volume, ...]
            out.append(
                {
                    "open": _safe_float(row[1]),
                    "high": _safe_float(row[2]),
                    "low": _safe_float(row[3]),
                    "close": _safe_float(row[4]),
                    "volume": _safe_float(row[5]),
                }
            )
    return out


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

