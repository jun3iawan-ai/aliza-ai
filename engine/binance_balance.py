"""
Binance Spot Balance Fetcher — Aliza-AI
Ambil USDT balance dari Binance spot wallet (signed /api/v3/account).
Cache untuk mengurangi API call.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

BINANCE_API_URL = os.getenv("BINANCE_API_BASE", "https://api.binance.com").rstrip("/")
BALANCE_CACHE_SECONDS = int(os.getenv("BINANCE_BALANCE_CACHE_SEC", "300"))

_balance_cache: dict[str, float | int] = {
    "value": 0.0,
    "fetched_at": 0,
    "ok": 0,  # 1 if last fetch succeeded (even if balance 0)
}


def _get_binance_credentials() -> tuple[str | None, str | None]:
    key = os.getenv("BINANCE_API_KEY", "").strip()
    secret = os.getenv("BINANCE_API_SECRET", "").strip()
    if key and secret:
        return key, secret
    return None, None


def _signed_get(endpoint: str, params: dict | None = None) -> dict:
    api_key, api_secret = _get_binance_credentials()
    if not api_key or not api_secret:
        raise ValueError("BINANCE_API_KEY atau BINANCE_API_SECRET tidak di-set")

    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    p["recvWindow"] = 10000
    query_string = urlencode(p)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = f"{BINANCE_API_URL}{endpoint}?{query_string}&signature={signature}"
    headers = {"X-MBX-APIKEY": api_key}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def fetch_spot_balance(asset: str = "USDT") -> float:
    """
    Ambil total (free + locked) balance untuk asset di spot.

    Returns:
        float — total USDT, atau 0.0 jika tidak ada kredensial / error / asset tidak ada.
    """
    now = time.time()
    k, s = _get_binance_credentials()
    if not k or not s:
        return 0.0

    if (
        float(_balance_cache.get("fetched_at", 0)) > 0
        and (now - float(_balance_cache["fetched_at"])) < BALANCE_CACHE_SECONDS
        and int(_balance_cache.get("ok", 0)) == 1
    ):
        return float(_balance_cache["value"])

    try:
        data = _signed_get("/api/v3/account")
    except ValueError as e:
        logger.debug("Binance balance skip: %s", e)
        return 0.0
    except requests.HTTPError as e:
        logger.warning("Binance balance HTTP error: %s", e)
        return 0.0
    except Exception as e:
        logger.warning("Binance balance fetch failed: %s", e)
        return 0.0

    balances = data.get("balances") or []
    for b in balances:
        if str(b.get("asset", "")).upper() == asset.upper():
            try:
                free = float(b.get("free", 0) or 0)
                locked = float(b.get("locked", 0) or 0)
            except (TypeError, ValueError):
                free = locked = 0.0
            total = free + locked
            _balance_cache["value"] = total
            _balance_cache["fetched_at"] = now
            _balance_cache["ok"] = 1
            logger.info(
                "Binance %s balance: %.2f (free: %.2f, locked: %.2f)",
                asset,
                total,
                free,
                locked,
            )
            return total

    logger.warning("Asset %s not found in Binance spot balances", asset)
    _balance_cache["value"] = 0.0
    _balance_cache["fetched_at"] = now
    _balance_cache["ok"] = 1
    return 0.0


def get_total_portfolio_value() -> float:
    """Fase ini: setara dengan USDT spot total."""
    return fetch_spot_balance("USDT")
