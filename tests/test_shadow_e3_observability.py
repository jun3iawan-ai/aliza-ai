"""Observability tests for engine/shadow/e3_shadow.py.

SHADOW_E3_STAGNATION_REPORT.md (docs/reports/2026-08-27-vps-health-shadow-e3/)
recommended adding a per-reason failure breakdown to shadow_e3's logging so
future investigations don't need a manual repro script to find out *why*
candidates=0. This module implements that as in-memory counters that are
purely observational.

Every test here also asserts that candidate generation itself is completely
unaffected: `build_shadow_signal()`'s return value and `collect_shadow_signals()`'s
`candidates=%d` count must be byte-identical to the pre-observability
behavior (see tests/test_fase4.py for the pre-existing baseline tests, which
this file does not duplicate — it only covers the new counters).
"""

import logging
import re
from collections import Counter

import pytest

from engine.shadow import e3_shadow as shadow


def _rows(n=20, flat=False):
    rows = []
    for i in range(n):
        close = 100.0
        high = close if flat else close + 0.5
        low = close if flat else close - 0.5
        rows.append({
            "open_time": i * 4 * 60 * 60 * 1000,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1.0,
            "close_time": i * 4 * 60 * 60 * 1000 + 4 * 60 * 60 * 1000 - 1,
        })
    return rows


VALID_MARKET_DATA = {
    "price": 100, "trend": "BULLISH", "rsi": 50,
    "support": 99, "resistance": 110, "trend_alignment": "BULLISH",
}


class FakeBrain:
    """Configurable stand-in for TradingBrain, set at class scope per test."""

    _result = None
    _raise = None

    def analyze(self, market_data):
        if FakeBrain._raise is not None:
            raise FakeBrain._raise
        return FakeBrain._result


@pytest.fixture(autouse=True)
def _reset_fake_brain():
    FakeBrain._result = None
    FakeBrain._raise = None
    yield
    FakeBrain._result = None
    FakeBrain._raise = None


# ---------------------------------------------------------------------------
# build_shadow_signal(): one test per early-return gate identified by reading
# the function line-by-line.
# ---------------------------------------------------------------------------

def test_insufficient_rows_market_data_not_dict():
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", None, _rows(15), counters=counters)
    assert result is None
    assert counters == Counter({"insufficient_rows": 1})


def test_insufficient_rows_too_few_rows():
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(14), counters=counters)
    assert result is None
    assert counters == Counter({"insufficient_rows": 1})


def test_atr_invalid_zero_true_range():
    # Flat OHLC (high == low == close, unchanging) -> Wilder true range is 0
    # for every candle -> ATR == 0, which fails the `atr <= 0` gate.
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20, flat=True), counters=counters)
    assert result is None
    assert counters == Counter({"atr_invalid": 1})


def test_trading_brain_exception(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._raise = RuntimeError("boom")
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20), counters=counters)
    assert result is None
    assert counters == Counter({"trading_brain_exception": 1})


def test_no_setup_none_signal(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = None
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20), counters=counters)
    assert result is None
    assert counters == Counter({"no_setup": 1})


def test_no_setup_explicit_no_setup_string(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "NO SETUP"}
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20), counters=counters)
    assert result is None
    assert counters == Counter({"no_setup": 1})


def test_invalid_side_entry_bad_side(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "PULLBACK LONG", "side": "SIDEWAYS", "entry": 100}
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20), counters=counters)
    assert result is None
    assert counters == Counter({"invalid_side_entry": 1})


def test_invalid_side_entry_nonpositive_entry(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "PULLBACK LONG", "side": "LONG", "entry": 0}
    counters: Counter[str] = Counter()
    result = shadow.build_shadow_signal(
        "BTC", {**VALID_MARKET_DATA, "price": 0}, _rows(20), counters=counters,
    )
    assert result is None
    assert counters == Counter({"invalid_side_entry": 1})


