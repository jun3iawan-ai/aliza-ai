# Klarifikasi & Bukti Lengkap — Alert Reversal Tren 2 Varian

Tanggal: 24 September 2026
Branch implementasi: feature/trend-reversal-alert
Status: belum merge dan belum deploy.

Dokumen ini melengkapi BUILD_ALERT_REVERSAL_2VARIAN_REPORT.md. Bila terdapat perbedaan pada perilaku retry dispatch, dokumen ini dan kode saat ini adalah yang berlaku.

## 1. Output mentah full test suite

### Sebelum perubahan — worktree terpisah dari main

Main tidak di-checkout pada worktree branch fitur. Untuk menghindari perubahan/stash pada branch kerja, dibuat worktree detached di /tmp/aliza-ai-main-baseline-20260924 dari main pada commit 4561a3f. Perintah yang dijalankan dari worktree tersebut:

```text
/opt/aliza-ai/venv/bin/python -m pytest -q 2>&1 | tee /tmp/pytest_main_before_reversal.txt
```

Output mentah:

```text
.......................................................................... [ 19%]
.................................................................. [ 36%]
........................................................................ [ 55%]
........................................................................ [ 74%]
........................................................................ [ 93%]
.......................                                                  [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
379 passed, 3 warnings, 76 subtests passed in 54.06s
```

### Sesudah perubahan — branch feature/trend-reversal-alert

Perintah yang dijalankan:

```text
venv/bin/python -m pytest -q 2>&1 | tee /tmp/pytest_feature_after_reversal.txt
```

Output mentah:

```text
.......................................................................... [ 18%]
.................................................................. [ 35%]
........................................................................ [ 54%]
........................................................................ [ 72%]
........................................................................ [ 91%]
..................................                                       [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
390 passed, 3 warnings, 76 subtests passed in 37.29s
```

Hasil pembanding: baseline main adalah 379 passed dan branch fitur pascarevisi adalah 390 passed. Seluruh 76 subtest juga lulus pada keduanya.

## 2. Diff kode aktual lengkap

Berikut output lengkap, tanpa elisi, dari perintah:

```text
git diff main -- interfaces/telegram_bot.py
```

