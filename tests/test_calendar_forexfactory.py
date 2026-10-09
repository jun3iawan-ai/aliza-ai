"""Kalender ekonomi via Forex Factory + cache tahan rate-limit (9 Okt 2026)."""
import json
import os
import time
from datetime import datetime, timedelta, timezone

from engine.market import economic_calendar as ec


def _rows():
    soon = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    later = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    return [
        {"title": "CPI m/m", "country": "USD", "date": soon, "impact": "High", "forecast": "0.3%", "previous": "0.4%"},
        {"title": "Retail Sales", "country": "USD", "date": soon, "impact": "Medium", "forecast": "", "previous": ""},
        {"title": "Bank Holiday", "country": "USD", "date": soon, "impact": "Holiday"},
        {"title": "GDP", "country": "EUR", "date": soon, "impact": "High"},
        {"title": "FOMC", "country": "USD", "date": later, "impact": "High"},
    ]


def _reset():
    ec._fmp_calendar_cache.update({"ts": 0.0, "days": 0, "events": None})


def test_forexfactory_parses_usd_high_medium_within_window(monkeypatch):
    monkeypatch.setattr(ec, "_ff_fetch_json", lambda url: (_rows(), 200) if "thisweek" in url else (None, 404))
    ok, ev = ec._fetch_forexfactory(2)
    assert ok is True
    assert [(e["name"], e["impact"]) for e in ev] == [("CPI m/m", "HIGH"), ("Retail Sales", "MEDIUM")]
    assert ev[0]["forecast"] == "0.3%" and ev[0]["previous"] == "0.4%"
    assert ev[1]["forecast"] == "—"


def test_empty_but_reachable_source_is_live_not_rule_based(monkeypatch):
    _reset()
    monkeypatch.setattr(ec, "_ff_fetch_json", lambda url: ([], 200))
    monkeypatch.setattr(ec, "_generate_rule_events", lambda d: (_ for _ in ()).throw(AssertionError("tak boleh")))
    assert ec.get_upcoming_events(2) == []
    assert ec.get_calendar_source() == "forexfactory" and ec.is_calendar_live()


def test_rate_limited_uses_stale_disk_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(ec, "FF_CACHE_DIR", str(tmp_path))
    path = tmp_path / "ff_calendar_thisweek.json"
    path.write_text(json.dumps(_rows()))
    old = time.time() - 3 * 3600  # 3 jam: lewat FRESH, masih dalam STALE_MAX
    os.utime(path, (old, old))
    monkeypatch.setattr(ec, "_ff_fetch_json", lambda url: (None, 429))
    ok, ev = ec._fetch_forexfactory(2)
    assert ok is True and len(ev) == 2


def test_all_live_sources_down_marks_not_live(monkeypatch):
    _reset()
    monkeypatch.setattr(ec, "_ff_fetch_json", lambda url: (None, 429))
    monkeypatch.setattr(ec, "_fetch_serper_events", lambda d: [])
    import engine.market.investing_calendar as inv
    monkeypatch.setattr(inv, "fetch_investing_calendar", lambda d: [])
    ec.get_upcoming_events(2)
    assert ec.get_calendar_source() == "rule_based" and not ec.is_calendar_live()


def test_non_live_result_is_retried_after_10_minutes_live_cached_1_hour(monkeypatch):
    _reset()
    calls = {"n": 0}
    def ff(url):
        calls["n"] += 1
        return (None, 429)
    monkeypatch.setattr(ec, "_ff_fetch_json", ff)
    monkeypatch.setattr(ec, "_fetch_serper_events", lambda d: [])
    import engine.market.investing_calendar as inv
    monkeypatch.setattr(inv, "fetch_investing_calendar", lambda d: [])
    ec.get_upcoming_events(2); first = calls["n"]
    ec.get_upcoming_events(2); assert calls["n"] == first          # masih di cache
    ec._fmp_calendar_cache["ts"] -= 601
    monkeypatch.setattr(ec, "_ff_fetch_json", lambda url: ([], 200))
    ec.get_upcoming_events(2)
    assert ec.is_calendar_live()                                    # pulih setelah 10 menit
    ec._fmp_calendar_cache["ts"] -= 601
    monkeypatch.setattr(ec, "_ff_fetch_json", lambda url: (_ for _ in ()).throw(AssertionError("live di-cache 1 jam")))
    ec.get_upcoming_events(2)
    assert ec.get_calendar_source() == "forexfactory"
