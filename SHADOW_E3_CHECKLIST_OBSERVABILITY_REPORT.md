# Laporan — Update Checklist Promosi + Observability Per-Alasan-Gagal shadow_e3

**Tanggal:** 27 Agustus 2026
**Branch:** `shadow-e3/evaluation-and-observability` (dibuat dari `main` terkini, **menunggu review manual** — tidak di-merge/push, sesuai pola gap-gap sebelumnya di repo ini)
**Konteks:** Tindak lanjut dari `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md`, yang menyimpulkan `shadow_e3` stagnan `candidates=0` selama 9 hari karena **limitasi desain** (filter regime pasar), bukan bug. User memutuskan dua tindak lanjut: (A) ganti kriteria evaluasi promosi dari tanggal kalender ke jumlah outcome, (B) tambah observability per-alasan-gagal di kode shadow_e3.

---

## Bagian A — `SHADOW_PROMOTION_CHECKLIST_REPORT.md`

### A.1 Kriteria evaluasi: dari tanggal kalender ke jumlah outcome

**Sebelum** (satu-satunya rujukan tanggal keras yang tersisa di file ini, pada bagian "Rekomendasi Sebelum Merge" #3):
```
3. Command ini akan sering melaporkan "BELUM MEMENUHI" untuk beberapa minggu ke depan (sesuai perkiraan `FASE4_REPORT.md`: observasi ≥6 minggu berakhir sekitar 1 September 2026) — ini perilaku yang diharapkan, bukan bug.
```

**Sesudah:**
```
3. Command ini akan sering melaporkan "BELUM MEMENUHI" untuk jangka waktu yang tidak pasti — **bukan lagi dibatasi target tanggal 1 September 2026** (estimasi awal dari `FASE4_REPORT.md`, kini digantikan kebijakan berbasis outcome; lihat "Update Kebijakan (27 Agustus 2026)" di atas). Jumlah outcome closed shadow_e3 berhenti bertambah sama sekali selama regime pasar `TREND` berlangsung (lihat "Limitasi Desain" di atas dan `SHADOW_E3_STAGNATION_REPORT.md`) — ini perilaku yang diharapkan, bukan bug.
```

Ditambahkan juga section baru **"Update Kebijakan (27 Agustus 2026)"** (disisipkan setelah metadata header, sebelum "Langkah 0"), isi lengkap:

> **Perubahan:** Kriteria "kapan boleh mengevaluasi promosi shadow_e3 → produksi" diubah dari **tanggal kalender tetap** (sebelumnya diperkirakan sekitar **1 September 2026**, mengikuti estimasi "≥6 minggu sejak aktivasi" di `FASE4_REPORT.md`) menjadi **murni jumlah outcome closed (≥60 outcome)**, **tanpa batas tanggal keras**.
>
> **Alasan:** `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md` membuktikan bahwa shadow_e3 hanya menghasilkan kandidat saat `market_regime` global (dihitung dari BTC saja) berstatus `RANGE` atau `DOWNTREND`... Regime `TREND` bisa bertahan berminggu-minggu tanpa kepastian durasi... menyebabkan `shadow_e3 candidates=0` selama 9+ hari/11.340 siklus berturut-turut, murni karena mekanisme desain — bukan bug... menjadwalkan evaluasi pada tanggal kalender tetap (1 September 2026) berisiko memaksa keputusan promosi/tidak-promosi dengan sampel yang masih jauh dari ambang statistik (≥60 outcome) semata-mata karena kondisi pasar sedang tidak kooperatif dengan strategi ini.
>
> **Kebijakan baru:** Evaluasi promosi shadow_e3 dilakukan setelah `signal_tracking` mencatat **≥60 outcome closed dengan `source='shadow_e3'`**, kapan pun itu tercapai — tidak ada lagi target tanggal tetap. Command `/shadow_promotion_check` (`engine/shadow/promotion_criteria.py`, **tidak diubah** oleh kebijakan ini) tetap bisa dijalankan kapan saja sebagai pantauan progres read-only... Kriteria numerik lain — expectancy >+0,3%/trade, profit factor >1,2, batas bawah bootstrap CI95 >−0,1%, tidak ada satu coin mendominasi >50% kontribusi profit — **tetap seperti sebelumnya**; hanya mekanisme "kapan boleh/harus dievaluasi" yang berubah, dari tanggal ke jumlah outcome.

**Kriteria numerik dipertahankan tanpa perubahan** (dikonfirmasi dari isi asli file, section "Item Implementasi"/"2-3. Modul kalkulasi"): expectancy >+0,3%/trade, profit factor >1,2, batas bawah bootstrap CI95 >−0,1%, tidak ada coin >50% kontribusi profit, dan kriteria observasi kode (`≥60 closed ATAU ≥6 minggu`, dihitung di `engine/shadow/promotion_criteria.py` — **modul kode ini tidak disentuh sama sekali**, hanya narasi kebijakan di dokumen checklist yang diperbarui).

### A.2 Section baru "Limitasi Desain shadow_e3 — Hanya Aktif Saat Regime RANGE/DOWNTREND"

Ditambahkan tepat setelah section "Update Kebijakan" di atas, mengutip kode aktual dari dua file (dibaca langsung, bukan dikarang):

`engine/strategy/strategy_regime_map.py` (dikutip utuh, 25 baris):
```python
STRATEGY_MAP = {
    "TREND": [
        "PULLBACK LONG",
        "PULLBACK SHORT",
        "MOMENTUM LONG",
        "MOMENTUM SHORT",
        "BREAKOUT LONG",
    ],
    "RANGE": [
        "OVERSOLD BOUNCE",
        "OVERBOUGHT REJECTION",
    ],
    "DOWNTREND": [
        "PULLBACK SHORT",
        "OVERBOUGHT REJECTION",
    ],
    "VOLATILE": [],
}
```

`engine/intelligence/market_regime_detector.py` (kutipan logika inti, baris 50-62):
```python
if trend == "BULLISH" and rsi > 60:
    return {"market_regime": "TREND"}
if trend == "SIDEWAYS" and 40 <= rsi <= 60:
    return {"market_regime": "RANGE"}
if trend == "BEARISH" and rsi < 40:
    return {"market_regime": "DOWNTREND"}

# Fallback by trend
if trend == "BULLISH":
    return {"market_regime": "TREND"}
if trend == "BEARISH":
    return {"market_regime": "DOWNTREND"}
return {"market_regime": "RANGE"}
```

Diikuti penjelasan implikasi: `OVERSOLD BOUNCE`/`OVERBOUGHT REJECTION` — satu-satunya dua setup yang pernah tercatat dari shadow_e3 — hanya diizinkan saat regime `RANGE`/`DOWNTREND`; karena regime dihitung market-wide dari BTC saja, selama BTC `trend=BULLISH`, seluruh 21 coin watchlist diblokir sekaligus, berapa pun lama itu berlangsung — **ini bukan indikasi kegagalan sistem**. Ditutup dengan referensi silang eksplisit ke `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md` sebagai bukti pendukung penuh.

### A.3 CHANGELOG.md

Entri baru ditambahkan di section `### 2026-08-27` (paling atas, sebelum entri `0370c42` yang sudah ada), mereferensikan branch `shadow-e3/evaluation-and-observability` (belum merge, sesuai konvensi repo untuk perubahan yang menunggu review) dan kedua dokumen laporan terkait.

---

## Bagian B — Observability per-alasan-gagal di `engine/shadow/e3_shadow.py`

### B.1 Semua titik early-return yang teridentifikasi (dibaca line-by-line dari kode aktual)

| # | Lokasi (baris asli sebelum edit) | Kondisi persis di kode | Counter reason |
|---|---|---|---|
| 1 | baris 97 | `not isinstance(market_data, dict) or len(rows or []) < 15` | `insufficient_rows` |
| 2 | baris 101 | `atr is None or float(atr) <= 0` | `atr_invalid` |
| 3 | baris 105-109 | `TradingBrain().analyze(data)` dibungkus `try/except Exception` | `trading_brain_exception` |
| 4 | baris 110 | `not signal or signal.get("setup") in (None, "NO SETUP")` | `no_setup` |
| 5 | baris 115 | `side not in {"LONG","SHORT"} or entry <= 0` **(gerbang ini TIDAK disebutkan eksplisit di daftar dugaan awal — ditemukan saat membaca ulang kode, ditambahkan)** | `invalid_side_entry` |
| 6 | baris 117-120 | Filter jarak-ke-support, khusus `setup == "OVERSOLD BOUNCE"`: `support is None or entry > float(support) * 1.01` | `support_filter_reject` |
| 7 | baris 121-133 (lolos semua gerbang) | Kandidat berhasil dibangun | `success` |

Ketujuh reason ini **saling eksklusif dan lengkap** — tepat satu di antaranya terjadi untuk setiap pemanggilan `build_shadow_signal()`, sehingga `sum(counters.values())` selalu sama dengan jumlah pemanggilan (jumlah coin diproses di siklus itu). Ini diverifikasi dengan `assert` di `collect_shadow_signals()` (lihat B.2) dan oleh test `test_collect_shadow_signals_breakdown_sums_to_total_processed`.

### B.2 Ringkasan perubahan kode

- Tambah `from collections import Counter`.
- `build_shadow_signal()`: tambah parameter opsional `counters: Counter[str] | None = None` (default `None`, **backward-compatible** — semua caller lama, termasuk `tests/test_fase4.py::test_shadow_levels_one_and_three_atr` yang memanggilnya positional tanpa `counters`, tetap berjalan identik). Helper lokal `_stop(reason)` menambah `counters[reason] += 1` hanya jika `counters is not None`, dipanggil tepat sebelum setiap `return None` dan sebelum `return signal` sukses. **Tidak ada kondisi `if`/logika keputusan yang diubah** — hanya baris `_stop(...)` disisipkan sebelum setiap `return` yang sudah ada.
- `collect_shadow_signals()`: buat `counters: Counter[str] = Counter()` **lokal** di awal fungsi (otomatis reset setiap panggilan/siklus, tidak ada state global/persisten), hitung `total_processed` (jumlah coin di `snapshot["data"]`), teruskan `counters=counters` ke tiap panggilan `build_shadow_signal()`. Setelah loop: `assert sum(counters.values()) == total_processed` (menjamin breakdown selalu lengkap), lalu log baris breakdown baru. `len(rows_by_coin)` (nilai `candidates=%d`) **tidak diubah sama sekali** — komputasinya identik dengan sebelum perubahan.

Diff lengkap: lihat `git diff main -- engine/shadow/e3_shadow.py` di branch ini (+57/-5 baris, semuanya penambahan `_stop(...)`, parameter, dan blok logging — nihil perubahan pada kondisi `if` yang sudah ada).

Potongan kunci (log line baru, dari `collect_shadow_signals`):
```python
logger.info(
    "shadow_e3 candidates=%d (success=%d, no_setup=%d, atr_invalid=%d, "
    "insufficient_rows=%d, invalid_side_entry=%d, support_filter_reject=%d, "
    "trading_brain_exception=%d)",
    len(rows_by_coin),
    counters.get("success", 0),
    counters.get("no_setup", 0),
    counters.get("atr_invalid", 0),
    counters.get("insufficient_rows", 0),
    counters.get("invalid_side_entry", 0),
    counters.get("support_filter_reject", 0),
    counters.get("trading_brain_exception", 0),
)
```

### B.3 Batasan yang dijaga (dikonfirmasi)

- **Tidak ada field DB baru**: tidak ada perubahan skema `signal_tracking` atau tabel lain — `grep -n "ALTER TABLE\|CREATE TABLE"` terhadap diff kosong.
- **Tidak ada env var baru**: `grep -n "os.getenv\|os.environ"` di diff kosong — counter murni in-memory, tidak dikontrol flag apa pun.
- **Tidak persisten**: `counters` adalah variabel lokal fungsi, tidak disimpan ke file/DB/cache modul.
- **`candidates=%d` dan `recorded=%d` byte-identik**: `candidates=%d` = `len(rows_by_coin)`, komputasi tidak berubah. `recorded=%d` ada di `interfaces/telegram_bot.py` (tidak disentuh sama sekali oleh perubahan ini).
- **Tidak ada file lain yang disentuh** di luar scope: dikonfirmasi lewat `git diff --stat main` (lihat bagian Verifikasi di bawah) — `engine/strategy/`, `engine/intelligence/`, dan modul trading/sinyal lain nihil perubahan.

---

## Hasil Test

### Test baru (`tests/test_shadow_e3_observability.py`) — 15/15 PASSED

```
test_insufficient_rows_market_data_not_dict PASSED
test_insufficient_rows_too_few_rows PASSED
test_atr_invalid_zero_true_range PASSED
test_trading_brain_exception PASSED
test_no_setup_none_signal PASSED
test_no_setup_explicit_no_setup_string PASSED
test_invalid_side_entry_bad_side PASSED
test_invalid_side_entry_nonpositive_entry PASSED
test_support_filter_reject_too_far PASSED
test_support_filter_reject_missing_support PASSED
test_success_candidate_produced_and_shape_unchanged PASSED
test_build_shadow_signal_without_counters_kwarg_unchanged PASSED
test_collect_shadow_signals_breakdown_sums_to_total_processed PASSED
test_collect_shadow_signals_counters_reset_every_cycle PASSED
test_collect_shadow_signals_empty_snapshot_no_assertion_error PASSED

15 passed in 0.15s
```

Cakupan: satu test per gerbang gagal (baris B.1 #1-6, termasuk dua varian untuk gerbang #1 dan #6), satu test regresi sukses yang membandingkan hasil persis dengan `tests/test_fase4.py::test_shadow_levels_one_and_three_atr` (SL=99.0, TP1=103.0, `source="shadow_e3"`, dll — tidak berubah), satu test memastikan pemanggilan tanpa `counters` (semua caller lama) tidak berubah perilakunya, dan tiga test end-to-end `collect_shadow_signals()` (breakdown menjumlah benar terhadap 8 coin sekaligus mencakup semua gerbang, counter reset per siklus/tidak bocor antar panggilan, dan snapshot kosong tidak memicu `AssertionError`).

### Regresi — full test suite

```
venv/bin/python -m pytest -q
342 passed, 3 warnings, 74 subtests passed in ~34s
```

Baseline sebelumnya (sebelum perubahan ini): 327 passed, 74 subtests. Selisih **+15** persis sama dengan jumlah test baru — **0 test lama yang gagal/berubah perilaku**, 74 subtests tetap identik.

Test `tests/test_fase4.py` (baseline shadow_e3, tidak diubah) dijalankan ulang terpisah untuk konfirmasi tambahan: **6/6 PASSED**, tidak terpengaruh oleh penambahan parameter `counters`.

---

## Simulasi Manual (read-only, dihapus setelah selesai)

Script sementara ditulis di scratchpad `/tmp` (di luar `/opt/aliza-ai`), **dihapus setelah dijalankan**, tidak ada file yang ditinggalkan, tidak ada panggilan API eksternal baru, tidak ada service yang disentuh. Skrip memakai data 4h historis **nyata yang sudah ada di repo** (`backtest/data/{BTC,ETH,ARB,ADA,BNB,SOL}USDT_4h.csv`, 100 candle terakhir tiap coin) — di-monkeypatch menggantikan `_closed_4h_klines()` (bukan panggilan Binance baru), lalu membangun `market_data` sederhana (RSI riil dari `calculate_rsi()`, trend dari perbandingan harga 20 candle, support/resistance dari min/max 20 candle terakhir) untuk 6 coin real + 2 coin sintetis (`THINCOIN` dengan <15 rows, `BADTYPECOIN` dengan `market_data` bukan dict) untuk memastikan gerbang `insufficient_rows` juga teruji dalam simulasi ini.

**Output aktual:**
```
shadow_e3 candidates=0 (success=0, no_setup=6, atr_invalid=0, insufficient_rows=2, invalid_side_entry=0, support_filter_reject=0, trading_brain_exception=0)

Total coins processed this cycle: 8
Coins: ['BTC', 'ETH', 'ARB', 'ADA', 'BNB', 'SOL', 'THINCOIN', 'BADTYPECOIN']
len(result) [candidates list actually returned] = 0
```

**Verifikasi penjumlahan:** `success(0) + no_setup(6) + atr_invalid(0) + insufficient_rows(2) + invalid_side_entry(0) + support_filter_reject(0) + trading_brain_exception(0) = 8 = total coin diproses` — cocok persis, tanpa `AssertionError` (assert breakdown di kode lolos). `candidates=0` = `len(result)=0` — konsisten. Kelima real-market coin (BTC/ETH/ADA/BNB/SOL) jatuh ke `no_setup` (TradingBrain mengembalikan `NO SETUP`, termasuk satu kasus ARB "Trade rejected: risk too high" yang tetap disederhanakan jadi setup kosong oleh `TradingBrain`, sehingga tetap terhitung `no_setup`, bukan gerbang lain — sesuai definisi gerbang #4). Kedua coin sintetis jatuh ke `insufficient_rows` sesuai desain skenario.

Skenario `success` (kandidat lolos semua gerbang) diverifikasi lewat unit test `test_success_candidate_produced_and_shape_unchanged` dan `test_collect_shadow_signals_breakdown_sums_to_total_processed` di atas (data pasar riil untuk semua 21 coin watchlist sedang tidak menghasilkan setup apa pun karena regime `TREND` sesuai `SHADOW_E3_STAGNATION_REPORT.md`, sehingga simulasi terhadap kondisi live saat ini secara alami tidak menghasilkan kandidat — konsisten dengan temuan investigasi sebelumnya, bukan kegagalan simulasi).

---

## Verifikasi Scope — `git diff --stat main`

```
 CHANGELOG.md                         |  1 +
 SHADOW_PROMOTION_CHECKLIST_REPORT.md | 61 +++++++++++++++++++++++++++++++++++-
 engine/shadow/e3_shadow.py           | 57 ++++++++++++++++++++++++++++++---
 3 files changed, 114 insertions(+), 5 deletions(-)
```

(File baru `tests/test_shadow_e3_observability.py` dan laporan ini sendiri tidak muncul di `git diff --stat` karena keduanya untracked sampai di-`git add`/commit — keduanya ditambahkan di commit yang sama dengan perubahan di atas.) `git status --porcelain` sebelum commit mengonfirmasi **hanya** 3 file termodifikasi + 2 file baru yang relevan tersentuh (di luar `MERGE_PUSH_BERES_MESSAGEFIX_REPORT.md` dan folder `AlizaAI-Crypto/01-hasil-audit-codex/`, keduanya untracked dari sesi lain, **tidak disentuh** proses ini). Tidak ada perubahan di `engine/strategy/`, `engine/intelligence/`, atau modul trading/sinyal lain.

---

## Yang TIDAK dilakukan (sesuai batasan)

- Tidak mengubah logika keputusan candidate generation shadow_e3 — hanya `_stop(reason)` disisipkan sebelum `return` yang sudah ada, nihil kondisi `if` yang diubah.
- Tidak mengubah kriteria numerik promosi yang sudah ada (expectancy, PF, CI bootstrap, dominasi coin, ambang observasi `≥60`/`≥6 minggu` di kode `promotion_criteria.py`) — hanya narasi kebijakan "kapan boleh dievaluasi" di dokumen yang diperbarui.
- Tidak menambah field DB baru, tidak menambah env var baru.
- Tidak restart service apa pun, tidak memanggil API eksternal baru (simulasi memakai data CSV yang sudah ada di repo).
- Tidak push/merge branch — menunggu review manual.
- Script investigasi sementara dihapus dari `/tmp`, tidak ada yang ditinggalkan di `/opt/aliza-ai`.
