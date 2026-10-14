"""Ekspor hasil Konteks Market ke satu file JSON (dibaca dashboard bot Porto).

Aturan:
- Field ``radar`` (tambahan, lihat radar_export.py) ikut ditulis; bila hitung radar gagal, radar TERAKHIR
  (dengan ts lamanya) dipertahankan. ``refresh_radar()`` memperbarui hanya field itu tiap siklus snapshot.
- Sumber tunggal: dict hasil ``calculate_market_score()`` — angka & teks dibangun lewat
  ``build_components_view`` yang sama dengan pesan Telegram /market_context.
- Penulisan atomik (tulis ``context.json.tmp`` lalu ``os.replace``). Bila apa pun gagal,
  file lama TIDAK ditimpa dan error tidak pernah menggagalkan perhitungan skor.
- Bila semua sumber data gagal (skor jatuh ke default netral 50), file tidak ditulis.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from engine.market import market_context_engine as mce

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_PATH = "/var/lib/market-context/context.json"
FILE_MODE = 0o644
DIR_MODE = 0o755
_ALL_FAILED = 5          # jumlah komponen = semua sumber gagal -> jangan tulis
_lock = threading.Lock()  # satu writer sekaligus (job, /konteks, brief bisa bersamaan)


def context_path() -> str:
    return os.getenv("MARKET_CONTEXT_PATH") or DEFAULT_PATH


def build_payload(result: dict[str, Any], radar: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bangun payload v1 dari hasil calculate_market_score(). ``radar`` opsional (field tambahan, v tetap 1)."""
    label_text = str(result.get("label") or "Neutral")
    score = int(result.get("total_score", 50))
    ts = result.get("timestamp_iso") or datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    payload = {
        "v": SCHEMA_VERSION,
        "ts": ts,
        "score": score,
        "max": sum(mce._MAX.values()),
        "label": mce.map_label_to_alert_status(label_text).lower(),
        "label_text": label_text,
        "level": mce.level_key_for_label(label_text, score),
        "summary": result.get("summary") or "Seimbang — belum ada arah dominan.",
        "thresholds": {
            "bearish_below": mce.BEARISH_BELOW,
            "bullish_above": mce.BULLISH_ABOVE,
        },
        "bands": mce.levels_bands(),
        "components": mce.build_components_view(result),
        "source": "aliza-ai",
    }
    if radar is not None:
        payload["radar"] = radar
    return payload


_RADAR_WARN_EVERY = 3600.0
_radar_last_warn = 0.0


def _write_unlocked(path: str, data: str) -> None:
    """Tulis atomik (tmp + rename), mode 644. Pemanggil memegang ``_lock``."""
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), mode=DIR_MODE, exist_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, FILE_MODE)  # umask tidak boleh mempersempit mode
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _build_radar_safe() -> dict[str, Any] | None:
    global _radar_last_warn
    try:
        from engine.market.radar_export import build_radar
        return build_radar()
    except Exception as e:  # noqa: BLE001 — radar tidak boleh mengganggu skor
        now = time.monotonic()
        if now - _radar_last_warn >= _RADAR_WARN_EVERY or _radar_last_warn == 0.0:
            _radar_last_warn = now
            logger.warning("radar_export: hitung radar gagal (radar lama dipertahankan): %s", e)
        return None


def export_context(result: dict[str, Any], path: str | None = None) -> bool:
    """Tulis JSON secara atomik. Return True bila file baru tertulis."""
    path = path or context_path()
    try:
        if int(result.get("failed_components") or 0) >= _ALL_FAILED:
            logger.warning("market_context_export: semua sumber gagal, file lama dipertahankan")
            return False
        new_radar = _build_radar_safe()
        with _lock:
            radar = new_radar
            if radar is None:   # gagal/belum ada snapshot -> radar terakhir, ts lamanya
                prev = (_read_json(path) or {}).get("radar")
                radar = prev if isinstance(prev, dict) else None
            _write_unlocked(path, _dumps(build_payload(result, radar)))
        return True
    except Exception as e:  # noqa: BLE001 — ekspor tidak boleh mengganggu perhitungan skor
        logger.warning("market_context_export gagal (file lama dipertahankan): %s", e)
        return False


def refresh_radar(path: str | None = None) -> bool:
    """Perbarui HANYA field ``radar`` di context.json yang sudah ada (dipanggil tiap siklus snapshot).

    Field lain tidak disentuh. File belum ada / rusak / bukan v1 -> tidak menulis apa pun.
    Return True bila file ditulis."""
    path = path or context_path()
    try:
        radar = _build_radar_safe()
        if radar is None:
            return False
        with _lock:
            data = _read_json(path)
            if not data or data.get("v") != SCHEMA_VERSION or data.get("radar") == radar:
                return False
            data["radar"] = radar
            _write_unlocked(path, _dumps(data))
        return True
    except Exception as e:  # noqa: BLE001
        logger.debug("market_context_export: refresh radar gagal: %s", e)
        return False
