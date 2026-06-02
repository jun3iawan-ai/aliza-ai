"""
Binance USDT-M Futures: funding rate, open interest (USD), morning-brief section,
dan alert kondisi ekstrem (cooldown per coin per kondisi).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "AlizaAI"}
PREMIUM_INDEX_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
OPEN_INTEREST_URL = "https://fapi.binance.com/fapi/v1/openInterest"
OPEN_INTEREST_HIST_URL = "https://fapi.binance.com/futures/data/openInterestHist"
GLOBAL_LS_RATIO_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
TIMEOUT = 15
OI_LS_HTTP_TIMEOUT = 8.0

WATCHLIST = ["BTC", "ETH", "BNB", "SOL", "XRP"]
SYMBOL_MAP = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
    "SOL": "SOLUSDT",
    "XRP": "XRPUSDT",
}
FUNDING_ALERT_THRESHOLD = 0.001  # |FR| > ini → ekstrem (setara ±0.1% jika FR sebagai desimal fee)
COOLDOWN_HOURS = 4

LABEL_THRESHOLD = 0.001  # ±0.1% tampilan vs FR mentah — sama dengan FUNDING_ALERT_THRESHOLD
CACHE_TTL_SEC = 15 * 60  # 15 menit

_funding_cache: dict[str, dict[str, Any]] = {}
_oi_cache: dict[str, dict[str, Any]] = {}

# Cooldown alert: key = "{COIN}|{condition}"
_last_alert_ts: dict[str, float] = {}
ALERT_COOLDOWN_SEC = COOLDOWN_HOURS * 3600


def _safe_float(val: Any, default: float | None = None) -> float | None:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fmt_oi_usd(v: float) -> str:
    ax = abs(v)
    if ax >= 1e9:
        return f"{v / 1e9:.2f}B"
    if ax >= 1e6:
        return f"{v / 1e6:.2f}M"
    if ax >= 1e3:
        return f"{v / 1e3:.2f}K"
    return f"{v:.2f}"


def _next_funding_time_str(ms: Any) -> str:
    """nextFundingTime (ms) → string singkat WIB jika bisa."""
    iv = _safe_float(ms, None)
    if iv is None:
        return "—"
    try:
        sec = int(iv / 1000.0)
        dt = datetime.utcfromtimestamp(sec)
        if ZoneInfo is not None:
            try:
                wib = datetime.fromtimestamp(sec, ZoneInfo("Asia/Jakarta"))
                return wib.strftime("%Y-%m-%d %H:%M WIB")
            except Exception:
                pass
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "—"


def get_funding_rate_data(symbol: str) -> dict[str, Any] | None:
    """
    Premium index: lastFundingRate, nextFundingTime, markPrice.
    Cache per coin TTL 15 menit.
    """
    coin = symbol.strip().upper()
    sym = SYMBOL_MAP.get(coin)
    if not sym:
        return None
    now = time.time()
    cached = _funding_cache.get(coin)
    if cached and now - cached.get("ts", 0) < CACHE_TTL_SEC:
        return dict(cached.get("data") or {})

    try:
        r = requests.get(
            PREMIUM_INDEX_URL,
            params={"symbol": sym},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("funding_rate_monitor: premiumIndex HTTP %s %s", r.status_code, sym)
            return None
        d = r.json()
        if not isinstance(d, dict):
            return None
        fr = _safe_float(d.get("lastFundingRate"))
        mp = _safe_float(d.get("markPrice"))
        if fr is None or mp is None or mp <= 0:
            return None
        nft = d.get("nextFundingTime")
        out = {
            "funding_rate": fr,
            "mark_price": mp,
            "next_funding_time": _next_funding_time_str(nft),
            "next_funding_time_raw": nft,
        }
        _funding_cache[coin] = {"data": out, "ts": now}
        return out
    except Exception as e:
        logger.warning("funding_rate_monitor: premiumIndex %s: %s", sym, e)
        return None


def get_open_interest(symbol: str) -> float | None:
    """
    Open interest (kontrak) × mark price → notional USD.
    Cache hasil per coin TTL 15 menit (terpisah dari cache funding struct).
    """
    coin = symbol.strip().upper()
    sym = SYMBOL_MAP.get(coin)
    if not sym:
        return None
    now = time.time()
    oi_cached = _oi_cache.get(coin)
    if oi_cached and now - oi_cached.get("ts", 0) < CACHE_TTL_SEC:
        v = oi_cached.get("oi_usd")
        if isinstance(v, (int, float)) and v >= 0:
            return float(v)

    fd = get_funding_rate_data(coin)
    if not fd:
        return None
    mark = fd.get("mark_price")
    if mark is None or mark <= 0:
        return None

    try:
        r = requests.get(
            OPEN_INTEREST_URL,
            params={"symbol": sym},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            logger.warning("funding_rate_monitor: openInterest HTTP %s %s", r.status_code, sym)
            return None
        d = r.json()
        if not isinstance(d, dict):
            return None
        oi = _safe_float(d.get("openInterest"))
        if oi is None or oi < 0:
            return None
        oi_usd = float(oi) * float(mark)
        _oi_cache[coin] = {"oi_usd": oi_usd, "ts": now}
        return oi_usd
    except Exception as e:
        logger.warning("funding_rate_monitor: openInterest %s: %s", sym, e)
        return None


def get_oi_delta_and_ls_ratio(coins: list[str]) -> dict[str, dict[str, Any]]:
    """
    Fetch OI delta 24h dan Long/Short ratio dari Binance Futures API.
    Return dict: {coin: {"oi_delta_pct": float | None, "ls_ratio": float | None}}
    Fallback None per coin jika gagal.

    Endpoints:
    - OI history: openInterestHist (1h, limit 25) → delta vs 24h lalu
    - L/S ratio: globalLongShortAccountRatio (1h, limit 1)
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        import httpx
    except ImportError:
        for c in coins:
            cu = str(c).strip().upper()
            out[cu] = {"oi_delta_pct": None, "ls_ratio": None}
        return out

    for raw in coins:
        coin = str(raw).strip().upper()
        sym = SYMBOL_MAP.get(coin)
        if not sym:
            out[coin] = {"oi_delta_pct": None, "ls_ratio": None}
            continue
        oi_delta_pct: float | None = None
        ls_ratio: float | None = None
        try:
            with httpx.Client(timeout=OI_LS_HTTP_TIMEOUT) as client:
                r = client.get(
                    OPEN_INTEREST_HIST_URL,
                    params={"symbol": sym, "period": "1h", "limit": 25},
                    headers=HEADERS,
                )
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) >= 2:
                        rows = sorted(data, key=lambda x: int(x.get("timestamp") or 0))
                        first = rows[0]
                        last = rows[-1]
                        oi_old = _safe_float(first.get("sumOpenInterestValue"))
                        if oi_old is None:
                            oi_old = _safe_float(first.get("sumOpenInterest"))
                        oi_new = _safe_float(last.get("sumOpenInterestValue"))
                        if oi_new is None:
                            oi_new = _safe_float(last.get("sumOpenInterest"))
                        if oi_old is not None and oi_old > 0 and oi_new is not None:
                            oi_delta_pct = round((oi_new - oi_old) / oi_old * 100.0, 2)

                r2 = client.get(
                    GLOBAL_LS_RATIO_URL,
                    params={"symbol": sym, "period": "1h", "limit": 1},
                    headers=HEADERS,
                )
                if r2.status_code == 200:
                    data2 = r2.json()
                    if isinstance(data2, list) and len(data2) > 0:
                        row = sorted(data2, key=lambda x: int(x.get("timestamp") or 0))[-1]
                        ls_ratio = _safe_float(row.get("longShortRatio"))
        except Exception as e:
            logger.debug("get_oi_delta_and_ls_ratio %s: %s", sym, e)

        out[coin] = {"oi_delta_pct": oi_delta_pct, "ls_ratio": ls_ratio}

    return out


