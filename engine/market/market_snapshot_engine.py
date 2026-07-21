"""
ALIZA MARKET SNAPSHOT ENGINE

Memastikan Aliza hanya menggunakan data market yang lengkap dan tervalidasi.
Snapshot di-update oleh job; command Telegram membaca dari snapshot agar output
tidak pernah kosong atau tidak lengkap.
"""

import logging
import os
import time
from copy import deepcopy

import requests
from datetime import datetime, timedelta, timezone
from threading import Lock

from engine.market_signal import generate_signal
from engine.market.market_radar import market_radar
from engine.market.global_market_cache import get_global_market_data
from engine.market.dynamic_universe import get_tradable_coins
from engine.market.market_universe import (
    MAJOR_COINS,
    get_polling_coins,
    get_universe_status,
    record_coin_validation,
)
from engine.market.market_analyzer import get_data_coverage

ENRICH_HEADERS = {"User-Agent": "AlizaAI"}


def _get_cg_headers() -> dict:
    h = {"User-Agent": "AlizaAI"}
    key = os.getenv("COINGECKO_API_KEY", "")
    if key:
        h["x-cg-demo-api-key"] = key
    return h

try:
    from engine.intelligence.market_intelligence_engine import generate_market_intelligence
except ImportError:
    generate_market_intelligence = None

# Snapshot storage global (thread-safe)
_snapshot_lock = Lock()
market_snapshot = {
    "data": {},
    "timestamp": None,
    "market_intelligence": None,
    "data_coverage": {},
}

_WIB = timezone(timedelta(hours=7))

MAX_AGE_SEC = 300
RETRY_DELAY_SEC = 30
RADAR_RETRY_DELAY = 2
SNAPSHOT_INVALID_COUNT = 0
CIRCUIT_BREAKER_ACTIVE = False
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CB_THRESHOLD", "10"))
CB_ALERT_SENT = False
CB_RECOVERY_ALERT_PENDING = False
RECOVERY_CONFIRMATION_COUNT = 3
_snapshot_recovery_counter = 0
CB_HEARTBEAT_EVERY = int(os.getenv("CB_HEARTBEAT_EVERY", "5"))
_cb_halt_cycle_counter = 0


def get_tradable_coins_fallback():
    """Daftar coin yang di-scan; fallback ke MAJOR_COINS jika dynamic_universe gagal."""
    try:
        coins = get_tradable_coins()
        if coins:
            return get_polling_coins(coins)
    except Exception as e:
        logging.warning("market_snapshot_engine get_tradable_coins: %s", e)
    return get_polling_coins(MAJOR_COINS)


def validate_market_data(data):
    """
    Data dianggap valid jika memiliki: price (numeric, not None), trend (one of BULLISH/BEARISH/SIDEWAYS),
    rsi (numeric, not None). price=0 and rsi=0 are accepted. Support, resistance, etc. optional.
    Return True jika valid.
    """
    if not data or not isinstance(data, dict):
        return False
    if data.get("error"):
        return False
    price = data.get("price")
    if price is None or not isinstance(price, (int, float)):
        return False
    trend = data.get("trend")
    if trend is None or not isinstance(trend, str) or str(trend).strip().upper() not in ("BULLISH", "BEARISH", "SIDEWAYS"):
        return False
    rsi = data.get("rsi")
    if rsi is None or not isinstance(rsi, (int, float)):
        return False
    logging.debug("Snapshot validation OK for %s", data.get("symbol"))
    return True


def _is_radar_incomplete(data):
    """True jika field radar masih UNKNOWN (cycle_phase atau whale_activity)."""
    if not data or not isinstance(data, dict):
        return True
    cycle = data.get("cycle_phase")
    whale = data.get("whale_activity")
    cycle_unknown = cycle is None or str(cycle).strip().upper() == "UNKNOWN"
    whale_unknown = whale is None or str(whale).strip().upper() == "UNKNOWN"
    return cycle_unknown or whale_unknown


def _data_to_validate(data):
    """Extract nested market_data for validation if present; otherwise return data as-is."""
    if data and isinstance(data, dict) and "market_data" in data:
        return data["market_data"]
    return data


