"""/cek rencana entry — penilaian deterministik."""
from datetime import datetime, timedelta, timezone

from engine.trading import entry_check as ec

NOW = datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc)
CLOSES = [100 + (0.6 if i % 2 else -0.6) for i in range(20)]  # gerak ±1.2%/candle


def ctx(**kw):
    base = dict(price=100.0, trend_4h="BULLISH", trend_1d="BULLISH", rsi=55,
                levels={"support": 97.0, "support2": 94.0, "resistance": 106.0, "resistance2": 110.0},
                closes_4h=CLOSES, funding_rate=0.00005, events=[], calendar_live=True,
                capital=1000.0, risk_pct_default=1.0, now=NOW)
    base.update(kw)
    return base


def run(text, **kw):
    plan, err = ec.parse_plan(text)
    assert err is None, err
    return plan, ec.evaluate(plan, ctx(**kw))


def test_parse_variants_and_errors():
    p, _ = ec.parse_plan("/cek btc LONG 82.5k sl 81,000 tp 86000 lev 5x risk 0.5%")
    assert (p.coin, p.side, p.entry, p.sl, p.tp, p.lev, p.risk_pct) == ("BTC", "LONG", 82500, 81000, 86000, 5, 0.5)
    p, _ = ec.parse_plan("cek sol short now sl 113")
    assert p.entry is None and p.side == "SHORT"
    assert ec.parse_plan("cek btc long 100")[1]                      # kurang data
    assert "Stop loss wajib" in ec.parse_plan("cek btc long 100 tp 110 lev 2")[1]
    assert "long/short" in ec.parse_plan("cek btc naik 100 sl 99")[1]


def test_good_long_with_trend_supports():
    _, r = run("cek btc long 100 sl 96 tp 106")
    assert r["verdict"].startswith("🟢")
    texts = " | ".join(t for _, t in r["checks"])
    assert "RR 1.5 ke TP" in texts and "SL di bawah support" in texts and "Searah tren 4H & 1D" in texts
    sz = r["sizing"]
    assert round(sz["risk_usd"], 2) == 10 and round(sz["notional"], 2) == 250


def test_countertrend_and_bad_rr_is_bertentangan():
    _, r = run("cek btc long 100 sl 96 tp 102", trend_4h="BEARISH", trend_1d="BEARISH")
    assert r["verdict"].startswith("🔴")
    marks = dict((t.split()[0], m) for m, t in r["checks"])
    assert marks["Melawan"] == ec.BAD and marks["RR"] == ec.BAD


def test_obstacle_tight_sl_and_sl_above_support():
    _, r = run("cek btc long 100 sl 99.5 tp 112")
    texts = " | ".join(f"{m} {t}" for m, t in r["checks"])
    assert "⚠️ Resistance $106 menghalangi sebelum TP" in texts
    assert "⚠️ SL 0.5% < gerak rata-rata" in texts
    assert "⚠️ SL di atas support $97" in texts


def test_leverage_liquidation_before_sl_is_critical():
    _, r = run("cek btc long 100 sl 90 lev 20")
    assert any(m == ec.BAD and "Likuidasi" in t for m, t in r["checks"])
    _, r2 = run("cek btc long 100 sl 96 lev 5")
    assert any(m == ec.OK and "Likuidasi" in t for m, t in r2["checks"])
    assert round(r2["sizing"]["margin"], 2) == 50


def test_high_event_soon_and_calendar_not_live():
    ev = [{"name": "CPI", "impact": "HIGH", "datetime_utc": (NOW + timedelta(hours=1)).isoformat()}]
    _, r = run("cek btc long 100 sl 96 lev 3", events=ev)
    assert any(m == ec.BAD and "CPI" in t for m, t in r["checks"])
    _, r2 = run("cek btc long 100 sl 96", calendar_live=False)
    assert any("kalender ekonomi live tidak tersedia" in t for _, t in r2["checks"])


