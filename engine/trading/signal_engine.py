"""
ALIZA SIGNAL ENGINE

Scan peluang signal (RR ≥ 3, confidence ≥ 70), pilih terbaik, kirim ke Telegram.
Market Context (BTC trend, market risk) disertakan pada object signal dan ditampilkan di pesan.
Macro: skip scan jika ada event high-impact US dalam window blok (swing safety).
"""

import logging
import time

from engine.state_store import load_state, save_state

try:
    from engine.market.market_snapshot_engine import get_market_snapshot
except ImportError:
    get_market_snapshot = None

try:
    from engine.utils.market_cache import get_all_market_data
except ImportError:
    get_all_market_data = None

try:
    from engine.macro.macro_checker import (
        get_upcoming_high_impact_events,
        is_macro_safe_to_trade,
    )
except ImportError:
    get_upcoming_high_impact_events = None
    is_macro_safe_to_trade = None

try:
    from engine.position_sizer import (
        calculate_position_size,
        get_account_balance,
        get_current_open_risk,
    )
    from engine.trading.trade_manager import get_active_trades
except ImportError:
    calculate_position_size = None
    get_account_balance = None
    get_current_open_risk = None
    get_active_trades = None

logger = logging.getLogger(__name__)

MIN_RR = 3
MIN_CONFIDENCE = 70

# Macro: blok scan jika high-impact event dalam N jam (swing)
MACRO_BLOCK_WINDOW_HOURS = 4
# Konteks pesan: event high-impact dalam N jam ke depan (peringatan, bukan blok jika scan lolos)
MACRO_WARN_WINDOW_HOURS = 24

# Dedup: hindari signal identik dikirim berulang dalam window TTL
LAST_SIGNALS = {}
SIGNAL_TTL_SECONDS = 900  # 15 menit


def cleanup_signals():
    """Hapus entri cache yang sudah lewat TTL agar memori tidak tumbuh tanpa batas."""
    now = time.time()
    keys_to_delete = [
        k for k, v in LAST_SIGNALS.items()
        if now - v["time"] > SIGNAL_TTL_SECONDS
    ]
    for k in keys_to_delete:
        del LAST_SIGNALS[k]
    if keys_to_delete:
        save_state(LAST_SIGNALS)


def _signal_body_for_dedup(signal: dict) -> dict:
    """Payload dedup tanpa meta (source, signal_type, …) agar isi trade sama tetap satu."""
    if not signal or not isinstance(signal, dict):
        return {}
    skip = frozenset({"source", "signal_mode", "signal_type"})
    return {k: v for k, v in signal.items() if k not in skip}


def can_send_signal(key: str, signal: dict) -> bool:
    """Return False jika signal sama dengan terakhir untuk key ini dan masih dalam TTL."""
    now = time.time()

    if key in LAST_SIGNALS:
        last = LAST_SIGNALS[key]

        # jika sama & masih dalam TTL → block (bandingkan tanpa source)
        if (
            _signal_body_for_dedup(last["signal"]) == _signal_body_for_dedup(signal)
            and (now - last["time"] < SIGNAL_TTL_SECONDS)
        ):
            return False

    return True


def record_signal_sent(key: str, signal: dict):
    LAST_SIGNALS[key] = {
        "signal": signal,
        "time": time.time()
    }
    save_state(LAST_SIGNALS)


def _init_last_signals_from_disk():
    global LAST_SIGNALS
    raw = load_state()
    if not isinstance(raw, dict):
        raw = {}
    LAST_SIGNALS = {}
    for k, v in raw.items():
        if isinstance(v, dict) and "signal" in v and "time" in v:
            LAST_SIGNALS[k] = v
    cleanup_signals()


def get_btc_context():
    """Ambil konteks market BTC: btc_trend, market_risk dari snapshot."""
    btc_trend = "UNKNOWN"
    market_risk = "UNKNOWN"
    if not get_market_snapshot:
        return btc_trend, market_risk
    try:
        snapshot = get_market_snapshot()
        data = snapshot.get("data") or {}
        btc = data.get("BTC")
        if btc and not btc.get("error"):
            btc_trend = btc.get("trend") or "UNKNOWN"
            market_risk = btc.get("market_risk_score") or "UNKNOWN"
    except Exception:
        pass
    return btc_trend, market_risk


