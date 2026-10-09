# Build Report: Alert Perubahan Status Konteks Market

Tanggal: 18 September 2026  
Branch kerja: `feature/alert-konteks-market` (dibuat dari `main` pada `eac382a`)  
Status: selesai dibangun dan diuji; committed lokal sebagai `7f5b5de`; belum di-merge, di-push, atau di-deploy.

## Implementasi

Tiga berkas dalam scope diubah/dibuat:

- `engine/market/market_context_engine.py`: fungsi tunggal `map_label_to_alert_status()` dekat `_label_for_score()`. Pemetaan: `Bearish`/`Weak` ke `Bearish`, `Neutral` ke `Neutral`, `Bullish`/`Strong Bullish` ke `Bullish`. Logika skor maupun `_label_for_score()` tidak diubah.
- `interfaces/telegram_bot.py`: job async `market_context_alert_job`, helper filter radar/formatter pesan, dan pendaftaran JobQueue `interval=900, first=200`.
- `tests/test_market_context_alert_job.py`: 11 test baru.

Perilaku job:

1. Mengambil `chat_id` dari `context.bot_data`, fallback `TELEGRAM_CHAT_ID` (`DEFAULT_CHAT_ID`), dan skip bila tidak tersedia.
2. Menghitung status hanya dari `result["label"]` melalui fungsi pemetaan baru.
3. Membaca/menulis `ngov` namespace `market_context_alert`, key `status`.
4. First run hanya menyimpan baseline; status sama tidak melakukan apa pun.
5. Pada transisi, memanggil `generate_radar_pro()` sekali hanya untuk status non-Netral; filter persis `STRONG_BULLISH` atau `STRONG_BEARISH`. Netral tidak memiliki daftar coin. Pesan tetap terkirim jika hasil filter kosong.
6. Memanggil `safe_dispatch(..., force=True)` dan baru menyimpan state baru setelah dispatcher mengembalikan sukses. Bila dispatch tidak terkirim, state lama dipertahankan agar siklus berikutnya dapat mencoba lagi.
7. Seluruh body job berada dalam `try/except` luas sehingga exception job dicatat dan tidak menghentikan JobQueue lain.

## Diff kode aktual

```diff
diff --git a/engine/market/market_context_engine.py b/engine/market/market_context_engine.py
index dc16051..aac3a5e 100644
--- a/engine/market/market_context_engine.py
+++ b/engine/market/market_context_engine.py
@@ -40,6 +40,16 @@ def _label_for_score(score: int) -> tuple[str, str, str]:
     return ("Strong Bullish", "💚", "Kondisi sangat baik — peluang swing terbuka, pantau entry di pullback.")
 
 
+def map_label_to_alert_status(label: str) -> str:
+    """Collapse the five market-score labels into the three alert statuses."""
+    normalized = str(label or "").strip()
+    if normalized in {"Bearish", "Weak"}:
+        return "Bearish"
+    if normalized in {"Bullish", "Strong Bullish"}:
+        return "Bullish"
+    return "Neutral"
+
+
 def _neutral_components() -> dict[str, dict[str, Any]]:
```

