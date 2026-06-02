"""
ALIZA WHY REASON ENGINE (PRO)

Priority-based reasoning (CRITICAL / WARNING), market context classification,
next triggers (harga konkret), insight & saran actionable.
Hanya membaca market_data dan trade_setup; tidak mengubah pipeline atau struktur data.
"""


def generate_trade_reasoning(market_data: dict, trade_setup: dict) -> dict:
    """
    Generate reasoning PRO: alasan berprioritas, context, insight, saran, triggers.

    Args:
        market_data: Dict dari snapshot["data"][symbol].
        trade_setup: Dict dari market_data["trade_setup"], boleh {}.

    Returns:
        {
            "decision": "TAKE" | "SKIP",
            "reasons": [{"level": "CRITICAL"|"WARNING", "text": str}],
            "context": str,
            "confidence_zone": "HIGH" | "MEDIUM" | "LOW",
            "insight": str,
            "suggestion": str,
            "triggers": list[str]
        }
    """
    if not market_data or not isinstance(market_data, dict):
        return {
            "decision": "SKIP",
            "reasons": [{"level": "CRITICAL", "text": "Data market tidak tersedia"}],
            "context": "—",
            "confidence_zone": "LOW",
            "insight": "Tidak dapat menganalisis market.",
            "suggestion": "Tunggu snapshot market tersedia.",
            "triggers": ["—"],
        }

    setup_raw = (trade_setup or {}).get("setup") if trade_setup else None
    setup = _normalize_setup(setup_raw)
    trend = (market_data.get("trend") or "").strip().upper() or "UNKNOWN"
    trend_alignment = (market_data.get("trend_alignment") or "").strip().upper() or "UNKNOWN"
    rsi = _safe_float(market_data.get("rsi"))
    price = _safe_float(market_data.get("price"))
    support = _safe_float(market_data.get("support"))
    resistance = _safe_float(market_data.get("resistance"))
    risk_reward = _safe_float((trade_setup or {}).get("risk_reward"))

    near_resistance = _is_near_resistance(price, resistance)
    near_support = _is_near_support(price, support)

    # --- Market context ---
    context = _get_market_context(trend, near_resistance, near_support)

    # --- Confidence zone (alignment + RR) ---
    confidence_zone = _get_confidence_zone(trend_alignment, risk_reward)

    # --- Triggers as RANGE (support/resistance * 0.995 – 1.005) ---
    triggers = _get_trigger_ranges(trend, support, resistance)

    # Setup valid = TAKE
    is_valid_setup = setup in ("LONG", "SHORT")
    if is_valid_setup:
        return {
            "decision": "TAKE",
            "reasons": [
                {"level": "WARNING", "text": "Trend mendukung"},
                {"level": "WARNING", "text": "Risk reward memenuhi"},
                {"level": "WARNING", "text": "Struktur market valid"},
            ],
            "context": context,
            "confidence_zone": confidence_zone,
            "insight": "Setup memenuhi kriteria trading Aliza.",
            "suggestion": "Entry sesuai setup dengan risk management.",
            "triggers": triggers,
        }

    # --- SKIP: clean reasons (no redundant "Setup tidak valid") ---
    reasons = []

    # CRITICAL only: alignment lemah, risk reward < 2
    if trend_alignment not in ("STRONG_BULLISH", "STRONG_BEARISH"):
        reasons.append({"level": "CRITICAL", "text": "Alignment lemah"})
    if risk_reward is not None and risk_reward < 2:
        reasons.append({"level": "CRITICAL", "text": "Risk reward tidak memenuhi"})

    # WARNING: RSI, dekat resistance/support
    if rsi is not None and trend in ("BULLISH", "STRONG_BULLISH") and rsi >= 65:
        reasons.append({"level": "WARNING", "text": "RSI mendekati overbought"})
    if rsi is not None and trend in ("BEARISH", "STRONG_BEARISH") and rsi <= 35:
        reasons.append({"level": "WARNING", "text": "RSI mendekati oversold"})
    if near_resistance:
        reasons.append({"level": "WARNING", "text": "Harga dekat resistance"})
    if near_support:
        reasons.append({"level": "WARNING", "text": "Harga dekat support"})
    if not reasons:
        reasons.append({"level": "WARNING", "text": "Market belum di area entry optimal"})

    # --- Insight by context ---
    insight = _get_insight_by_context(context, trend)

    # --- Suggestion ---
    suggestion = "Tunggu konfirmasi pada area tersebut sebelum entry."
    if trend == "SIDEWAYS":
        suggestion = "Tunggu konfirmasi breakout sebelum entry."

    return {
        "decision": "SKIP",
        "reasons": reasons,
        "context": context,
        "confidence_zone": confidence_zone,
        "insight": insight,
        "suggestion": suggestion,
        "triggers": triggers,
    }


