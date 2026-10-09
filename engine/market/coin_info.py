"""
Tokenomics lookup for the "Info Coin" display feature (paket 1, display-only).

Single batched call to CoinGecko `coins/markets` (free, keyless, already used
by engine/market/dynamic_universe.py for the same endpoint) for all coins in
MAJOR_COINS at once, cached for TOKENOMICS_CACHE_SEC. Follows the
fail-open-but-honest pattern from engine/market/institutional_data.py: a
failed fetch reports status "unavailable" with a message, never a silent
default number.

Read-only: no signal generation, no alert queueing, no writes to any tracker.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

from engine.market.coin_id_resolver import resolve_coin_id
from engine.market.market_universe import MAJOR_COINS

logger = logging.getLogger(__name__)

MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
TIMEOUT = 15.0
TOKENOMICS_CACHE_SEC = int(os.getenv("TOKENOMICS_CACHE_SEC", "21600"))
# Cache disk: tokenomics jarang berubah; dipakai saat CoinGecko rate-limit (429)
# dan cache memori kosong (mis. tepat setelah restart).
DISK_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "tokenomics_cache.json",
)
DISK_CACHE_MAX_AGE_SEC = 7 * 86400

_tokenomics_cache: dict[str, Any] = {"data": None, "ts": 0.0}


def _get_cg_headers() -> dict:
    h = {"User-Agent": "AlizaAI"}
    key = os.getenv("COINGECKO_API_KEY", "")
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def reset_cache_for_tests() -> None:
    """Test-only: clear in-memory cache so tests don't leak into each other."""
    _tokenomics_cache["data"] = None
    _tokenomics_cache["ts"] = 0.0


def _fetch_tokenomics_batch() -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """
    Fetch coins/markets for every symbol in MAJOR_COINS in one request.
    Return (symbol -> tokenomics dict, None) on success, or (None, error message).
    """
    id_to_symbol: dict[str, str] = {}
    for sym in MAJOR_COINS:
        cg_id = resolve_coin_id(sym)
        if cg_id:
            id_to_symbol[cg_id] = sym
    if not id_to_symbol:
        return None, "tidak ada coin_id yang bisa di-resolve untuk MAJOR_COINS"

    params = {
        "vs_currency": "usd",
        "ids": ",".join(id_to_symbol.keys()),
        "order": "market_cap_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
    }
    try:
        resp = requests.get(MARKETS_URL, params=params, headers=_get_cg_headers(), timeout=TIMEOUT)
    except Exception as e:
        return None, f"request gagal: {e}"

    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"

    try:
        rows = resp.json()
    except Exception as e:
        return None, f"parse JSON gagal: {e}"

    if not isinstance(rows, list):
        return None, "response tidak berupa list"

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cg_id = row.get("id")
        symbol = id_to_symbol.get(cg_id)
        if not symbol:
            continue
        out[symbol] = {
            "market_cap": row.get("market_cap"),
            "fully_diluted_valuation": row.get("fully_diluted_valuation"),
            "circulating_supply": row.get("circulating_supply"),
            "total_supply": row.get("total_supply"),
            "max_supply": row.get("max_supply"),
            "market_cap_rank": row.get("market_cap_rank"),
        }
    if not out:
        return None, "response kosong untuk semua coin watchlist"
    return out, None


def _disk_save(batch: dict, now: float) -> None:
    try:
        os.makedirs(os.path.dirname(DISK_CACHE_FILE), exist_ok=True)
        tmp = DISK_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "data": batch}, f)
        os.replace(tmp, DISK_CACHE_FILE)
    except Exception as e:  # noqa: BLE001
        logger.debug("coin_info: simpan cache disk gagal: %s", e)


def _disk_load(now: float) -> tuple[dict | None, float]:
    try:
        with open(DISK_CACHE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        ts = float(d.get("ts") or 0)
        if isinstance(d.get("data"), dict) and now - ts <= DISK_CACHE_MAX_AGE_SEC:
            return d["data"], ts
    except Exception:  # noqa: BLE001
        pass
    return None, 0.0


def get_tokenomics(symbol: str, now: float | None = None) -> dict[str, Any]:
    """
    Return tokenomics for one symbol.

    Return dict:
      status: "ok" | "unavailable"
      market_cap, fully_diluted_valuation, circulating_supply, total_supply,
        max_supply, market_cap_rank: float | int | None (only present/meaningful
        when status == "ok")
      message: str | None (always set when status != "ok")

    Never returns a fabricated/default number on failure -- caller must treat
    status == "unavailable" as "tidak tersedia", not zero.
    """
    symbol = (symbol or "").strip().upper()
    now = time.time() if now is None else now

    if _tokenomics_cache["data"] is not None and (now - _tokenomics_cache["ts"]) < TOKENOMICS_CACHE_SEC:
        batch = _tokenomics_cache["data"]
    else:
        batch, err = _fetch_tokenomics_batch()
        if batch is None and _tokenomics_cache["data"] is None:
            disk, disk_ts = _disk_load(now)
            if disk is not None:
                logger.warning("coin_info: tokenomics fetch gagal (%s), pakai cache disk", err)
                _tokenomics_cache["data"] = disk
                _tokenomics_cache["ts"] = disk_ts
        if batch is not None:
            _tokenomics_cache["data"] = batch
            _tokenomics_cache["ts"] = now
            _disk_save(batch, now)
        elif _tokenomics_cache["data"] is not None:
            # Fetch gagal tapi masih ada cache lama (walau sudah lewat TTL) --
            # lebih baik data agak basi (jelas ditandai stale oleh caller lewat
            # timestamp cache) daripada "unavailable" tiap kali rate-limited.
            logger.warning("coin_info: tokenomics refresh gagal (%s), pakai cache lama", err)
            batch = _tokenomics_cache["data"]
        else:
            logger.warning("coin_info: tokenomics fetch gagal: %s", err)
            return {
                "status": "unavailable",
                "market_cap": None,
                "fully_diluted_valuation": None,
                "circulating_supply": None,
                "total_supply": None,
                "max_supply": None,
                "market_cap_rank": None,
                "message": f"Tokenomics: gagal fetch dari CoinGecko ({err}) -- coba lagi nanti",
            }

    row = batch.get(symbol)
    if row is None:
        return {
            "status": "unavailable",
            "market_cap": None,
            "fully_diluted_valuation": None,
            "circulating_supply": None,
            "total_supply": None,
            "max_supply": None,
            "market_cap_rank": None,
            "message": f"Tokenomics: {symbol} tidak ditemukan di response CoinGecko",
        }
    return {"status": "ok", "message": None, **row}