```diff
diff --git a/interfaces/telegram_bot.py b/interfaces/telegram_bot.py
index 6bb4dcc..b6dd5d1 100644
--- a/interfaces/telegram_bot.py
+++ b/interfaces/telegram_bot.py
@@ -72,7 +72,11 @@ from engine.market.economic_calendar import (
 )
 from engine.market import institutional_data as inst_data
-from engine.market.market_context_engine import calculate_market_score, format_context_for_brief
+from engine.market.market_context_engine import (
+    calculate_market_score,
+    format_context_for_brief,
+    map_label_to_alert_status,
+)
 import engine.market.market_snapshot_engine as snapshot_state
@@ -5499,6 +5503,95 @@ async def pre_fetch_brief_data_job(_context: ContextTypes.DEFAULT_TYPE) -> None:
         logging.warning("pre_fetch_brief_data_job: %s", e)
 
 
+def _coins_aligned_with_market_status(status: str, radar_data: list[dict]) -> list[str]:
+    """Return only coins whose multi-timeframe alignment strongly matches status."""
+    required_alignment = {
+        "Bullish": "STRONG_BULLISH",
+        "Bearish": "STRONG_BEARISH",
+    }.get(status)
+    if not required_alignment:
+        return []
+    return [
+        str(item.get("coin"))
+        for item in radar_data
+        if item.get("trend_alignment") == required_alignment and item.get("coin")
+    ]
+
+
+def _format_market_context_alert_message(
+    previous_status: str,
+    current_status: str,
+    score: int | float,
+    aligned_coins: list[str],
+    timestamp: str,
+) -> str:
+    emoji = {"Bearish": "🔴", "Neutral": "⚪", "Bullish": "🟢"}
+    lines = [
+        "🔔 Perubahan Status Konteks Market",
+        "",
+        f"{previous_status} {emoji[previous_status]} → {current_status} {emoji[current_status]}",
+        f"Skor: {score}/100",
+    ]
+    if current_status != "Neutral":
+        lines.extend(["", "Coin searah (trend kuat sama arah):"])
+        if aligned_coins:
+            lines.append(", ".join(aligned_coins))
+        else:
+            lines.append("Tidak ada coin dengan trend kuat searah saat ini.")
+    lines.extend(["", f"⏰ {timestamp}"])
+    return "\n".join(lines)
+
+
+async def market_context_alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
+    """Alert once when the persisted three-state market context changes."""
+    try:
+        chat_id = None
+        try:
+            if context and getattr(context, "bot_data", None):
+                chat_id = context.bot_data.get("chat_id")
+        except Exception:
+            chat_id = None
+        if not chat_id:
+            chat_id = DEFAULT_CHAT_ID
+        if not chat_id:
+            logging.warning("market_context_alert skipped: no chat_id (set TELEGRAM_CHAT_ID or /start)")
+            return
+
+        result = calculate_market_score()
+        current_status = map_label_to_alert_status(result.get("label", "Neutral"))
+        previous_status = ngov.get_value("market_context_alert", "status")
+        if previous_status is None:
+            ngov.set_value("market_context_alert", "status", current_status)
+            return
+        if previous_status == current_status:
+            return
+
+        aligned_coins: list[str] = []
+        if current_status != "Neutral":
+            radar_data = generate_radar_pro()
+            aligned_coins = _coins_aligned_with_market_status(current_status, radar_data)
+
+        timestamp = result.get("timestamp") or datetime.now(
+            timezone(timedelta(hours=7))
+        ).strftime("%Y-%m-%d %H:%M:%S WIB")
+        message = _format_market_context_alert_message(
+            str(previous_status), current_status, result.get("total_score", 50),
+            aligned_coins, str(timestamp),
+        )
+        sent = await safe_dispatch(message, chat_id=chat_id, force=True)
+        if sent:
+            ngov.set_value("market_context_alert", "status", current_status)
+        else:
+            logging.warning("market_context_alert dispatch not sent; state not updated")
+    except Exception as e:
+        logging.exception("market_context_alert_job: %s", e)
+
@@ -7940,6 +8033,13 @@ def main():
         logging.info(
             "Pre-fetch brief data job scheduled (every 900s, window 06:00–07:50 / 18:00–19:50 WIB)."
         )
+        app.job_queue.run_repeating(
+            market_context_alert_job,
+            interval=900,
+            first=200,
+            name="market_context_alert",
+        )
+        logging.info("Market context alert job scheduled (every 900s, first in 200s).")
```

```diff
diff --git a/tests/test_market_context_alert_job.py b/tests/test_market_context_alert_job.py
new file mode 100644
--- /dev/null
+++ b/tests/test_market_context_alert_job.py
@@
+@pytest.mark.parametrize(
+    ("label", "expected"),
+    [
+        ("Bearish", "Bearish"), ("Weak", "Bearish"),
+        ("Neutral", "Neutral"), ("Bullish", "Bullish"),
+        ("Strong Bullish", "Bullish"),
+    ],
+)
+def test_map_label_to_alert_status_for_all_market_score_labels(label, expected):
+    assert map_label_to_alert_status(label) == expected
+
+def test_bootstrap_persists_baseline_without_sending(monkeypatch):
+    # state missing → set market_context_alert/status; dispatcher tidak dipanggil
+
+def test_changed_status_sends_alert_filters_strong_bullish_and_persists(monkeypatch):
+    # STRONG_BULLISH lolos; PARTIAL/MIXED/UNKNOWN/STRONG_BEARISH tidak lolos
+
+def test_same_status_does_not_send_or_update_state(monkeypatch):
+    # status sama → tanpa dispatch atau write state
+
+def test_alignment_filter_returns_only_strong_matches():
+    # Bullish → STRONG_BULLISH; Bearish → STRONG_BEARISH; Neutral → []
+
+def test_transition_to_neutral_has_no_coin_list(monkeypatch):
+    # generate_radar_pro tidak boleh dipanggil; pesan tanpa bagian Coin searah
+
+def test_changed_status_without_strong_aligned_coins_still_sends(monkeypatch):
+    # list kosong → pesan tetap dikirim dengan fallback text
```

Diff test di atas menampilkan seluruh perilaku yang ditambahkan; file test lengkap berisi fixture `_Context`, `AsyncMock` dispatcher, dan assertion message/state untuk masing-masing test. Tidak ada perubahan di luar tiga file scope.

