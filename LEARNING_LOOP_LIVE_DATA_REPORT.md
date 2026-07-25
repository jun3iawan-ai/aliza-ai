# Laporan — Sambungkan Learning Loop ke Data Live

**Tanggal:** 25 Juli 2026
**Branch:** `feat/learning-loop-live-data` (dibuat dari `main`)
**Scope:** `/opt/aliza-ai` — sambungkan `confidence_adjuster` + `drawdown_protector` ke hasil sinyal live, tanpa mekanisme baru, tanpa memperluas cakupan drawdown ke broadcast otomatis, tanpa mengubah `.env` produksi.

Konteks: audit read-only sebelumnya (`AUDIT_MEKANISME_EVALUASI_REPORT.md`) menemukan `engine/learning/confidence_adjuster.py` dan `engine/portfolio/drawdown_protector.py` sudah terpasang di jalur produksi (`TradingBrain.analyze()`, perintah `/entry`), tapi mati secara fungsional karena sumber datanya, `data/trade_history.json`, beku sejak 13 Maret 2025 (2 baris seed) dan tidak pernah ditulis oleh kode live manapun.

---

## Langkah 0 — Diagnosis & Keputusan

### 0.1–0.2 Pemetaan format data

`analyze_strategy_performance()` (`engine/learning/strategy_performance.py:10-59`) dan `analyze_performance()` (`engine/analytics/performance_analyzer.py:11-78`) mengharapkan `history`: list of dict dengan minimal `setup`, `result` ("WIN"/"LOSS"), `rr`. `drawdown_protector.check_drawdown()` (`engine/portfolio/drawdown_protector.py:17-44`) mengharapkan list yang sama, diasumsikan **urut kronologis dengan trade terbaru di posisi akhir list** (dipakai `reversed(closed)` lalu berhenti pada non-LOSS pertama).

Skema `signal_tracking` (SQLite, `engine/trading/signal_tracker.py:71-92`) sudah punya semua field yang dibutuhkan: `coin`, `setup`, `side`, `rr`, `confidence`, `status` (`OPEN`/`WIN`/`LOSS`/`EXPIRED`), `close_time`, `signal_time`, `source`. Tinggal proyeksi 1:1: `status` closed (`WIN`/`LOSS`) → `result`, `rr`/`confidence` langsung dipetakan, urut ASC berdasar `COALESCE(close_time, signal_time)`.

### 0.3 Pendekatan dipilih: **(A) — baca langsung dari SQLite**

Diaudit dulu apakah ada pemanggil lain `trade_history.json`/`record_trade_open`/`record_trade_close` yang perlu dipertahankan:
```
grep -rn "record_trade_open\|record_trade_close" --include="*.py" .
→ hanya definisi di trade_history_tracker.py, tidak ada pemanggil lain di seluruh repo.
```
Ditemukan juga **satu konsumen tambahan** yang belum tercatat di audit sebelumnya: `/performance` command (`interfaces/telegram_bot.py:1619-1644`, fungsi `performance_command`) memakai `get_closed_history()` + `analyze_performance()` — sama-sama mengandalkan file beku yang sama. Ini otomatis ikut diperbaiki oleh perubahan di titik yang sama, tanpa perlu sentuh `telegram_bot.py`.

Karena tidak ada penulis aktif untuk `trade_history.json` dan tiga konsumen (`learning_engine`, `drawdown_protector`, `/performance`) semuanya masuk lewat satu fungsi (`trade_history_tracker.get_closed_history()`), Pendekatan (A) dipilih: ubah **hanya** implementasi `get_closed_history()` agar query SQLite langsung. `record_trade_open()`/`record_trade_close()`/`_load_history()`/`_save_history()` dibiarkan apa adanya (tidak dipakai kode produksi, tidak menghalangi siapa pun yang mau jurnal manual terpisah) — sesuai instruksi untuk tidak menulis mekanisme baru dan tidak menyentuh yang di luar scope.

