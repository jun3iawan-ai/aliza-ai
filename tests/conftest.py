"""Fixture global test suite."""
import sys

import pytest

from engine.alerts import notification_governor as _ngov
from engine import state_store as _state_store


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
