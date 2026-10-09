"""Alert level buatan user."""
import asyncio
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from engine.alerts import user_alerts as ua

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
with patch("dotenv.load_dotenv", return_value=False):
    from interfaces import telegram_bot as tb


def test_parse_variants_and_errors():
    assert ua.parse_alert("/alert eth above 2,553")[0] == {"coin": "ETH", "direction": "above", "level": 2553.0, "tf": None}
    assert ua.parse_alert("alert btcusdt bawah 81k 4h")[0] == {"coin": "BTC", "direction": "below", "level": 81000.0, "tf": "4h"}
    assert "above/below" in ua.parse_alert("alert eth naikkk 1")[1]
    assert "1h, 4h, atau 1d" in ua.parse_alert("alert eth above 1 15m")[1]
    assert ua.parse_alert("alert eth")[1]


def test_create_rejects_already_crossed_and_persists():
    spec = {"coin": "ETH", "direction": "above", "level": 2553.0, "tf": None}
    assert "sudah di atas" in ua.create_alert(spec, 2600.0)[1]
    assert "tidak ditemukan" in ua.create_alert(spec, None)[1]
    a, err = ua.create_alert(spec, 2500.0)
    assert err is None and a["id"] == 1 and ua.active_alerts()[0]["level"] == 2553.0
    assert ua.delete_alert(1) and ua.active_alerts() == [] and not ua.delete_alert(1)


def test_evaluate_touch_and_close_with_creation_guard():
    t0 = 1_000_000.0
    touch = {"id": 1, "coin": "ETH", "direction": "above", "level": 100.0, "tf": None, "created_at": t0}
    close = {"id": 2, "coin": "BTC", "direction": "below", "level": 50.0, "tf": "4h", "created_at": t0}
    hits = ua.evaluate([touch, close], {"ETH": 100.5}, lambda c, tf: (49.0, int((t0 + 10) * 1000)))
    assert [(h["alert"]["id"], h["kind"]) for h in hits] == [(1, "touch"), (2, "close")]
    # candle tutup sebelum alert dibuat → tidak dihitung
    assert ua.evaluate([close], {}, lambda c, tf: (49.0, int((t0 - 10) * 1000))) == []
    assert ua.evaluate([touch], {"ETH": 99.0}, lambda c, tf: None) == []


def test_mark_triggered_deactivates():
    a, _ = ua.create_alert({"coin": "ETH", "direction": "below", "level": 90.0, "tf": None}, 100.0)
    ua.mark_triggered([a["id"]], {a["id"]: 89.5})
    assert ua.active_alerts() == []


def _upd(text, replies):
    async def reply_text(m, **k):
        replies.append(m)
    msg = SimpleNamespace(text=text, reply_text=reply_text)
    return SimpleNamespace(message=msg, effective_message=msg)


def test_bot_create_list_delete_and_job_dispatch(monkeypatch):
    replies = []
    monkeypatch.setattr(ua, "fetch_prices", lambda coins: {c: 100.0 for c in coins})
    asyncio.run(tb.menu_button_handler(_upd("alert eth above 105", replies), SimpleNamespace(user_data={})))
    assert "✅ Alert #1 dibuat" in replies[-1]
    asyncio.run(tb.menu_button_handler(_upd("🔔 Alert Saya", replies), SimpleNamespace(user_data={})))
    assert "#1  ETH" in replies[-1]
    # harga naik ke 106 → job mengirim & menonaktifkan
    monkeypatch.setattr(ua, "fetch_prices", lambda coins: {c: 106.0 for c in coins})
    sent = AsyncMock(return_value=True)
    with patch.object(tb, "safe_dispatch", sent):
        asyncio.run(tb.user_alert_job(SimpleNamespace(bot_data={"chat_id": 1})))
    assert sent.await_count == 1 and "🔔 ALERT TERPICU" in sent.await_args.args[0]
    assert ua.active_alerts() == []
    asyncio.run(tb.menu_button_handler(_upd("alert hapus 1", replies), SimpleNamespace(user_data={})))
    assert "tidak ditemukan" in replies[-1]