def get_all_funding_data() -> dict[str, dict[str, Any]]:
    """
    Gabungan funding + OI USD per coin. Coin gagal di-skip.
    next_funding_time sebagai string untuk brief / tabel.
    """
    out: dict[str, dict[str, Any]] = {}
    for coin in WATCHLIST:
        fd = get_funding_rate_data(coin)
        if not fd:
            continue
        oi_usd = get_open_interest(coin)
        row = {
            "funding_rate": float(fd["funding_rate"]),
            "mark_price": float(fd["mark_price"]),
            "next_funding_time": fd.get("next_funding_time") or "—",
        }
        if oi_usd is not None:
            row["oi_usd"] = float(oi_usd)
        else:
            row["oi_usd"] = None
        out[coin] = row
    return out


def _fr_label(fr: float) -> str:
    """Label singkat untuk baris brief."""
    if fr > LABEL_THRESHOLD:
        return "⚠️ Long dominan"
    if fr < -LABEL_THRESHOLD:
        return "⚠️ Short dominan"
    return "—"


def _fr_pct_str(fr: float) -> str:
    """FR sebagai persen (×100), 4 desimal."""
    return f"{fr * 100:+.4f}%"


def _ls_ratio_interpret(ls: float) -> str:
    """Interpretasi singkat rasio long/short (global accounts)."""
    if ls < 0.8:
        return "shorts sangat dominan → potensi short squeeze"
    if ls < 1.0:
        return "shorts dominan"
    if ls <= 1.2:
        return "seimbang"
    return "longs dominan → hati-hati long squeeze"