```diff
diff --git a/interfaces/telegram_bot.py b/interfaces/telegram_bot.py
index eee0bdf..54eba15 100644
--- a/interfaces/telegram_bot.py
+++ b/interfaces/telegram_bot.py
@@ -50,6 +50,7 @@ from engine.market.coin_info import get_tokenomics
 from engine.market.volume_spike_detector import (
     run_volume_spike_check,
     format_volume_spike_alert_message,
+    get_avg_volume,
 )
 from engine.market.funding_rate_monitor import (
     format_funding_section_for_brief,
@@ -5592,6 +5593,139 @@ async def market_context_alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
         logging.exception("market_context_alert_job: %s", e)


+_STRONG_ALIGNMENT_DIRECTIONS = {
+    "STRONG_BULLISH": "BULLISH",
+    "STRONG_BEARISH": "BEARISH",
+}
+
+
+def _strong_alignment_direction(alignment: object) -> str | None:
+    """Return a confirmed strong direction, or None for transitional alignment."""
+    return _STRONG_ALIGNMENT_DIRECTIONS.get(str(alignment or "").strip().upper())
+
+
+def _format_trend_reversal_alert(
+    coin: str,
+    old_direction: str,
+    new_direction: str,
+    alignment: str,
+    price: object,
+    *,
+    volume_24h: float | None = None,
+    avg_volume: float | None = None,
+) -> str:
+    """Format the simple or volume-confirmed per-coin reversal notification."""
+    timestamp = _wib_now_label()
+    if volume_24h is None or avg_volume is None:
+        return (
+            "🔄 REVERSAL TREN TERDETEKSI\n\n"
+            f"{coin}: {old_direction} → {new_direction}\n"
+            f"Alignment: {alignment} (4H & 1D searah)\n"
+            f"Harga: {_fmt_snapshot_usd(price)}\n\n"
+            f"⏰ {timestamp}"
+        )
+    return (
+        "🔄✅ REVERSAL TREN TERKONFIRMASI\n\n"
+        f"{coin}: {old_direction} → {new_direction}\n"
+        f"Alignment: {alignment} (4H & 1D searah)\n"
+        f"Volume 24h: {volume_24h:,.2f} USDT (avg 14D: {avg_volume:,.2f} USDT) — tidak anomali rendah\n"
+        f"Harga: {_fmt_snapshot_usd(price)}\n\n"
+        f"⏰ {timestamp}"
+    )
+
+
+async def trend_reversal_checker(context: ContextTypes.DEFAULT_TYPE) -> None:
+    """Send simple and volume-confirmed alerts when a coin's strong direction reverses.
+
+    The persisted value is deliberately the *last confirmed strong direction*,
+    not the raw alignment from the last snapshot. Transitional PARTIAL/MIXED/
+    UNKNOWN snapshots therefore cannot erase the baseline before the opposite
+    strong alignment is reached.
+    """
+    try:
+        chat_id = None
+        if context and getattr(context, "bot_data", None):
+            chat_id = context.bot_data.get("chat_id")
+        if not chat_id:
+            chat_id = DEFAULT_CHAT_ID
+        if not chat_id:
+            logging.warning("trend_reversal_checker: no chat_id")
+            return
+
+        snapshot = get_market_snapshot()
+        data_map = snapshot.get("data") or {}
+        if not data_map:
+            logging.warning("trend_reversal_checker: empty snapshot")
+            return
+
+        for raw_coin, coin_data in data_map.items():
+            if not isinstance(coin_data, dict):
+                continue
+            coin = str(raw_coin or "").strip().upper()
+            if not coin:
+                continue
+            alignment = str(coin_data.get("trend_alignment") or "").strip().upper()
+            current_direction = _strong_alignment_direction(alignment)
+            if current_direction is None:
+                # Preserve the last confirmed strong state across the expected
+                # PARTIAL/MIXED/UNKNOWN transition period.
+                continue
+
+            previous_direction = ngov.get_value("trend_reversal_state", coin)
+            if previous_direction is None:
+                # Bootstrap is intentionally silent, just like the market-context alert.
+                ngov.set_value("trend_reversal_state", coin, current_direction)
+                continue
+
+            previous_direction = str(previous_direction).strip().upper()
+            if previous_direction == current_direction:
+                continue
+
+            simple_sent = False
+            try:
+                simple_message = _format_trend_reversal_alert(
+                    coin,
+                    previous_direction,
+                    current_direction,
+                    alignment,
+                    coin_data.get("price"),
+                )
+                simple_sent = await safe_dispatch(simple_message, chat_id=chat_id, force=True)
+
+                volume_24h = _snapshot_float(coin_data.get("volume_24h"))
+                # This intentionally loose gate reuses the 14D quote-volume helper.
+                # get_avg_volume() may include the still-open daily candle, which is
+                # acceptable here because the requirement is only "not abnormally low",
+                # not a precision closed-candle volume confirmation.
+                avg_volume = get_avg_volume(coin)
+                if (
+                    simple_sent
+                    and volume_24h is not None
+                    and avg_volume is not None
+                    and avg_volume > 0
+                    and volume_24h >= avg_volume * 0.5
+                ):
+                    strict_message = _format_trend_reversal_alert(
+                        coin,
+                        previous_direction,
+                        current_direction,
+                        alignment,
+                        coin_data.get("price"),
+                        volume_24h=volume_24h,
+                        avg_volume=float(avg_volume),
+                    )
+                    await safe_dispatch(strict_message, chat_id=chat_id, force=True)
+            except Exception as coin_error:
+                logging.warning("trend_reversal_checker: alert processing failed for %s: %s", coin, coin_error)
+            finally:
+                # The simple alert is the primary event notification. Keep its
+                # prior baseline for a later retry if Telegram did not accept it.
+                # A strict-volume alert is supplementary and cannot block update.
+                if simple_sent:
+                    ngov.set_value("trend_reversal_state", coin, current_direction)
+    except Exception as e:
+        logging.exception("trend_reversal_checker: %s", e)
+
 import re as _re_sig


@@ -8058,6 +8192,13 @@ def main():
             name="market_context_alert",
         )
         logging.info("Market context alert job scheduled (every 900s, first in 200s).")
+        app.job_queue.run_repeating(
+            trend_reversal_checker,
+            interval=300,
+            first=210,
+            name="trend_reversal_checker",
+        )
+        logging.info("Trend reversal checker job scheduled (every 300s, first in 210s).")
         WIB_TIMES_UTC = [
             (23, 0),  # 06:00 WIB
             (5, 0),  # 12:00 WIB
```

## 3. Output test reversal verbose

Perintah yang dijalankan:

```text
venv/bin/python -m pytest tests/test_trend_reversal_alert.py -v
```

Output mentah:

