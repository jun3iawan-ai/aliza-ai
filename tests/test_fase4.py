import asyncio
import copy
import json

from engine.shadow import e3_shadow as shadow


def _rows(n=15):
    rows = []
    for i in range(n):
        rows.append({
            "open_time": i * 4 * 60 * 60 * 1000,
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": 1.0,
            "close_time": i * 4 * 60 * 60 * 1000 + 4 * 60 * 60 * 1000 - 1,
        })
    return rows


def test_shadow_disabled_does_not_change_snapshot_payload(monkeypatch):
    monkeypatch.setenv("SHADOW_E3_ENABLED", "false")
    snapshot = {"data": {"BTC": {"price": 100, "setup": "production"}}}
    before = json.dumps(copy.deepcopy(snapshot), sort_keys=True)
    monkeypatch.setattr(shadow.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    assert shadow.collect_shadow_signals(snapshot) == []
    assert json.dumps(snapshot, sort_keys=True) == before


def test_shadow_signal_source_excluded_from_default_stats(monkeypatch, tmp_path):
    from engine.trading import signal_tracker
    import interfaces.telegram_bot as telegram_bot

    signal_tracker.DB_PATH = str(tmp_path / "shadow.db")
    assert signal_tracker.init_signal_tracking_db()
    candidate = {
        "coin": "BTC", "setup": "PULLBACK LONG", "side": "LONG",
        "entry": 100, "sl": 99, "tp1": 103, "confidence": 80,
        "source": "shadow_e3", "signal_time": "2026-01-01T00:00:00+00:00",
    }
    monkeypatch.setenv("SHADOW_E3_DISPATCH", "false")
    monkeypatch.setattr(telegram_bot, "collect_shadow_signals", lambda snapshot: [candidate])
    async def fail_dispatch(*args, **kwargs):
        raise AssertionError("shadow dispatch must be off")
    monkeypatch.setattr(telegram_bot, "safe_dispatch", fail_dispatch)
    assert asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None)) == 1
    rows = signal_tracker._connect().execute("SELECT source, dispatch_status FROM signal_tracking").fetchall()
    assert [(row[0], row[1]) for row in rows] == [("shadow_e3", "RECORDED")]
    assert signal_tracker.get_signal_stats()["total_signals"] == 0
    assert signal_tracker.get_signal_stats(source="shadow_e3")["total_signals"] == 1


def test_shadow_levels_one_and_three_atr(monkeypatch):
    class FakeBrain:
        def analyze(self, market_data):
            return {"setup": "PULLBACK LONG", "side": "LONG", "entry": market_data["price"], "confidence": 80}

    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    signal = shadow.build_shadow_signal(
        "BTC", {
            "price": 100, "trend": "BULLISH", "rsi": 50,
            "support": 99, "resistance": 110, "trend_alignment": "BULLISH",
        }, _rows(),
    )
    assert signal is not None
    assert signal["sl"] == 99.0
    assert signal["tp1"] == 103.0
    assert signal["source"] == "shadow_e3"
