"""context.json (dibaca dashboard Porto): satu sumber dengan pesan Telegram, atomik, aman saat gagal."""

import asyncio
import json
import os
import stat
from unittest.mock import patch

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from engine.market import market_context_engine as mce
from engine.market import market_context_export as mcx

with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


def _result(total, label, emoji, summary, comps, **extra):
    r = {"total_score": total, "label": label, "emoji": emoji, "summary": summary, "components": comps,
         "timestamp": "2026-10-13 15:15:40 WIB", "timestamp_iso": "2026-10-13T15:15:40+07:00",
         "failed_components": 0}
    r.update(extra)
    return r


def _spec_example():
    return _result(55, "Neutral", "⚪", "Seimbang — belum ada arah dominan.", {
        "price_trend": {"score": 24, "btc_4h": "BULLISH", "btc_1d": "SIDEWAYS", "up": 3, "down": 4, "n": 18, "max": 40},
        "macro": {"score": 4, "cpi_change": 0.40, "fed_rate": 3.75, "fed_change": 0.25, "max": 20},
        "fear_greed": {"score": 13, "value": 57.0, "max": 15},
        "funding_rate": {"score": 8, "avg_fr": 0.0034, "max": 15},
        "btc_dominance": {"score": 6, "value": 59.8, "max": 10},
    })


def _all_none():
    return _result(50, "Neutral", "⚪", "Seimbang — belum ada arah dominan.", mce._neutral_components())


def _bearish():
    return _result(22, "Bearish", "🔴", "Tekanan turun dominan — tren harga dan konteks searah melemah.", {
        "price_trend": {"score": 3, "btc_4h": "BEARISH", "btc_1d": "BEARISH", "up": 1, "down": 15, "n": 18, "max": 40},
        "macro": {"score": 20, "cpi_change": -0.12, "fed_rate": 3.5, "fed_change": -0.25, "max": 20},
        "fear_greed": {"score": 4, "value": 18.0, "max": 15},
        "funding_rate": {"score": 15, "avg_fr": -0.0612, "max": 15},
        "btc_dominance": {"score": 10, "value": 45.04, "max": 10},
    })


SCENARIOS = [_spec_example, _all_none, _bearish]


def _legacy_message(result):
    """Salinan persis kode pesan /market_context SEBELUM refactor (referensi regresi)."""
    c = result.get("components", {})
    pt = c.get("price_trend") or {}
    macro = c.get("macro") or {}
    fg = c.get("fear_greed") or {}
    fr = c.get("funding_rate") or {}
    dom = c.get("btc_dominance") or {}
    _arw = {"BULLISH": "↑", "BEARISH": "↓", "SIDEWAYS": "→"}
    if pt.get("n"):
        n, up, down = pt["n"], pt.get("up") or 0, pt.get("down") or 0
        pt_label = (f"BTC 4H {_arw.get(pt.get('btc_4h'), '?')} 1D {_arw.get(pt.get('btc_1d'), '?')}"
                    f" · {up}/{n} coin 4H naik, {down}/{n} turun")
    else:
        pt_label = "data tidak tersedia"
    cpi_change, fed_rate, fed_change = macro.get("cpi_change"), macro.get("fed_rate"), macro.get("fed_change")
    cpi_label = "—" if cpi_change is None else f"{float(cpi_change):+.2f}%"
    fed_label = "—" if fed_rate is None else f"{float(fed_rate):.2f}%"
    if fed_change is not None:
        fed_label += " (naik)" if fed_change > 0 else " (turun)" if fed_change < 0 else " (tetap)"
    fg_val, fr_val, dom_val = fg.get("value"), fr.get("avg_fr"), dom.get("value")
    fg_label = "—" if fg_val is None else f"{float(fg_val):.0f}"
    if fr_val is None:
        fr_label = "—"
    else:
        frv = float(fr_val)
        fr_label = f"{frv:+.4f}% " + ("(short ramai)" if frv < -0.01 else "(long ramai)" if frv > 0.01 else "(seimbang)")
    dom_label = "—" if dom_val is None else f"{float(dom_val):.1f}%"
    return (
        "🎯 Konteks Market\n\n"
        f"Total: {result.get('total_score', 50)}/100 — {result.get('label', 'Neutral')} {result.get('emoji', '⚪')}\n\n"
        "Breakdown:\n"
        f"• Tren harga: {pt.get('score', 0)}/40 ({pt_label})\n"
        f"• Makro: {macro.get('score', 0)}/20 (CPI MoM: {cpi_label} | Fed: {fed_label})\n"
        f"• Fear & Greed: {fg.get('score', 0)}/15 (nilai: {fg_label})\n"
        f"• Funding: {fr.get('score', 0)}/15 (avg: {fr_label})\n"
        f"• BTC Dominance: {dom.get('score', 0)}/10 (nilai: {dom_label})\n\n"
        f"{result.get('summary', 'Seimbang — belum ada arah dominan.')}\n\n"
        f"⏰ {result.get('timestamp', '—')}"
    )


class _Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **_kw):
        self.sent.append(text)


