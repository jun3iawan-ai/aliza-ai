"""
Data makro AS dari FRED API (perlu FRED_API_KEY di environment).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import httpx

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"
HEADERS = {}
TIMEOUT = 25            # per percobaan (dulu 60); FRED normalnya < 2 dtk
FETCH_ATTEMPTS = 3      # percobaan awal + 2 retry (HTTP 5xx/429, timeout, body kosong/JSON rusak)
RETRY_DELAYS = (2.0, 5.0)
FAIL_BACKOFF_SEC = 60   # setelah gagal total, jangan hajar FRED lagi selama ini (pakai last-good)
MAX_STALE_SEC = 7 * 86400   # last-good dipakai maksimal 7 hari (data CPI/FEDFUNDS bulanan)
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FETCH_LIMIT = 15  # cukup untuk YoY + 1 bulan sebelumnya (butuh indeks 0–13)
CACHE_TTL_SEC = 6 * 3600

MACRO_SERIES: dict[str, dict[str, Any]] = {
    "CPI": {
        "series_id": "CPIAUCSL",
        "label": "CPI (YoY)",
        "unit": "%",
        "transform": "pct_change_yoy",
    },
    "CORE_PCE": {
        "series_id": "PCEPILFE",
        "label": "Core PCE (YoY)",
        "unit": "%",
        "transform": "pct_change_yoy",
    },
    "NFP": {
        "series_id": "PAYEMS",
        "label": "NFP",
        "unit": "K jobs",
        "transform": "mom_change",
    },
    "FED_RATE": {
        "series_id": "FEDFUNDS",
        "label": "Fed Rate",
        "unit": "%",
        "transform": "latest",
    },
}

_obs_raw_cache: dict[str, dict[str, Any]] = {}

_last_seen_date: dict[str, str] = {}


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None or val == ".":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fred_api_key() -> str | None:
    k = os.getenv("FRED_API_KEY")
    if not k or not str(k).strip():
        return None
    return str(k).strip()


_fail_until: dict[str, float] = {}
_disk_loaded = False
_cache_lock = threading.RLock()
_sleep = time.sleep


def _cache_path() -> str:
    return os.getenv("ALIZA_MACRO_CACHE") or os.path.join(_REPO, "data", "macro_last_good.json")


def reset_for_tests() -> None:
    global _disk_loaded
    with _cache_lock:
        _obs_raw_cache.clear()
        _fail_until.clear()
        _disk_loaded = False


def _valid_obs(obs: Any) -> bool:
    """Observasi layak dipakai/di-cache: list dengan >= 2 titik bernilai angka."""
    return isinstance(obs, list) and len(_parse_valid_series(obs)) >= 2


def _load_disk() -> None:
    """Muat last-good dari disk sekali (selamat dari restart). Pemanggil memegang _cache_lock."""
    global _disk_loaded
    if _disk_loaded:
        return
    _disk_loaded = True
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            data = json.load(f)
        for sid, e in (data.items() if isinstance(data, dict) else []):
            if not isinstance(e, dict) or not _valid_obs(e.get("obs")):
                continue
            ts = _safe_float(e.get("ts"))
            cur = _obs_raw_cache.get(sid)
            if ts is not None and (cur is None or ts > cur.get("ts", 0)):
                _obs_raw_cache[sid] = {"obs": e["obs"], "ts": ts}
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_monitor: cache last-good tidak terbaca (%s)", e)


def _save_disk() -> None:
    """Tulis last-good atomik (mode 600). Gagal tulis tidak boleh mengganggu. Pemanggil memegang _cache_lock."""
    path = _cache_path()
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_obs_raw_cache, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        logger.debug("macro_monitor: gagal menulis cache last-good: %s", e)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _request_once(series_id: str, key: str) -> tuple[list[dict[str, Any]] | None, bool]:
    """Satu permintaan FRED. Return (observasi|None, layak_diulang). Respons gagal/kosong TIDAK pernah di-cache."""
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            r = client.get(
                FRED_OBS_URL,
                params={
                    "series_id": series_id,
                    "api_key": key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": FETCH_LIMIT,
                },
                headers=HEADERS,
            )
            if r.status_code != 200:
                logger.warning("macro_monitor: FRED HTTP %s %s", r.status_code, series_id)
                return None, (r.status_code >= 500 or r.status_code == 429)
            d = r.json()
    except httpx.ReadTimeout as e:
        logger.warning("macro_monitor: FRED ReadTimeout %s: %s", series_id, e)
        return None, True
    except httpx.RemoteProtocolError as e:
        logger.warning("macro_monitor: FRED RemoteProtocolError %s: %s", series_id, e)
        return None, True
    except httpx.HTTPError as e:
        logger.warning("macro_monitor: FRED HTTPError %s: %s", series_id, e)
        return None, True
    except ValueError as e:     # body kosong / bukan JSON
        logger.warning("macro_monitor: FRED JSON parse %s: %s", series_id, e)
        return None, True
    obs = d.get("observations") if isinstance(d, dict) else None
    if not _valid_obs(obs):
        logger.warning("macro_monitor: FRED observasi kosong/tidak valid %s", series_id)
        return None, True
    return obs, False


def _fetch_observations(
    series_id: str, bypass_cache: bool = False
) -> tuple[list[dict[str, Any]] | None, float | None, bool]:
    """Return (observasi, waktu_ambil, stale). Urutan: cache segar (TTL 6 jam) -> FRED (retry+backoff) ->
    last-good (maks 7 hari, stale=True bila lebih tua dari TTL) -> None."""
    key = _fred_api_key()
    if not key:
        return None, None, False
    now = time.time()
    with _cache_lock:
        _load_disk()
        c = _obs_raw_cache.get(series_id)
        if c and not bypass_cache and now - c.get("ts", 0) < CACHE_TTL_SEC:
            return c["obs"], c["ts"], False
        in_backoff = now < _fail_until.get(series_id, 0.0)
    if not in_backoff:
        for attempt in range(FETCH_ATTEMPTS):
            obs, retryable = _request_once(series_id, key)
            if obs is not None:
                ts = time.time()
                with _cache_lock:
                    _obs_raw_cache[series_id] = {"obs": obs, "ts": ts}
                    _fail_until.pop(series_id, None)
                    _save_disk()
                return obs, ts, False
            if not retryable or attempt == FETCH_ATTEMPTS - 1:
                break
            _sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
        with _cache_lock:
            _fail_until[series_id] = time.time() + FAIL_BACKOFF_SEC
    with _cache_lock:
        c = _obs_raw_cache.get(series_id)
    if c:
        age = time.time() - c.get("ts", 0)
        if age <= MAX_STALE_SEC:
            logger.warning("macro_monitor: FRED gagal %s, pakai data terakhir yang berhasil (umur %.1f jam)",
                           series_id, age / 3600)
            return c["obs"], c["ts"], age > CACHE_TTL_SEC
    return None, None, False


def _fetch_observations_raw(series_id: str, bypass_cache: bool = False) -> list[dict[str, Any]] | None:
    """Kompatibilitas: hanya observasinya."""
    return _fetch_observations(series_id, bypass_cache)[0]


def _parse_valid_series(obs: list[dict[str, Any]]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for o in obs:
        if not isinstance(o, dict):
            continue
        dt = o.get("date")
        fv = _safe_float(o.get("value"))
        if dt and fv is not None:
            out.append((str(dt), fv))
    return out


def get_macro_data(
    series_id: str, transform: str, bypass_cache: bool = False
) -> dict[str, Any] | None:
    """
    Ambil observasi FRED, hitung value/change sesuai transform.
    Observations di-cache per series_id TTL 6 jam (bypass_cache=True untuk cek rilis baru).
    Return: value, date, prev_value, prev_date, change, stale, age_sec
    (pct_change_yoy: value = YoY %, change = MoM %).
    FRED gagal -> retry+backoff, lalu data terakhir yang berhasil (maks 7 hari, stale=True).
    """
    if not _fred_api_key():
        return None

    obs_raw, fetched_ts, stale = _fetch_observations(series_id, bypass_cache=bypass_cache)
    if not obs_raw:
        return None
    pts = _parse_valid_series(obs_raw)
    if len(pts) < 2:
        return None

    def yoy_at(idx_now: int) -> float | None:
        if idx_now + 12 >= len(pts):
            return None
        v_now = pts[idx_now][1]
        v_12 = pts[idx_now + 12][1]
        if v_12 == 0:
            return None
        return (v_now - v_12) / v_12 * 100.0

    if transform == "pct_change_yoy":
        if len(pts) < 14:
            return None
        yoy = yoy_at(0)
        mom_pct = None
        if pts[1][1] != 0:
            mom_pct = (pts[0][1] - pts[1][1]) / pts[1][1] * 100.0
        yoy_prev = yoy_at(1)
        if yoy is None:
            return None
        out = {
            "value": float(yoy),
            "date": pts[0][0],
            "prev_value": float(yoy_prev) if yoy_prev is not None else None,
            "prev_date": pts[1][0],
            "change": float(mom_pct) if mom_pct is not None else 0.0,
        }
    elif transform == "mom_change":
        # PAYEMS: selisih level (ribu pekerjaan) antar bulan
        ch = pts[0][1] - pts[1][1]
        out = {
            "value": float(ch),
            "date": pts[0][0],
            "prev_value": float(pts[1][1]),
            "prev_date": pts[1][0],
            "change": float(ch),
        }
    elif transform == "latest":
        ch = pts[0][1] - pts[1][1] if len(pts) >= 2 else 0.0
        out = {
            "value": float(pts[0][1]),
            "date": pts[0][0],
            "prev_value": float(pts[1][1]) if len(pts) >= 2 else None,
            "prev_date": pts[1][0] if len(pts) >= 2 else "",
            "change": float(ch),
        }
    else:
        return None

    out["stale"] = bool(stale)    # True = FRED gagal, ini data terakhir yang berhasil (umur > TTL)
    out["age_sec"] = max(0.0, time.time() - fetched_ts) if fetched_ts else 0.0
    return out


def _get_macro_for_key(macro_key: str, bypass_cache: bool = False) -> dict[str, Any] | None:
    spec = MACRO_SERIES.get(macro_key)
    if not spec:
        return None
    return get_macro_data(spec["series_id"], spec["transform"], bypass_cache=bypass_cache)


def interpret_macro_for_crypto(series: str, value: float, change: float) -> str:
    s = series.upper()
    try:

        def _is_nan(x: float) -> bool:
            return x != x

        if s in ("CPI", "CORE_PCE"):
            if _is_nan(change):
                return "➡️ Dalam range normal"
            if change < 0:
                return "📉 Inflasi turun → dovish signal → bullish crypto"
            if change > 0:
                return "📈 Inflasi naik → hawkish signal → bearish crypto"
            return "➡️ Dalam range normal"
        if s == "NFP":
            v = value
            if v < 150:
                return "📉 Pasar kerja melemah → dovish signal → bullish crypto"
            if v > 250:
                return "📈 Pasar kerja kuat → hawkish signal → bearish crypto"
            return "➡️ Dalam range normal"
        if s == "FED_RATE":
            if change < 0:
                return "📉 Rate cut → bullish crypto"
            if change > 0:
                return "📈 Rate hike → bearish crypto"
            return "➡️ Dalam range normal"
    except Exception:
        pass
    return "➡️ Dalam range normal"


def format_macro_section_for_brief() -> str:
    if not _fred_api_key():
        return "🌐 Makro Ekonomi\nData tidak tersedia — cek FRED_API_KEY"
    lines = ["🌐 Makro Ekonomi"]

    cpi = _get_macro_for_key("CPI")
    if cpi:
        mom = cpi.get("change", 0.0)
        lines.append(
            f"CPI (YoY): {cpi['value']:.1f}% ({mom:+.2f}% MoM) • {cpi['date']}"
        )
    else:
        lines.append("CPI (YoY): — • —")

    pce = _get_macro_for_key("CORE_PCE")
    if pce:
        mom = pce.get("change", 0.0)
        lines.append(
            f"Core PCE (YoY): {pce['value']:.1f}% ({mom:+.2f}%) • {pce['date']}"
        )
    else:
        lines.append("Core PCE (YoY): — • —")

    nfp = _get_macro_for_key("NFP")
    if nfp:
        v = nfp["value"]
        sign = "+" if v >= 0 else ""
        lines.append(f"NFP: {sign}{v:.0f}k jobs • {nfp['date']}")
    else:
        lines.append("NFP: — • —")

    fed = _get_macro_for_key("FED_RATE")
    if fed:
        lines.append(f"Fed Rate: {fed['value']:.2f}% • {fed['date']}")
    else:
        lines.append("Fed Rate: — • —")

    if all(
        _get_macro_for_key(k) is None for k in ("CPI", "CORE_PCE", "NFP", "FED_RATE")
    ):
        return "🌐 Makro Ekonomi\nData tidak tersedia — cek FRED_API_KEY"
    return "\n".join(lines)


def build_macro_check_command_text() -> str:
    if not _fred_api_key():
        return ""
    blocks = ["🌐 Makro AS (FRED)"]
    for mkey in ("CPI", "CORE_PCE", "NFP", "FED_RATE"):
        spec = MACRO_SERIES[mkey]
        d = _get_macro_for_key(mkey)
        if not d:
            blocks.append(f"{spec['label']}: —")
            continue
        inter = interpret_macro_for_crypto(mkey, d.get("value", 0.0), d.get("change", 0.0))
        if mkey in ("CPI", "CORE_PCE"):
            blocks.append(
                f"{spec['label']}: {d['value']:.2f}% (MoM {d['change']:+.2f}%) • {d['date']}\n   {inter}"
            )
        elif mkey == "NFP":
            blocks.append(
                f"{spec['label']}: {d['value']:+.0f}k jobs (vs periode lalu) • {d['date']}\n   {inter}"
            )
        else:
            blocks.append(
                f"{spec['label']}: {d['value']:.2f}% (Δ {d['change']:+.2f}pp) • {d['date']}\n   {inter}"
            )
    return "\n\n".join(blocks)


def initialize_macro_seen_dates() -> None:
    """Seed _last_seen_date tanpa memicu alert (sekali saat startup)."""
    if not _fred_api_key():
        return
    for mkey in MACRO_SERIES:
        d = _get_macro_for_key(mkey)
        if d and d.get("date"):
            _last_seen_date[mkey] = str(d["date"])


def check_new_macro_release() -> list[dict[str, Any]]:
    """
    Deteksi tanggal observasi baru vs cache _last_seen_date.
    """
    if not _fred_api_key():
        return []
    out: list[dict[str, Any]] = []
    for mkey, spec in MACRO_SERIES.items():
        data = _get_macro_for_key(mkey, bypass_cache=True)
        if not data or not data.get("date"):
            continue
        cur_d = str(data["date"])
        prev_s = _last_seen_date.get(mkey)
        if prev_s is None:
            _last_seen_date[mkey] = cur_d
            continue
        if cur_d != prev_s:
            out.append(
                {
                    "series": mkey,
                    "label": spec["label"],
                    "value": float(data["value"]),
                    "change": float(data.get("change", 0.0)),
                    "date": cur_d,
                    "prev_value": data.get("prev_value"),
                }
            )
            _last_seen_date[mkey] = cur_d
    return out


def format_macro_alert_message(item: dict[str, Any]) -> str:
    label = item.get("label", "—")
    series = item.get("series", "")
    val = item.get("value", 0.0)
    ch = item.get("change", 0.0)
    dt = item.get("date", "—")
    pv = item.get("prev_value")

    try:
        val_f = float(val)
        ch_f = float(ch)
    except (TypeError, ValueError):
        val_f = ch_f = 0.0

    if series in ("CPI", "CORE_PCE"):
        val_s = f"{val_f:.2f}%"
        prev_s = f"{float(pv):.2f}%" if pv is not None and pv == pv else "—"
        ch_s = f"{ch_f:+.2f}%"
    elif series == "NFP":
        val_s = f"{val_f:+.0f}k jobs"
        prev_s = f"{float(pv):.0f}k" if pv is not None and pv == pv else "—"
        ch_s = f"{ch_f:+.0f}k"
    else:
        val_s = f"{val_f:.2f}%"
        prev_s = f"{float(pv):.2f}%" if pv is not None and pv == pv else "—"
        ch_s = f"{ch_f:+.2f}pp"

    interp = interpret_macro_for_crypto(series, val_f, ch_f)

    if ZoneInfo is not None:
        try:
            ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        except Exception:
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    else:
        ts = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB")

    return (
        "🌐 MACRO DATA ALERT\n\n"
        f"{label} — Data Baru Rilis\n"
        f"Nilai: {val_s} (sebelumnya: {prev_s})\n"
        f"Perubahan: {ch_s}\n"
        f"Tanggal: {dt}\n\n"
        f"{interp}\n\n"
        "💡 Pantau reaksi BTC dalam 1-4 jam ke depan.\n\n"
        f"⏰ {ts}\n"
        "——\n"
        "Aliza Engine • Macro Monitor"
    )
