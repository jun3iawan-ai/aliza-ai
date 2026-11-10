"""Siklus BTC: hitung murni (tanpa jaringan), zona, simpan/baca, tampilan."""

import json

import numpy as np
import pandas as pd
import pytest

from engine.market import btc_cycle as bc


def _frame(prices, mvrv=1.5, vix=18.0, hr=None, end="2026-11-09"):
    n = len(prices)
    idx = pd.date_range(end=end, periods=n, freq="D")
    d = pd.DataFrame({"p": np.asarray(prices, dtype=float), "mvrv": mvrv, "vix": vix}, index=idx)
    d["hr"] = np.linspace(100, 120, n) if hr is None else hr
    return d


def test_data_kurang_ditolak():
    with pytest.raises(ValueError):
        bc.compute_cycle(_frame(np.linspace(100, 110, 100)))


def test_netral_pada_tren_naik_biasa():
    r = bc.compute_cycle(_frame(np.linspace(100, 160, 600)))
    assert r["zone"] == "netral" and r["zone_label"] == "Netral"
    assert r["above_ma200"] is True and r["dasar_count"] == 0
    assert r["puncak"]["pi_near"] is False


def test_mvrv_di_bawah_1_jadi_akumulasi():
    r = bc.compute_cycle(_frame(np.linspace(160, 100, 600), mvrv=0.9))
    assert r["dasar"]["mvrv_lt1"]["active"] is True
    assert r["zone"] == "akumulasi"


def test_mvrv_nan_hari_terakhir_pakai_nilai_valid_terakhir():
    d = _frame(np.linspace(100, 160, 600), mvrv=1.39)
    d.loc[d.index[-1], "mvrv"] = np.nan
    r = bc.compute_cycle(d)
    assert r["mvrv"] == 1.39
    assert r["mvrv_date"] == d.index[-2].date().isoformat()


def test_vix_hilang_tidak_menjatuhkan_hitungan():
    d = _frame(np.linspace(100, 160, 600)).drop(columns=["vix"])
    r = bc.compute_cycle(d)
    assert r["vix"] is None and r["dasar"]["vix_gt30"]["active"] is False


def test_vix_lonjakan_5_hari_terakhir_aktif():
    d = _frame(np.linspace(100, 160, 600))
    d.loc[d.index[-3]:, "vix"] = 35.0
    assert bc.compute_cycle(d)["dasar"]["vix_gt30"]["active"] is True


def test_pi_cycle_dekat_pemicu_jadi_rawan_puncak():
    prices = np.concatenate([np.full(650, 100.0), np.geomspace(100, 3000, 150)])
    r = bc.compute_cycle(_frame(prices, mvrv=0.9))   # MVRV<1 sengaja: puncak harus menang
    assert r["puncak"]["pi_ratio"] >= bc.PI_NEAR
    assert r["zone"] == "rawan_puncak"


def test_dua_sinyal_dasar_cukup_jadi_akumulasi():
    # turun lama (di bawah MA128/200), lalu breakout < 30 hari lalu + VIX tinggi di 5 hari terakhir
    prices = np.concatenate([np.linspace(200, 100, 500), np.linspace(100, 260, 100)])
    d = _frame(prices)
    d.loc[d.index[-2]:, "vix"] = 40.0
    r = bc.compute_cycle(d)
    assert r["dasar"]["vix_gt30"]["active"] is True
    assert r["dasar"]["dma_breakout"]["active"] is False   # breakout terjadi >30 hari lalu pada data ini
    d2 = _frame(np.concatenate([np.linspace(200, 100, 580), np.linspace(100, 230, 20)]))
    d2.loc[d2.index[-2]:, "vix"] = 40.0
    r2 = bc.compute_cycle(d2)
    assert r2["dasar"]["dma_breakout"]["active"] and r2["dasar_count"] >= 2
    assert r2["zone"] == "akumulasi"


def test_halving_clock():
    r = bc.compute_cycle(_frame(np.linspace(100, 160, 600), end="2025-10-01"))
    assert r["puncak"]["halving_date"] == "2024-04-20"
    assert r["puncak"]["halving_days"] == (pd.Timestamp("2025-10-01") - pd.Timestamp("2024-04-20")).days  # 529
    assert r["puncak"]["in_halving_window"] is True
    r2 = bc.compute_cycle(_frame(np.linspace(100, 160, 600), end="2025-12-01"))   # hari ke-590: lewat jendela
    assert r2["puncak"]["in_halving_window"] is False


def test_zone_changed():
    assert bc.zone_changed(None, "netral") is False       # baseline pertama
    assert bc.zone_changed("netral", "netral") is False
    assert bc.zone_changed("netral", "rawan_puncak") is True


def test_simpan_baca_dan_cache_rusak(tmp_path):
    r = bc.compute_cycle(_frame(np.linspace(100, 160, 600)))
    p = str(tmp_path / "sub" / "c.json")
    bc.save(r, p)
    assert bc.load_last(p)["zone"] == r["zone"]
    assert (tmp_path / "sub" / "c.json").stat().st_mode & 0o777 == 0o644
    (tmp_path / "bad.json").write_text("{bukan json")
    assert bc.load_last(str(tmp_path / "bad.json")) is None
    (tmp_path / "x.json").write_text(json.dumps({"v": 2, "zone": "netral"}))
    assert bc.load_last(str(tmp_path / "x.json")) is None
    assert bc.load_last(str(tmp_path / "tidak-ada.json")) is None