**Keuntungan pendekatan ini:** nol perubahan di titik pemanggilan (`learning_engine.py`, `drawdown_protector.py`, `telegram_bot.py` tidak disentuh sama sekali) — hanya satu fungsi yang berubah implementasinya, tiga konsumen otomatis mendapat data live.

### 0.4 Scope sumber data: **`source='deterministic'` saja (default)**

Alasan: `get_signal_stats()` (fungsi statistik produksi yang sudah ada) sudah punya konvensi yang sama — default filternya `source='deterministic'`, mengecualikan `shadow_e3`, `llm`, dan `legacy`. Menyamakan konvensi ini penting supaya "belajar dari hasil sinyal" hanya belajar dari sinyal yang benar-benar dikirim ke user sebagai sinyal produksi resmi, bukan tercemar oleh:
- `shadow_e3` — riset terisolasi, secara desain tidak boleh memengaruhi apa pun di produksi (`signal_tracker.py:477-481`).
- `llm` — sinyal SPOT/advisory, belum ada satupun outcome closed saat ini (`STATUS_WINRATE_REPORT.md`: 8/8 masih OPEN).
- `legacy` — data pre-Fase 1, integritas belum terjamin sama seperti sinyal deterministic saat ini.

Diimplementasikan sebagai default argumen (`get_closed_history(source=None)` → default `"deterministic"`), bukan hardcode tanpa opsi, supaya tetap testable untuk skenario shadow (lihat `test_can_explicitly_query_shadow_e3`) tanpa menambah env var baru yang tidak diminta.

### 0.5 Ambang sampel minimum: **`LEARNING_MIN_SAMPLES` env, default 10**

Data produksi saat ini (dicek ulang saat audit ini, read-only, terhadap `data/aliza.db`):
```
coin  setup            side  source         status  rr    confidence  pnl_pct  signal_time
ARB   OVERSOLD BOUNCE  LONG  deterministic  LOSS    5.33  75.0        -1.7     2026-07-24T23:05:52
SUI   OVERSOLD BOUNCE  LONG  deterministic  OPEN    5.33  75.0        —        2026-07-24T23:40:49
```
Hanya **N=1 closed outcome** untuk `OVERSOLD BOUNCE`, dan itu pun sebuah LOSS (winrate mentah 0%). Guard lama di `confidence_adjuster.py` hanya mensyaratkan `total_trades >= 1` — kalau pendekatan (A) diterapkan **tanpa** menaikkan ambang ini, `adjust_confidence()` akan langsung menjatuhkan confidence -10 untuk setiap sinyal `OVERSOLD BOUNCE` berikutnya, murni berdasarkan satu kejadian rugi yang bisa jadi noise, bukan tren. Ini persis risiko yang diperingatkan di prompt.

Nilai default dipilih **10** (bukan formula statistik rumit) karena ini konsisten dengan level "belum cukup data" yang sudah dipakai `STATUS_WINRATE_REPORT.md` (menyebut ambang bermakna ~20-30, tapi 10 dipilih sebagai batas bawah yang tidak terlalu ketat mengingat volume sinyal `deterministic` yang masih rendah — bisa dinaikkan lewat env tanpa redeploy kode begitu volume data bertambah dan user ingin ambang lebih konservatif).

---

## Perubahan Kode

### `engine/learning/trade_history_tracker.py`
- `get_closed_history(source=None)` diubah total: tidak lagi membaca `data/trade_history.json`, melainkan query `signal_tracking` via `signal_tracker.DB_PATH` (referensi modul, bukan konstanta ter-cache — tetap mendukung isolasi test lewat `monkeypatch.setattr(signal_tracker, "DB_PATH", ...)`).
- Filter: `WHERE source = ? AND status IN ('WIN', 'LOSS')` (OPEN dan EXPIRED dikecualikan — bukan outcome trading).
- Urutan: `ORDER BY COALESCE(close_time, signal_time) ASC, id ASC` — kronologis, tie-break lewat `id` untuk baris yang closed di detik yang sama (presisi SQLite `datetime('now')`).
- `record_trade_open()`/`record_trade_close()`/`_load_history()`/`_save_history()`/`HISTORY_PATH` **tidak diubah** — tetap ada untuk siapa pun yang ingin jurnal manual terpisah, sesuai instruksi untuk tidak memperluas scope.

