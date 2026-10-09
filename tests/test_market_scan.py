"""⚡ Scan Pasar: read-only, tidak menyentuh cooldown alert."""
from unittest.mock import patch

from engine.market import market_scan as ms
from engine.market import breakout_detector as bd

DATA = {
    "BTC": {"price": 82500.0, "rsi": 39, "resistance": 86242.0, "volume_24h": 3e10},
    "SOL": {"price": 110.0, "rsi": 28, "resistance": 120.8, "volume_24h": 5e9},
    "OM": {"price": 100.0, "rsi": 72, "resistance": 101.0, "volume_24h": 9e8},
}
SR = {
    "BTC": {"resistance": [86000.0], "support": [80000.0]},
    "SOL": {"resistance": [125.0], "support": [110.8]},   # 110 < 110.8*0.995 → breakdown
    "OM": {"resistance": [99.0], "support": [80.0]},      # 100 > 99*1.005 → breakout
}
AVG = {"BTC": 2e10, "SOL": 1e9, "OM": 8e8}


def test_scan_sections_and_no_cooldown_side_effects():
    with patch.object(bd.ngov, "record_cooldown") as rc, patch.object(bd.ngov, "set_value") as sv:
        scan = ms.collect_scan(DATA, {"BTC": 0.3, "SOL": -1.2, "OM": 3.4}, SR.get, AVG.get)
    rc.assert_not_called(); sv.assert_not_called()
    out = ms.format_market_scan(scan, snapshot_ts="14:40")
    assert "▲ OM +3.4% · BTC +0.3%" in out
    assert "▼ SOL -1.2%" in out
    assert "💥 Big move (≥3%): OM +3.4%" in out
    assert "SOL jebol ke bawah" in out and "OM tembus ke atas" in out
    assert "Spike: SOL 5.0×" in out
    assert "Oversold (<30): SOL 28" in out and "Overbought (>70): OM 72" in out
    assert "OM 1.0% →" in out


def test_scan_empty_sections_are_explicit():
    scan = ms.collect_scan({"BTC": {"price": 1.0, "rsi": 50}}, {}, lambda c: None, lambda c: None)
    out = ms.format_market_scan(scan)
    assert "Data perubahan 1 jam tidak tersedia" in out
    assert out.count("tidak ada") >= 2


def test_evaluate_breakout_matches_check_breakout_core():
    assert bd.evaluate_breakout(100.0, {"resistance": [99.0], "support": [80.0]})["direction"] == "UP"
    assert bd.evaluate_breakout(105.0, {"resistance": [99.0], "support": [80.0]}) is None  # >2% dari level
    assert bd.evaluate_breakout(90.0, {"resistance": [99.0], "support": [80.0]}) is None



def test_unified_breakout_requires_cross_from_previous_close():
    lv = {"levels": [99.0, 110.0], "prev_close": 98.0}
    assert bd.evaluate_breakout(100.0, lv)["direction"] == "UP"            # kemarin 98 < 99, kini 100
    assert bd.evaluate_breakout(100.0, dict(lv, prev_close=99.5)) is None   # sudah di atas sejak kemarin
    down = bd.evaluate_breakout(108.5, {"levels": [110.0], "prev_close": 111.0})
    assert down["direction"] == "DOWN" and down["level"] == 110.0
    assert bd.evaluate_breakout(105.0, {"levels": [99.0], "prev_close": 98.0}) is None  # >2% dari level


def test_scan_near_resistance_uses_levels_map():
    data = {"BTC": {"price": 100.0, "resistance": 150.0}}
    scan = ms.collect_scan(data, {}, lambda c: None, lambda c: None,
                           levels_map={"BTC": {"resistance": 102.0}})
    assert scan["near_res"][0][2] == 102.0