class _Update:
    def __init__(self):
        self.effective_message = _Msg()


def _telegram_text(monkeypatch, result):
    monkeypatch.setattr(tb, "calculate_market_score", lambda: result)
    upd = _Update()
    asyncio.run(tb.market_context_command(upd, None))
    return upd.effective_message.sent[0]


@pytest.mark.parametrize("make", SCENARIOS)
def test_telegram_message_unchanged_after_refactor(monkeypatch, make):
    r = make()
    assert _telegram_text(monkeypatch, r) == _legacy_message(r)


@pytest.mark.parametrize("make", SCENARIOS)
def test_json_numbers_and_text_identical_to_telegram(monkeypatch, make):
    r = make()
    msg = _telegram_text(monkeypatch, r)
    p = mcx.build_payload(r)
    assert f"Total: {p['score']}/100 — {p['label_text']} {r['emoji']}" in msg
    assert p["summary"] in msg
    for c in p["components"]:
        assert f"• {c['name']}: {c['score']}/{c['max']} ({c['detail']})" in msg
    assert [c["key"] for c in p["components"]] == ["trend", "macro", "fng", "funding", "dominance"]
    assert p["max"] == 100 == sum(c["max"] for c in p["components"])


def test_payload_matches_spec_example():
    p = mcx.build_payload(_spec_example())
    assert p["v"] == 1 and p["source"] == "aliza-ai" and p["ts"] == "2026-10-13T15:15:40+07:00"
    assert (p["score"], p["max"], p["label"], p["label_text"]) == (55, 100, "neutral", "Neutral")
    assert p["components"][0] == {"key": "trend", "name": "Tren harga", "score": 24, "max": 40,
                                  "detail": "BTC 4H ↑ 1D → · 3/18 coin 4H naik, 4/18 turun", "ok": True}
    assert p["components"][1]["detail"] == "CPI MoM: +0.40% | Fed: 3.75% (naik)"
    assert p["components"][2]["detail"] == "nilai: 57"
    assert p["components"][3]["detail"] == "avg: +0.0034% (seimbang)"
    assert p["components"][4]["detail"] == "nilai: 59.8%"


def test_thresholds_reproduce_label_for_every_score():
    t = mcx.build_payload(_spec_example())["thresholds"]
    assert t == {"bearish_below": 46, "bullish_above": 55}
    for s in range(0, 101):
        derived = "bearish" if s < t["bearish_below"] else "bullish" if s > t["bullish_above"] else "neutral"
        assert derived == mce.map_label_to_alert_status(mce._label_for_score(s)[0]).lower(), s


@pytest.mark.parametrize("score,label,expected", [
    (30, "Bearish", "bearish"), (45, "Weak", "bearish"), (55, "Neutral", "neutral"),
    (56, "Bullish", "bullish"), (71, "Strong Bullish", "bullish")])
def test_label_three_state_keeps_five_level_text(score, label, expected):
    r = _spec_example(); r["total_score"] = score; r["label"] = label
    p = mcx.build_payload(r)
    assert (p["label"], p["label_text"]) == (expected, label)


def test_export_writes_atomic_0644_and_valid_json(tmp_path):
    path = tmp_path / "mc" / "context.json"
    assert mcx.export_context(_spec_example(), str(path)) is True
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    assert not os.path.exists(str(path) + ".tmp")
    assert json.loads(path.read_text(encoding="utf-8"))["score"] == 55


def test_failure_never_overwrites_old_file(tmp_path, monkeypatch):
    path = tmp_path / "context.json"
    assert mcx.export_context(_spec_example(), str(path))
    before = path.read_bytes()

    bad = _spec_example(); bad["total_score"] = float("nan")          # gagal saat build payload
    assert mcx.export_context(bad, str(path)) is False
    assert path.read_bytes() == before

    def boom(*a, **k):
        raise OSError("disk penuh")
    monkeypatch.setattr(mcx.os, "replace", boom)                      # gagal saat replace
    changed = _spec_example(); changed["total_score"] = 40
    assert mcx.export_context(changed, str(path)) is False
    assert path.read_bytes() == before
    assert not os.path.exists(str(path) + ".tmp")


def test_all_sources_failed_does_not_write(tmp_path):
    path = tmp_path / "context.json"
    r = _all_none(); r["failed_components"] = 5
    assert mcx.export_context(r, str(path)) is False
    assert not path.exists()