def _fetch_with_radar_retry(symbol, radar_data=None):
    """
    Panggil generate_signal(symbol, radar_data). Jika data valid tapi radar belum terisi
    (cycle_phase atau whale_activity == UNKNOWN), retry sekali setelah 2 detik.
    Return data (pertama atau retry yang lebih lengkap); tidak raise.
    """
    try:
        data = generate_signal(symbol, radar_data)
    except Exception as e:
        logging.warning("market_snapshot_engine fetch %s: %s", symbol, e)
        return None

    to_validate = _data_to_validate(data)
    if not validate_market_data(to_validate):
        return data

    if not _is_radar_incomplete(data):
        return data

    try:
        time.sleep(RADAR_RETRY_DELAY)
        retry_data = generate_signal(symbol, radar_data)
        to_validate_retry = _data_to_validate(retry_data)
        if validate_market_data(to_validate_retry) and not _is_radar_incomplete(retry_data):
            return retry_data
    except Exception as e:
        logging.warning("market_snapshot_engine radar retry %s: %s", symbol, e)

    return data


def _enrich_collected_with_binance_24h(collected):
    """
    Tambah price_change_percentage_24h, price_change_pct_24h, volume_24h (quote USDT)
    per coin dari satu request Binance /api/v3/ticker/24hr (semua pasangan).
    """
    if not collected:
        return
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            headers=ENRICH_HEADERS,
            timeout=20,
        )
        if r.status_code != 200:
            logging.warning(
                "market_snapshot_engine: Binance 24hr ticker HTTP %s",
                r.status_code,
            )
            return
        rows = r.json()
        if not isinstance(rows, list):
            return
        by_sym = {x.get("symbol"): x for x in rows if isinstance(x, dict)}
    except Exception as e:
        logging.warning("market_snapshot_engine: Binance 24hr fetch failed: %s", e)
        return

    for sym, row in collected.items():
        if not isinstance(row, dict):
            continue
        pair = f"{str(sym).strip().upper()}USDT"
        t = by_sym.get(pair)
        if not t:
            continue
        try:
            pct = t.get("priceChangePercent")
            if pct is not None:
                v = float(pct)
                row["price_change_percentage_24h"] = v
                row["price_change_pct_24h"] = v
        except (TypeError, ValueError):
            pass
        try:
            qv = t.get("quoteVolume")
            if qv is not None:
                row["volume_24h"] = float(qv)
        except (TypeError, ValueError):
            pass


def _coverage_for_symbol(symbol, data, valid, reason=None):
    payload = data.get("market_data") if isinstance(data, dict) and isinstance(data.get("market_data"), dict) else data
    coverage = payload.get("data_coverage") if isinstance(payload, dict) else None
    if not isinstance(coverage, dict):
        coverage = get_data_coverage(symbol)
    if not coverage:
        coverage = {"coin": str(symbol).upper(), "klines_4h": 0, "klines_1d": 0, "price_source": "none", "reason": reason or ("ok" if valid else "validation_failed")}
    else:
        coverage = dict(coverage)
        coverage["coin"] = str(symbol).upper()
        if not valid and reason:
            coverage["reason"] = reason
    coverage["valid"] = bool(valid)
    if not valid:
        logging.warning(
            "data_coverage coin=%s klines_4h=%d klines_1d=%d price_source=%s reason=%s",
            coverage.get("coin", str(symbol).upper()), int(coverage.get("klines_4h", 0)),
            int(coverage.get("klines_1d", 0)), coverage.get("price_source", "none"),
            coverage.get("reason", reason or "validation_failed"),
        )
    return coverage

