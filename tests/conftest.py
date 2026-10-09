"""Fixture global test suite."""
import sys

import pytest

from engine.alerts import notification_governor as _ngov
from engine import state_store as _state_store
from engine.market import economic_calendar as _ecal
from engine.market import news_feed as _news_feed
from engine.market import key_levels as _key_levels
from engine import user_config as _user_config


@pytest.fixture(autouse=True)
def _isolate_user_config(tmp_path, monkeypatch):
    """Test tidak boleh mengubah modal/risiko produksi (data/user_config.db)."""
    monkeypatch.setattr(_user_config, "DB_PATH", str(tmp_path / "user_config.db"))
    yield


@pytest.fixture(autouse=True)
def _no_live_key_levels(monkeypatch):
    """Test tidak boleh mengambil kline harian Binance sungguhan untuk level S/R
    (fallback ke level snapshot, perilaku lama)."""
    monkeypatch.setattr(_key_levels, "_fetch_daily", lambda symbol: None)
    _key_levels._cache.clear()
    yield


@pytest.fixture(autouse=True)
def _no_live_rss(monkeypatch):
    """Test tidak boleh mengambil RSS berita sungguhan."""
    monkeypatch.setattr(_news_feed, "_fetch_feed", lambda source, url: [])
    yield


@pytest.fixture(autouse=True)
def _no_live_forexfactory(tmp_path, monkeypatch):
    """Test tidak boleh memanggil Forex Factory sungguhan (rate-limit 429 dan
    ikut mengganggu bot produksi) atau menulis cache kalender produksi."""
    monkeypatch.setattr(_ecal, "_ff_fetch_json", lambda url: (None, None))
    monkeypatch.setattr(_ecal, "FF_CACHE_DIR", str(tmp_path / "ff_calendar_cache"))
    _ecal._last_source["source"] = "none"
    yield


@pytest.fixture(scope="session", autouse=True)
def _isolate_persistent_state_session(tmp_path_factory):
    """Level sesi: aktif SEBELUM setUpModule/setUpClass (mis.
    test_notifikasi_mitigasi.setUpModule memanggil reset_state_for_tests()
    yang menghapus STATE_FILE). Mengalihkan semua file state produksi di
    data/ ke direktori sementara selama seluruh sesi pytest."""
    d = tmp_path_factory.mktemp("prod_state_guard")
    saved = (_ngov.STATE_FILE, _state_store.STATE_FILE)
    _ngov.STATE_FILE = str(d / "alert_cooldown_state.json")
    _state_store.STATE_FILE = str(d / "signal_state.json")
    yield
    _ngov.STATE_FILE, _state_store.STATE_FILE = saved


@pytest.fixture(autouse=True)
def _isolate_alert_state(tmp_path, monkeypatch):
    """Cegah test menulis/menghapus state alert produksi
    (data/alert_cooldown_state.json). Terjadi 9 Okt 2026: test notifikasi
    menimpa file produksi, dan reset_state_for_tests() bahkan menghapusnya —
    status konteks market, baseline reversal, level breakout, cooldown dan
    circuit breaker ikut hilang setiap kali pytest dijalankan di VPS.
    Test yang sudah mem-patch STATE_FILE sendiri tetap bekerja (patch mereka
    berlaku setelah fixture ini)."""
    monkeypatch.setattr(_ngov, "STATE_FILE", str(tmp_path / "alert_cooldown_state.json"))
    monkeypatch.setattr(_ngov, "_state_cache", None)
    yield


@pytest.fixture(autouse=True)
def _isolate_brief_map_state(tmp_path, monkeypatch):
    """Cegah test yang menjalankan morning_brief_job menulis state peta pagi
    produksi (data/brief_map_state.json) — terjadi 9 Okt 2026 saat pytest
    menulis teks mock "Analisis" ke file produksi."""
    tb = sys.modules.get("interfaces.telegram_bot")
    if tb is not None and hasattr(tb, "_BRIEF_MAP_STATE_PATH"):
        monkeypatch.setattr(tb, "_BRIEF_MAP_STATE_PATH", str(tmp_path / "brief_map_state.json"))
    yield
