import asyncio
import copy
import json
import time

from engine.alerts import notification_governor as ngov
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


def test_shadow_dispatch_cooldown_suppresses_repeat_within_window(monkeypatch, tmp_path):
    """Spam bug (SHADOW_SIGNAL_SPAM_REPORT.md): shadow_e3 used to dispatch to
    Telegram every ~60s snapshot cycle for as long as the setup stayed
    satisfied, with no cooldown at all. Only the first dispatch of a
    (coin, setup, side) should go out within the cooldown window."""
    from engine.trading import signal_tracker
    import interfaces.telegram_bot as telegram_bot

    signal_tracker.DB_PATH = str(tmp_path / "shadow_cooldown.db")
    assert signal_tracker.init_signal_tracking_db()
    ngov.reset_state_for_tests()

    candidate = {
        "coin": "SUI", "setup": "OVERSOLD BOUNCE", "side": "LONG",
        "entry": 0.71, "sl": 0.69, "tp1": 0.75, "confidence": 80,
        "source": "shadow_e3", "atr_14": 0.0121,
    }
    monkeypatch.setenv("SHADOW_E3_DISPATCH", "true")
    monkeypatch.setenv("SHADOW_SIGNAL_COOLDOWN_SEC", "14400")
    monkeypatch.setattr(telegram_bot, "collect_shadow_signals", lambda snapshot: [dict(candidate)])

    sent = []

    async def fake_dispatch(message, chat_id=None):
        sent.append(message)
        return True

    monkeypatch.setattr(telegram_bot, "safe_dispatch", fake_dispatch)

    t0 = 1_800_000_000.0
    clock = {"t": t0}
    monkeypatch.setattr(telegram_bot.time_module, "time", lambda: clock["t"])

    # First snapshot cycle: setup satisfied, nothing sent yet -> dispatch.
    asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None))
    assert len(sent) == 1

    # Setup keeps being satisfied for several more 60s cycles -> suppressed.
    for i in range(1, 11):
        clock["t"] = t0 + i * 60
        asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None))
    assert len(sent) == 1

    # Still inside the cooldown window (just under 4h) -> still suppressed.
    clock["t"] = t0 + 14400 - 1
    asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None))
    assert len(sent) == 1

    # Cooldown window elapsed and setup is still satisfied -> dispatch again.
    clock["t"] += 121
    asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None))
    assert len(sent) == 2


def test_shadow_dispatch_cooldown_scoped_per_coin_setup_side(monkeypatch, tmp_path):
    from engine.trading import signal_tracker
    import interfaces.telegram_bot as telegram_bot

    signal_tracker.DB_PATH = str(tmp_path / "shadow_cooldown_scope.db")
    assert signal_tracker.init_signal_tracking_db()
    ngov.reset_state_for_tests()

    monkeypatch.setenv("SHADOW_E3_DISPATCH", "true")
    monkeypatch.setenv("SHADOW_SIGNAL_COOLDOWN_SEC", "14400")

    sui = {
        "coin": "SUI", "setup": "OVERSOLD BOUNCE", "side": "LONG",
        "entry": 0.71, "sl": 0.69, "tp1": 0.75, "confidence": 80, "source": "shadow_e3",
    }
    arb = {
        "coin": "ARB", "setup": "OVERSOLD BOUNCE", "side": "LONG",
        "entry": 0.5, "sl": 0.48, "tp1": 0.56, "confidence": 80, "source": "shadow_e3",
    }
    monkeypatch.setattr(telegram_bot, "collect_shadow_signals", lambda snapshot: [dict(sui), dict(arb)])

    sent = []

    async def fake_dispatch(message, chat_id=None):
        sent.append(message)
        return True

    monkeypatch.setattr(telegram_bot, "safe_dispatch", fake_dispatch)
    monkeypatch.setattr(telegram_bot.time_module, "time", lambda: 1_800_000_000.0)

    asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None))
    # Different coins are independent cooldowns -> both go out once.
    assert len(sent) == 2

    asyncio.run(telegram_bot._run_shadow_e3({"data": {}}, None))
    # Same cycle repeated immediately -> both suppressed.
    assert len(sent) == 2


def test_shadow_atr_stable_within_same_4h_window_not_a_freshness_bug(monkeypatch):
    """SHADOW_SIGNAL_SPAM_REPORT.md Langkah 0.5: an identical ATR14 4h across
    many consecutive shadow messages within the same hour is NOT a stale-cache
    bug. `_closed_4h_klines` only ever returns fully CLOSED 4h candles, and a
    4h ATR is only supposed to change once a new 4h candle closes (every 4h)
    — regardless of how often the cache is refetched in between. Simulate a
    refetch (cache forced stale) where Binance has not closed a new candle
    yet: the derived ATR and the last candle's close_time must stay identical."""
    now_ms = int(time.time() * 1000)
    four_h_ms = 4 * 3600 * 1000
    raw = []
    for i in range(20):
        idx = i - 19  # oldest first; last candle closes well before "now"
        open_time = now_ms + idx * four_h_ms - four_h_ms
        close_time = open_time + four_h_ms - 1
        o = 100.0 + i
        raw.append([open_time, o, o + 1, o - 1, o + 0.5, 10.0, close_time, 0, 0, 0, 0, 0])

    class FakeResp:
        status_code = 200

        def json(self):
            return raw

    monkeypatch.setattr(shadow.requests, "get", lambda *a, **k: FakeResp())
    shadow._cache.clear()

    rows1 = shadow._closed_4h_klines("ATRCOIN")
    assert rows1, "fixture must produce at least one closed candle"
    fetched_at, cached_rows = shadow._cache["ATRCOIN"]
    # Force the cache to look stale (as if >15 min had passed) even though no
    # new 4h candle has actually closed on the exchange in that time.
    shadow._cache["ATRCOIN"] = (fetched_at - shadow.CACHE_TTL_SEC - 1, cached_rows)
    rows2 = shadow._closed_4h_klines("ATRCOIN")

    from engine.market.features import average_true_range
    atr1 = average_true_range(rows1, 14)[-1]
    atr2 = average_true_range(rows2, 14)[-1]
    assert atr1 == atr2
    assert rows1[-1]["close_time"] == rows2[-1]["close_time"]


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