def _get_market_context(trend: str, near_resistance: bool, near_support: bool) -> str:
    """TASK 3: Market context classification."""
    if trend in ("BULLISH", "STRONG_BULLISH"):
        if near_resistance:
            return "TREND CONTINUATION (MID ZONE)"
        if near_support:
            return "PULLBACK ZONE"
        return "TREND CONTINUATION"
    if trend == "SIDEWAYS":
        return "RANGE MARKET"
    if trend in ("BEARISH", "STRONG_BEARISH"):
        return "DOWNTREND"
    return "UNKNOWN"


def _get_confidence_zone(trend_alignment: str, risk_reward: float | None) -> str:
    """Confidence zone: alignment kuat + RR ≥ 2.5 → HIGH; mixed → MEDIUM; lemah → LOW."""
    strong = trend_alignment in ("STRONG_BULLISH", "STRONG_BEARISH")
    mixed = trend_alignment == "MIXED"
    rr_ok = risk_reward is not None and risk_reward >= 2.5
    if strong and rr_ok:
        return "HIGH"
    if mixed:
        return "MEDIUM"
    return "LOW"


def _get_trigger_ranges(trend: str, support: float | None, resistance: float | None) -> list:
    """Trigger sebagai range: level * 0.995 – level * 1.005. Selalu ada trigger."""
    def _range_str(level: float) -> str:
        low = level * 0.995
        high = level * 1.005
        return f"{low:.0f} – {high:.0f}" if level >= 1000 else f"{low:.2f} – {high:.2f}"

    out = []
    if trend in ("BULLISH", "STRONG_BULLISH"):
        if support is not None and support > 0:
            out.append(f"Pullback ke {_range_str(support)}")
        if resistance is not None and resistance > 0:
            out.append(f"Breakout di atas {resistance:.0f}" if resistance >= 1000 else f"Breakout di atas {resistance:.2f}")
    elif trend in ("BEARISH", "STRONG_BEARISH"):
        if resistance is not None and resistance > 0:
            out.append(f"Rejection di {resistance:.0f}" if resistance >= 1000 else f"Rejection di {resistance:.2f}")
        if support is not None and support > 0:
            out.append(f"Breakdown di bawah {_range_str(support)}")
    else:
        if support is not None and support > 0:
            out.append(f"Support {_range_str(support)}")
        if resistance is not None and resistance > 0:
            out.append(f"Resistance {_range_str(resistance)}")
    return out if out else ["—"]


def _get_insight_by_context(context: str, trend: str) -> str:
    """TASK 5: Insight berdasarkan context."""
    if "TREND CONTINUATION" in context and "MID ZONE" in context:
        return "Market sedang tren naik tetapi belum di area entry optimal."
    if context == "TREND CONTINUATION":
        return "Market sedang tren naik tetapi belum di area entry optimal."
    if context == "PULLBACK ZONE":
        return "Market mendekati area pullback potensial."
    if context == "RANGE MARKET":
        return "Market sideways, peluang terbatas."
    if context == "DOWNTREND":
        return "Market dalam downtrend, tunggu konfirmasi reversal atau breakdown."
    return "Kondisi market belum memberikan konfirmasi entry yang jelas."


def _is_near_resistance(price: float | None, resistance: float | None) -> bool:
    if price is None or resistance is None or resistance <= 0:
        return False
    return price >= resistance * 0.98


def _is_near_support(price: float | None, support: float | None) -> bool:
    if price is None or support is None or support <= 0:
        return False
    return price <= support * 1.02


def _normalize_setup(v) -> str:
    if v is None:
        return "NO SETUP"
    s = (str(v) or "").strip().upper()
    if s in ("", "NO SETUP", "NO DATA", "NONE"):
        return "NO SETUP"
    if s in ("LONG", "SHORT"):
        return s
    return "NO SETUP"


def _safe_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
