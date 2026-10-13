"""Ekspor hasil Konteks Market ke satu file JSON (dibaca dashboard bot Porto).

Aturan:
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


def build_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Bangun payload v1 dari hasil calculate_market_score()."""
    label_text = str(result.get("label") or "Neutral")
    score = int(result.get("total_score", 50))
    ts = result.get("timestamp_iso") or datetime.now(timezone(timedelta(hours=7))).isoformat(timespec="seconds")
    return {
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


def export_context(result: dict[str, Any], path: str | None = None) -> bool:
    """Tulis JSON secara atomik. Return True bila file baru tertulis."""
    path = path or context_path()
    tmp = path + ".tmp"
    try:
        if int(result.get("failed_components") or 0) >= _ALL_FAILED:
            logger.warning("market_context_export: semua sumber gagal, file lama dipertahankan")
            return False
        data = json.dumps(build_payload(result), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with _lock:
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
        return True
    except Exception as e:  # noqa: BLE001 — ekspor tidak boleh mengganggu perhitungan skor
        logger.warning("market_context_export gagal (file lama dipertahankan): %s", e)
        return False
