"""Makro: FRED gagal sementara -> retry, last-good (maks 7 hari), tidak men-cache respons gagal;
detail CPI jelas (MoM vs YoY) tanpa mengubah skor."""
import json
import os
import time

import httpx
import pytest

from engine.market import macro_monitor as mm
from engine.market import market_context_engine as mce


def _obs(n=15, start=100.0, step=0.5):
    """desc seperti FRED: tanggal terbaru dulu."""
    return [{"date": f"2026-{(15 - i) % 12 + 1:02d}-01", "value": str(start + (n - 1 - i) * step)} for i in range(n)]


class _Resp:
    def __init__(self, status=200, body=None, raw=None):
        self.status_code, self._body, self._raw = status, body, raw

    def json(self):
        if self._raw is not None:
            return json.loads(self._raw)       # "" -> JSONDecodeError (ValueError), seperti 'Expecting value'
        return self._body


class _Fake:
    """Skrip respons berurutan; Exception di-raise. calls = jumlah permintaan."""
    def __init__(self, script):
        self.script, self.calls = list(script), 0

    def __call__(self, *a, **k):
        outer = self

        class _C:
            def __enter__(s): return s
            def __exit__(s, *e): return False
            def get(s, *a, **k):
                outer.calls += 1
                item = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                if isinstance(item, Exception):
                    raise item
                return item
        return _C()


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")


def _ok():
    return _Resp(200, {"observations": _obs()})


def _install(monkeypatch, script):
    f = _Fake(script)
    monkeypatch.setattr(mm.httpx, "Client", f)
    return f


@pytest.mark.parametrize("bad", [
    _Resp(504), _Resp(503), _Resp(429), _Resp(200, raw=""),
    httpx.ReadTimeout("t"), httpx.ConnectError("c"), httpx.RemoteProtocolError("r"),
])
def test_gangguan_sementara_di_retry_lalu_berhasil(monkeypatch, bad):
    f = _install(monkeypatch, [bad, bad, _ok()])
    d = mm.get_macro_data("CPIAUCSL", "pct_change_yoy")
    assert d and f.calls == 3 and d["stale"] is False


def test_4xx_tidak_diulang(monkeypatch):
    f = _install(monkeypatch, [_Resp(400)])
    assert mm.get_macro_data("CPIAUCSL", "pct_change_yoy") is None and f.calls == 1


def test_gagal_semua_tanpa_last_good_none_dan_tidak_di_cache(monkeypatch):
    f = _install(monkeypatch, [_Resp(504)])
    assert mm.get_macro_data("CPIAUCSL", "pct_change_yoy") is None
    assert f.calls == mm.FETCH_ATTEMPTS and "CPIAUCSL" not in mm._obs_raw_cache


def test_observasi_kosong_tidak_di_cache_sebagai_valid(monkeypatch):
    f = _install(monkeypatch, [_Resp(200, {"observations": []}), _Resp(200, {"observations": []}),
                               _Resp(200, {"observations": []})])
    assert mm.get_macro_data("CPIAUCSL", "pct_change_yoy") is None and "CPIAUCSL" not in mm._obs_raw_cache
    mm._fail_until.clear()                              # lewati backoff
    _install(monkeypatch, [_ok()])
    assert mm.get_macro_data("CPIAUCSL", "pct_change_yoy") is not None   # tidak terjebak cache kosong 6 jam


def test_backoff_setelah_gagal_total(monkeypatch):
    f = _install(monkeypatch, [_Resp(504)])
    mm.get_macro_data("CPIAUCSL", "pct_change_yoy")
    n = f.calls
    mm.get_macro_data("CPIAUCSL", "pct_change_yoy")
    assert f.calls == n


def _age(sid, seconds):
    mm._obs_raw_cache[sid]["ts"] -= seconds


def test_last_good_dipakai_saat_gagal_dan_ditandai_stale(monkeypatch):
    _install(monkeypatch, [_ok()])
    fresh = mm.get_macro_data("CPIAUCSL", "pct_change_yoy")
    assert fresh["stale"] is False
    _age("CPIAUCSL", 2 * 86400)
    mm._fail_until.clear()
    _install(monkeypatch, [_Resp(504)])
    d = mm.get_macro_data("CPIAUCSL", "pct_change_yoy")
    assert d["stale"] is True and 2 * 86400 <= d["age_sec"] < 2 * 86400 + 60
    assert d["value"] == fresh["value"] and d["change"] == fresh["change"]