def test_support_filter_reject_too_far(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "OVERSOLD BOUNCE", "side": "LONG", "entry": 100}
    counters: Counter[str] = Counter()
    # entry(100) > support(90) * 1.01 (90.9) -> rejected
    market_data = {**VALID_MARKET_DATA, "support": 90}
    result = shadow.build_shadow_signal("BTC", market_data, _rows(20), counters=counters)
    assert result is None
    assert counters == Counter({"support_filter_reject": 1})


def test_support_filter_reject_missing_support(monkeypatch):
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "OVERSOLD BOUNCE", "side": "LONG", "entry": 100}
    counters: Counter[str] = Counter()
    market_data = {**VALID_MARKET_DATA, "support": None}
    result = shadow.build_shadow_signal("BTC", market_data, _rows(20), counters=counters)
    assert result is None
    assert counters == Counter({"support_filter_reject": 1})


def test_success_candidate_produced_and_shape_unchanged(monkeypatch):
    """Regression check: with the counters kwarg wired in, the candidate dict
    produced on success is identical (fields + SL/TP math) to the
    pre-observability behavior covered by
    tests/test_fase4.py::test_shadow_levels_one_and_three_atr."""
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "PULLBACK LONG", "side": "LONG", "entry": 100, "confidence": 80}
    counters: Counter[str] = Counter()
    signal = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20), counters=counters)
    assert signal is not None
    assert counters == Counter({"success": 1})
    assert signal["sl"] == 99.0
    assert signal["tp1"] == 103.0
    assert signal["source"] == "shadow_e3"
    assert signal["risk_reward"] == 3.0
    assert signal["dispatch_status"] == "RECORDED"
    assert signal["coin"] == "BTC"


def test_build_shadow_signal_without_counters_kwarg_unchanged(monkeypatch):
    """The counters kwarg is optional and defaults to None: every pre-existing
    call site (interfaces/telegram_bot.py via collect_shadow_signals,
    tests/test_fase4.py's direct call) omits it and must behave exactly as
    before this change — no crash, identical return value."""
    monkeypatch.setattr(shadow, "TradingBrain", FakeBrain)
    FakeBrain._result = {"setup": "PULLBACK LONG", "side": "LONG", "entry": 100, "confidence": 80}
    signal = shadow.build_shadow_signal("BTC", VALID_MARKET_DATA, _rows(20))
    assert signal is not None
    assert signal["sl"] == 99.0
    assert signal["tp1"] == 103.0


# ---------------------------------------------------------------------------
# collect_shadow_signals(): end-to-end breakdown + log line format.
# ---------------------------------------------------------------------------

class _ScenarioBrain:
    """TradingBrain stand-in that varies its answer per coin symbol, so a
    single collect_shadow_signals() cycle can exercise every gate at once."""

    def analyze(self, market_data):
        symbol = market_data.get("symbol")
        if symbol == "EXCEPTCOIN":
            raise RuntimeError("boom")
        if symbol == "NOSETUPCOIN":
            return None
        if symbol == "BADSIDE":
            return {"setup": "PULLBACK LONG", "side": "SIDEWAYS", "entry": 100}
        if symbol == "SUPPORTFAIL":
            return {"setup": "OVERSOLD BOUNCE", "side": "LONG", "entry": 100}
        if symbol == "WINCOIN":
            return {"setup": "PULLBACK LONG", "side": "LONG", "entry": 100, "confidence": 80}
        return {"setup": "NO SETUP"}


