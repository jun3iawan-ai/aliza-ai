# Klarifikasi dan Bukti Fix BEARISH Palsu + Fallback Konteks

Tanggal bukti: 18 September 2026
Branch kerja: `fix/bearish-palsu-fallback-konteks`
Status: belum di-commit, belum di-push, belum di-merge, dan tidak ada deployment.

Dokumen ini melengkapi laporan fix awal dengan bukti mentah untuk review sebelum merge.

## 1. Klarifikasi branch

Command yang dijalankan sebelum membuat branch:

```text
main
23d6b0d fix: crash risk label no longer defaults to every coin on global HIGH risk
d35c6c2 docs: add merge/deploy/verification report for duplikasi-header-utf16 fix
068fd6a fix: dedup duplicate KEPUTUSAN HARI INI block, restore missing SARAN SPOT header, UTF-16-aware message split
46b37ae docs: pindahkan 3 file report tracked terakhir + update indeks
42f3258 docs: rapikan 3 laporan lepas 27 Agustus ke docs/reports
```

- `git rev-parse main origin/main` menghasilkan hash identik `23d6b0d0c7c818c746faf3c916b57c7ab0ae373d` dua kali.
- `git log origin/main..main` dan `git log main..origin/main` kosong: tidak ada commit lokal yang belum dipush dan tidak ada commit remote yang belum ada di lokal.
- Jadi fix ini tidak pernah di-commit langsung ke `main`; ia masih working-tree change pada `main`. Tidak dilakukan reset atau hard reset.
- Langkah isolasi yang dijalankan: `git switch -c fix/bearish-palsu-fallback-konteks`.
- Setelah itu branch aktif adalah `fix/bearish-palsu-fallback-konteks`, sementara `main` tetap sama dengan `origin/main` pada `23d6b0d`.


## 2. Diff kode aktual terhadap main

Diff berikut berasal dari `git diff main -- <file>`.

### engine/market/market_context_engine.py

```diff
diff --git a/engine/market/market_context_engine.py b/engine/market/market_context_engine.py
index 982334b..dc16051 100644
--- a/engine/market/market_context_engine.py
+++ b/engine/market/market_context_engine.py
@@ -62,7 +62,7 @@ def calculate_market_score() -> dict[str, Any]:
     try:
         g = get_global_market_data() or {}
         fg = _safe_float(g.get("fear_greed"))
-        if fg is None:
+        if g.get("fear_greed_status") == "failed" or fg is None:
             failed_components += 1
         else:
             if fg <= 24:
@@ -84,7 +84,7 @@ def calculate_market_score() -> dict[str, Any]:
     try:
         g = get_global_market_data() or {}
         dom = _safe_float(g.get("btc_dominance"))
-        if dom is None:
+        if g.get("btc_dominance_status") == "failed" or dom is None:
             failed_components += 1
         else:
             if dom > 60:
```


### engine/prediction/prediction_engine.py

```diff
diff --git a/engine/prediction/prediction_engine.py b/engine/prediction/prediction_engine.py
index dc60d0b..23c3fb2 100644
--- a/engine/prediction/prediction_engine.py
+++ b/engine/prediction/prediction_engine.py
@@ -22,7 +22,7 @@ def generate_market_prediction(snapshot):
     """
     1. Panggil calculate_market_bias(snapshot)
     2. Panggil calculate_probabilities(bullish_score, bearish_score)
-    3. Bias: bullish_probability > bearish_probability → BULLISH, else → BEARISH
+    3. Bias: probabilitas lebih tinggi menentukan BULLISH/BEARISH; skor seri → NEUTRAL
     4. Confidence: > 70 → HIGH, 55–70 → MEDIUM, < 55 → LOW
 
     Return: {
@@ -55,8 +55,10 @@ def generate_market_prediction(snapshot):
 
         if bull_p > bear_p:
             result["bias"] = "BULLISH"
-        else:
+        elif bear_p > bull_p:
+            result["bias"] = "BEARISH"
+        else:
+            result["bias"] = "NEUTRAL"
         if bull_p > 70 or bear_p > 70:
```

### interfaces/telegram_bot.py

```diff
diff --git a/interfaces/telegram_bot.py b/interfaces/telegram_bot.py
index 2ae0fa6..6bb4dcc 100644
--- a/interfaces/telegram_bot.py
+++ b/interfaces/telegram_bot.py
@@ -2132,7 +2132,12 @@ async def quant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
         scores = calculate_market_bias(snapshot)
         bullish_score = scores.get("bullish_score", 0)
         bearish_score = scores.get("bearish_score", 0)
-        bias = "BULLISH" if bullish_score > bearish_score else "BEARISH"
+        if bullish_score > bearish_score:
+            bias = "BULLISH"
+        elif bearish_score > bullish_score:
+            bias = "BEARISH"
+        else:
+            bias = "NEUTRAL"
         total = bullish_score + bearish_score
         if total == 0:
```

## 3. Konsumen bias `/predict` dan `/quant`