### `engine/learning/confidence_adjuster.py`
- Guard `stats.get("total_trades", 0) < 1` diubah menjadi `< _min_samples()`, dengan `_min_samples()` membaca env `LEARNING_MIN_SAMPLES` (default 10, fallback ke default kalau env tidak valid/≤0).
- **Aturan inti tidak diubah**: `winrate > 0.65 → +5`; `winrate < 0.40 → -10`; clamp 0–100 — persis sama seperti sebelumnya.

### `engine/portfolio/drawdown_protector.py`
- **Tidak diubah sama sekali.** Otomatis mendapat data live karena memanggil `get_closed_history()` yang implementasinya sudah berubah di titik lain. Ambang `LOSS_STREAK_THRESHOLD = 3` tetap seperti semula, dan cakupannya tetap hanya menggerbangi `/entry` (`portfolio_ai_engine.evaluate_trade()`) — **tidak** diperluas ke jalur broadcast sinyal otomatis, sesuai instruksi.

### `.env.example`
- Ditambah dokumentasi `LEARNING_MIN_SAMPLES` (opsional, commented-out, default 10 otomatis berlaku tanpa di-set). **`.env` produksi tidak disentuh.**

### `tests/test_learning_loop_live_data.py` (baru)
16 test baru, dirinci di bagian Hasil Test.

Ringkasan diff:
```
 .env.example                             |  6 ++++
 engine/learning/confidence_adjuster.py   | 18 +++++++++-
 engine/learning/trade_history_tracker.py | 56 +++++++++++++++++++++++++++++---
 3 files changed, 74 insertions(+), 6 deletions(-)
 tests/test_learning_loop_live_data.py    | (baru, 16 test)
```

---

## Hasil Test

### Test baru (`tests/test_learning_loop_live_data.py`) — 16/16 PASSED

```
tests/test_learning_loop_live_data.py::TestGetClosedHistoryLiveData::test_reads_from_signal_tracking_not_json_seed PASSED
tests/test_learning_loop_live_data.py::TestGetClosedHistoryLiveData::test_excludes_shadow_e3_by_default PASSED
tests/test_learning_loop_live_data.py::TestGetClosedHistoryLiveData::test_can_explicitly_query_shadow_e3 PASSED
tests/test_learning_loop_live_data.py::TestGetClosedHistoryLiveData::test_excludes_open_signals PASSED
tests/test_learning_loop_live_data.py::TestGetClosedHistoryLiveData::test_chronological_order_oldest_first PASSED
tests/test_learning_loop_live_data.py::TestConfidenceAdjusterMinSamples::test_below_default_threshold_no_adjustment PASSED
tests/test_learning_loop_live_data.py::TestConfidenceAdjusterMinSamples::test_at_default_threshold_applies_high_winrate_bonus PASSED
tests/test_learning_loop_live_data.py::TestConfidenceAdjusterMinSamples::test_at_default_threshold_applies_low_winrate_penalty PASSED
tests/test_learning_loop_live_data.py::TestConfidenceAdjusterMinSamples::test_env_override_lowers_threshold PASSED
tests/test_learning_loop_live_data.py::TestConfidenceAdjusterMinSamples::test_env_override_raises_threshold PASSED
tests/test_learning_loop_live_data.py::TestDrawdownProtectorLiveTrigger::test_three_consecutive_live_losses_blocks_trading PASSED
tests/test_learning_loop_live_data.py::TestDrawdownProtectorLiveTrigger::test_win_breaks_streak_allows_trading PASSED
tests/test_learning_loop_live_data.py::TestDrawdownProtectorLiveTrigger::test_two_losses_does_not_block PASSED
tests/test_learning_loop_live_data.py::TestDrawdownProtectorLiveTrigger::test_no_closed_trades_allows_trading PASSED
tests/test_learning_loop_live_data.py::TestLearningEngineIntegration::test_get_strategy_stats_reflects_live_outcomes PASSED
tests/test_learning_loop_live_data.py::TestLearningEngineIntegration::test_confidence_adjuster_end_to_end_with_live_data PASSED

16 passed in 0.45s
```