def update_market_snapshot():
    """
    Fetch data market via generate_signal(symbol, radar_data) untuk semua get_tradable_coins().
    Radar dipanggil sekali per cycle; hasilnya diteruskan ke setiap generate_signal.
    Validasi tiap coin (price, trend, rsi, support, resistance).
    Jika data valid tetapi cycle_phase atau whale_activity == UNKNOWN, retry sekali
    setelah ~2 detik; jika retry lebih lengkap gunakan data retry.
    Jika validasi gagal, retry sekali setelah 30 detik untuk coin yang gagal.
    """
    coins = get_tradable_coins_fallback()
    coverage_summary = {"_universe": get_universe_status(MAJOR_COINS)}
    if not coins:
        logging.warning("market_snapshot_engine: no coins to fetch")
        with _snapshot_lock:
            market_snapshot["data_coverage"] = coverage_summary
        return

    # Fetch radar sekali per snapshot cycle (hindari API call berulang per coin)
    radar_data = None
    try:
        global_data = get_global_market_data()
        radar_data = market_radar(global_data.get("fear_greed"), global_data.get("btc_dominance"))
        if radar_data:
            logging.info("Market radar fetched once per snapshot")
    except Exception as e:
        logging.warning("market_snapshot_engine radar fetch: %s", e)

    # Pre-fetch harga coin non-Binance via CoinGecko batch
    try:
        from engine.market.coin_id_resolver import resolve_coin_id
        from engine.market.market_analyzer import set_cg_price_cache
        NON_BINANCE = ["BONE", "FARTCOIN", "HYPE", "ZEREBRO"]
        cg_ids = [resolve_coin_id(s) for s in NON_BINANCE]
        cg_ids = [cid for cid in cg_ids if cid]
        if cg_ids:
            _r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price"
                f"?ids={','.join(cg_ids)}&vs_currencies=usd",
                headers=_get_cg_headers(),
                timeout=10,
            )
            if _r.status_code == 200:
                _cg_data = _r.json()
                _price_map = {}
                for sym in NON_BINANCE:
                    cid = resolve_coin_id(sym)
                    if cid and cid in _cg_data:
                        _price_map[sym] = float(_cg_data[cid]["usd"])
                set_cg_price_cache(_price_map)
                logging.info("snapshot: pre-fetched CoinGecko prices: %s", _price_map)
    except Exception as _e:
        logging.warning("snapshot: CoinGecko pre-fetch failed: %s", _e)

    collected = {}
    failed = []
    validation_results = {}

    for symbol in coins:
        logging.info("Snapshot processing coin: %s", symbol)
        try:
            data = _fetch_with_radar_retry(symbol, radar_data)
            to_validate = _data_to_validate(data)
            if data and validate_market_data(to_validate):
                collected[symbol] = data
                logging.info("Snapshot success: %s", symbol)
                validation_results[symbol] = (data, True, "ok")
            else:
                failed.append(symbol)
                logging.warning("Snapshot failed validation: %s", symbol)
                validation_results[symbol] = (data, False, "validation_failed")
        except Exception as e:
            logging.error("Snapshot error for %s: %s", symbol, str(e))
            failed.append(symbol)
            validation_results[symbol] = (None, False, "exception")

    if failed:
        time.sleep(RETRY_DELAY_SEC)
        for symbol in failed[:]:
            logging.info("Snapshot processing coin (retry): %s", symbol)
            try:
                data = _fetch_with_radar_retry(symbol, radar_data)
                to_validate = _data_to_validate(data)
                if data and validate_market_data(to_validate):
                    collected[symbol] = data
                    failed.remove(symbol)
                    logging.info("Snapshot success: %s", symbol)
                    validation_results[symbol] = (data, True, "ok")
                else:
                    logging.warning("Snapshot failed validation: %s", symbol)
                    validation_results[symbol] = (data, False, "validation_failed")
            except Exception as e:
                logging.error("Snapshot error for %s: %s", symbol, str(e))
                validation_results[symbol] = (None, False, "exception")

    for symbol in coins:
        data, valid, reason = validation_results.get(symbol, (None, False, "not_processed"))
        coverage_summary[symbol] = _coverage_for_symbol(symbol, data, valid, reason)
        record_coin_validation(symbol, valid, reason=reason)
    coverage_summary["_universe"] = get_universe_status(MAJOR_COINS)

    if collected:
        _enrich_collected_with_binance_24h(collected)
        snapshot_ts = datetime.utcnow()
        market_intelligence = None
        if generate_market_intelligence is not None:
            try:
                snapshot_view = {"data": collected, "timestamp": snapshot_ts}
                market_intelligence = generate_market_intelligence(snapshot_view)
            except Exception as e:
                logging.debug("market_intelligence update: %s", e)

        # Spot engine: sinyal BUY/WAIT/EXIT per coin (tidak mengubah trade_setup/futures)
        try:
            from engine.spot.spot_engine import analyze_spot_opportunity
            intel = market_intelligence or {}
            for sym, sym_data in collected.items():
                sym_data["spot_signal"] = analyze_spot_opportunity(sym, sym_data, intel)
        except Exception as e:
            logging.debug("spot_engine enrichment: %s", e)

        # Atomic snapshot swap to avoid partial-read race conditions.
        with _snapshot_lock:
            market_snapshot["data"] = collected
            market_snapshot["timestamp"] = snapshot_ts
            market_snapshot["market_intelligence"] = market_intelligence
            market_snapshot["data_coverage"] = coverage_summary
        logging.info("market_snapshot_engine: updated %d coins", len(collected))
    else:
        logging.warning("market_snapshot_engine: no valid data collected")
        with _snapshot_lock:
            market_snapshot["market_intelligence"] = None
            market_snapshot["data_coverage"] = coverage_summary
    logging.info("Snapshot completed. Valid coins: %d", len(collected))


