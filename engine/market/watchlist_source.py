"""Sumber daftar coin pantau Aliza: /var/lib/porto/coins.json (ditulis bot Porto).

Aliza HANYA MEMBACA file itu (tidak pernah menulis ke /var/lib/porto).

Perilaku:
- Format v1: {"v": 1, "symbols": [...], ...}. Versi lain / JSON rusak / symbols kosong / simbol
  tidak valid -> file ditolak seluruhnya (daftar pantau tidak pernah dikosongkan oleh file buruk).
- Daftar valid terakhir disimpan sebagai cache di sisi Aliza (data/watchlist_cache.json).
- Urutan fallback: file valid -> daftar valid terakhir (memori, lalu cache disk) -> daftar lama (default).
- Dibaca ulang bila (mtime, ukuran, inode) berubah (dicek tiap <=5 detik) atau tiap 5 menit.
- Perubahan daftar dicatat sebagai "notifikasi tertunda" sampai benar-benar terkirim ke Telegram.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_PATH = "/var/lib/porto/coins.json"
STAT_INTERVAL_SEC = 5.0       # seberapa sering mtime dicek
REREAD_INTERVAL_SEC = 300.0   # baca ulang paksa walau mtime sama (<= 5 menit)
WARN_REPEAT_SEC = 3600.0      # warning masalah yang sama diulang paling cepat per jam
MAX_SYMBOLS = 100
_SYM_RE = re.compile(r"^[A-Z0-9]{1,20}$")
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WIB = timezone(timedelta(hours=7))


def file_path() -> str:
    return os.getenv("PORTO_COINS_PATH") or DEFAULT_PATH


def cache_path() -> str:
    return os.getenv("ALIZA_WATCHLIST_CACHE") or os.path.join(_REPO, "data", "watchlist_cache.json")


def parse_symbols(obj: Any) -> list[str]:
    """Validasi isi file; kembalikan simbol unik (urutan asli). Lempar ValueError bila tidak valid."""
    if not isinstance(obj, dict):
        raise ValueError("isi bukan objek JSON")
    v = obj.get("v")
    if isinstance(v, bool) or v != SCHEMA_VERSION:
        raise ValueError(f"versi tidak didukung: {v!r} (butuh {SCHEMA_VERSION})")
    syms = obj.get("symbols")
    if not isinstance(syms, list) or not syms:
        raise ValueError("symbols kosong atau bukan list")
    out: list[str] = []
    for s in syms:
        if not isinstance(s, str):
            raise ValueError(f"simbol bukan string: {s!r}")
        u = s.strip().upper()
        if not _SYM_RE.match(u):
            raise ValueError(f"simbol tidak valid: {s!r}")
        if u not in out:
            out.append(u)
    if len(out) > MAX_SYMBOLS:
        raise ValueError(f"terlalu banyak simbol: {len(out)}")
    return out


class _State:
    def __init__(self) -> None:
        self.symbols: list[str] | None = None   # daftar yang sedang dipakai
        self.good: list[str] | None = None      # daftar valid terakhir (dari file)
        self.status = "init"                    # porto | cache | default
        self.reason = ""
        self.sig: tuple | None = None
        self.last_stat = 0.0
        self.last_read = 0.0
        self.announced: list[str] | None = None  # daftar terakhir yang sudah diberitahukan ke Telegram
        self.warned_reason: str | None = None
        self.warned_at = 0.0
        self.file_ts: str | None = None


_S = _State()
_lock = threading.RLock()


def reset_for_tests() -> None:
    global _S
    with _lock:
        _S = _State()


def _load_cache() -> dict[str, Any] | None:
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            c = json.load(f)
        syms = parse_symbols({"v": SCHEMA_VERSION, "symbols": c.get("symbols")})
        ann = c.get("announced")
        ann = parse_symbols({"v": SCHEMA_VERSION, "symbols": ann}) if ann else None
        return {"symbols": syms, "announced": ann}
    except Exception:  # noqa: BLE001 — cache rusak/tidak ada = tidak ada cache
        return None


def _save_cache(symbols: list[str], announced: list[str] | None) -> None:
    path = cache_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {"v": SCHEMA_VERSION, "saved": datetime.now(_WIB).isoformat(timespec="seconds"),
                   "symbols": symbols, "announced": announced or symbols}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001 — cache bersifat best-effort
        logger.warning("watchlist: gagal menyimpan cache: %s", e)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _warn_once(reason: str, now: float) -> None:
    if reason != _S.warned_reason or now - _S.warned_at >= WARN_REPEAT_SEC:
        logger.warning("watchlist: %s -> pakai %s (%d coin)", reason, _S.status, len(_S.symbols or []))
        _S.warned_reason, _S.warned_at = reason, now


def refresh(default: Iterable[str], force: bool = False, now: float | None = None) -> dict[str, Any]:
    """Segarkan daftar bila perlu. Tidak pernah melempar. Return {symbols, status, reason, changed}."""
    now = time.time() if now is None else now
    default_list = list(default)
    with _lock:
        first = _S.symbols is None
        if not first and not force and now - _S.last_stat < STAT_INTERVAL_SEC:
            return _result(False)
        _S.last_stat = now
        path = file_path()
        sig: tuple | None
        stat_err = ""
        try:
            st = os.stat(path)
            sig = (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError as e:
            sig, stat_err = None, f"file tidak bisa dibaca ({e.__class__.__name__})"
        if not (first or force or sig != _S.sig or now - _S.last_read >= REREAD_INTERVAL_SEC):
            return _result(False)
        _S.last_read = now
        prev = _S.symbols
        cached = _load_cache() if first else None
        if first:
            _S.announced = (cached or {}).get("announced") or (cached or {}).get("symbols") or list(default_list)

        symbols: list[str] | None = None
        reason = ""
        try:
            if sig is None:
                raise OSError(stat_err)
            with open(path, "r", encoding="utf-8") as f:   # mode baca saja
                obj = json.load(f)
            symbols = parse_symbols(obj)
            _S.file_ts = obj.get("ts") if isinstance(obj.get("ts"), str) else None
        except Exception as e:  # noqa: BLE001
            reason = stat_err or f"{type(e).__name__}: {e}"
        _S.sig = sig

        if symbols is not None:
            _S.good = symbols
            _S.status, _S.reason = "porto", ""
            _S.warned_reason = None
            if first or prev != symbols:
                _save_cache(symbols, _S.announced)
        else:
            if _S.good:
                symbols, _S.status = list(_S.good), "cache"
            else:
                cached = cached or _load_cache()
                if cached:
                    symbols, _S.status = list(cached["symbols"]), "cache"
                    _S.good = list(symbols)
                else:
                    symbols, _S.status = default_list, "default"
            _S.reason = reason
            _S.symbols = symbols
            _warn_once(reason, now)

        _S.symbols = symbols
        changed = prev is not None and prev != symbols
        if changed or first:
            add = [s for s in symbols if s not in (prev or [])]
            rem = [s for s in (prev or []) if s not in symbols]
            logger.info("watchlist: %s (%d coin) sumber=%s%s", "berubah" if changed else "dimuat",
                        len(symbols), _S.status, f" +{add} -{rem}" if changed else "")
        return _result(changed)


def _result(changed: bool) -> dict[str, Any]:
    return {"symbols": list(_S.symbols or []), "status": _S.status, "reason": _S.reason, "changed": changed}


def pending_notice() -> dict[str, Any] | None:
    """Selisih daftar saat ini vs daftar terakhir yang sudah diumumkan; None bila sama."""
    with _lock:
        if _S.symbols is None or _S.announced is None:
            return None
        added = [s for s in _S.symbols if s not in _S.announced]
        removed = [s for s in _S.announced if s not in _S.symbols]
        if not added and not removed:
            return None
        return {"added": added, "removed": removed, "total": len(_S.symbols), "symbols": list(_S.symbols)}


def mark_announced() -> None:
    with _lock:
        if _S.symbols is None:
            return
        _S.announced = list(_S.symbols)
        _save_cache(_S.symbols, _S.announced)


def get_status() -> dict[str, Any]:
    with _lock:
        return {"status": _S.status, "reason": _S.reason, "count": len(_S.symbols or []),
                "path": file_path(), "file_ts": _S.file_ts}
