"""
Regression tests for the /radarpro "Crash Risk" mislabeling bug.

Bug (see RADAR_MARKET_VS_RADAR_PRO_AUDIT_REPORT.md, bagian 5.1): generate_radar_pro()
used to default EVERY coin to "Crash Risk" whenever market_risk_score (a GLOBAL
value, identical for all coins in a snapshot cycle) was "HIGH" -- before the
contextual per-coin detect_crash_risk() detector ran. detect_crash_risk() only
ever overwrote the label when it returned True; it never reverted the default
back to something else when it returned False. Net effect: once the global
market risk was HIGH, all 21 watchlist coins showed "Crash Risk" in /radarpro,
even coins that were clearly bullish and not at risk at all.

Fix: the naive "if risk == 'HIGH': label = Crash Risk" default branch was
removed. "Crash Risk" is now only ever set by detect_crash_risk() itself, which
already requires market_risk_score HIGH *and* a per-coin technical condition
(bearish trend, overbought RSI, or strong liquidation risk).
"""

from engine.market import market_radar_pro_analyzer as analyzer


def _coin(
    trend="SIDEWAYS",
    trend_alignment="UNKNOWN",
    rsi=50,
    whale_activity="LOW",
    market_risk_score="LOW",
    market_phase_prediction="UNKNOWN",
    liquidation_risk="LOW",
):
    return {
        "trend": trend,
        "trend_alignment": trend_alignment,
        "rsi": rsi,
        "whale_activity": whale_activity,
        "market_risk_score": market_risk_score,
        "market_phase_prediction": market_phase_prediction,
        "liquidation_risk": liquidation_risk,
    }


def _snapshot(markets):
    return {"data": markets}


def _label_for(monkeypatch, markets, coin):
    monkeypatch.setattr(analyzer, "get_market_snapshot", lambda: _snapshot(markets))
    radar_data = analyzer.generate_radar_pro()
    by_coin = {item["coin"]: item for item in radar_data}
    assert coin in by_coin, f"{coin} missing from radar_data: {by_coin.keys()}"
    return by_coin[coin]


class TestCrashRiskNoLongerBlanket:
    def test_bullish_coin_not_labeled_crash_risk_when_global_risk_high(self, monkeypatch):
        # Global market_risk_score is HIGH for every coin in this snapshot cycle,
        # but ETH itself is bullish, not overbought, and has no liquidation risk --
        # detect_crash_risk() must evaluate this coin-specific case to False.
        markets = {
            "BTC": _coin(
                trend="BULLISH",
                trend_alignment="BULLISH",
                rsi=55,
                whale_activity="LOW",
                market_risk_score="HIGH",
                market_phase_prediction="BEAR",
            ),
            "ETH": _coin(
                trend="BULLISH",
                trend_alignment="STRONG_BULLISH",
                rsi=63,
                whale_activity="LOW",
                market_risk_score="HIGH",
                market_phase_prediction="BEAR",
                liquidation_risk="LOW",
            ),
        }
        item = _label_for(monkeypatch, markets, "ETH")

        assert item["label"] != "⚠ Crash Risk"
        assert item["label"] == "🚀 Momentum"
        assert item["crash_risk"] is False

    def test_crash_risk_still_applies_when_detector_confirms_it(self, monkeypatch):
        # Same global HIGH risk, but this coin IS bearish -- detect_crash_risk()
        # must confirm it, and the label must still say Crash Risk (fix must not
        # suppress true positives).
        markets = {
            "BTC": _coin(
                trend="BULLISH",
                trend_alignment="BULLISH",
                rsi=55,
                whale_activity="LOW",
                market_risk_score="HIGH",
            ),
            "XRP": _coin(
                trend="BEARISH",
                trend_alignment="STRONG_BEARISH",
                rsi=38,
                whale_activity="LOW",
                market_risk_score="HIGH",
                liquidation_risk="LOW",
            ),
        }
        item = _label_for(monkeypatch, markets, "XRP")

        assert item["label"] == "⚠ Crash Risk"
        assert item["crash_risk"] is True

    def test_low_global_risk_never_confuses_baseline_with_crash(self, monkeypatch):
        # Sanity check: with market_risk_score LOW, a bearish/oversold coin should
        # never be labeled Crash Risk (detect_crash_risk requires HIGH risk too).
        markets = {
            "BTC": _coin(trend="SIDEWAYS", market_risk_score="LOW"),
            "SOL": _coin(
                trend="BEARISH",
                rsi=30,
                whale_activity="LOW",
                market_risk_score="LOW",
            ),
        }
        item = _label_for(monkeypatch, markets, "SOL")

        assert item["label"] != "⚠ Crash Risk"
        assert item["crash_risk"] is False


class TestOtherDetectorsUnaffectedByFix:
    def test_altseason_signal_still_detected(self, monkeypatch):
        markets = {
            "BTC": _coin(trend="SIDEWAYS", market_risk_score="LOW"),
            "SUI": _coin(
                trend="BULLISH",
                rsi=62,
                whale_activity="LOW",
                market_risk_score="LOW",
            ),
        }
        item = _label_for(monkeypatch, markets, "SUI")

        assert item["label"] == "🚀 Altseason Signal"

    def test_whale_accumulation_still_detected(self, monkeypatch):
        markets = {
            "BTC": _coin(trend="BULLISH", market_risk_score="LOW"),
            "ADA": _coin(
                trend="SIDEWAYS",
                rsi=50,
                whale_activity="HIGH",
                market_risk_score="LOW",
            ),
        }
        item = _label_for(monkeypatch, markets, "ADA")

        assert item["label"] == "🐋 Whale Accumulation"

    def test_whale_activity_default_still_shown_when_not_accumulating(self, monkeypatch):
        # whale_activity default branch (not touched by this fix) must still work
        # for coins that don't meet the more specific accumulation pattern.
        markets = {
            "BTC": _coin(trend="BULLISH", market_risk_score="LOW"),
            "BNB": _coin(
                trend="BEARISH",
                rsi=45,
                whale_activity="HIGH",
                market_risk_score="LOW",
            ),
        }
        item = _label_for(monkeypatch, markets, "BNB")

        assert item["label"] == "🐋 Whale Activity"
