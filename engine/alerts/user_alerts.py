"""Alert level buatan user (9 Okt 2026).

/alert ETH above 2553        → terpicu saat harga menyentuh/melewati level
/alert ETH above 2553 4h     → terpicu saat candle 4H CLOSE di atas level
Disimpan di data/user_alerts.json (atomic). Sekali terpicu → nonaktif.
Fungsi evaluasi murni; I/O jaringan dipisah supaya mudah dites.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALERTS_FILE = os.path.join(_ROOT, "data", "user_alerts.json")
MAX_ACTIVE = 20
TF_SECONDS = {"1h": 3600, "4h": 14400, "1d": 86400}
PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
KLINES_URL = "https://api.binance.com/api/v3/klines"

USAGE = (
    "Format:\n"
    "/alert <COIN> <above|below> <harga> [1h|4h|1d]\n\n"
    "Contoh:\n"
    "/alert ETH above 2553 → kabari saat harga menyentuh $2,553\n"
    "/alert BTC below 81000 4h → kabari saat candle 4H close di bawah $81,000\n"
    "alert sol atas 112 (boleh tanpa garis miring)\n\n"
    "/alerts → daftar alert · /alert hapus <id> → hapus"
)


# ---------- penyimpanan ----------
def _load() -> dict[str, Any]:
    try:
        with open(ALERTS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data.setdefault("next_id", 1)
            data.setdefault("alerts", [])
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        logger.warning("user_alerts: gagal baca %s: %s", ALERTS_FILE, e)
    return {"next_id": 1, "alerts": []}


def _save(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    tmp = ALERTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, ALERTS_FILE)


def active_alerts() -> list[dict[str, Any]]:
    return [a for a in _load()["alerts"] if a.get("active")]


# ---------- parsing ----------
def parse_alert(text: str) -> tuple[dict[str, Any] | None, str | None]:
    toks = [t for t in re.split(r"\s+", (text or "").strip()) if t]
    if toks and toks[0].lower().lstrip("/") in ("alert", "alarm"):
        toks = toks[1:]
    if len(toks) < 3:
        return None, "Data kurang.\n\n" + USAGE
    coin = toks[0].upper().removesuffix("USDT")
    d = {"above": "above", "atas": "above", ">": "above", "naik": "above",
         "below": "below", "bawah": "below", "<": "below", "turun": "below"}.get(toks[1].lower())
    if not d:
        return None, f"Arah harus above/below (atas/bawah), bukan '{toks[1]}'.\n\n" + USAGE
    try:
        raw = toks[2].lower().replace(",", "").replace("$", "")
        level = float(raw[:-1]) * 1000 if raw.endswith("k") else float(raw)
    except ValueError:
        return None, f"Harga '{toks[2]}' bukan angka.\n\n" + USAGE
    if level <= 0:
        return None, "Harga harus > 0."
    tf = None
    if len(toks) >= 4:
        tf = toks[3].lower().removeprefix("close").strip() or None
        if tf not in TF_SECONDS:
            return None, f"Timeframe harus 1h, 4h, atau 1d, bukan '{toks[3]}'.\n\n" + USAGE
    if len(toks) > 4:
        return None, f"Bagian '{' '.join(toks[4:])}' tidak dikenali.\n\n" + USAGE
    return {"coin": coin, "direction": d, "level": level, "tf": tf}, None


def describe(a: dict[str, Any], fmt: Callable[[float], str]) -> str:
    arah = "di atas" if a["direction"] == "above" else "di bawah"
    if a.get("tf"):
        return f"{a['coin']} close {a['tf'].upper()} {arah} {fmt(a['level'])}"
    return f"{a['coin']} {'menyentuh/naik ke' if a['direction'] == 'above' else 'menyentuh/turun ke'} {fmt(a['level'])}"


# ---------- jaringan ----------
def fetch_prices(coins: list[str]) -> dict[str, float]:
    if not coins:
        return {}
    syms = sorted({f"{c}USDT" for c in coins})
    try:
        r = requests.get(PRICE_URL, params={"symbols": json.dumps(syms, separators=(",", ":"))}, timeout=10)
        if r.status_code == 200:
            return {x["symbol"][:-4]: float(x["price"]) for x in r.json()}
        logger.warning("user_alerts: ticker HTTP %s", r.status_code)
    except Exception as e:  # noqa: BLE001
        logger.warning("user_alerts: ticker gagal: %s", e)
    # fallback per simbol (mis. satu simbol invalid membuat batch 400)
    out: dict[str, float] = {}
    for s in syms:
        try:
            r = requests.get(PRICE_URL, params={"symbol": s}, timeout=8)
            if r.status_code == 200:
                out[s[:-4]] = float(r.json()["price"])
        except Exception:  # noqa: BLE001
            pass
    return out


def fetch_last_closed(coin: str, tf: str) -> tuple[float, int] | None:
    """(close, close_time_ms) candle TERAKHIR yang sudah tutup."""
    try:
        r = requests.get(KLINES_URL, params={"symbol": f"{coin}USDT", "interval": tf, "limit": 2}, timeout=10)
        if r.status_code != 200:
            return None
        rows = r.json()
        now_ms = int(time.time() * 1000)
        closed = [x for x in rows if int(x[6]) < now_ms]
        if not closed:
            return None
        return float(closed[-1][4]), int(closed[-1][6])
    except Exception as e:  # noqa: BLE001
        logger.warning("user_alerts: klines %s %s gagal: %s", coin, tf, e)
        return None


# ---------- operasi ----------
def create_alert(spec: dict[str, Any], current_price: float | None, now: float | None = None) -> tuple[dict | None, str | None]:
    if current_price is None:
        return None, f"{spec['coin']}USDT tidak ditemukan di Binance (atau harga tidak tersedia)."
    if spec["direction"] == "above" and current_price >= spec["level"]:
        return None, f"Harga {spec['coin']} sekarang ({current_price:g}) sudah di atas {spec['level']:g} — alert akan langsung terpicu. Pakai level lebih tinggi atau arah 'below'."
    if spec["direction"] == "below" and current_price <= spec["level"]:
        return None, f"Harga {spec['coin']} sekarang ({current_price:g}) sudah di bawah {spec['level']:g} — alert akan langsung terpicu. Pakai level lebih rendah atau arah 'above'."
    data = _load()
    if sum(1 for a in data["alerts"] if a.get("active")) >= MAX_ACTIVE:
        return None, f"Maksimal {MAX_ACTIVE} alert aktif. Hapus dulu: /alerts"
    a = dict(spec, id=data["next_id"], active=True, created_at=now or time.time(),
             price_at_create=current_price)
    data["next_id"] += 1
    data["alerts"].append(a)
    _save(data)
    return a, None


def delete_alert(alert_id: int) -> bool:
    data = _load()
    for a in data["alerts"]:
        if a.get("id") == alert_id and a.get("active"):
            a["active"] = False
            a["deleted_at"] = time.time()
            _save(data)
            return True
    return False


def evaluate(alerts: list[dict[str, Any]], prices: dict[str, float],
             last_closed: Callable[[str, str], tuple[float, int] | None]) -> list[dict[str, Any]]:
    """Alert yang terpicu: [{alert, value, kind}]. Murni (I/O lewat argumen)."""
    hits = []
    for a in alerts:
        above = a["direction"] == "above"
        if a.get("tf"):
            lc = last_closed(a["coin"], a["tf"])
            if not lc:
                continue
            close, close_ms = lc
            if close_ms / 1000 <= a["created_at"]:
                continue  # candle ini tutup sebelum alert dibuat
            if (above and close > a["level"]) or (not above and close < a["level"]):
                hits.append({"alert": a, "value": close, "kind": "close"})
        else:
            p = prices.get(a["coin"])
            if p is None:
                continue
            if (above and p >= a["level"]) or (not above and p <= a["level"]):
                hits.append({"alert": a, "value": p, "kind": "touch"})
    return hits


def mark_triggered(alert_ids: list[int], values: dict[int, float]) -> None:
    if not alert_ids:
        return
    data = _load()
    now = time.time()
    for a in data["alerts"]:
        if a.get("id") in alert_ids and a.get("active"):
            a["active"] = False
            a["triggered_at"] = now
            a["triggered_value"] = values.get(a["id"])
    # simpan riwayat 50 alert nonaktif terakhir saja
    inactive = [a for a in data["alerts"] if not a.get("active")][-50:]
    data["alerts"] = [a for a in data["alerts"] if a.get("active")] + inactive
    _save(data)
