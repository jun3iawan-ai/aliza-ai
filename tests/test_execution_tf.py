"""Timeframe eksekusi 1H/15m: indikator, swing, catatan timing, integrasi /cek."""
from engine.market import execution_tf as ex
from engine.trading.entry_check import evaluate, parse_plan


def _ohlc(closes):
    return {"close": closes, "high": [c * 1.002 for c in closes], "low": [c * 0.998 for c in closes]}


def test_analyze_uptrend():
    d = ex.analyze(_ohlc([100 + i for i in range(80)]))
    assert d["trend"] == "BULLISH" and d["rsi"] > 70 and d["atr_pct"] > 0


def test_analyze_downtrend():
    assert ex.analyze(_ohlc([200 - i for i in range(80)]))["trend"] == "BEARISH"


def test_swings_pick_nearest_pivots():
    h = [10, 11, 15, 11, 10, 9, 10, 13, 10, 9, 8]
    lo = [x - 1 for x in h]
    lo[5] = 5
    sh, sl = ex._swings(h, lo, 12)
    assert sh == 13 and sl == 5


def test_timing_note_correction_in_uptrend():
    exv = {"1h": {"trend": "BEARISH", "rsi": 40, "swing_high": 105.0, "swing_low": 99.0}, "15m": {"trend": "BULLISH", "rsi": 55}}
    notes = ex.timing_notes("BULLISH", exv)
    assert any("Koreksi di dalam tren 4H naik" in n and "105" in n for n in notes)
    assert any("15m sudah berbalik ↑" in n for n in notes)


def test_format_section():
    exv = {"1h": {"trend": "SIDEWAYS", "rsi": 50.0, "atr_pct": 0.8, "swing_high": 105.0, "swing_low": 99.0},
           "15m": None}
    s = ex.format_section("SIDEWAYS", exv, lambda v: f"${v:g}")
    assert "1H : →" in s and "ATR ±0.80%" in s and "$99 – $105" in s


def _ctx(**kw):
    base = {"price": 100.0, "trend_4h": "BULLISH", "trend_1d": "BULLISH", "rsi": 50,
            "levels": {}, "closes_4h": [], "events": [], "calendar_live": True}
    base.update(kw)
    return base


def test_entry_check_uses_1h_swing_and_trend():
    plan, _ = parse_plan("cek BTC long now sl 98.5")
    exv = {"1h": {"trend": "BEARISH", "swing_low": 98.0, "swing_high": 103.0}, "15m": {"rsi": 80}}
    res = evaluate(plan, _ctx(exec=exv))
    texts = " | ".join(t for _, t in res["checks"])
    assert "1H masih ↓ berlawanan" in texts
    assert "SL di atas swing low 1H" in texts
    assert "RSI 15m 80" in texts


def test_entry_check_sl_below_swing_ok():
    plan, _ = parse_plan("cek BTC long now sl 97")
    exv = {"1h": {"trend": "BULLISH", "swing_low": 98.0, "swing_high": 103.0}}
    texts = " | ".join(t for _, t in evaluate(plan, _ctx(exec=exv))["checks"])
    assert "SL di bawah swing low 1H" in texts and "1H searah LONG" in texts
