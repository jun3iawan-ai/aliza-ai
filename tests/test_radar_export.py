"""Radar -> context.json (dibaca dashboard Porto): satu sumber dengan Telegram, additive, aman saat gagal."""

import json
import os
import stat
from datetime import datetime

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.market import market_context_export as mcx
from engine.market import radar_export as rx
from engine.market.market_radar_pro_analyzer import format_radar_report, generate_radar_pro

TS = datetime(2026, 10, 14, 5, 21, 30)   # naive UTC -> 12:21:30 WIB


def _m(t4, t1, rsi, **kw):
    d = {"trend": t4, "trend_4h": t4, "trend_1d": t1, "trend_alignment": "X", "rsi": rsi}
    d.update(kw)
    return d


def _snap(ts=TS):
    return {"timestamp": ts, "data": {
        "SUI": _m("SIDEWAYS", "SIDEWAYS", 45.34),
        "BTC": _m("BULLISH", "SIDEWAYS", 54.06),
        "ETH": _m("BEARISH", "BEARISH", 45.0),
        "HYPE": _m("BULLISH", "UNKNOWN", 61.23),
        "ERR": {"error": "x"},
    }}


COINS = ["SUI", "BTC", "ETH", "HYPE", "BONE"]


@pytest.fixture
def snap(monkeypatch):
    s = _snap()
    from engine.market import market_snapshot_engine as mse
    monkeypatch.setattr(mse, "get_market_snapshot", lambda: s)
    return s


def test_semua_simbol_ada_dan_bone_na(snap):
    r = rx.build_radar(snap, COINS)
    assert list(r["coins"]) == COINS
    assert r["coins"]["BONE"] == {"t4h": "na", "t1d": "na", "rsi4h": None, "cond": None,
                                  "strong": False, "label": None, "src": None}


def test_nilai_dan_aturan(snap):
    c = rx.build_radar(snap, COINS)["coins"]
    assert (c["SUI"]["t4h"], c["SUI"]["t1d"], c["SUI"]["rsi4h"], c["SUI"]["strong"]) == ("side", "side", 45.3, False)
    assert (c["BTC"]["t4h"], c["BTC"]["t1d"], c["BTC"]["rsi4h"]) == ("up", "side", 54.1)
    assert c["ETH"]["t4h"] == "down" and c["ETH"]["t1d"] == "down" and c["ETH"]["strong"] is True
    assert c["HYPE"]["t1d"] == "na" and c["HYPE"]["strong"] is False
    for v in c.values():
        assert v["t4h"] in ("up", "down", "side", "na") and v["t1d"] in ("up", "down", "side", "na")
        assert v["cond"] in ("uptrend", "downtrend", None)
        assert v["rsi4h"] is None or isinstance(v["rsi4h"], float)


def test_cond_dari_label_telegram(snap):
    c = rx.build_radar(snap, COINS)["coins"]
    assert c["BTC"]["cond"] == "uptrend" and c["BTC"]["label"] == "📈 Uptrend"
    assert c["ETH"]["cond"] == "downtrend"
    assert c["SUI"]["cond"] is None and c["SUI"]["label"] is None
    snap["data"]["BTC"]["rsi"] = 70.0                     # bullish & RSI>60 -> Momentum, bukan uptrend
    b = rx.build_radar(snap, COINS)["coins"]["BTC"]
    assert b["cond"] is None and "Momentum" in b["label"]


def test_rsi_null_bila_4h_tidak_cukup(snap):
    snap["data"]["BTC"]["trend_4h"] = "UNKNOWN"
    assert rx.build_radar(snap, COINS)["coins"]["BTC"]["rsi4h"] is None


def test_sama_dengan_pesan_telegram(snap):
    """Arah, RSI, kondisi, bintang di JSON == baris pesan /radar dari snapshot yang sama."""
    r = rx.build_radar(snap, COINS)["coins"]
    arrow = {"up": "↑", "down": "↓", "side": "→", "na": "?"}
    for line in format_radar_report(generate_radar_pro(snap)).splitlines():
        parts = line.split()
        if len(parts) < 7 or parts[1] != "4H":
            continue
        coin = parts[0]
        if coin not in r:
            continue
        assert parts[2] == arrow[r[coin]["t4h"]] and parts[4] == arrow[r[coin]["t1d"]]
        if r[coin]["rsi4h"] is not None:
            assert parts[6] == f"{r[coin]['rsi4h']:.0f}"
        assert line.endswith("⭐") == r[coin]["strong"]
        assert (r[coin]["label"] or "—") in line


def test_ts_wib_dan_interval(snap):
    r = rx.build_radar(snap, COINS)
    assert r["ts"] == "2026-10-14T12:21:30+07:00" and r["interval_min"] == 1
    assert set(r["def"]) == {"t4h", "t1d", "rsi4h", "cond", "strong"} and all(r["def"].values())