- Konsumen langsung `prediction.get("bias", "NEUTRAL")` hanya berada di `interfaces/telegram_bot.py:2092`; nilainya langsung dimasukkan ke string `Short-term Bias` pada baris 2098. Tidak ada asumsi `else == BEARISH`.

- Pencarian pemanggil `calculate_market_bias()` menghasilkan tepat dua pemakaian produksi selain definisinya:

```text
engine/prediction/prediction_engine.py:45  bias_out = calculate_market_bias(snapshot)
interfaces/telegram_bot.py:2132            scores = calculate_market_bias(snapshot)
engine/prediction/bias_score_engine.py:11  def calculate_market_bias(snapshot)
```

- `quant_command` hanya dipanggil oleh routing tombol Telegram pada `interfaces/telegram_bot.py:791` dan `:949`; ia tidak mengembalikan nilai `bias`, hanya mengirim string `Market Bias` pada baris 2165.
- Tidak ada formatter lain, command lain, atau consumer hasil `calculate_market_bias()` yang perlu disesuaikan. Test baru adalah satu-satunya referensi tambahan, dan hanya memverifikasi output.


## 4. Output test mentah

Command test baru: `venv/bin/python -m pytest tests/test_prediction_bias_and_market_context.py -v`

```text
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.1.1, pluggy-1.6.0 -- /opt/aliza-ai/venv/bin/python
cachedir: .pytest_cache
rootdir: /opt/aliza-ai
plugins: anyio-4.12.1, langsmith-0.7.14
collecting ... collected 4 items

tests/test_prediction_bias_and_market_context.py::test_predict_and_quant_report_neutral_for_a_genuine_zero_zero_tie PASSED [ 25%]
tests/test_prediction_bias_and_market_context.py::test_predict_and_quant_keep_their_existing_non_tie_directions PASSED [ 50%]
tests/test_prediction_bias_and_market_context.py::test_failed_global_statuses_exclude_fallback_values_from_market_score PASSED [ 75%]
tests/test_prediction_bias_and_market_context.py::test_brief_format_is_stable_for_ok_status_and_valid_when_status_failed PASSED [100%]

=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 4 passed, 3 warnings in 9.29s =========================
```
### Full suite sebelum fix

Perintah tanpa scope path yang dijalankan dari worktree sementara `/tmp/aliza-ai-baseline-proof` adalah `/opt/aliza-ai/venv/bin/python -m pytest -q`; worktree detached pada `main` = `origin/main` = `23d6b0d`.

```text
.......................................................................... [ 20%]
.................................................................... [ 39%]
........................................................................ [ 59%]
........................................................................ [ 79%]
........................................................................ [ 99%]
.                                                                        [100%]
=============================== warnings summary ===============================
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyPacked has no __module__ attribute
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type SwigPyObject has no __module__ attribute
<frozen importlib._bootstrap>:241
  <frozen importlib._bootstrap>:241: DeprecationWarning: builtin type swigvarlink has no __module__ attribute

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
359 passed, 3 warnings, 74 subtests passed in 33.23s
```

### Full suite sesudah fix

Perintah yang dijalankan dari branch fix: `venv/bin/python -m pytest -q`.

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
363 passed, 3 warnings, 74 subtests passed in 33.11s
```

## 5. Fixture Bug 2 dan perhitungan skor

Fixture bersama di `_market_score()`:

```python
get_all_funding_data() -> {
    "BTC": {"funding_rate": 0.0}, "ETH": {"funding_rate": 0.0},
    "BNB": {"funding_rate": 0.0}, "SOL": {"funding_rate": 0.0},
    "XRP": {"funding_rate": 0.0},
}
get_macro_data("CPIAUCSL", "pct_change_yoy") -> {"change": -1.0}
get_macro_data("FEDFUNDS", "latest") -> {"value": 5.0, "change": 0.0}
scan_for_signals() -> {"confidence": 80}
```

Global input normal adalah `{"fear_greed": 50.0, "fear_greed_status": "ok", "btc_dominance": 55.0, "btc_dominance_status": "ok"}`. Variasi gagal mempertahankan angka fallback yang sama, tetapi mengubah status field terkait menjadi `"failed"`.

| Komponen | Input/rule | Status ok | Status failed |
|---|---|---:|---:|
| Fear & Greed | 50.0, `<=55` | 13 | 10 (default komponen gagal) |
| BTC dominance | 55.0, `>=50` | 10 | 8 (default komponen gagal) |
| Funding | rata-rata 0.0%, `<=0.05` | 25 | 25 |
| Macro | CPI -1.0, Fed 5.0 stabil | 25 | 25 |
| Technical | confidence 80, `>70` | 15 | 15 |

- Normal: `13 + 10 + 25 + 25 + 15 = 88`.
- Fear & Greed gagal: `10 + 10 + 25 + 25 + 15 = 85`.
- Dominance gagal: `13 + 8 + 25 + 25 + 15 = 86`.
- Keduanya gagal: `10 + 8 + 25 + 25 + 15 = 83`.
- Assertion juga mengecek value komponen gagal bernilai `None`; `format_context_for_brief()` membentuk output valid tanpa string `None`, serta normal output memuat `F&G : 50 (Neutral) | BTC.D: 55.0%`.

