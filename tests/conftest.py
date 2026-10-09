"""Fixture global test suite."""
import sys

import pytest


@pytest.fixture(autouse=True)
def _isolate_brief_map_state(tmp_path, monkeypatch):
    """Cegah test yang menjalankan morning_brief_job menulis state peta pagi
    produksi (data/brief_map_state.json) — terjadi 9 Okt 2026 saat pytest
    menulis teks mock "Analisis" ke file produksi."""
    tb = sys.modules.get("interfaces.telegram_bot")
    if tb is not None and hasattr(tb, "_BRIEF_MAP_STATE_PATH"):
        monkeypatch.setattr(tb, "_BRIEF_MAP_STATE_PATH", str(tmp_path / "brief_map_state.json"))
    yield