def get_market_snapshot():
    """
    Return snapshot terbaru.
    Return dict: {"data": { symbol: market_data }, "timestamp": datetime or None, "market_intelligence": dict or None }
    """
    with _snapshot_lock:
        ts = market_snapshot.get("timestamp")
        data = deepcopy(market_snapshot.get("data") or {})
        intel = deepcopy(market_snapshot.get("market_intelligence"))
        coverage = deepcopy(market_snapshot.get("data_coverage") or {})
        return {"data": data, "timestamp": ts, "market_intelligence": intel, "data_coverage": coverage}


def get_snapshot_timestamp_str():
    """Format timestamp snapshot untuk tampilan Telegram: HH:MM:SS (WIB)."""
    snap = get_market_snapshot()
    ts = snap.get("timestamp")
    if ts is None:
        return "—"
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_wib = ts.astimezone(_WIB)
        return ts_wib.strftime("%H:%M:%S")
    if hasattr(ts, "strftime"):
        return ts.strftime("%H:%M:%S")
    return "—"


def is_snapshot_valid(snapshot, max_age_sec):
    global SNAPSHOT_INVALID_COUNT, CIRCUIT_BREAKER_ACTIVE, CB_ALERT_SENT, CB_RECOVERY_ALERT_PENDING
    global _snapshot_recovery_counter, _cb_halt_cycle_counter

    def _mark_invalid_locked():
        global SNAPSHOT_INVALID_COUNT, CIRCUIT_BREAKER_ACTIVE, CB_ALERT_SENT, _snapshot_recovery_counter, _cb_halt_cycle_counter
        SNAPSHOT_INVALID_COUNT += 1
        _snapshot_recovery_counter = 0
        logging.error("SNAPSHOT INVALID COUNT: %d", SNAPSHOT_INVALID_COUNT)
        if SNAPSHOT_INVALID_COUNT >= CIRCUIT_BREAKER_THRESHOLD:
            if not CIRCUIT_BREAKER_ACTIVE:
                CIRCUIT_BREAKER_ACTIVE = True
                CB_ALERT_SENT = False
                _cb_halt_cycle_counter = 0
                logging.critical("CIRCUIT BREAKER ACTIVATED — SNAPSHOT INVALID PERSISTENT")
            _cb_halt_cycle_counter += 1
            if _cb_halt_cycle_counter % max(1, CB_HEARTBEAT_EVERY) == 0:
                logging.critical("SYSTEM HALTED — WAITING FOR RECOVERY")

    ts = None
    if not snapshot:
        with _snapshot_lock:
            _mark_invalid_locked()
        return False
    ts = snapshot.get("timestamp")
    if not ts:
        with _snapshot_lock:
            _mark_invalid_locked()
        return False

    try:
        age = (datetime.utcnow() - ts).total_seconds()
        logging.info("SNAPSHOT AGE: %.2fs", age)
        if age > max_age_sec:
            with _snapshot_lock:
                _mark_invalid_locked()
            return False
    except Exception:
        with _snapshot_lock:
            _mark_invalid_locked()
        return False

    with _snapshot_lock:
        _snapshot_recovery_counter += 1
        if CIRCUIT_BREAKER_ACTIVE:
            if _snapshot_recovery_counter >= RECOVERY_CONFIRMATION_COUNT:
                logging.info("CIRCUIT BREAKER RECOVERED — SNAPSHOT NORMAL")
                CB_RECOVERY_ALERT_PENDING = True
                SNAPSHOT_INVALID_COUNT = 0
                CIRCUIT_BREAKER_ACTIVE = False
                CB_ALERT_SENT = False
                _snapshot_recovery_counter = 0
                _cb_halt_cycle_counter = 0
        else:
            SNAPSHOT_INVALID_COUNT = 0
            _snapshot_recovery_counter = 0

    return True