def test_tanpa_snapshot_none():
    assert rx.build_radar({"timestamp": None, "data": {}}, COINS) is None


def test_src_futures_untuk_coin_tanpa_spot(snap):
    from engine.market import coin_support
    coin_support.set_data_for_tests({"SUIUSDT", "BTCUSDT"}, {"SUI": "SUIUSDT", "BTC": "BTCUSDT", "FARTCOIN": "FARTCOINUSDT"})
    snap["data"]["FARTCOIN"] = _m("BULLISH", "BULLISH", 55.0)
    c = rx.build_radar(snap, ["SUI", "FARTCOIN", "BONE"])["coins"]
    assert c["SUI"]["src"] == "binance:SUIUSDT"
    assert c["FARTCOIN"]["src"] == "binance-futures:FARTCOINUSDT"
    assert c["BONE"]["src"] is None


# ---------- context.json ----------
def _res(score=54):
    return {"total_score": score, "label": "Neutral", "emoji": "⚪", "summary": "s", "components": {},
            "timestamp": "t", "timestamp_iso": "2026-10-14T12:20:00+07:00", "failed_components": 0}


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def test_export_memuat_radar_field_lain_tetap(tmp_path, monkeypatch, snap):
    monkeypatch.setattr(rx, "get_polling_coins", lambda: COINS, raising=False)
    from engine.market import market_universe as mu
    monkeypatch.setattr(mu, "get_polling_coins", lambda coins=None, now=None: COINS)
    p = str(tmp_path / "context.json")
    assert mcx.export_context(_res(), p)
    d = _load(p)
    base = mcx.build_payload(_res())
    assert d["v"] == 1 and list(d)[:len(base)] == list(base)       # urutan & set field lama sama
    assert {k: d[k] for k in base} == base
    assert list(d["radar"]["coins"]) == COINS and d["radar"]["ts"] == "2026-10-14T12:21:30+07:00"
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o644 and not os.path.exists(p + ".tmp")


def test_radar_gagal_skor_tetap_tertulis_radar_lama_dipertahankan(tmp_path, monkeypatch, snap):
    from engine.market import market_universe as mu
    monkeypatch.setattr(mu, "get_polling_coins", lambda coins=None, now=None: COINS)
    p = str(tmp_path / "context.json")
    mcx.export_context(_res(54), p)
    old = _load(p)["radar"]
    monkeypatch.setattr(rx, "build_radar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert mcx.export_context(_res(61), p)
    d = _load(p)
    assert d["score"] == 61 and d["radar"] == old and d["radar"]["ts"] == "2026-10-14T12:21:30+07:00"


def test_radar_belum_ada_field_dihilangkan(tmp_path, monkeypatch):
    monkeypatch.setattr(rx, "build_radar", lambda *a, **k: None)
    p = str(tmp_path / "context.json")
    assert mcx.export_context(_res(), p)
    assert "radar" not in _load(p)


def test_refresh_radar_hanya_ganti_radar(tmp_path, monkeypatch, snap):
    from engine.market import market_universe as mu
    monkeypatch.setattr(mu, "get_polling_coins", lambda coins=None, now=None: COINS)
    p = str(tmp_path / "context.json")
    mcx.export_context(_res(), p)
    before = _load(p)
    snap["timestamp"] = datetime(2026, 10, 14, 5, 22, 30)
    snap["data"]["SUI"]["rsi"] = 70.5
    assert mcx.refresh_radar(p)
    after = _load(p)
    assert {k: v for k, v in after.items() if k != "radar"} == {k: v for k, v in before.items() if k != "radar"}
    assert after["radar"]["ts"] == "2026-10-14T12:22:30+07:00" and after["radar"]["coins"]["SUI"]["rsi4h"] == 70.5
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o644 and not os.path.exists(p + ".tmp")


def test_refresh_radar_tidak_membuat_atau_merusak_file(tmp_path, snap):
    p = str(tmp_path / "context.json")
    assert mcx.refresh_radar(p) is False and not os.path.exists(p)          # belum ada -> tidak dibuat
    open(p, "w").write("{rusak")
    assert mcx.refresh_radar(p) is False and open(p).read() == "{rusak"
    open(p, "w").write(json.dumps({"v": 2, "x": 1}))
    assert mcx.refresh_radar(p) is False and _load(p) == {"v": 2, "x": 1}


def test_refresh_radar_gagal_file_tetap(tmp_path, monkeypatch, snap):
    from engine.market import market_universe as mu
    monkeypatch.setattr(mu, "get_polling_coins", lambda coins=None, now=None: COINS)
    p = str(tmp_path / "context.json")
    mcx.export_context(_res(), p)
    raw = open(p).read()
    monkeypatch.setattr(rx, "build_radar", lambda *a, **k: None)
    assert mcx.refresh_radar(p) is False and open(p).read() == raw