def test_refresh_pakai_fetch_palsu_dan_gagal_tidak_merusak_cache(tmp_path):
    p = str(tmp_path / "c.json")
    r = bc.refresh(lambda: _frame(np.linspace(100, 160, 600)), p)
    assert bc.load_last(p)["asof"] == r["asof"]

    def boom():
        raise RuntimeError("jaringan mati")

    with pytest.raises(RuntimeError):
        bc.refresh(boom, p)
    assert bc.load_last(p)["asof"] == r["asof"]       # cache lama utuh


def test_format_telegram_dan_export_view():
    r = bc.compute_cycle(_frame(np.linspace(100, 160, 600)))
    txt = bc.format_telegram(r)
    assert "Siklus BTC: Netral" in txt and "bukan sinyal entry" in txt
    txt2 = bc.format_telegram(r, changed_from="akumulasi")
    assert "Akumulasi → Netral" in txt2
    v = bc.export_view(r)
    assert v["zone"] == "netral" and v["active"] == [] and bc.export_view(None) is None
    json.dumps(v)  # harus serializable


def test_build_payload_cycle_additif():
    from engine.market import market_context_export as mcx

    base = mcx.build_payload({"total_score": 50, "label": "Neutral"})
    assert "cycle" not in base and base["v"] == 1
    r = bc.compute_cycle(_frame(np.linspace(100, 160, 600)))
    withc = mcx.build_payload({"total_score": 50, "label": "Neutral"}, None, bc.export_view(r))
    assert withc["cycle"]["zone"] == "netral" and withc["v"] == 1


def test_cycle_view_safe_pakai_cache(tmp_path, monkeypatch):
    from engine.market import market_context_export as mcx

    monkeypatch.setenv("ALIZA_CYCLE_CACHE", str(tmp_path / "c.json"))
    assert mcx._cycle_view_safe() is None            # belum ada cache -> field tidak ditulis
    bc.save(bc.compute_cycle(_frame(np.linspace(100, 160, 600))))
    assert mcx._cycle_view_safe()["zone"] == "netral"


def test_perintah_dan_job_terdaftar():
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[1] / "interfaces" / "telegram_bot.py").read_text(encoding="utf-8")
    assert 'CommandHandler("siklus", siklus_command)' in src
    assert "btc_cycle_job," in src and 'name="btc_cycle"' in src


def test_advance_zone_butuh_3_hari_data_berbeda():
    adv = bc.advance_zone
    p, a = adv("netral", None, "akumulasi", "2026-12-01")
    assert a is None and p["days"] == 1
    p, a = adv("netral", p, "akumulasi", "2026-12-01")        # job diulang, data sama -> tidak menambah
    assert a is None and p["days"] == 1
    p, a = adv("netral", p, "akumulasi", "2026-12-02")
    assert a is None and p["days"] == 2
    p, a = adv("netral", p, "akumulasi", "2026-12-03")
    assert a == "netral" and p["days"] == 3


def test_advance_zone_bolak_balik_tidak_pernah_alert():
    p, a = bc.advance_zone("netral", None, "akumulasi", "2026-12-01")
    p, a = bc.advance_zone("netral", p, "akumulasi", "2026-12-02")
    p, a = bc.advance_zone("netral", p, "netral", "2026-12-03")   # kembali -> pending dibuang
    assert p is None and a is None
    p, a = bc.advance_zone("netral", p, "akumulasi", "2026-12-04")
    assert a is None and p["days"] == 1                           # hitungan mulai dari awal


def test_advance_zone_ganti_calon_mereset_dan_baseline():
    p, _ = bc.advance_zone("netral", None, "akumulasi", "2026-12-01")
    p, a = bc.advance_zone("netral", p, "rawan_puncak", "2026-12-02")
    assert p["zone"] == "rawan_puncak" and p["days"] == 1 and a is None
    assert bc.advance_zone(None, None, "netral", "2026-12-01") == (None, None)


def test_advance_zone_kirim_gagal_dicoba_lagi_hari_berikut():
    p = {"zone": "akumulasi", "asof": "2026-12-03", "days": 3}
    p2, a = bc.advance_zone("netral", p, "akumulasi", "2026-12-04")   # confirmed belum diubah
    assert a == "netral" and p2["days"] == 4


def test_format_menyebut_hari_bertahan():
    r = bc.compute_cycle(_frame(np.linspace(100, 160, 600)))
    assert "(bertahan 3 hari)" in bc.format_telegram(r, changed_from="akumulasi", stable_days=3)


def test_is_fresh_dan_stale_days():
    from datetime import date

    today = date(2026, 12, 10)
    assert bc.is_fresh("2026-12-09", today) and bc.is_fresh("2026-12-08", today)
    assert not bc.is_fresh("2026-12-07", today) and not bc.is_fresh("bukan-tanggal", today)
    assert bc.stale_days("2026-12-07", today) == 3
    assert bc.stale_days(None, today) is None and bc.stale_days("xx", today) is None


def test_pesan_peringatan_dan_pemulihan():
    assert "3 hari" in bc.format_stale_warning(3, "2026-12-07") and "2026-12-07" in bc.format_stale_warning(3, "2026-12-07")
    assert "kembali diperbarui" in bc.format_recovery()