Mencakup keempat item wajib dari prompt: (1) data live vs seed beku, (2) guard sampel minimum di kedua sisi ambang + override env, (3) exclude/include `shadow_e3` eksplisit, (4) `drawdown_protector` benar-benar terpicu oleh 3 LOSS live berturut-turut (dan tidak terpicu oleh 2 LOSS atau LOSS-LOSS-WIN).

### Regresi — full suite

```
venv/bin/python -m pytest -q
234 passed, 3 warnings, 74 subtests passed in 28.63s
```

Tidak ada test yang gagal atau berubah perilaku di luar scope. (Tidak ada test existing yang menyentuh `engine/learning/*` sebelum perubahan ini — dikonfirmasi lewat `grep -rln "trade_history_tracker\|learning_engine\|confidence_adjuster\|drawdown_protector" tests/` sebelum implementasi, hasil kosong — sehingga tidak ada risiko breaking existing coverage untuk modul-modul ini.)

---

## Contoh Konkret Before/After

Dijalankan read-only terhadap `data/aliza.db` produksi (bukan DB test) untuk mengilustrasikan efek nyata perubahan ini pada state produksi saat ini:

**State produksi `signal_tracking` (source='deterministic') per 25 Juli 2026:**
```
coin  setup            side  status  rr    confidence  pnl_pct  signal_time
ARB   OVERSOLD BOUNCE  LONG  LOSS    5.33  75.0        -1.7     2026-07-24T23:05:52+07:00
SUI   OVERSOLD BOUNCE  LONG  OPEN    5.33  75.0        —        2026-07-24T23:40:49+07:00
```

**SEBELUM perubahan ini (kode di `main`):**
`get_strategy_stats()` membaca `data/trade_history.json` (beku sejak Maret 2025): `{"PULLBACK LONG": {"winrate": 0.5, "avg_rr": 1.25, "total_trades": 2}}`. Untuk sinyal live `OVERSOLD BOUNCE` (setup yang sekarang benar-benar dipakai produksi), `strategy_stats.get("OVERSOLD BOUNCE")` → `None` (tidak ada di seed) → guard `not stats` di `confidence_adjuster.py` langsung mengembalikan confidence dasar tanpa perubahan. **Hasil: sinyal ARB/SUI di atas sama sekali tidak pernah "dilihat" oleh learning loop — bukan cuma tidak nge-tune, tapi benar-benar tidak terbaca.**

**SESUDAH perubahan ini (branch ini), dijalankan langsung terhadap `data/aliza.db` produksi:**
```python
>>> from engine.learning import learning_engine, confidence_adjuster, trade_history_tracker
>>> trade_history_tracker.get_closed_history()
[{'coin': 'ARB', 'setup': 'OVERSOLD BOUNCE', 'side': 'LONG', 'result': 'LOSS',
  'rr': 5.33, 'confidence': 75.0, 'timestamp': '2026-07-25T07:41:04.669114+07:00'}]

>>> learning_engine.get_strategy_stats()
{'OVERSOLD BOUNCE': {'winrate': 0.0, 'avg_rr': 5.33, 'total_trades': 1}}

>>> confidence_adjuster.adjust_confidence('OVERSOLD BOUNCE', 65, learning_engine.get_strategy_stats())
65   # unchanged — N=1 < LEARNING_MIN_SAMPLES(10), penyesuaian ditahan
```
Learning loop **sekarang benar-benar membaca** outcome ARB (LOSS) — beda signifikan dari sebelumnya yang bahkan tidak melihatnya. Tapi confidence tetap 65 (tidak berubah) karena `LEARNING_MIN_SAMPLES=10` menahan penyesuaian sampai ada cukup data — **inilah tepatnya perilaku yang diminta**: terhubung ke live data, tapi tidak "over-react" ke satu titik data.