def scan_for_signals():
    """
    Scan market, filter RR ≥ 3 dan confidence ≥ 70, pilih signal terbaik.
    BTC context (btc_trend, market_risk) disimpan di object signal agar ikut dikirim.
    Jika kalender makro menunjuk high-impact event dalam MACRO_BLOCK_WINDOW_HOURS → tidak ada sinyal (return None).
    """
    if is_macro_safe_to_trade:
        try:
            safe, blocking = is_macro_safe_to_trade(window_hours=MACRO_BLOCK_WINDOW_HOURS)
            if not safe:
                names = ", ".join(str(e.get("event", "—")) for e in blocking)
                logger.warning(
                    "Signal scan BLOCKED — high-impact macro within %sh: %s",
                    MACRO_BLOCK_WINDOW_HOURS,
                    names,
                )
                return None
        except Exception as e:
            logger.warning("macro safety check failed (degraded, scan continues): %s", e)

    if get_market_snapshot:
        try:
            snapshot = get_market_snapshot()
            markets = snapshot.get("data") or {}
        except Exception:
            markets = {}
    else:
        markets = get_all_market_data() if get_all_market_data else {}

    if not markets:
        return None

    btc_trend, market_risk = get_btc_context()

    nearby_events: list = []
    if get_upcoming_high_impact_events:
        try:
            nearby_events = get_upcoming_high_impact_events(window_hours=MACRO_WARN_WINDOW_HOURS)
        except Exception as e:
            logger.warning("macro context fetch failed (degraded): %s", e)

    candidates = []
    for coin, data in markets.items():
        if not data or data.get("error"):
            continue
        trade = data.get("trade_setup")
        if not trade:
            continue
        rr = trade.get("risk_reward")
        conf = trade.get("confidence")
        if rr is None or (MIN_RR is not None and rr < MIN_RR):
            continue
        if conf is not None and MIN_CONFIDENCE is not None and conf < MIN_CONFIDENCE:
            continue
        candidates.append({
            "coin": coin,
            "setup": trade.get("setup"),
            "entry": trade.get("entry"),
            "sl": trade.get("sl"),
            "tp1": trade.get("tp1"),
            "tp2": trade.get("tp2"),
            "rr": rr,
            "confidence": conf,
            "trend": data.get("trend"),
        })

    if not candidates:
        return None

    candidates.sort(key=lambda x: x.get("rr") or 0, reverse=True)

    # === POSITION SIZING (kandidat terbaik saja; risk agregat dari posisi terbuka di DB) ===
    if calculate_position_size and get_account_balance and get_current_open_risk and get_active_trades:
        try:
            balance = get_account_balance()
            if balance > 0:
                active = get_active_trades() or []
                current_risk = get_current_open_risk(active, balance)
                sig = candidates[0]
                entry = sig.get("entry")
                sl = sig.get("sl")
                if entry is not None and sl is not None:
                    try:
                        e_f = float(entry)
                        sl_f = float(sl)
                        size_result = calculate_position_size(
                            entry_price=e_f,
                            stop_loss=sl_f,
                            account_balance=balance,
                            current_open_risk_usdt=current_risk,
                        )
                        if size_result:
                            sig["position_size"] = {
                                "units": size_result.size_units,
                                "usdt": size_result.size_usdt,
                                "risk_usdt": size_result.risk_amount_usdt,
                                "risk_pct": size_result.risk_percent,
                                "alloc_pct": size_result.allocation_percent,
                                "limited_by": size_result.limited_by,
                                "warnings": list(size_result.warnings),
                            }
                    except (TypeError, ValueError) as conv_err:
                        logger.debug("position sizing parse: %s", conv_err)
        except Exception as e:
            logger.warning("position sizing (scan) skipped: %s", e)

    best_signal = candidates[0]
    best_signal["btc_trend"] = btc_trend
    best_signal["market_risk"] = market_risk
    best_signal["macro_context"] = nearby_events
    return best_signal


