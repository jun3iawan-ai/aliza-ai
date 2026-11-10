"""Siklus BTC: konteks dasar/puncak jangka panjang (harian). BUKAN sinyal entry, TIDAK masuk skor Konteks Market.

Sumber data gratis: Coin Metrics Community (PriceUSD, CapMVRVCur, HashRate) + FRED VIXCLS.
Indikator dan ambang ditetapkan dari backtest 10 Nov 2026 (docs: 03-analisis/30) — bulat, tidak di-tuning.
Zona = ringkasan heuristik; kombinasi indikator TIDAK terbukti lebih baik dari indikator tunggal di backtest,
jadi zona dipakai sebagai konteks, bukan trigger.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
HALVINGS = (date(2012, 11, 28), date(2016, 7, 9), date(2020, 5, 11), date(2024, 4, 20))
HALVING_WINDOW = (480, 560)         # hari pasca-halving tempat 3 puncak terakhir terjadi (371-546, rentang dilebarkan)
LOOKBACK_DAYS = 1000
SIGNAL_RECENT_DAYS = 30             # sinyal "peristiwa" (hash ribbon, DMA breakout) dianggap aktif 30 hari
VIX_RECENT_DAYS = 5
PI_NEAR = 0.95                      # MA111 >= 95% dari 2xMA350 -> Rawan Puncak
ZONES = {"akumulasi": "Akumulasi", "netral": "Netral", "rawan_puncak": "Rawan Puncak"}
COINMETRICS_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
HTTP_TIMEOUT = 60
MIN_ROWS = 420                      # MA350 + ruang untuk hash ribbon


def cache_path() -> str:
    return os.getenv("ALIZA_CYCLE_CACHE") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "btc_cycle_last.json"
    )


# ---------------------------------------------------------------- data
def _fetch_coinmetrics(days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    import requests

    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    params: dict | None = dict(assets="btc", metrics="PriceUSD,CapMVRVCur,HashRate", frequency="1d",
                               start_time=start, page_size=10000)
    url: str | None = COINMETRICS_URL
    rows: list[dict] = []
    while url:
        r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        j = r.json()
        rows += j.get("data", [])
        url, params = j.get("next_page_url"), None
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("Coin Metrics: data kosong")
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
    df = df.set_index("time").drop(columns=["asset"]).astype(float)
    return df.rename(columns={"PriceUSD": "p", "CapMVRVCur": "mvrv", "HashRate": "hr"})


def _fetch_vix(days: int = LOOKBACK_DAYS) -> pd.Series | None:
    key = os.getenv("FRED_API_KEY")
    if not key:
        return None
    try:
        import requests

        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        r = requests.get(FRED_URL, params=dict(series_id="VIXCLS", api_key=key, file_type="json",
                                               observation_start=start), timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        return pd.Series({pd.Timestamp(o["date"]): float(o["value"]) for o in obs if o.get("value") not in (None, ".")})
    except Exception as e:  # noqa: BLE001
        logger.warning("btc_cycle: VIX gagal diambil: %s", e)
        return None


def fetch_frame() -> pd.DataFrame:
    """Frame harian: p, mvrv, hr, vix. Gagal Coin Metrics -> exception; gagal VIX -> kolom vix NaN."""
    d = _fetch_coinmetrics()
    vix = _fetch_vix()
    d["vix"] = vix.reindex(d.index).ffill(limit=4) if vix is not None else np.nan
    return d


# ---------------------------------------------------------------- hitung
def _days_since_halving(today: date) -> tuple[int | None, date | None]:
    past = [h for h in HALVINGS if h <= today]
    if not past:
        return None, None
    h = past[-1]
    return (today - h).days, h


def compute_cycle(df: pd.DataFrame) -> dict[str, Any]:
    """Hitung semua indikator dari frame harian. Fungsi murni (tanpa jaringan)."""
    d = df.copy().sort_index()
    d = d[d["p"].notna()]
    if len(d) < MIN_ROWS:
        raise ValueError(f"data kurang: {len(d)} baris (butuh >= {MIN_ROWS})")
    p = d["p"]
    ma = {n: p.rolling(n).mean() for n in (111, 128, 200, 350)}
    hr30, hr60 = d["hr"].rolling(30).mean(), d["hr"].rolling(60).mean()
    last_day = d.index[-1]
    recent = d.index >= last_day - pd.Timedelta(days=SIGNAL_RECENT_DAYS)

    price = float(p.iloc[-1])
    ma111, ma200, ma350, ma128 = (float(ma[n].iloc[-1]) for n in (111, 200, 350, 128))
    pi_ratio = ma111 / (2 * ma350)
    mayer = price / ma200

    mv = d["mvrv"].dropna()
    mvrv = float(mv.iloc[-1]) if len(mv) else None
    mvrv_date = mv.index[-1].date().isoformat() if len(mv) else None

    vix_s = d["vix"].dropna() if "vix" in d else pd.Series(dtype=float)
    vix_now = float(vix_s.iloc[-1]) if len(vix_s) else None
    vix_recent_max = (float(d["vix"].iloc[-VIX_RECENT_DAYS:].max())
                      if len(vix_s) and d["vix"].iloc[-VIX_RECENT_DAYS:].notna().any() else None)

    # hash ribbon: MA30 menembus atas MA60 setelah fase capitulation (MA30<MA60 dalam 60 hari terakhir)
    hrx = (hr30 > hr60) & (hr30.shift(1) <= hr60.shift(1)) & ((hr30 < hr60).rolling(60).max() > 0)
    # breakout DMA: close tembus atas MA128 & MA200 setelah berada di bawah keduanya dalam 90 hari
    top = np.maximum(ma[128], ma[200])
    below = (p < np.minimum(ma[128], ma[200])).rolling(90).max() > 0
    cross = (p > top) & (p.shift(1) <= top.shift(1)) & below

    def _last(s: pd.Series) -> str | None:
        t = s[s.fillna(False)]
        return t.index[-1].date().isoformat() if len(t) else None

    signals = {
        "mvrv_lt1": {"active": bool(mvrv is not None and mvrv < 1.0),
                     "detail": f"MVRV {mvrv:.2f}" if mvrv is not None else "MVRV tidak tersedia"},
        "vix_gt30": {"active": bool(vix_recent_max is not None and vix_recent_max > 30),
                     "detail": f"VIX {vix_now:.1f}" if vix_now is not None else "VIX tidak tersedia"},
        "hash_ribbon": {"active": bool(hrx[recent].any()), "detail": f"terakhir {_last(hrx) or '-'}"},
        "dma_breakout": {"active": bool(cross[recent].any()), "detail": f"terakhir {_last(cross) or '-'}"},
    }
    base_count = sum(1 for s in signals.values() if s["active"])

    hd, hdate = _days_since_halving(last_day.date())
    in_window = hd is not None and HALVING_WINDOW[0] <= hd <= HALVING_WINDOW[1]
    puncak = {
        "pi_ratio": round(pi_ratio, 3),
        "pi_cross": bool(pi_ratio >= 1.0),
        "pi_near": bool(pi_ratio >= PI_NEAR),
        "halving_days": hd,
        "halving_date": hdate.isoformat() if hdate else None,
        "in_halving_window": bool(in_window),
    }

    if puncak["pi_near"]:
        zone = "rawan_puncak"
    elif signals["mvrv_lt1"]["active"] or base_count >= 2:
        zone = "akumulasi"
    else:
        zone = "netral"

    return {
        "v": 1,
        "asof": last_day.date().isoformat(),
        "ts": datetime.now(WIB).isoformat(timespec="seconds"),
        "zone": zone,
        "zone_label": ZONES[zone],
        "price": round(price, 2),
        "mayer": round(mayer, 2),
        "ma200": round(ma200, 2),
        "above_ma200": bool(price > ma200),
        "above_ma128": bool(price > ma128),
        "mvrv": round(mvrv, 2) if mvrv is not None else None,
        "mvrv_date": mvrv_date,
        "vix": round(vix_now, 1) if vix_now is not None else None,
        "pi": {"ma111": round(ma111, 0), "ma350x2": round(2 * ma350, 0)},
        "dasar": signals,
        "dasar_count": base_count,
        "puncak": puncak,
    }


# ---------------------------------------------------------------- simpan / baca
def save(result: dict[str, Any], path: str | None = None) -> None:
    path = path or cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".btc_cycle.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_last(path: str | None = None) -> dict[str, Any] | None:
    try:
        with open(path or cache_path(), encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) and j.get("v") == 1 and j.get("zone") in ZONES else None
    except (OSError, ValueError):
        return None


def refresh(fetch: Callable[[], pd.DataFrame] = fetch_frame, path: str | None = None) -> dict[str, Any]:
    """Ambil data, hitung, simpan. Exception diteruskan ke pemanggil (job akan log, cache lama tetap)."""
    result = compute_cycle(fetch())
    save(result, path)
    return result


def zone_changed(prev: str | None, cur: str) -> bool:
    """True bila zona berubah dari zona sebelumnya. Observasi pertama (prev None) = baseline, bukan perubahan."""
    return prev is not None and prev != cur


CONFIRM_DAYS = 3   # zona baru harus bertahan N hari data berbeda sebelum alert (anti bolak-balik)


def advance_zone(confirmed: str | None, pending: dict | None, cur: str, asof: str,
                 need: int = CONFIRM_DAYS) -> tuple[dict | None, str | None]:
    """Mesin konfirmasi zona. Return (pending_baru, zona_asal_untuk_alert).

    - cur == confirmed -> pending dibuang (perubahan sementara tidak pernah dialert).
    - cur != confirmed -> hitung hari DATA berbeda (``asof``) berturut-turut untuk zona itu;
      menjalankan job dua kali pada data yang sama tidak menambah hitungan.
    - alert hanya bila hitungan >= need; pemanggil mengubah ``confirmed`` HANYA setelah kirim sukses.
    """
    if confirmed is None or cur == confirmed:
        return None, None
    p = pending if isinstance(pending, dict) else {}
    if p.get("zone") == cur:
        days = int(p.get("days") or 1)
        if p.get("asof") != asof:
            days += 1
    else:
        days = 1
    new = {"zone": cur, "asof": asof, "days": days}
    return new, (confirmed if days >= need else None)


def age_hours(result: dict[str, Any]) -> float | None:
    try:
        return (datetime.now(WIB) - datetime.fromisoformat(result["ts"])).total_seconds() / 3600
    except (KeyError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------- tampilan
_ICON = {"akumulasi": "🟢", "netral": "🟡", "rawan_puncak": "🔴"}
_NAMES = {"mvrv_lt1": "MVRV < 1", "vix_gt30": "VIX > 30", "hash_ribbon": "Hash ribbon pulih", "dma_breakout": "Breakout MA128/200"}


def format_telegram(r: dict[str, Any], *, changed_from: str | None = None, stable_days: int | None = None) -> str:
    p = r["puncak"]
    lines = []
    if changed_from:
        tail = f" (bertahan {stable_days} hari)" if stable_days else ""
        lines.append(f"🔔 Zona siklus BTC berubah: {ZONES.get(changed_from, changed_from)} → {r['zone_label']}{tail}")
    lines += [
        f"{_ICON[r['zone']]} Siklus BTC: {r['zone_label']} (data {r['asof']})",
        f"Harga ${r['price']:,.0f} | Mayer {r['mayer']} | {'di atas' if r['above_ma200'] else 'di bawah'} MA200 (${r['ma200']:,.0f})",
        "",
        f"Sinyal dasar aktif: {r['dasar_count']}/4",
    ]
    for k, s in r["dasar"].items():
        lines.append(f"• {'✅' if s['active'] else '▫️'} {_NAMES[k]} — {s['detail']}")
    lines += [
        "",
        f"Puncak: Pi Cycle {p['pi_ratio']:.0%} dari pemicu (MA111 ${r['pi']['ma111']:,.0f} vs 2×MA350 ${r['pi']['ma350x2']:,.0f})",
        f"Halving: hari ke-{p['halving_days']} pasca {p['halving_date']}"
        + (" (di jendela puncak historis)" if p["in_halving_window"] else ""),
        "",
        "ℹ️ Konteks jangka panjang, bukan sinyal entry. Backtest: sampel kecil (N 4–20), in-sample; "
        "Pi Cycle satu-satunya penanda puncak yang konsisten.",
    ]
    return "\n".join(lines)


def export_view(r: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ringkasan untuk field `cycle` di context.json (additive)."""
    if not r:
        return None
    return {
        "zone": r["zone"], "zone_label": r["zone_label"], "asof": r["asof"], "ts": r["ts"],
        "price": r["price"], "mayer": r["mayer"], "above_ma200": r["above_ma200"],
        "mvrv": r["mvrv"], "vix": r["vix"], "dasar_count": r["dasar_count"],
        "active": [k for k, s in r["dasar"].items() if s["active"]],
        "pi_ratio": r["puncak"]["pi_ratio"], "halving_days": r["puncak"]["halving_days"],
    }
