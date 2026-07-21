import logging

def test_coin_fail_threshold_suspend_and_retry(monkeypatch):
    from engine.market import market_universe as universe
    monkeypatch.setenv("COIN_FAIL_THRESHOLD", "10")
    monkeypatch.setenv("COIN_SUSPEND_HOURS", "6")
    universe.reset_coverage_gate()
    now = 1000.0
    for _ in range(10):
        universe.record_coin_validation("BONE", False, reason="insufficient_1d", now=now)
    assert "BONE" not in universe.get_polling_coins(["BONE"], now=now + 1)
    assert "BONE" in universe.get_polling_coins(["BONE"], now=now + 6 * 3600 + 1)
    universe.reset_coverage_gate()

def test_coin_success_resets_failure_counter(monkeypatch):
    from engine.market import market_universe as universe
    universe.reset_coverage_gate()
    monkeypatch.setenv("COIN_FAIL_THRESHOLD", "10")
    for _ in range(3):
        universe.record_coin_validation("BTC", False, now=100.0)
    universe.record_coin_validation("BTC", True, now=100.0)
    universe.record_coin_validation("BTC", False, now=100.0)
    status = universe.get_universe_status(["BTC"], now=100.0)
    assert status["fail_counts"]["BTC"] == 1
    universe.reset_coverage_gate()

def test_universe_exclude(monkeypatch):
    from engine.market.market_universe import get_polling_coins
    monkeypatch.setenv("UNIVERSE_EXCLUDE", "BONE,ZEREBRO")
    assert get_polling_coins(["BONE", "ZEREBRO", "BTC"]) == ["BTC"]

def test_data_coverage_log_when_1d_short(monkeypatch, caplog):
    from engine.market import market_analyzer as analyzer
    monkeypatch.setattr(analyzer, "_get_price_from_binance", lambda symbol: 100.0)
    monkeypatch.setattr(
        analyzer,
        "_get_binance_klines",
        lambda symbol, interval, limit=100: list(range(1, 61)) if interval == "4h" else list(range(1, 21)),
    )
    monkeypatch.setattr(analyzer, "get_global_market_data", lambda: {"fear_greed": 50, "btc_dominance": 50})
    monkeypatch.setattr(analyzer, "market_radar", lambda fear, dominance: {})
    caplog.set_level(logging.WARNING)
    result = analyzer.market_signal("TEST", radar_data={})
    assert result is not None
    assert result["data_coverage"]["klines_4h"] == 60
    assert result["data_coverage"]["klines_1d"] == 20
    assert result["data_coverage"]["alignment"] == "UNKNOWN"
    assert any("data_coverage coin=TEST" in record.message and "reason=insufficient_1d" in record.message for record in caplog.records)