def test_collect_shadow_signals_breakdown_sums_to_total_processed(monkeypatch, caplog):
    monkeypatch.setenv("SHADOW_E3_ENABLED", "true")
    monkeypatch.setattr(shadow, "TradingBrain", _ScenarioBrain)

    def fake_klines(symbol):
        if symbol == "ATRCOIN":
            return _rows(20, flat=True)
        if symbol == "FEWROWS":
            return _rows(5)
        return _rows(20)

    monkeypatch.setattr(shadow, "_closed_4h_klines", fake_klines)

    common = dict(VALID_MARKET_DATA)
    snapshot = {
        "data": {
            "BADTYPE": "not-a-dict",  # -> insufficient_rows (bad market_data type)
            "FEWROWS": dict(common),  # -> insufficient_rows (rows < 15)
            "ATRCOIN": dict(common),  # -> atr_invalid (flat candles)
            "EXCEPTCOIN": dict(common),  # -> trading_brain_exception
            "NOSETUPCOIN": dict(common),  # -> no_setup
            "BADSIDE": dict(common),  # -> invalid_side_entry
            "SUPPORTFAIL": {**common, "support": 90},  # -> support_filter_reject
            "WINCOIN": dict(common),  # -> success
        }
    }
    total_processed = len(snapshot["data"])

    with caplog.at_level(logging.INFO, logger="engine.shadow.e3_shadow"):
        result = shadow.collect_shadow_signals(snapshot)

    # candidates=%d semantics unchanged: exactly the successful ones.
    assert len(result) == 1
    assert result[0]["coin"] == "WINCOIN"

    log_lines = [r.message for r in caplog.records if r.message.startswith("shadow_e3 candidates=")]
    assert len(log_lines) == 1
    line = log_lines[0]

    match = re.match(
        r"shadow_e3 candidates=(\d+) \(success=(\d+), no_setup=(\d+), atr_invalid=(\d+), "
        r"insufficient_rows=(\d+), invalid_side_entry=(\d+), support_filter_reject=(\d+), "
        r"trading_brain_exception=(\d+)\)",
        line,
    )
    assert match, f"unexpected log format: {line!r}"
    candidates, success, no_setup, atr_invalid, insufficient_rows, invalid_side_entry, \
        support_filter_reject, trading_brain_exception = (int(g) for g in match.groups())

    assert candidates == 1
    assert success == 1
    assert no_setup == 1
    assert atr_invalid == 1
    assert insufficient_rows == 2
    assert invalid_side_entry == 1
    assert support_filter_reject == 1
    assert trading_brain_exception == 1

    breakdown_total = (
        success + no_setup + atr_invalid + insufficient_rows
        + invalid_side_entry + support_filter_reject + trading_brain_exception
    )
    assert breakdown_total == total_processed == 8
    # candidates=%d must still match len(result) exactly (unchanged semantics).
    assert candidates == len(result)


def test_collect_shadow_signals_counters_reset_every_cycle(monkeypatch, caplog):
    """Counters must not leak/accumulate across separate collect_shadow_signals()
    calls (separate snapshot cycles) — each call starts from zero."""
    monkeypatch.setenv("SHADOW_E3_ENABLED", "true")
    monkeypatch.setattr(shadow, "TradingBrain", _ScenarioBrain)
    monkeypatch.setattr(shadow, "_closed_4h_klines", lambda symbol: _rows(20))

    snapshot = {"data": {"NOSETUPCOIN": dict(VALID_MARKET_DATA)}}

    with caplog.at_level(logging.INFO, logger="engine.shadow.e3_shadow"):
        shadow.collect_shadow_signals(snapshot)
        caplog.clear()
        shadow.collect_shadow_signals(snapshot)

    log_lines = [r.message for r in caplog.records if r.message.startswith("shadow_e3 candidates=")]
    assert len(log_lines) == 1
    # Second cycle alone should report no_setup=1, not 2 (which would happen
    # if a module-level counter leaked across calls instead of being local).
    assert "no_setup=1" in log_lines[0]
    assert "candidates=0" in log_lines[0]


def test_collect_shadow_signals_empty_snapshot_no_assertion_error(monkeypatch, caplog):
    monkeypatch.setenv("SHADOW_E3_ENABLED", "true")
    with caplog.at_level(logging.INFO, logger="engine.shadow.e3_shadow"):
        result = shadow.collect_shadow_signals({"data": {}})
    assert result == []
    log_lines = [r.message for r in caplog.records if r.message.startswith("shadow_e3 candidates=")]
    assert len(log_lines) == 1
    assert "candidates=0 (success=0, no_setup=0, atr_invalid=0, insufficient_rows=0, " \
        "invalid_side_entry=0, support_filter_reject=0, trading_brain_exception=0)" in log_lines[0]