def test_short_mirror_and_default_target_and_geometry_error():
    _, r = run("cek btc short now sl 104", trend_4h="BEARISH", trend_1d="SIDEWAYS")
    texts = " | ".join(t for _, t in r["checks"])
    assert "ke level support terdekat $97" in texts and "SL di atas resistance" not in texts
    _, bad = run("cek btc long 100 sl 101")
    assert "harus di bawah entry" in bad["error"]


def test_limit_entry_far_from_price_is_flagged():
    _, r = run("cek btc long 95 sl 93 tp 100")
    assert any(m == ec.WARN and "order limit belum tentu terisi" in t for m, t in r["checks"])


def test_format_contains_verdict_and_no_signal_wording():
    plan, r = run("cek btc long 100 sl 96 tp 106 lev 5")
    out = ec.format_result(plan, r, label="📈 Uptrend", snapshot_ts="15:00")
    assert "🧭 CEK RENCANA — BTC LONG (futures 5×)" in out and "Penilaian: 🟢" in out
    assert "bukan sinyal" in out and "Margin 5×" in out
    plan2, r2 = run("cek btc long 100 sl 96", capital=None)
    assert "/modal 1000" in ec.format_result(plan2, r2)


# ---- integrasi bot ----
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


def _upd(text, replies):
    async def reply_text(m, **k):
        replies.append(m)
    msg = SimpleNamespace(text=text, reply_text=reply_text)
    return SimpleNamespace(message=msg, effective_message=msg)


def test_free_text_and_menu_buttons_route():
    replies = []
    with patch.object(tb, "_run_entry_check", AsyncMock()) as run:
        asyncio.run(tb.menu_button_handler(_upd("cek btc long 100 sl 96", replies), SimpleNamespace(user_data={})))
    run.assert_awaited_once()
    asyncio.run(tb.menu_button_handler(_upd("🧭 Cek Entry", replies), SimpleNamespace(user_data={})))
    assert "/cek BTC long" in replies[-1]
    labels = [getattr(b, "text", b) for row in tb._trading_submenu_keyboard().keyboard for b in row]
    assert "🧭 Cek Entry" in labels and "🧮 Atur Modal" in labels


def test_modal_command_persists_capital_and_risk():
    replies = []
    with patch.object(tb, "_authorized_chat", return_value=True):
        asyncio.run(tb.modal_command(_upd("", replies), SimpleNamespace(args=["2500", "risk", "1.5"])))
    assert tb._risk_settings() == (2500.0, 1.5)
    assert "2,500.00 USDT" in replies[-1] and "1.5%" in replies[-1]


def test_run_entry_check_end_to_end_with_stubbed_data():
    replies = []
    snap = {"data": {"BTC": {"price": 100.0}}}
    c = ctx(capital=1000.0)
    async def go():
        with patch.object(tb, "get_market_snapshot", return_value=snap), \
             patch.object(tb, "_gather_entry_context", return_value=c), \
             patch.object(tb, "get_snapshot_timestamp_str", return_value="15:00"):
            async def reply(m):
                replies.append(m)
            await tb._run_entry_check("cek btc long 100 sl 96 tp 106 lev 5", reply)
            await tb._run_entry_check("cek doge long 1 sl 0.9", reply)
    asyncio.run(go())
    assert "🧭 CEK RENCANA — BTC LONG (futures 5×)" in replies[0]
    assert "tidak ada di daftar coin" in replies[1]


def test_short_without_lev_is_not_spot_and_no_spot_size_warning():
    plan, r = run("cek btc short 100 sl 100.5", trend_4h="BEARISH")
    out = ec.format_result(plan, r)
    assert "(futures, leverage belum diisi)" in out
    assert not any("untuk spot" in t for _, t in r["checks"])


def test_tight_sl_with_high_leverage_is_critical_and_margin_over_capital():
    _, r = run("cek btc long 100 sl 99.5 tp 106 lev 20")
    assert any(m == ec.BAD and "kritis dengan leverage 20×" in t for m, t in r["checks"])
    _, r2 = run("cek btc long 100 sl 99 lev 1", capital=100.0, risk_pct_default=5)
    assert any(m == ec.BAD and "Margin" in t and "> modal" in t for m, t in r2["checks"])