```text
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.1.1, pluggy-1.6.0 -- /opt/aliza-ai/venv/bin/python
cachedir: .pytest_cache
rootdir: /opt/aliza-ai
plugins: anyio-4.12.1, langsmith-0.7.14
collecting ... collected 11 items

tests/test_trend_reversal_alert.py::test_bootstrap_stores_strong_baseline_without_alert PASSED [  9%]
tests/test_trend_reversal_alert.py::test_transitional_alignments_preserve_baseline_without_alert[PARTIAL] PASSED [ 18%]
tests/test_trend_reversal_alert.py::test_transitional_alignments_preserve_baseline_without_alert[MIXED] PASSED [ 27%]
tests/test_trend_reversal_alert.py::test_transitional_alignments_preserve_baseline_without_alert[UNKNOWN] PASSED [ 36%]
tests/test_trend_reversal_alert.py::test_reversal_survives_mixed_and_partial_before_opposite_strong PASSED [ 45%]
tests/test_trend_reversal_alert.py::test_simple_alert_sends_when_volume_is_anomalously_low PASSED [ 54%]
tests/test_trend_reversal_alert.py::test_strict_alert_sends_only_when_volume_meets_half_of_average PASSED [ 63%]
tests/test_trend_reversal_alert.py::test_same_strong_direction_does_not_refire_after_reversal PASSED [ 72%]
tests/test_trend_reversal_alert.py::test_simple_dispatch_false_keeps_baseline_for_retry PASSED [ 81%]
tests/test_trend_reversal_alert.py::test_simple_dispatch_exception_keeps_baseline_for_retry PASSED [ 90%]
tests/test_trend_reversal_alert.py::test_strict_dispatch_failure_does_not_block_baseline_update PASSED [100%]

=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute

<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 11 passed, 3 warnings in 14.45s ========================
```

Delapan test awal tetap ada; tiga test regresi ditambahkan untuk kebijakan retry dispatch yang dijelaskan pada bagian berikut.

## 4. Klarifikasi dan revisi desain baseline

### Perilaku sebelum revisi

Ya. Implementasi awal benar-benar memajukan trend_reversal_state di blok finally tanpa memeriksa nilai balik safe_dispatch. Akibatnya dua kondisi berikut sama-sama memindahkan baseline:

- safe_dispatch alert sederhana mengembalikan False;
- safe_dispatch alert sederhana melempar exception.

Alert ketat yang gagal juga memindahkan baseline karena finally selalu berjalan. Ini berbeda dari market_context_alert_job, yang menulis state hanya setelah safe_dispatch mengembalikan nilai truthy.

Perilaku tersebut bukan keputusan sadar yang diperlukan oleh spesifikasi. Instruksi build memang menyatakan baseline harus tetap di-update bila alert ketat tidak lolos volume, tetapi tidak memberi alasan untuk menghilangkan event ketika alert sederhana—satu-satunya notifikasi primer—gagal dikirim. Risiko Telegram down pada saat reversal lalu event hilang permanen tidak dapat diterima untuk alert primer.

### Perilaku sesudah revisi

Kode sekarang menginisialisasi simple_sent = False dan menyimpan hasil dispatch alert sederhana:

```python
simple_sent = await safe_dispatch(simple_message, chat_id=chat_id, force=True)
```

State hanya diperbarui bila simple_sent truthy:

```python
if simple_sent:
    ngov.set_value("trend_reversal_state", coin, current_direction)
```

Konsekuensinya:

- Bila dispatch sederhana mengembalikan False atau melempar exception, baseline tetap arah lama; reversal yang sama dievaluasi ulang pada job berikutnya (5 menit). Alert ketat juga tidak dikirim sebelum alert sederhana sukses.
- Bila dispatch sederhana sukses, baseline segera berpindah, bahkan bila volume rendah, helper volume gagal, atau dispatch alert ketat gagal/exception. Ini mempertahankan aturan bahwa alert ketat adalah pelengkap dan tidak boleh menyebabkan duplikasi alert sederhana.

Test yang membuktikan perilaku ini adalah test_simple_dispatch_false_keeps_baseline_for_retry, test_simple_dispatch_exception_keeps_baseline_for_retry, dan test_strict_dispatch_failure_does_not_block_baseline_update; semuanya PASSED pada output verbose di atas.

## Verifikasi akhir

Selain pytest, verifikasi berikut lulus tanpa output error:

```text
venv/bin/python -m py_compile interfaces/telegram_bot.py tests/test_trend_reversal_alert.py
git diff --check main -- interfaces/telegram_bot.py
```

Tidak ada merge, commit, restart service, atau deploy yang dilakukan.

