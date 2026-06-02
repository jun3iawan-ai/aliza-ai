"""
Unified signal gateway: satu pintu masuk ke Telegram untuk alert trading & operasional.
Trade signals: cek makro sebelum kirim (hold jika event high-impact sangat dekat; blok jika <4h).
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Gateway: lebih ketat untuk event sangat dekat (last mile; juga untuk jalur non-scan)
MACRO_GATEWAY_HOLD_HOURS = 1.0
MACRO_GATEWAY_BLOCK_HOURS = 4.0

try:
    from engine.macro.macro_checker import get_upcoming_high_impact_events
except ImportError:
    get_upcoming_high_impact_events = None

# Klasifikasi sinyal (wajib di payload gateway)
SIGNAL_TYPE_TRADE = "trade_signal"
SIGNAL_TYPE_INFORMATIONAL = "informational_signal"


def _trade_levels_present(signal: dict) -> bool:
    """Entry + SL + TP (nama kanonis atau sl/tp1 legacy)."""
    if not signal:
        return False
    e = signal.get("entry")
    sl = signal.get("stop_loss") if signal.get("stop_loss") is not None else signal.get("sl")
    tp = signal.get("take_profit") if signal.get("take_profit") is not None else signal.get("tp1")
    return e is not None and sl is not None and tp is not None


def validate_signal_risk(signal: dict) -> bool:
    """Delegasi ke risk_manager; hanya dipanggil untuk trade_signal yang sudah lengkap level."""
    entry = signal.get("entry")
    sl = signal.get("stop_loss") if signal.get("stop_loss") is not None else signal.get("sl")
    tp1 = signal.get("take_profit") if signal.get("take_profit") is not None else signal.get("tp1")
    if entry is None or sl is None or tp1 is None:
        return False
    try:
        from engine.risk_manager import validate_proposed_trade

        return validate_proposed_trade(entry, sl, tp1)
    except Exception as e:
        logger.error(
            "Risk validation error — REJECTING signal for safety (risk checker failure, not rule rejection): %s",
            e,
            exc_info=True,
        )
        logger.error(
            "Cek engine.risk_manager.validate_proposed_trade dan payload sinyal bila error berulang."
        )
        return False


def _is_operational_source(source: str) -> bool:
    return source in ("system", "watchdog")


def _macro_gateway_evaluate_trade() -> tuple[
    Optional[str], list[dict[str, Any]], list[dict[str, Any]]
]:
    """
    Returns (reason, events_1h, events_4h) where reason is 'hold'|'block'|None.
    hold = high-impact dalam ≤1h; block = dalam (1h, 4h] (scan biasanya sudah blok ≤4h; ini untuk jalur lain).
    On failure: (None, [], []) — caller allows send (degraded).
    """
    if not get_upcoming_high_impact_events:
        return None, [], []
    try:
        ev1 = get_upcoming_high_impact_events(1)
        ev4 = get_upcoming_high_impact_events(4)
    except Exception as e:
        logger.warning("macro gateway: calendar fetch failed: %s", e)
        return None, [], []
    if ev1:
        return "hold", ev1, ev4
    if ev4:
        return "block", ev1, ev4
    return None, ev1, ev4


def _format_macro_hold_log(
    signal: dict, reason: str, events: list[dict[str, Any]]
) -> str:
    coin = signal.get("coin") or signal.get("symbol") or "—"
    setup = signal.get("setup") or signal.get("type") or "—"
    rr = signal.get("rr")
    try:
        rr_s = f"{float(rr):.2f}" if rr is not None else "—"
    except (TypeError, ValueError):
        rr_s = "—"
    detail = ", ".join(str(e.get("event", "—")) for e in events[:3]) if events else "—"
    return (
        f"🚫 Signal HELD — {coin} {setup} (RR {rr_s})\n"
        f"Ditahan karena: {detail} ({reason})\n"
        "Signal akan di-review setelah jendela makro aman."
    )


def _enrich_trade_message_with_position(message: str, signal: dict) -> str:
    """Tambahkan blok Position Size jika belum ada di pesan (jalur non-scan)."""
    if "💰 Position Size" in message or "Position Size" in message:
        return message
    try:
        from engine.position_sizer import (
            calculate_position_size,
            get_account_balance,
            get_current_open_risk,
        )
        from engine.trading.trade_manager import get_active_trades
        from engine.trading.signal_engine import _format_position_size_block
    except Exception as e:
        logger.debug("position enrich import skipped: %s", e)
        return message

    if signal.get("position_size"):
        bal = float(get_account_balance() or 0)
        insert = _format_position_size_block(signal, bal)
        if not insert:
            return message
        if "⚠️ Macro Context:" in message:
            return message.replace("⚠️ Macro Context:", insert + "\n\n⚠️ Macro Context:", 1)
        if "\n\n⚠️ Ini bukan saran investasi" in message:
            return message.replace(
                "\n\n⚠️ Ini bukan saran investasi",
                insert + "\n\n⚠️ Ini bukan saran investasi",
                1,
            )
        return message + insert

    balance = float(get_account_balance() or 0)
    if balance <= 0:
        return message

    entry = signal.get("entry")
    sl = signal.get("stop_loss") if signal.get("stop_loss") is not None else signal.get("sl")
    if entry is None or sl is None:
        return message
    try:
        active = get_active_trades() or []
        current_risk = get_current_open_risk(active, balance)
        size_result = calculate_position_size(
            entry_price=float(entry),
            stop_loss=float(sl),
            account_balance=balance,
            current_open_risk_usdt=current_risk,
        )
        if size_result:
            signal["position_size"] = {
                "units": size_result.size_units,
                "usdt": size_result.size_usdt,
                "risk_usdt": size_result.risk_amount_usdt,
                "risk_pct": size_result.risk_percent,
                "alloc_pct": size_result.allocation_percent,
                "limited_by": size_result.limited_by,
                "warnings": list(size_result.warnings),
            }
            insert = _format_position_size_block(signal, balance)
            if insert and "⚠️ Macro Context:" in message:
                return message.replace("⚠️ Macro Context:", insert + "\n\n⚠️ Macro Context:", 1)
            return message + insert if insert else message
    except Exception as e:
        logger.debug("position enrich failed: %s", e)
    return message


def _enrich_trade_message_with_macro(message: str, signal: dict) -> str:
    """Tambahkan section Macro Context jika belum ada (jalur non-scan)."""
    if "Macro Context:" in message:
        return message
    try:
        from engine.trading.signal_engine import (
            MACRO_WARN_WINDOW_HOURS,
            _format_macro_context_block,
            get_upcoming_high_impact_events as _gup,
        )

        ctx = signal.get("macro_context")
        if not isinstance(ctx, list) and _gup:
            ctx = _gup(window_hours=MACRO_WARN_WINDOW_HOURS)
        elif not isinstance(ctx, list):
            ctx = []
        return message + _format_macro_context_block(ctx)
    except Exception as e:
        logger.debug("macro message enrich skipped: %s", e)
        return message


def build_unified_signal(
    *,
    source: str,
    coin: str,
    setup: str = "",
    entry: Any = None,
    sl: Any = None,
    tp1: Any = None,
    tp2: Any = None,
    rr: Any = None,
    confidence: Any = None,
    **extra: Any,
) -> dict:
    """Format kanonis untuk gateway (tanpa mengubah logika strategi di sumber)."""
    c = (coin or "").strip().upper()
    sym = c if c.endswith("USDT") else (f"{c}USDT" if c else "UNKNOWN")
    typ = str(setup or extra.get("type") or "ALERT")
    base = {
        "symbol": sym,
        "type": typ,
        "entry": entry,
        "stop_loss": sl,
        "take_profit": tp1,
        "confidence": confidence,
        "source": source,
        "rr": rr,
        "tp2": tp2,
        "coin": c,
        "setup": setup,
        "signal_type": SIGNAL_TYPE_TRADE,
    }
    merged = {**base}
    for k, v in extra.items():
        if k not in merged:
            merged[k] = v
    if "signal_type" not in merged:
        merged["signal_type"] = SIGNAL_TYPE_TRADE
    return merged


def attach_strategy_source(sig: dict) -> dict:
    """Tambahkan field kanonis + source strategy dari dict scan_for_signals."""
    u = dict(sig)
    coin = u.get("coin") or ""
    u["symbol"] = f"{coin}USDT" if coin and not str(coin).upper().endswith("USDT") else (coin or "UNKNOWN")
    u["type"] = str(u.get("setup") or "ALERT")
    u["stop_loss"] = u.get("sl")
    u["take_profit"] = u.get("tp1")
    u["source"] = "strategy"
    u["signal_type"] = SIGNAL_TYPE_TRADE
    return u


async def process_signal(
    key: str,
    signal: Optional[dict],
    message: str,
    *,
    chat_id=None,
    force: bool = False,
) -> bool:
    """
    Unified signal entry point: klasifikasi signal_type → risk (trade saja) → dedup → dispatch.
    source system/watchdog: hanya dispatch (tanpa risk/dedup/record).
    """
    try:
        if signal is None:
            return False
        if not isinstance(signal, dict):
            return False

        src = signal.get("source") or "unknown"
        signal_type = signal.get("signal_type") or SIGNAL_TYPE_TRADE

        if not _is_operational_source(src):
            logger.info(f"[SIGNAL TYPE] {signal_type} | {key}")

            if signal_type == SIGNAL_TYPE_TRADE:
                if not _trade_levels_present(signal):
                    logger.warning(f"[INVALID] trade_signal missing fields {key}")
                    return False
                if not validate_signal_risk(signal):
                    logger.info(f"[BLOCKED] risk rejected {key}")
                    return False

            elif signal_type == SIGNAL_TYPE_INFORMATIONAL:
                if not signal.get("symbol") or not signal.get("type"):
                    logger.warning(f"[INVALID] informational signal malformed {key}")
                    return False
                logger.info(f"[INFO] informational signal {key} bypass risk")

            else:
                logger.warning(f"[INVALID] unknown signal_type {signal_type!r} for {key}")
                return False

            from engine.trading import signal_engine as trading_se

            trading_se.cleanup_signals()
            if not trading_se.can_send_signal(key, signal):
                logger.info(f"[BLOCKED] duplicate signal {key}")
                return False

            if signal_type == SIGNAL_TYPE_TRADE:
                reason, ev1, ev4 = _macro_gateway_evaluate_trade()
                if reason == "hold":
                    log_txt = _format_macro_hold_log(signal, "≤1 jam", ev1)
                    logger.warning("[MACRO GATEWAY HOLD] %s", log_txt.replace("\n", " | "))
                    return False
                if reason == "block":
                    log_txt = _format_macro_hold_log(
                        signal, f"≤{MACRO_GATEWAY_BLOCK_HOURS} jam (gateway)", ev4
                    )
                    logger.warning("[MACRO GATEWAY BLOCK] %s", log_txt.replace("\n", " | "))
                    return False

        logger.info(f"[SIGNAL] {key} from {src}")

        out_msg = message
        if not _is_operational_source(src):
            prefix = (
                "[INFO SIGNAL]\n\n"
                if signal_type == SIGNAL_TYPE_INFORMATIONAL
                else "[TRADE SIGNAL]\n\n"
            )
            out_msg = prefix + out_msg
            if signal_type == SIGNAL_TYPE_TRADE:
                out_msg = _enrich_trade_message_with_macro(out_msg, signal)
                out_msg = _enrich_trade_message_with_position(out_msg, signal)

        from interfaces.telegram_bot import safe_dispatch

        sent = await safe_dispatch(out_msg, chat_id=chat_id, force=force)
        if sent and not _is_operational_source(src):
            from engine.trading import signal_engine as trading_se

            trading_se.record_signal_sent(key, signal)
        return bool(sent)
    except Exception as e:
        logger.warning("process_signal failed: %s", e)
        return False
