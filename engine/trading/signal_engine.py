"""
ALIZA SIGNAL ENGINE

Scan peluang signal (RR ≥ 3, confidence ≥ 70), pilih terbaik, kirim ke Telegram.
Market Context (BTC trend, market risk) disertakan pada object signal dan ditampilkan di pesan.
Macro: skip scan jika ada event high-impact US dalam window blok (swing safety).
"""

import logging
import os
import time

from engine.state_store import load_state, save_state
from engine.utils.formatters import format_price, format_ratio

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

# Dedup: floor waktu untuk melindungi dispatch ganda meski edge state rusak.
LAST_SIGNALS = {}
SIGNAL_TTL_SECONDS = 900  # 15 menit

# Edge-triggered re-arm: satu episode setup hanya boleh mengirim sekali.
# Setup harus absen dari evaluasi snapshot yang valid selama N scan berturut-turut
# sebelum dianggap reset dan boleh menjadi episode baru.
EDGE_SIGNAL_STATE = {}
DEFAULT_SIGNAL_REARM_DEBOUNCE_SCANS = 3


def signal_rearm_debounce_scans() -> int:
    """Jumlah scan tidak-valid berturut-turut sebelum episode boleh re-arm."""
    try:
        return max(1, int(os.getenv(
            "SIGNAL_REARM_DEBOUNCE_SCANS",
            str(DEFAULT_SIGNAL_REARM_DEBOUNCE_SCANS),
        )))
    except (TypeError, ValueError):
        return DEFAULT_SIGNAL_REARM_DEBOUNCE_SCANS


def _edge_key(signal: dict | None) -> str:
    """Identity episode deterministic: coin + setup + side."""
    payload = signal if isinstance(signal, dict) else {}
    coin = str(payload.get("coin") or payload.get("symbol") or "").upper()
    coin = coin.replace("USDT", "").strip()
    setup = str(payload.get("setup") or "").strip().upper()
    side = str(payload.get("side") or "UNKNOWN").strip().upper()
    return f"{coin}|{setup}|{side}"


def _edge_state_for(signal: dict) -> tuple[str, dict]:
    key = _edge_key(signal)
    state = EDGE_SIGNAL_STATE.setdefault(
        key,
        {"active": False, "inactive_scans": 0},
    )
    return key, state


def _save_signal_state() -> None:
    """Persist both floor-cooldown and episode state in one backward-compatible file."""
    save_state({
        "last_signals": LAST_SIGNALS,
        "edge_signal_state": EDGE_SIGNAL_STATE,
    })


def observe_signal_validity(
    valid_signals: list[dict],
    observed_coins: set[str] | None = None,
) -> None:
    """Advance re-arm debounce once for this completed market evaluation.

    ``valid_signals`` contains every coin that passed the production setup, RR and
    confidence filters in the current snapshot. Coins absent because data was
    unavailable are not counted as invalid, preventing an outage from re-arming
    a still-active setup.
    """
    valid_keys = {_edge_key(signal) for signal in valid_signals}
    observed = None if observed_coins is None else {
        str(coin or "").upper().replace("USDT", "").strip()
        for coin in observed_coins
    }
    debounce = signal_rearm_debounce_scans()
    changed = False

    for key, raw_state in EDGE_SIGNAL_STATE.items():
        state = raw_state if isinstance(raw_state, dict) else {}
        if state is not raw_state:
            EDGE_SIGNAL_STATE[key] = state
            changed = True
        coin = key.split("|", 1)[0]
        if observed is not None and coin not in observed:
            continue
        if key in valid_keys:
            if state.get("inactive_scans", 0) != 0:
                state["inactive_scans"] = 0
                changed = True
            continue

        inactive_scans = int(state.get("inactive_scans", 0) or 0) + 1
        state["inactive_scans"] = inactive_scans
        changed = True
        if state.get("active") and inactive_scans >= debounce:
            state["active"] = False
            logger.info(
                "[TRADE SIGNAL EDGE] reset key=%s invalid_scans=%d debounce=%d",
                key, inactive_scans, debounce,
            )

    if changed:
        _save_signal_state()


def cleanup_signals():
    """Hapus entri floor cooldown lewat TTL agar memori tidak tumbuh tanpa batas."""
    now = time.time()
    keys_to_delete = [
        k for k, v in LAST_SIGNALS.items()
        if now - v["time"] > SIGNAL_TTL_SECONDS
    ]
    for k in keys_to_delete:
        del LAST_SIGNALS[k]
    if keys_to_delete:
        _save_signal_state()


def _signal_body_for_dedup(signal: dict) -> dict:
    """Payload dedup tanpa meta. TIDAK DIPAKAI lagi sejak dedup berbasis key+TTL (17 Juli) —
    dipertahankan untuk referensi/kompatibilitas."""
    if not signal or not isinstance(signal, dict):
        return {}
    skip = frozenset({"source", "signal_mode", "signal_type"})
    return {k: v for k, v in signal.items() if k not in skip}