## Verifikasi cache dan keputusan interval

Hasil pemeriksaan sebelum menetapkan interval:

| Sumber yang dipanggil `calculate_market_score()` | Cache aktual | Dampak job 900 dtk |
|---|---|---|
| Fear & Greed + BTC dominance, `get_global_market_data()` | `engine/market/global_market_cache.py:14,141-152`: TTL 300 dtk; refresh hanya bila umur cache >= 300 dtk | Tidak memaksa call setiap eksekusi. `snapshot_job` berjalan tiap 60 dtk dan memanggil global market untuk radar, sehingga dalam operasi normal cache sudah hangat. |
| Funding, `get_all_funding_data()` | `engine/market/funding_rate_monitor.py:121,170-182`: cache per coin TTL 900 dtk | Pada cache hit tidak ada request. Pada masa cache habis, job 15 menit paling banyak memicu refresh dalam kadens TTL yang sudah didefinisikan. |
| CPI/FED, `get_macro_data()` | `engine/market/macro_monitor.py:26,77-107,135-146`: raw observation cache per series TTL 21.600 dtk/6 jam, dan job memanggil default `bypass_cache=False` | Tidak menambah request FRED setiap 15 menit; paling banyak refresh per seri setiap 6 jam, setelah cache kosong/expired. |

`pre_fetch_brief_data_job` sendiri (`interfaces/telegram_bot.py:5481-5503`) hanya mengisi `_BRIEF_DATA_CACHE` untuk data brief. Ia bukan cache eksplisit untuk tiga input skor di atas. Cache yang membuat job ini aman adalah cache native global/funding/macro; khusus global juga lazim sudah dihangatkan `snapshot_job` tiap 60 detik. Kesimpulan: **interval 900 detik tetap dipakai**, sesuai keputusan desain; tidak ada bukti kebutuhan menaikkannya ke 1.800 detik.

## Output test mentah

Baseline sebelum perubahan, perintah `venv/bin/python -m pytest -q`:

```text
.......................................................................... [ 20%]
.................................................................... [ 39%]
........................................................................ [ 58%]
........................................................................ [ 78%]
........................................................................ [ 98%]
.....                                                                    [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
363 passed, 3 warnings, 74 subtests passed in 36.73s
```

Test baru, perintah `venv/bin/python -m pytest tests/test_market_context_alert_job.py -v`:

```text
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.1.1, pluggy-1.6.0 -- /opt/aliza-ai/venv/bin/python
cachedir: .pytest_cache
rootdir: /opt/aliza-ai
plugins: anyio-4.12.1, langsmith-0.7.14
collecting ... collected 11 items

tests/test_market_context_alert_job.py::test_map_label_to_alert_status_for_all_market_score_labels[Bearish-Bearish] PASSED [  9%]
tests/test_market_context_alert_job.py::test_map_label_to_alert_status_for_all_market_score_labels[Weak-Bearish] PASSED [ 18%]
tests/test_market_context_alert_job.py::test_map_label_to_alert_status_for_all_market_score_labels[Neutral-Neutral] PASSED [ 27%]
tests/test_market_context_alert_job.py::test_map_label_to_alert_status_for_all_market_score_labels[Bullish-Bullish] PASSED [ 36%]
tests/test_market_context_alert_job.py::test_map_label_to_alert_status_for_all_market_score_labels[Strong Bullish-Bullish] PASSED [ 45%]
tests/test_market_context_alert_job.py::test_bootstrap_persists_baseline_without_sending PASSED [ 54%]
tests/test_market_context_alert_job.py::test_changed_status_sends_alert_filters_strong_bullish_and_persists PASSED [ 63%]
tests/test_market_context_alert_job.py::test_same_status_does_not_send_or_update_state PASSED [ 72%]
tests/test_market_context_alert_job.py::test_alignment_filter_returns_only_strong_matches PASSED [ 81%]
tests/test_market_context_alert_job.py::test_transition_to_neutral_has_no_coin_list PASSED [ 90%]
tests/test_market_context_alert_job.py::test_changed_status_without_strong_aligned_coins_still_sends PASSED [100%]

=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 11 passed, 3 warnings in 9.15s ========================
```

Full suite sesudah perubahan, perintah `venv/bin/python -m pytest -q`:

```text
.......................................................................... [ 19%]
........................................................................ [ 37%]
........................................................................ [ 57%]
........................................................................ [ 76%]
........................................................................ [ 95%]
................                                                         [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
374 passed, 3 warnings, 74 subtests passed in 34.98s
```

`git diff --check` juga lulus tanpa whitespace error.