def test_calculate_market_score_exports_and_survives_export_error(tmp_path, monkeypatch):
    path = tmp_path / "context.json"
    monkeypatch.setenv("MARKET_CONTEXT_PATH", str(path))
    for name, val in (("get_all_funding_data", {}), ("get_global_market_data", {}),
                      ("get_macro_data", None), ("_get_snapshot", {})):
        monkeypatch.setattr(mce, name, (lambda *a, _v=val, **k: _v))
    r = mce.calculate_market_score()
    assert r["failed_components"] == 5 and not path.exists()          # semua gagal -> tidak ditulis

    monkeypatch.setattr(mce, "_calculate_market_score", lambda: _spec_example())
    assert mce.calculate_market_score()["total_score"] == 55
    assert json.loads(path.read_text(encoding="utf-8"))["score"] == 55

    monkeypatch.setattr(mcx, "export_context", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    assert mce.calculate_market_score()["total_score"] == 55          # error ekspor tidak menjalar


# ---- level 5 tingkat + bands + status per komponen ----

def test_level_matches_label_text_for_every_score():
    for sc in range(0, 101):
        label = mce._label_for_score(sc)[0]
        r = _spec_example(); r["total_score"] = sc; r["label"] = label
        p = mcx.build_payload(r)
        assert p["label_text"] == label
        band = next(b for b in p["bands"] if sc <= b["upto"])           # band yang memuat skor
        assert p["level"] == band["key"], sc
        assert band["text"] == label, sc
        three = "bearish" if sc < p["thresholds"]["bearish_below"] else "bullish" if sc > p["thresholds"]["bullish_above"] else "neutral"
        assert p["label"] == three, sc                                   # 3 keadaan tetap konsisten


def test_bands_exact_and_derived_from_named_constants():
    p = mcx.build_payload(_spec_example())
    assert p["bands"] == [
        {"upto": 30, "key": "bearish", "text": "Bearish"},
        {"upto": 45, "key": "weak", "text": "Weak"},
        {"upto": 55, "key": "neutral", "text": "Neutral"},
        {"upto": 70, "key": "bullish", "text": "Bullish"},
        {"upto": 100, "key": "strong_bullish", "text": "Strong Bullish"},
    ]
    assert [b["upto"] for b in p["bands"]] == [mce.BEARISH_MAX, mce.WEAK_MAX, mce.NEUTRAL_MAX, mce.BULLISH_MAX, 100]
    assert (p["thresholds"], p["v"], p["label"]) == ({"bearish_below": 46, "bullish_above": 55}, 1, "neutral")


def test_old_fields_all_still_present():
    p = mcx.build_payload(_spec_example())
    assert {"v", "ts", "score", "max", "label", "label_text", "summary", "thresholds", "components", "source"} <= set(p)


def _patch_sources(monkeypatch, fear_greed_fails=False):
    snap = {"data": {c: {"trend_4h": "BULLISH", "trend_1d": "SIDEWAYS"} for c in ("BTC", "ETH", "SOL")}}
    monkeypatch.setattr(mce, "_get_snapshot", lambda: snap)
    monkeypatch.setattr(mce, "get_macro_data", lambda *a, **k: {"change": 0.3, "value": 3.5})
    monkeypatch.setattr(mce, "get_all_funding_data", lambda: {"BTC": {"funding_rate": 0.0001}})
    g = {"btc_dominance": 55.0}
    if fear_greed_fails:
        g["fear_greed_status"] = "failed"
    else:
        g["fear_greed"] = 57
    monkeypatch.setattr(mce, "get_global_market_data", lambda: g)


def test_failed_component_marked_not_ok_but_still_written(tmp_path, monkeypatch):
    path = tmp_path / "context.json"
    monkeypatch.setenv("MARKET_CONTEXT_PATH", str(path))
    _patch_sources(monkeypatch, fear_greed_fails=True)
    r = mce.calculate_market_score()
    assert r["failed_components"] == 1 and r["component_ok"]["fear_greed"] is False
    data = json.loads(path.read_text(encoding="utf-8"))
    ok = {c["key"]: c["ok"] for c in data["components"]}
    assert ok == {"trend": True, "macro": True, "fng": False, "funding": True, "dominance": True}
    fng = next(c for c in data["components"] if c["key"] == "fng")
    assert fng["detail"] == "nilai: —" and fng["score"] == r["components"]["fear_greed"]["score"]  # apa adanya, sama dgn Telegram
    assert data["score"] == r["total_score"]


def test_all_components_ok_when_sources_healthy(tmp_path, monkeypatch):
    path = tmp_path / "context.json"
    monkeypatch.setenv("MARKET_CONTEXT_PATH", str(path))
    _patch_sources(monkeypatch)
    r = mce.calculate_market_score()
    assert r["failed_components"] == 0 and all(r["component_ok"].values())
    assert all(c["ok"] is True for c in json.loads(path.read_text(encoding="utf-8"))["components"])


@pytest.mark.parametrize("key", ["price_trend", "macro", "funding_rate", "btc_dominance"])
def test_each_component_failure_flags_only_itself(monkeypatch, key):
    _patch_sources(monkeypatch)
    if key == "price_trend":
        monkeypatch.setattr(mce, "_get_snapshot", lambda: {})
    elif key == "macro":
        monkeypatch.setattr(mce, "get_macro_data", lambda *a, **k: None)
    elif key == "funding_rate":
        monkeypatch.setattr(mce, "get_all_funding_data", lambda: {})
    else:
        monkeypatch.setattr(mce, "get_global_market_data",
                            lambda: {"fear_greed": 57, "btc_dominance_status": "failed"})
    ok = mce._calculate_market_score()["component_ok"]
    assert [k for k, v in ok.items() if not v] == [key]