def can_send_signal(key: str, signal: dict) -> bool:
    """Gate deterministic dengan edge episode lalu floor cooldown 15 menit.

    Source selain deterministic mempertahankan perilaku TTL lama agar checker/LLM
    yang berbagi gateway tidak ikut berubah.
    """
    now = time.time()
    is_deterministic = str((signal or {}).get("source") or "").lower() == "deterministic"

    if is_deterministic:
        edge_key, state = _edge_state_for(signal)
        if state.get("active"):
            logger.info("[TRADE SIGNAL EDGE] suppressed_same_episode key=%s", edge_key)
            return False

    if key in LAST_SIGNALS:
        last = LAST_SIGNALS[key]
        if now - last["time"] < SIGNAL_TTL_SECONDS:
            if is_deterministic:
                logger.info(
                    "[TRADE SIGNAL EDGE] suppressed_floor_cooldown key=%s",
                    _edge_key(signal),
                )
            return False

    if is_deterministic:
        logger.info("[TRADE SIGNAL EDGE] new key=%s", _edge_key(signal))
    return True


def record_signal_sent(key: str, signal: dict):
    LAST_SIGNALS[key] = {
        "signal": signal,
        "time": time.time()
    }
    if str((signal or {}).get("source") or "").lower() == "deterministic":
        _, state = _edge_state_for(signal)
        state["active"] = True
        state["inactive_scans"] = 0
    _save_signal_state()


def _init_last_signals_from_disk():
    global LAST_SIGNALS, EDGE_SIGNAL_STATE
    raw = load_state()
    if not isinstance(raw, dict):
        raw = {}
    # Pre-edge versions stored LAST_SIGNALS directly. Keep reading that shape and
    # bootstrap its recent keys as active episodes on the first upgrade.
    if isinstance(raw.get("last_signals"), dict):
        raw_last = raw.get("last_signals") or {}
        raw_edge = raw.get("edge_signal_state") or {}
    else:
        raw_last = raw
        raw_edge = {}
    LAST_SIGNALS = {}
    for k, v in raw_last.items():
        if isinstance(v, dict) and "signal" in v and "time" in v:
            LAST_SIGNALS[k] = v
    EDGE_SIGNAL_STATE = {
        str(k): dict(v)
        for k, v in raw_edge.items()
        if isinstance(v, dict)
    }
    for last in LAST_SIGNALS.values():
        signal = last.get("signal")
        if isinstance(signal, dict) and str(signal.get("source") or "").lower() == "deterministic":
            EDGE_SIGNAL_STATE.setdefault(
                _edge_key(signal),
                {"active": True, "inactive_scans": 0},
            )
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
    # A coin with a usable market row was evaluated this snapshot. Missing/error
    # rows are intentionally excluded from debounce so a data outage cannot reset
    # an episode.
    observed_coins: set[str] = set()
    no_data = 0
    no_setup = 0
    no_valid_setup = 0
    reject_rr = 0
    reject_conf = 0
    passed = 0
    rejected_rr_values = []
    for coin, data in markets.items():
        if not data or data.get("error"):
            no_data += 1
            continue
        observed_coins.add(str(coin or "").upper().replace("USDT", "").strip())
        trade = data.get("trade_setup")
        if not trade:
            no_setup += 1
            continue
        if trade.get("setup") == "NO SETUP":
            no_valid_setup += 1
            continue
        rr = trade.get("risk_reward")
        conf = trade.get("confidence")
        if rr is None or (MIN_RR is not None and rr < MIN_RR):
            reject_rr += 1
            if rr is not None:
                rejected_rr_values.append(rr)
            logger.debug(
                "scan_for_signals: %s rejected setup=%s rr=%s conf=%s",
                coin,
                trade.get("setup"),
                rr,
                conf,
            )
            continue
        if conf is not None and MIN_CONFIDENCE is not None and conf < MIN_CONFIDENCE:
            reject_conf += 1
            logger.debug(
                "scan_for_signals: %s rejected setup=%s rr=%s conf=%s",
                coin,
                trade.get("setup"),
                rr,
                conf,
            )
            continue
        passed += 1
        candidates.append({
            "coin": coin,
            "setup": trade.get("setup"),
            "side": trade.get("side"),
            "entry": trade.get("entry"),
            "sl": trade.get("sl"),
            "tp1": trade.get("tp1"),
            "tp2": trade.get("tp2"),
            "rr": rr,
            "confidence": conf,
            "trend": data.get("trend"),
        })

    logger.info(
        "scan_for_signals: total=%d no_data=%d no_setup=%d no_valid_setup=%d reject_rr=%d reject_conf=%d passed=%d rr_min=%s rr_max=%s rr_avg=%s",
        len(markets),
        no_data,
        no_setup,
        no_valid_setup,
        reject_rr,
        reject_conf,
        passed,
        round(min(rejected_rr_values), 2) if rejected_rr_values else None,
        round(max(rejected_rr_values), 2) if rejected_rr_values else None,
        round(sum(rejected_rr_values) / len(rejected_rr_values), 2) if rejected_rr_values else None,
    )

    # This is the one per-snapshot truth point for whether each production setup
    # remains valid. Observe all candidates, not just the highest-RR one.
    observe_signal_validity(candidates, observed_coins)

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
        return format_price(v)

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
        f"RR : {format_ratio(rr)} | Confidence : {confidence}\n\n"
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
