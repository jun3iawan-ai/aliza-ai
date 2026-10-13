"""Daftar coin pantau dari Porto (/var/lib/porto/coins.json): loader, fallback, dukungan data, notifikasi."""

import asyncio
import builtins
import json
import os
import time
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.market import coin_support as cs
from engine.market import funding_rate_monitor as frm
from engine.market import market_analyzer as ma
from engine.market import market_context_engine as mce
from engine.market import market_context_export as mcx
from engine.market import market_universe as mu
from engine.market import positioning
from engine.market import watchlist_source as wl

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb

PORTO = ["ADA", "ARB", "ASTER", "BNB", "BONE", "BTC", "ETH", "FARTCOIN", "HYPE", "JTO", "PEPE", "SOL", "SUI",
         "TRX", "XPL", "XRP", "ZEC"]
LEGACY = list(mu.LEGACY_CORE_COINS)


def _doc(symbols=PORTO, v=1):
    return {"v": v, "source": "porto-crypto-jun", "ts": "2026-10-13T16:03:25+07:00", "symbols": symbols,
            "coins": [{"key": s, "symbol": s} for s in symbols]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    f, c = tmp_path / "coins.json", tmp_path / "cache.json"
    monkeypatch.setenv("PORTO_COINS_PATH", str(f))
    monkeypatch.setenv("ALIZA_WATCHLIST_CACHE", str(c))
    wl.reset_for_tests()
    return f, c


def _write(path, obj):
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")


# ---------------- loader ----------------

def test_normal_file_replaces_lists_in_place_and_writes_cache(env):
    f, c = env
    _write(f, _doc())
    refs = (mu.CORE_COINS, mu.MAJOR_COINS, mu.TRADABLE_COINS)
    res = mu.refresh_watchlist()
    assert res["status"] == "porto" and mu.CORE_COINS == mu.MAJOR_COINS == mu.TRADABLE_COINS == PORTO
    assert (mu.CORE_COINS, mu.MAJOR_COINS, mu.TRADABLE_COINS) == refs and all(a is b for a, b in zip(refs, (mu.CORE_COINS, mu.MAJOR_COINS, mu.TRADABLE_COINS)))
    assert json.loads(c.read_text())["symbols"] == PORTO


def test_missing_file_without_cache_falls_back_to_legacy(env):
    res = mu.refresh_watchlist()
    assert res["status"] == "default" and mu.CORE_COINS == LEGACY


def test_missing_file_uses_last_valid_from_memory_then_from_disk_after_restart(env):
    f, c = env
    _write(f, _doc()); mu.refresh_watchlist()
    f.unlink()
    res = wl.refresh(LEGACY, now=time.time() + 10)
    assert res["status"] == "cache" and res["symbols"] == PORTO
    wl.reset_for_tests()                                    # simulasi restart service, file masih hilang
    res = wl.refresh(LEGACY)
    assert res["status"] == "cache" and res["symbols"] == PORTO


def test_corrupt_json_keeps_last_valid_and_recovers(env):
    f, _ = env
    _write(f, _doc()); mu.refresh_watchlist()
    t = time.time() + 10
    _write(f, "{ini bukan json,,")
    res = wl.refresh(LEGACY, now=t)
    assert res["status"] == "cache" and res["symbols"] == PORTO and "JSONDecodeError" in res["reason"]
    _write(f, _doc(PORTO[:5]) | {"pad": "x" * 20})
    res = wl.refresh(LEGACY, now=t + 10)
    assert res["status"] == "porto" and res["symbols"] == PORTO[:5] and res["changed"]


BAD_DOCS = [
    ("versi 2", {"v": 2, "symbols": ["BTC"]}),
    ("tanpa versi", {"symbols": ["BTC"]}),
    ("versi bool", {"v": True, "symbols": ["BTC"]}),
    ("symbols kosong", {"v": 1, "symbols": []}),
    ("symbols bukan list", {"v": 1, "symbols": "BTC,ETH"}),
    ("simbol tidak valid", {"v": 1, "symbols": ["BTC", "ETH/USDT"]}),
    ("simbol bukan string", {"v": 1, "symbols": ["BTC", 5]}),
    ("top-level list", ["BTC"]),
]


@pytest.mark.parametrize("name,doc", BAD_DOCS, ids=[n for n, _ in BAD_DOCS])
def test_invalid_versions_and_shapes_are_rejected(env, name, doc):
    f, _ = env
    _write(f, doc)
    res = mu.refresh_watchlist()                             # belum pernah ada daftar valid -> daftar lama
    assert res["status"] == "default" and mu.CORE_COINS == LEGACY and res["reason"]
    wl.reset_for_tests()
    _write(f, _doc()); mu.refresh_watchlist()
    _write(f, doc)
    res = wl.refresh(LEGACY, now=time.time() + 10)           # sudah pernah valid -> pakai yang valid terakhir
    assert res["status"] == "cache" and res["symbols"] == PORTO


def test_reload_on_mtime_change_and_at_least_every_5_minutes(env):
    f, _ = env
    _write(f, _doc())
    t0 = time.time()
    reads = []
    real_load = json.load

    def counting(fp, *a, **k):
        reads.append(1)
        return real_load(fp, *a, **k)

    with patch.object(wl.json, "load", counting):
        wl.refresh(LEGACY, now=t0)
        assert len(reads) == 1
        wl.refresh(LEGACY, now=t0 + 1)                       # <5 detik: tidak cek apa pun
        wl.refresh(LEGACY, now=t0 + 6)                       # mtime sama: tidak baca ulang
        assert len(reads) == 1
        wl.refresh(LEGACY, now=t0 + 301)                     # >=5 menit: baca ulang paksa
        assert len(reads) == 2
        _write(f, _doc(PORTO[:4]))
        res = wl.refresh(LEGACY, now=t0 + 310)               # mtime/ukuran berubah: baca segera
        assert len(reads) == 3 and res["changed"] and res["symbols"] == PORTO[:4]


def test_loader_only_opens_porto_file_for_reading(env, monkeypatch):
    f, _ = env
    modes = []
    real_open = builtins.open

    def spy(file, mode="r", *a, **k):
        if str(file) == str(f):
            modes.append(mode)
        return real_open(file, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", spy)
    _write(f, _doc()); stat_before = os.stat(f)
    mu.refresh_watchlist()
    _write(f, "rusak"); os.utime(f, (stat_before.st_atime, stat_before.st_mtime))
    stat_bad = os.stat(f)
    modes.clear()
    wl.refresh(LEGACY, now=time.time() + 10, force=True)
    f.unlink(); wl.refresh(LEGACY, now=time.time() + 20, force=True)
    assert set(modes) <= {"r"} and modes
    assert stat_bad.st_size == 5                              # isi file tidak diubah loader


# ---------------- notifikasi perubahan ----------------

def test_notice_lists_added_removed_and_clears_after_mark(env):
    f, c = env
    _write(f, _doc()); mu.refresh_watchlist()
    n = mu.pending_watchlist_notice()
    assert n["added"] == [s for s in PORTO if s not in LEGACY]            # BONE, FARTCOIN, TRX, ZEC
    assert n["removed"] == [s for s in LEGACY if s not in PORTO]          # ETHFI, OM, TAO, WLD, XAUT
    assert n["total"] == 17
    mu.mark_watchlist_announced()
    assert mu.pending_watchlist_notice() is None
    new = [s for s in PORTO if s != "BONE"] + ["ZZZ"]
    _write(f, _doc(new))
    wl.refresh(LEGACY, now=time.time() + 10)
    n = mu.pending_watchlist_notice()
    assert (n["added"], n["removed"]) == (["ZZZ"], ["BONE"])
    wl.reset_for_tests()                                      # restart sebelum sempat terkirim -> tetap tertunda
    wl.refresh(LEGACY)
    assert mu.pending_watchlist_notice() is not None


def test_sync_job_sends_one_short_message_per_change(env):
    f, _ = env
    _write(f, _doc())
    cs.set_data_for_tests(
        {f"{c}USDT" for c in PORTO if c not in ("BONE", "FARTCOIN")},
        {**{c: f"{c}USDT" for c in PORTO if c != "BONE"}, "1000PEPE": "1000PEPEUSDT"})
    dispatch = AsyncMock(return_value=True)

    class Ctx:
        bot_data = {"chat_id": 1}

    with patch.object(tb, "safe_dispatch", dispatch):
        asyncio.run(tb.watchlist_sync_job(Ctx()))
        asyncio.run(tb.watchlist_sync_job(Ctx()))             # tidak ada perubahan baru -> tidak kirim lagi
    assert dispatch.await_count == 1
    text = dispatch.await_args.args[0]
    assert text.startswith("📋 Daftar pantau diperbarui dari Porto: +4 (BONE, FARTCOIN, TRX, ZEC), −5 (ETHFI, WLD, OM, TAO, XAUT)")
    assert "total 17 coin" in text and "Tanpa data Binance (dilewati): BONE" in text
    assert "FARTCOIN" not in text.split("\n")[1]              # FARTCOIN punya futures -> bukan 'tanpa data'


def test_sync_job_retries_when_dispatch_fails(env):
    f, _ = env
    _write(f, _doc())

    class Ctx:
        bot_data = {"chat_id": 1}

    fail, ok = AsyncMock(return_value=False), AsyncMock(return_value=True)
    with patch.object(tb, "safe_dispatch", fail):
        asyncio.run(tb.watchlist_sync_job(Ctx()))
    assert mu.pending_watchlist_notice() is not None
    with patch.object(tb, "safe_dispatch", ok):
        asyncio.run(tb.watchlist_sync_job(Ctx()))
    assert ok.await_count == 1 and mu.pending_watchlist_notice() is None


# ---------------- coin yang datanya tidak tersedia ----------------

def _support():
    spot = {f"{c}USDT" for c in PORTO if c not in ("BONE", "FARTCOIN")}
    fut = {c: f"{c}USDT" for c in PORTO if c not in ("BONE", "PEPE")}
    fut["1000PEPE"] = "1000PEPEUSDT"
    cs.set_data_for_tests(spot, fut)


def test_unsupported_coins_are_skipped_per_component(env):
    f, _ = env
    _write(f, _doc()); mu.refresh_watchlist(); _support()
    assert cs.is_unsupported("BONE") and not cs.is_unsupported("FARTCOIN") and not cs.is_unsupported("BTC")
    assert cs.has_spot("FARTCOIN") is False and cs.futures_symbol("PEPE") == "1000PEPEUSDT"
    assert "BONE" not in mu.get_analyzable_coins() and "FARTCOIN" in mu.get_analyzable_coins()
    assert len(mu.get_analyzable_coins()) == 16
    assert "BONE" not in frm._watchlist() and "FARTCOIN" in frm._watchlist() and "TRX" in frm._watchlist()
    assert frm.futures_symbol("BONE") is None and frm.futures_symbol("FARTCOIN") == "FARTCOINUSDT"
    assert frm.get_funding_rate_data("BONE") is None and frm.get_open_interest("BONE") is None   # tanpa jaringan/exception
    assert positioning.collect(["BONE"]) == []
    assert mu.get_universe_status()["unsupported"] == ["BONE"]


def test_unknown_support_data_keeps_old_behaviour(env):
    cs.reset_for_tests()
    assert cs.is_unsupported("BONE") is False and cs.has_spot("BONE") is None
    assert frm.futures_symbol("PEPE") == "1000PEPEUSDT" and frm.futures_symbol("TRX") == "TRXUSDT"


def test_no_spot_coin_goes_straight_to_futures_klines_and_uses_cache(env):
    _support()
    rows = [[i * 1000, "1", "2", "0.5", str(1 + i), "0", i * 1000 + 1] for i in range(100)]

    class R:
        status_code = 200
        def json(self): return rows

    stored = {}
    with patch.object(ma, "_get_binance_spot_klines", side_effect=AssertionError("spot tidak boleh dipanggil")), \
         patch.object(ma, "get_cached_klines", side_effect=lambda s, i: stored.get((s, i))), \
         patch.object(ma, "set_cached_klines", side_effect=lambda s, i, c: stored.__setitem__((s, i), c)), \
         patch.object(ma.requests, "get", return_value=R()) as get:
        out = ma._get_binance_klines("FARTCOINUSDT", "4h", 100)
        assert len(out) == 100 and get.call_args.kwargs["params"]["symbol"] == "FARTCOINUSDT"
        again = ma._get_binance_klines("FARTCOINUSDT", "4h", 100)     # dari cache, tanpa request kedua
        assert again == out and get.call_count == 1


# ---------------- Konteks Market ----------------

@pytest.mark.parametrize("coins", [PORTO[:3] + PORTO[5:], [c for c in PORTO if c != "BONE"], ["BTC", "ETH"]])
def test_trend_text_uses_dynamic_coin_count(monkeypatch, coins):
    data = {c: {"trend_4h": "BULLISH" if i % 3 == 0 else "BEARISH", "trend_1d": "SIDEWAYS"} for i, c in enumerate(coins)}
    data["BONE"] = {"error": "tidak ada data"}               # coin tanpa data: tidak dihitung
    data.setdefault("BTC", {"trend_4h": "SIDEWAYS", "trend_1d": "SIDEWAYS"})
    monkeypatch.setattr(mce, "_get_snapshot", lambda: {"data": data})
    r = mce._calculate_market_score()
    pt = r["components"]["price_trend"]
    n = len([c for c in data if c != "BONE"])
    assert pt["n"] == n
    detail = mce.build_components_view(r)[0]["detail"]
    assert f"/{n} coin 4H naik" in detail and f"/{n} turun" in detail
    assert 0 <= pt["score"] <= 40                              # skala tren tetap 0-40, tidak ikut N


def test_context_json_schema_is_unchanged():
    p = mcx.build_payload({"total_score": 55, "label": "Neutral", "summary": "x", "components": mce._neutral_components(),
                           "timestamp_iso": "2026-10-13T15:15:40+07:00", "failed_components": 0})
    assert set(p) == {"v", "ts", "score", "max", "label", "label_text", "level", "summary", "thresholds",
                      "bands", "components", "source"}
    assert [c["key"] for c in p["components"]] == ["trend", "macro", "fng", "funding", "dominance"]
    assert p["v"] == 1 and p["source"] == "aliza-ai"


# ---------------- harga & id CoinGecko untuk coin baru ----------------

def test_resolve_coin_id_static_first_never_triggers_dynamic_refresh():
    from engine.market import coin_id_resolver as cir
    with patch.object(cir, "_dynamic_get_coin_id", side_effect=AssertionError("dynamic tidak boleh dipanggil")):
        assert cir.resolve_coin_id("FARTCOIN") == "fartcoin"
        assert cir.resolve_coin_id("trx") == "tron" and cir.resolve_coin_id("ZEC") == "zcash"
        assert cir.resolve_coin_id("BONE") == "bone-shibaswap"
    with patch.object(cir, "_dynamic_get_coin_id", return_value="dyn-id"):
        assert cir.resolve_coin_id("NOTINSTATIC") == "dyn-id"           # simbol di luar peta statis tetap lewat dynamic


def test_futures_only_coin_price_comes_from_futures_ticker():
    _support()
    calls = []

    class R:
        def __init__(self, code, body): self.status_code, self._b = code, body
        def json(self): return self._b

    def fake_get(url, params=None, **k):
        calls.append((url, params["symbol"]))
        if "fapi" in url:
            return R(200, {"symbol": params["symbol"], "price": "0.1636"})
        return R(400, {"code": -1121})

    with patch.object(ma.requests, "get", side_effect=fake_get):
        assert ma._get_price_from_binance("FARTCOIN") == 0.1636
        assert calls == [(ma.BINANCE_TICKER_URL, "FARTCOINUSDT"), (ma.BINANCE_FUTURES_TICKER_URL, "FARTCOINUSDT")]
        calls.clear()
        assert ma._get_price_from_binance("BONE") is None                 # tanpa spot & tanpa futures: tidak ada panggilan futures
        assert all("fapi" not in u for u, _ in calls)
        calls.clear()
        assert ma._get_price_from_binance("BTC") is None                  # ada di spot: spot gagal tidak jatuh ke futures
        assert all("fapi" not in u for u, _ in calls)