def format_funding_section_for_brief() -> str:
    """Satu section teks untuk morning brief."""
    data = get_all_funding_data()
    oi_ls_map: dict[str, dict[str, Any]] = {}
    try:
        oi_ls_map = get_oi_delta_and_ls_ratio(list(WATCHLIST))
    except Exception as e:
        logger.debug("format_funding_section_for_brief get_oi_delta_and_ls_ratio: %s", e)
        oi_ls_map = {}

    lines = ["🔄 Funding Rate & OI"]
    if not data:
        return "🔄 Funding Rate & OI\nData tidak tersedia"
    for coin in WATCHLIST:
        row = data.get(coin)
        if not row:
            continue
        fr = row.get("funding_rate")
        oi = row.get("oi_usd")
        oi_row = oi_ls_map.get(coin) or {}
        oi_delta_pct = oi_row.get("oi_delta_pct")
        ls_r = oi_row.get("ls_ratio")
        if fr is None:
            lines.append(f"{coin} FR: — | OI: — | L/S: N/A  —")
            continue
        oi_s = f"${_fmt_oi_usd(oi)}" if oi is not None else "$—"
        if oi is not None:
            if oi_delta_pct is not None:
                oi_part = f"{oi_s} ({oi_delta_pct:+.1f}% 24h)"
            else:
                oi_part = f"{oi_s} (N/A 24h)"
        else:
            oi_part = oi_s
        ls_s = f"{float(ls_r):.2f}" if ls_r is not None else "N/A"
        lines.append(
            f"{coin} FR: {_fr_pct_str(fr)} | OI: {oi_part} | L/S: {ls_s}  {_fr_label(fr)}"
        )
    if len(lines) <= 1:
        return "🔄 Funding Rate & OI\nData tidak tersedia"

    # Auto-interpret funding divergence
    interpretations = []
    if data:
        neg_coins = [c for c in WATCHLIST if data.get(c) and (data[c].get("funding_rate") or 0) < -0.0003]
        pos_coins = [c for c in WATCHLIST if data.get(c) and (data[c].get("funding_rate") or 0) > 0.0003]
        extreme_neg = [c for c in WATCHLIST if data.get(c) and (data[c].get("funding_rate") or 0) < -0.005]
        extreme_pos = [c for c in WATCHLIST if data.get(c) and (data[c].get("funding_rate") or 0) > 0.005]

        if extreme_neg:
            coins_str = ", ".join(extreme_neg)
            interpretations.append(f"⚡ {coins_str} FR sangat negatif = shorts dominan → potensi short squeeze jika harga naik")
        elif neg_coins:
            coins_str = ", ".join(neg_coins)
            interpretations.append(f"📉 {coins_str} FR negatif = shorts paying longs → market positioned short")

        if extreme_pos:
            coins_str = ", ".join(extreme_pos)
            interpretations.append(f"⚠️ {coins_str} FR sangat positif = longs dominan → risiko long squeeze")
        elif pos_coins:
            coins_str = ", ".join(pos_coins)
            interpretations.append(f"📈 {coins_str} FR positif = longs paying shorts → market positioned long")

        if not interpretations:
            interpretations.append("✅ FR semua coin netral — tidak ada positioning ekstrem")

        ls_notes: list[str] = []
        for c in WATCHLIST:
            ls_v = (oi_ls_map.get(c) or {}).get("ls_ratio")
            if ls_v is not None:
                try:
                    ls_f = float(ls_v)
                    ls_notes.append(f"{c} L/S {ls_f:.2f}: {_ls_ratio_interpret(ls_f)}")
                except (TypeError, ValueError):
                    ls_notes.append(f"{c} L/S: N/A")
        if ls_notes:
            interpretations.append("📊 " + " | ".join(ls_notes))

    if interpretations:
        lines.append("💡 " + " | ".join(interpretations))

    return "\n".join(lines)


