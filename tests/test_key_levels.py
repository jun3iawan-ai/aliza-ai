"""Mesin level S/R terpadu (pivot harian)."""
from engine.market import key_levels as kl


def test_pivots_cluster_and_nearest():
    # puncak di 110 (2x, berdekatan → 1 level) & 120; lembah di 90 & 80
    highs = [100, 105, 110, 104, 101, 106, 110.5, 103, 100, 108, 120, 109, 101, 100, 99]
    lows = [95, 96, 98, 92, 90, 93, 97, 94, 80, 85, 99, 98, 91, 92, 93]
    lv = kl.pivot_levels(highs, lows, k=2)
    levels = [round(x["level"], 2) for x in lv]
    assert levels == [80.0, 90.5, 110.25, 120.0]  # low 90 & 91 tergabung (≤1,2%)
    assert next(x for x in lv if round(x["level"], 2) == 110.25)["touches"] == 2
    n = kl.nearest(lv, 100.0)
    assert n["resistance"] == 110.25 and n["resistance2"] == 120
    assert n["support"] == 90.5 and n["support2"] == 80


def test_price_on_a_level_is_not_its_own_support():
    lv = [{"level": 100.0, "touches": 1}, {"level": 95.0, "touches": 1}]
    assert kl.nearest(lv, 100.1)["support"] == 95.0


def test_key_levels_uses_cache_and_closed_candles(monkeypatch):
    kl._cache.clear()
    calls = {"n": 0}

    def fake_fetch(sym):
        calls["n"] += 1
        h = [100, 105, 110, 104, 101, 106, 112, 103, 100, 104]
        l = [95, 96, 98, 92, 90, 93, 97, 94, 91, 95]
        return {"high": h, "low": l, "close": [x - 1 for x in h]}

    monkeypatch.setattr(kl, "_fetch_daily", fake_fetch)
    a = kl.key_levels("BTC", 100.0)
    b = kl.key_levels("BTC", 100.0)
    assert calls["n"] == 1 and a == b
    assert a["prev_close"] == 103 and a["source"] == kl.SOURCE_LABEL
    assert kl.key_levels("BTC", None) is None