def test_last_good_lebih_dari_7_hari_ditolak(monkeypatch):
    _install(monkeypatch, [_ok()])
    mm.get_macro_data("CPIAUCSL", "pct_change_yoy")
    _age("CPIAUCSL", 7 * 86400 + 120)
    mm._fail_until.clear()
    _install(monkeypatch, [_Resp(504)])
    assert mm.get_macro_data("CPIAUCSL", "pct_change_yoy") is None


def test_last_good_selamat_dari_restart_lewat_disk(monkeypatch):
    _install(monkeypatch, [_ok()])
    mm.get_macro_data("FEDFUNDS", "latest")
    assert os.stat(mm._cache_path()).st_mode & 0o777 == 0o600
    mm.reset_for_tests()                                 # = proses baru, memori kosong
    f = _install(monkeypatch, [_Resp(504)])
    d = mm.get_macro_data("FEDFUNDS", "latest", bypass_cache=True)
    assert d is not None and f.calls == mm.FETCH_ATTEMPTS
    assert d["stale"] is False                           # umur < TTL -> belum dianggap basi


def test_tanpa_api_key_tetap_none(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY")
    assert mm.get_macro_data("CPIAUCSL", "pct_change_yoy") is None


# ---------------- konteks market ----------------
def _macro_result(cpi, fed):
    import engine.market.market_context_engine as m
    orig = m.get_macro_data
    m.get_macro_data = lambda code, kind: cpi if code == "CPIAUCSL" else fed
    try:
        return m._calculate_market_score()
    finally:
        m.get_macro_data = orig


CPI = {"value": 4.02, "prev_value": 3.71, "change": 0.65, "stale": False, "age_sec": 10.0}
FED = {"value": 3.75, "change": 0.12, "stale": False, "age_sec": 10.0}


def test_detail_cpi_mom_dan_yoy_format_dipertahankan():
    r = _macro_result(CPI, FED)
    macro = next(c for c in mce.build_components_view(r) if c["key"] == "macro")
    assert macro["detail"] == "CPI MoM: +0.65% (YoY 4.02%) | Fed: 3.75% (naik)"
    parts = [p.strip() for p in macro["detail"].split("|")]
    assert len(parts) == 2 and parts[1].startswith("Fed ") is False and parts[1].startswith("Fed:")
    assert r["components"]["macro"]["cpi_yoy_prev"] == 3.71 and macro["ok"] is True


def test_skor_makro_tidak_berubah_oleh_yoy():
    a = _macro_result(CPI, FED)["components"]["macro"]["score"]
    b = _macro_result({**CPI, "value": 1.0, "prev_value": 9.0}, FED)["components"]["macro"]["score"]
    assert a == b == 4          # MoM 0.65 >= 0.5 -> 4; skor hanya dari MoM seperti sebelumnya


def test_detail_stale_diberi_umur_dan_tetap_ok():
    r = _macro_result({**CPI, "stale": True, "age_sec": 3 * 3600}, {**FED, "stale": True, "age_sec": 50 * 3600})
    m = next(c for c in mce.build_components_view(r) if c["key"] == "macro")
    assert m["detail"].endswith("| data cache 2 hari") and m["ok"] is True
    assert r["component_ok"]["macro"] is True
    r2 = _macro_result({**CPI, "stale": True, "age_sec": 3 * 3600}, FED)
    assert next(c for c in mce.build_components_view(r2) if c["key"] == "macro")["detail"].endswith("| data cache 3 jam")


def test_tanpa_data_sama_sekali_netral_dan_ok_false():
    r = _macro_result(None, None)
    m = next(c for c in mce.build_components_view(r) if c["key"] == "macro")
    assert r["components"]["macro"]["score"] == 10 and m["ok"] is False
    assert m["detail"] == "CPI MoM: — | Fed: —"


def test_yoy_tidak_ada_detail_tanpa_kurung_yoy():
    r = _macro_result({"change": 0.3}, {"value": 3.5, "change": 0.0})
    assert next(c for c in mce.build_components_view(r) if c["key"] == "macro")["detail"] == "CPI MoM: +0.30% | Fed: 3.50% (tetap)"