def format_funding_table_for_command() -> str:
    """Tabel singkat untuk /check_funding."""
    data = get_all_funding_data()
    block = ["📌 Funding & Open Interest (Binance USDT-M)"]
    for coin in WATCHLIST:
        row = data.get(coin)
        if not row:
            block.append(f"{coin}  —")
            continue
        fr = row.get("funding_rate")
        oi = row.get("oi_usd")
        nft = row.get("next_funding_time", "—")
        if fr is None:
            block.append(f"{coin}  —")
            continue
        oi_s = f"${_fmt_oi_usd(oi)}" if oi is not None else "$—"
        block.append(
            f"{coin}  FR {_fr_pct_str(fr)}  OI {oi_s}  Next: {nft}  {_fr_label(fr)}"
        )
    if len(block) <= 1:
        return "📌 Funding & OI: data tidak tersedia (cek koneksi atau Binance Futures)."
    return "\n".join(block)


def check_funding_extremes() -> list[dict[str, Any]]:
    """
    |FR| > FUNDING_ALERT_THRESHOLD → LONG atau SHORT squeeze risk.
    Cooldown per coin per kondisi (LONG_SQUEEZE_RISK / SHORT_SQUEEZE_RISK).
    """
    data = get_all_funding_data()
    now = time.time()
    out: list[dict[str, Any]] = []

    for coin, row in data.items():
        fr = row.get("funding_rate")
        oi_usd = row.get("oi_usd")
        if fr is None:
            continue

        condition = None
        if fr > FUNDING_ALERT_THRESHOLD:
            condition = "LONG_SQUEEZE_RISK"
        elif fr < -FUNDING_ALERT_THRESHOLD:
            condition = "SHORT_SQUEEZE_RISK"
        else:
            continue

        key = f"{coin}|{condition}"
        last = _last_alert_ts.get(key)
        if last is not None and (now - last) < ALERT_COOLDOWN_SEC:
            continue

        _last_alert_ts[key] = now
        out.append(
            {
                "symbol": coin,
                "funding_rate": float(fr),
                "condition": condition,
                "oi_usd": float(oi_usd) if oi_usd is not None else None,
            }
        )
    return out


def format_funding_alert_message(item: dict[str, Any]) -> str:
    """Pesan Telegram untuk satu kondisi ekstrem."""
    coin = item.get("symbol", "—")
    fr = item.get("funding_rate", 0.0)
    cond = item.get("condition", "")
    oi_usd = item.get("oi_usd")

    try:
        fr_f = float(fr)
    except (TypeError, ValueError):
        fr_f = 0.0
    fr_s = _fr_pct_str(fr_f)
    oi_s = f"${_fmt_oi_usd(float(oi_usd))}" if oi_usd is not None else "$—"

    if ZoneInfo is not None:
        try:
            ts = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M WIB")
        except Exception:
            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    else:
        ts = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M WIB")

    if cond == "LONG_SQUEEZE_RISK":
        header = "🔴 LONG SQUEEZE RISK"
        kondisi = "Terlalu banyak long — potensi long squeeze"
        saran = "Pertimbangkan kurangi posisi long dan tunggu koreksi"
    else:
        header = "🟢 SHORT SQUEEZE RISK"
        kondisi = "Terlalu banyak short — potensi short squeeze"
        saran = "Potensi short squeeze — harga bisa balik naik kencang"

    return (
        "⚠️ FUNDING RATE ALERT\n\n"
        f"{header}\n"
        f"Coin: {coin}\n"
        f"Funding Rate: {fr_s}\n"
        f"Open Interest: {oi_s}\n"
        f"Kondisi: {kondisi}\n\n"
        f"💡 {saran}\n\n"
        f"⏰ {ts}\n"
        "——\n"
        "Aliza Engine • Funding Monitor"
    )
