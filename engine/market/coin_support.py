"""Dukungan data per coin di Binance (spot USDT & futures perpetual USDT-M).

Dipakai supaya coin yang datanya tidak ada DILEWATI dengan rapi per komponen, bukan error:
- tanpa spot & tanpa futures  -> tidak dianalisis sama sekali (mis. BONE)
- tanpa spot, ada futures     -> dianalisis lewat candle futures (mis. FARTCOIN)
- tanpa futures               -> dilewati di funding/OI/long-short

Sumber: endpoint publik Binance, di-cache 6 jam (memori + data/coin_support_cache.json).
Jaringan HANYA dipakai di maybe_refresh(); accessor tidak pernah memanggil jaringan.
Data belum diketahui (jaringan gagal & belum ada cache) -> semua coin dianggap didukung (perilaku lama).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

TTL_SEC = 6 * 3600
RETRY_AFTER_FAIL_SEC = 300
SPOT_URL = "https://api.binance.com/api/v3/ticker/price"
FUTURES_INFO_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_lock = threading.RLock()
_state: dict[str, Any] = {"spot": None, "fut": None, "ts": 0.0, "next_try": 0.0, "disk_loaded": False}


def cache_path() -> str:
    return os.getenv("ALIZA_COIN_SUPPORT_CACHE") or os.path.join(_REPO, "data", "coin_support_cache.json")


def reset_for_tests() -> None:
    with _lock:
        _state.update({"spot": None, "fut": None, "ts": 0.0, "next_try": 0.0, "disk_loaded": False})


def set_data_for_tests(spot_symbols, futures_map) -> None:
    with _lock:
        _state.update({"spot": set(spot_symbols), "fut": dict(futures_map), "ts": time.time(),
                       "next_try": 0.0, "disk_loaded": True})


def _load_disk() -> None:
    if _state["disk_loaded"]:
        return
    _state["disk_loaded"] = True
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            c = json.load(f)
        spot, fut = c.get("spot"), c.get("fut")
        if isinstance(spot, list) and isinstance(fut, dict) and spot and fut:
            _state["spot"], _state["fut"] = set(spot), dict(fut)
            _state["ts"] = float(c.get("ts") or 0.0)
    except Exception:  # noqa: BLE001 — tidak ada cache = belum diketahui
        pass


def _save_disk() -> None:
    path = cache_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": _state["ts"], "spot": sorted(_state["spot"]), "fut": _state["fut"]}, f)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        logger.debug("coin_support: gagal simpan cache: %s", e)


def _fetch_remote() -> tuple[set[str], dict[str, str]] | None:
    """Ambil daftar spot & futures dari Binance. None bila gagal / mode offline (tes)."""
    if os.getenv("ALIZA_COIN_SUPPORT_OFFLINE") == "1":
        return None
    import requests
    h = {"User-Agent": "AlizaAI"}
    spot = {d["symbol"] for d in requests.get(SPOT_URL, headers=h, timeout=15).json()}
    fut: dict[str, str] = {}
    for s in requests.get(FUTURES_INFO_URL, headers=h, timeout=20).json().get("symbols", []):
        if s.get("contractType") == "PERPETUAL" and s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING":
            fut.setdefault(s["baseAsset"], s["symbol"])
    if not spot or not fut:
        raise ValueError("daftar Binance kosong")
    return spot, fut


def maybe_refresh(force: bool = False) -> bool:
    """Segarkan bila TTL habis. Tidak pernah melempar. Return True bila data baru terambil."""
    now = time.time()
    with _lock:
        _load_disk()
        if not force and _state["spot"] is not None and now - _state["ts"] < TTL_SEC:
            return False
        if not force and now < _state["next_try"]:
            return False
        try:
            got = _fetch_remote()
        except Exception as e:  # noqa: BLE001
            _state["next_try"] = now + RETRY_AFTER_FAIL_SEC
            logger.warning("coin_support: refresh gagal (%s); pakai data terakhir bila ada", e)
            return False
        if got is None:
            _state["next_try"] = now + RETRY_AFTER_FAIL_SEC
            return False
        _state["spot"], _state["fut"] = got
        _state["ts"], _state["next_try"] = now, 0.0
        _save_disk()
        return True


def known() -> bool:
    with _lock:
        _load_disk()
        return _state["spot"] is not None and _state["fut"] is not None


def has_spot(coin: str) -> bool | None:
    """True/False; None bila belum diketahui."""
    with _lock:
        _load_disk()
        if _state["spot"] is None:
            return None
        return f"{str(coin).strip().upper()}USDT" in _state["spot"]


def futures_symbol(coin: str) -> str | None:
    """Simbol perpetual USDT-M (mis. PEPE -> 1000PEPEUSDT); None bila tidak ada / belum diketahui."""
    c = str(coin or "").strip().upper()
    with _lock:
        _load_disk()
        fut = _state["fut"]
        if not c or fut is None:
            return None
        return fut.get(c) or fut.get("1000" + c) or fut.get("1000000" + c)


def is_unsupported(coin: str) -> bool:
    """True hanya bila KEDUANYA pasti tidak ada (spot & futures). Belum diketahui -> False."""
    with _lock:
        _load_disk()
        if _state["spot"] is None or _state["fut"] is None:
            return False
        return has_spot(coin) is False and futures_symbol(coin) is None


def support_table(coins) -> list[dict[str, Any]]:
    return [{"coin": c, "spot": has_spot(c), "futures": futures_symbol(c), "unsupported": is_unsupported(c)}
            for c in coins]