def _format_position_size_block(signal: dict, balance: float = 0.0) -> str:
    """Format blok position sizing untuk pesan Telegram."""
    ps = signal.get("position_size")
    if not isinstance(ps, dict):
        return ""

    limited = ps.get("limited_by") or ""
    units = float(ps.get("units") or 0)
    if limited != "total_risk_exceeded" and units <= 0:
        return ""

    coin_raw = str(signal.get("coin") or signal.get("symbol") or "?").replace("USDT", "").strip() or "?"

    lines: list[str] = []
    if balance > 0:
        lines.append(f"\n💰 Position Size (akun {balance:,.0f} USDT):")
    else:
        lines.append("\n💰 Position Size:")

    if limited == "total_risk_exceeded":
        lines.append("• 🚫 Risk budget penuh — tidak bisa buka posisi baru")
        try:
            if get_active_trades is not None:
                nopen = len(get_active_trades() or [])
                if nopen >= 1:
                    lines.append(
                        f"• Sudah ada {nopen} posisi terbuka — review risk agregat"
                    )
        except Exception:
            pass
    else:
        lines.append(
            f"• Size: {units:.4f} {coin_raw} (~{float(ps.get('usdt') or 0):,.0f} USDT)"
        )
        lines.append(
            f"• Risk: {float(ps.get('risk_usdt') or 0):,.0f} USDT ({float(ps.get('risk_pct') or 0):.1f}% akun)"
        )
        lines.append(f"• Alokasi: {float(ps.get('alloc_pct') or 0):.1f}% akun")

    if limited == "allocation":
        lines.append("• ⚠️ Size dibatasi max alokasi")

    for w in ps.get("warnings") or []:
        if w and str(w) not in "\n".join(lines):
            lines.append(f"• ⚠️ {w}")

    return "\n".join(lines)


def _format_macro_context_block(macro_context: list | None) -> str:
    """Section tambahan untuk Telegram: konteks makro (high-impact US)."""
    lines: list[str] = ["", "⚠️ Macro Context:"]
    ctx = macro_context if isinstance(macro_context, list) else []
    within4 = [x for x in ctx if isinstance(x, dict) and float(x.get("hours_until", 999)) <= 4]
    if not within4:
        lines.append("• Tidak ada high-impact event dalam 4 jam ke depan ✅")
    if not ctx:
        lines.append(
            "• Tidak ada event high-impact US terjadwal dalam 24 jam ke depan (kalender internal)."
        )
        return "\n".join(lines)
    for e in ctx:
        if not isinstance(e, dict):
            continue
        name = e.get("event", "—")
        hu = e.get("hours_until")
        try:
            hu_f = float(hu) if hu is not None else None
        except (TypeError, ValueError):
            hu_f = None
        if hu_f is not None:
            lines.append(f"• {name} dalam ~{hu_f:.1f} jam — pertimbangkan timing entry")
        else:
            lines.append(f"• {name} — pertimbangkan timing entry")
    return "\n".join(lines)


def format_signal_message(signal):
    """
    Format pesan Telegram untuk signal. Tampilkan Market Context (btc_trend, market_risk).
    """
    if not signal:
        return "Tidak ada signal."

    coin = signal.get("coin", "")
    setup = signal.get("setup", "")
    entry = signal.get("entry")
    sl = signal.get("sl") if signal.get("sl") is not None else signal.get("stop_loss")
    tp1 = signal.get("tp1") if signal.get("tp1") is not None else signal.get("take_profit")
    tp2 = signal.get("tp2")
    rr = signal.get("rr")
    confidence = signal.get("confidence")
    btc_trend = signal.get("btc_trend", "UNKNOWN")
    market_risk = signal.get("market_risk", "UNKNOWN")
    macro_ctx = signal.get("macro_context")

    def _fmt(v):
        if v is None:
            return "—"
        if isinstance(v, float):
            return round(v, 2)
        return v

    bal = 0.0
    try:
        if get_account_balance:
            bal = float(get_account_balance() or 0)
    except Exception:
        bal = 0.0

    msg = (
        "🚨 HIGH PROBABILITY TRADE\n\n"
        f"{coin} {setup}\n\n"
        f"Entry : {_fmt(entry)}\n"
        f"SL    : {_fmt(sl)}\n"
        f"TP1   : {_fmt(tp1)}\n"
        f"TP2   : {_fmt(tp2)}\n\n"
        f"RR : {_fmt(rr)} | Confidence : {_fmt(confidence)}\n\n"
        "Market Context\n"
        f"BTC Trend : {btc_trend}\n"
        f"Market Risk : {market_risk}"
    )
    msg += _format_position_size_block(signal, bal)
    msg += _format_macro_context_block(macro_ctx if isinstance(macro_ctx, list) else [])
    msg += (
        "\n\n⚠️ Ini bukan saran investasi — data dari sistem Aliza. "
        "Keputusan dan risiko tetap di kamu.\n\n"
        "Signal otomatis oleh AlizaAI"
    )
    return msg


_init_last_signals_from_disk()