**Ilustrasi kontras — risiko kalau guard sampel TIDAK dinaikkan:** dengan guard lama (`total_trades < 1`), pemanggilan yang sama akan lolos guard (N=1 ≥ 1) dan langsung menjatuhkan confidence karena `winrate 0.0 < 0.40` → `65 - 10 = 55`, murni dari satu LOSS. Ini contoh nyata mengapa Langkah 0.5 (menaikkan ambang) bukan opsional, melainkan prasyarat aman untuk Langkah 0.3 (sambung ke data live).

**Ilustrasi ketika data sudah cukup** (dari `tests/test_learning_loop_live_data.py::test_confidence_adjuster_end_to_end_with_live_data`, memakai DB test terisolasi): 10 outcome live untuk `PULLBACK LONG` (7 WIN, 3 LOSS → winrate 70%) menghasilkan `adjust_confidence("PULLBACK LONG", 50, stats) == 55` — bonus +5 diterapkan dengan benar begitu ambang sampel terpenuhi.

---

## Yang SENGAJA TIDAK Dikerjakan (sesuai instruksi)

- Logika inti `adjust_confidence()` (aturan winrate>0.65→+5, winrate<0.40→-10) dan `check_drawdown()` (ambang loss-streak 3) **tidak diubah** — hanya sumber datanya yang disambungkan ke live.
- `drawdown_protector` **tidak diperluas** ke jalur broadcast sinyal otomatis (`_dispatch_and_record_deterministic_signal`/`signal_check_job`) — tetap hanya menggerbangi perintah manual `/entry`, persis seperti sebelumnya. Ini item terpisah yang belum diputuskan user.
- `.env` produksi **tidak disentuh** — `LEARNING_MIN_SAMPLES` hanya didokumentasikan di `.env.example` sebagai opsional, default 10 berlaku otomatis tanpa perlu di-set apa pun di server.
- Tidak ada perubahan pada `data/trade_history.json` itu sendiri, tidak ada migrasi/penghapusan file — dibiarkan sebagai peninggalan tak terpakai, konsisten dengan instruksi untuk tidak menulis mekanisme baru dari nol maupun membongkar hal yang di luar scope.
- Tidak ada commit yang dibuat oleh sesi ini — perubahan berada di working tree branch `feat/learning-loop-live-data`, menunggu review/commit oleh user.

---

## Catatan Operasional untuk User

- Setelah merge & deploy, `confidence_adjuster` dan `drawdown_protector` akan **otomatis aktif** memakai data live tanpa perlu ubah `.env` — perilakunya tidak berubah sampai suatu setup mengumpulkan ≥10 outcome closed (`WIN`/`LOSS`) dari sinyal `deterministic`.
- Berdasarkan volume sinyal saat ini (N=1 untuk `OVERSOLD BOUNCE`, N=0 untuk setup lain), butuh waktu sebelum ambang 10 tercapai untuk setup manapun — ini alasan defaultnya dipilih tidak terlalu tinggi.
- `drawdown_protector` akan mulai benar-benar bisa memblokir `/entry` begitu ada 3 LOSS live berturut-turut untuk `source='deterministic'` — sebelumnya (dengan data beku) ini **tidak pernah mungkin terjadi** apa pun kondisi live-nya.
