# Laporan — Checklist Promosi Shadow→Produksi

**Tanggal:** 25 Juli 2026
**Branch:** `feat/shadow-promotion-checklist` (dibuat dari `main` terkini)
**Status:** **BELUM di-merge/deploy** — implementasi + test saja, menunggu review sebelum merge.

Konteks: `FASE4_REPORT.md` mendefinisikan kriteria promosi shadow_e3 → produksi (expectancy >+0,3%/trade, PF >1,2, batas bawah bootstrap CI >−0,1%, tidak ada coin >50% kontribusi profit, ≥60 outcome closed ATAU ≥6 minggu observasi). Audit sebelumnya menemukan kriteria ini hanya didokumentasikan, tidak ada kode yang mengevaluasinya. Gap ini menambahkan command Telegram read-only yang menghitung status kriteria ini dari data live — **bukan auto-promote**, keputusan tetap manual.

**Catatan konteks percabangan:** dua gap sebelumnya (`feat/drawdown-gate-broadcast`, `feat/weekly-winrate-summary`) masih menunggu review, belum di-merge. Karena prompt ini meminta branch baru "dari `main` terkini", perubahan yang belum di-commit di kedua branch tersebut sudah di-*stash* sebelumnya (lihat `stash@{0}` dan `stash@{1}`, keduanya masih aman tersimpan) sebelum membuat branch bersih untuk gap ini.

---

## Langkah 0 — Diagnosis & Keputusan

### 0.1 Metodologi bootstrap CI — pendekatan yang dipilih & keterbatasannya

`backtest/robustness.py::_bootstrap()` ([backtest/robustness.py:56-73](backtest/robustness.py#L56-L73)) melakukan **percentile bootstrap**: resample `pnl_pct` dengan penggantian sebanyak N (ukuran sampel asli) untuk setiap iterasi, hitung rata-rata tiap resample, ulangi 10.000 kali, lalu ambil persentil ke-2,5 dan ke-97,5 dari distribusi rata-rata tersebut sebagai CI 95%. Ini murni matematika statistik generik atas daftar `pnl_pct` — **tidak spesifik untuk konteks backtest** (tidak butuh data historis ratusan hari, tidak butuh simulator) — sehingga bisa dipakai ulang persis untuk data live tanpa modifikasi formula.

**Keterbatasan yang didokumentasikan secara eksplisit (bukan diabaikan):**
- Bootstrap pada N sangat kecil (mis. N=1) menghasilkan CI berlebar-nol/degenerate (bootstrap dari satu nilai yang sama berulang-ulang selalu menghasilkan rata-rata = nilai itu sendiri) — ini BUKAN presisi tinggi, melainkan tidak informatif sama sekali. Karena itu ditambahkan **ambang minimum N sebelum bootstrap dihitung** (`BOOTSTRAP_MIN_N = 10`), di bawah itu hasil dilaporkan eksplisit "belum bisa dihitung", bukan angka CI yang menyesatkan. Nilai 10 dipilih **konsisten dengan `LEARNING_MIN_SAMPLES`** (default di `engine/learning/confidence_adjuster.py`, dipakai ulang lagi di Gap 2 `weekly_winrate_summary`) — bukan angka baru yang tidak berhubungan, supaya seluruh sistem punya satu definisi "cukup data secara statistik" yang konsisten.
- **Tidak diimpor langsung dari `backtest/robustness.py`** — direplikasi sebagai fungsi lokal di `engine/shadow/promotion_criteria.py` dengan formula & konvensi seed yang identis (10.000 iterasi, seed `20260721`). Alasan: `backtest/` adalah paket tooling offline yang secara eksplisit ditandai **"JANGAN SENTUH"** di `REPO_CLEANUP_REPORT.md`, dan modulnya (`data_loader.py`, `simulator.py`) menarik dependency jauh lebih berat (fetch data Binance, simulasi event-driven) yang tidak relevan/tidak aman diimpor ke proses runtime produksi (`interfaces/telegram_bot.py`). Duplikasi logika sekecil ini (± 10 baris) jauh lebih aman daripada menyambungkan runtime produksi ke paket backtest.

### 0.2 Definisi "kontribusi profit per coin" — didefinisikan baru, didokumentasikan

Dicari definisi persis yang dipakai backtest:
```
grep -rn "coin_profit_share" backtest/*.py
→ backtest/run_experiments.py:94: "coin_profit_share_lt": 0.50   (HANYA label ambang di dict `criteria`, ditulis ke manifest.json untuk review manusia — TIDAK ADA fungsi yang menghitungnya di mana pun)
```
**Tidak ada rumus resmi yang bisa dipakai ulang** — istilah ini hanya muncul sebagai label ambang yang tidak pernah diimplementasikan. Sebagai gantinya, `ROBUSTNESS_RESULTS.md` menangani kekhawatiran yang sama secara kualitatif lewat analisis **"Exclude-WLD"** (jalankan ulang backtest tanpa WLD, lihat apakah hasil tetap positif) — pendekatan leave-one-out, bukan formula persentase.

Untuk kebutuhan live (harus bisa dihitung instan dari data yang ada, bukan re-run simulasi), didefinisikan:
```
profit_share(coin) = Σ(pnl_pct positif milik coin itu) / Σ(seluruh pnl_pct positif semua coin)
```
— proporsi kontribusi coin tersebut terhadap **total PnL positif** (bukan total PnL bersih, supaya loss dari coin lain tidak "menutupi" konsentrasi laba). Ini secara konsep sejalan dengan pertanyaan yang sama seperti Exclude-WLD (apakah satu coin mendominasi sisi untung), hanya diformulasikan sebagai rasio langsung, bukan re-run leave-one-out. Kalau tidak ada trade profit sama sekali, dilaporkan sebagai kasus khusus ("belum ada trade profit untuk dihitung") — lihat catatan edge-case di bagian Hasil Test.

### 0.3 Awal jendela observasi — `MIN(signal_time)`, bukan tanggal deploy kode

```python
def _first_signal_time(source):
    ...
    row = conn.execute("SELECT MIN(signal_time) FROM signal_tracking WHERE source = ?", (source,)).fetchone()
```
Dipakai `MIN(signal_time) WHERE source='shadow_e3'` — **bukan** tanggal commit `fe7c18e1` (fitur di-merge ke kode). Alasan eksplisit sesuai prompt: `SHADOW_SIGNAL_SPAM_REPORT.md` mendokumentasikan bahwa 21–23 Juli kode sudah ada tapi nol kandidat sinyal shadow tercatat — observasi yang bermakna baru mulai saat ada sinyal sungguhan pertama (24 Juli 2026, dikonfirmasi lewat jalankan command terhadap data produksi di bagian akhir laporan ini), bukan sejak baris kode ter-deploy.

---

## Item Implementasi

### 1. Command baru — `/shadow_promotion_check`, terpisah dari `/shadow_stats`

**Keputusan (item 4 di prompt):** command **baru dan terpisah**, bukan perluasan `/shadow_stats`. Alasan:
- `/shadow_stats` adalah command ringan untuk sekali lihat cepat (N/WR/expectancy/per-setup); menambahkan 5 kriteria PASS/FAIL plus komputasi bootstrap (10.000 iterasi) akan membuatnya lebih lambat dan lebih ramai untuk tujuan aslinya yang sederhana.
- Secara semantik berbeda: `/shadow_stats` = "apa yang terjadi", `/shadow_promotion_check` = "apakah sudah siap dipertimbangkan untuk promosi" — audiens/mental model berbeda (lihat cepat vs tinjauan keputusan formal).
- Konsisten dengan pola codebase yang sudah memisahkan `/signal_stats` dari `/shadow_stats` untuk alasan serupa.

Otorisasi memakai pola `_authorized_chat(update)` yang sama persis seperti `/entry` ([interfaces/telegram_bot.py:1245-1247](interfaces/telegram_bot.py#L1245-L1247)):
```python
if not _authorized_chat(update):
    await msg.reply_text("⛔ Unauthorized.")
    return
```

### 2-3. Modul kalkulasi — `engine/shadow/promotion_criteria.py` (baru)

Fungsi murni, tidak bergantung Telegram, mudah diuji:
- `evaluate_promotion_criteria(source="shadow_e3")` — baca `signal_tracking` (read-only, `SELECT` saja), hitung kelima kriteria, return dict terstruktur dengan `value`/`threshold`/`passed` per kriteria + `all_passed`.
- `format_promotion_check_message(result)` — render teks Telegram, ✅/❌ per baris + angka asli, kesimpulan "MEMENUHI SEMUA KRITERIA" hanya kalau seluruh `passed=True`, kalau tidak "BELUM MEMENUHI — kriteria yang belum: [daftar]".
- `_profit_factor()` **sengaja tidak memakai** `engine.analytics.performance_analyzer.analyze_performance()` yang sudah ada — fungsi itu menghitung profit factor dari field `rr` (rasio risk/reward **rencana** saat sinyal dibuat), bukan dari `pnl_pct` **realisasi**. Untuk keputusan promosi yang harus berbasis hasil nyata (persis metodologi `backtest/metrics.py::aggregate_metrics()` yang dipakai `ROBUSTNESS_RESULTS.md`: `gross_win/gross_loss` dari `pnl_pct`), memakai basis `rr` rencana akan salah kaprah. Ini murni pilihan rumus di modul baru — **tidak mengubah** `performance_analyzer.py` itu sendiri.

### 4. Tidak ada auto-promote — dikonfirmasi

Modul ini **hanya membaca** `signal_tracking` lewat `sqlite3.connect(signal_tracker.DB_PATH)` dengan `SELECT` — tidak ada satu baris `INSERT`/`UPDATE`/`DELETE`, tidak ada penulisan ke `.env`, tidak ada pembacaan/penulisan `SHADOW_E3_ENABLED`/`SHADOW_E3_DISPATCH`. Dikonfirmasi statis (`grep`) dan lewat test (`TestReadOnly`, lihat Hasil Test).

---

## Ringkasan Perubahan File

```
 interfaces/telegram_bot.py                    | 26 ++++++++++++++++++++++++
 engine/shadow/promotion_criteria.py            | (baru, ~200 baris, murni fungsi)
 tests/test_shadow_promotion_criteria.py        | (baru, 13 test)
```
`interfaces/telegram_bot.py`: 2 baris import (`evaluate_promotion_criteria`, `format_promotion_check_message`), fungsi `shadow_promotion_check_command()` (± 18 baris), 1 baris registrasi `CommandHandler`. Tidak ada logika strategi shadow_e3 (`engine/shadow/e3_shadow.py`) yang disentuh — file itu tidak ada di diff.

---

## Hasil Test

### Test baru (`tests/test_shadow_promotion_criteria.py`) — 13/13 PASSED

```
TestAllCriteriaPass::test_all_pass PASSED
TestEachCriterionFailsInIsolation::test_expectancy_fails_others_pass PASSED
TestEachCriterionFailsInIsolation::test_profit_factor_fails_others_pass PASSED
TestEachCriterionFailsInIsolation::test_ci_lower_bound_fails_others_pass PASSED
TestEachCriterionFailsInIsolation::test_coin_concentration_fails_others_pass PASSED
TestEachCriterionFailsInIsolation::test_observation_fails_others_pass PASSED
TestTinySampleDoesNotCrash::test_n_one_reports_not_computable_instead_of_fake_number PASSED
TestTinySampleDoesNotCrash::test_zero_closed_signals_does_not_crash PASSED
TestReadOnly::test_evaluate_does_not_modify_signal_tracking PASSED
TestReadOnly::test_module_source_contains_no_write_statements PASSED
TestReadOnly::test_command_does_not_touch_shadow_env_flags PASSED
TestCommandAuthorization::test_unauthorized_chat_gets_rejected PASSED
TestCommandAuthorization::test_authorized_chat_receives_report PASSED

13 passed in 18.06s
```

Setiap kriteria diuji **gagal sendirian** (4 kriteria lain tetap lolos di skenario yang sama) — dirancang lewat perhitungan numerik langsung terhadap fungsi asli sebelum dikunci sebagai data test (bukan tebakan), supaya tiap skenario benar-benar mengisolasi satu kegagalan.

### Regresi — full test scope

```
venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q
247 passed, 3 warnings, 74 subtests passed in 22.32s
```
(234 sebelumnya + 13 test baru = 247, tidak ada yang gagal.)

---

## Contoh Output Lengkap per Skenario Test

### 1. MEMENUHI SEMUA KRITERIA (70 closed: 50 WIN@+1,0%, 20 LOSS@−0,3%, tersebar 70 coin unik)
```
🔍 SHADOW E3 → PRODUKSI: CEK KRITERIA PROMOSI
(read-only, TIDAK mengubah SHADOW_E3_ENABLED/SHADOW_E3_DISPATCH apa pun)

N closed outcome: 70

✅ Expectancy: +0.6286% (ambang >+0.3%)
✅ Profit Factor: 8.33 (ambang >1.2)
✅ Batas bawah bootstrap CI95: +0.4800% (ambang >-0.1%)
✅ Konsentrasi profit: C0 = 2.0% dari total profit (ambang <=50%)
✅ Observasi: N=70 closed (ambang ≥60) ATAU 0.0 minggu sejak sinyal pertama (ambang ≥6 minggu)

✅ MEMENUHI SEMUA KRITERIA — siap dipertimbangkan untuk promosi.

Keputusan promosi tetap manual — command ini tidak mengubah apa pun.
```

### 2. Gagal expectancy saja (40 WIN@+0,35%, 30 LOSS@−0,20%)
```
N closed outcome: 70

❌ Expectancy: +0.1143% (ambang >+0.3%)
✅ Profit Factor: 2.33 (ambang >1.2)
✅ Batas bawah bootstrap CI95: +0.0514% (ambang >-0.1%)
✅ Konsentrasi profit: C0 = 2.5% dari total profit (ambang <=50%)
✅ Observasi: N=70 closed (ambang ≥60) ATAU 0.0 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: expectancy.
```

### 3. Gagal profit factor saja (N=1000, magnitudo direplikasi supaya CI tetap sempit)
```
N closed outcome: 1000

✅ Expectancy: +0.3300% (ambang >+0.3%)
❌ Profit Factor: 1.18 (ambang >1.2)
✅ Batas bawah bootstrap CI95: +0.0886% (ambang >-0.1%)
✅ Konsentrasi profit: C0 = 0.2% dari total profit (ambang <=50%)
✅ Observasi: N=1000 closed (ambang ≥60) ATAU 0.0 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: profit factor.
```
**Catatan metodologi:** untuk mengisolasi kegagalan PF saja, dibutuhkan N besar (1000) supaya variansi bootstrap cukup kecil dan CI tidak ikut gagal — dengan N kecil (mis. 100) memakai magnitudo per-trade yang sama, CI ikut turun di bawah −0,1% (variansi tinggi mengonta-ganti kesimpulan CI, bukan hanya rata-rata). Ini justru menggambarkan kenapa kriteria CI dan PF **saling melengkapi**, bukan redundan: PF/expectancy bisa lolos dari rata-rata yang baik, tapi CI menangkap ketidakpastian kalau datanya berisik/variatif.

### 4. Gagal CI saja (5 WIN besar @+20%, 25 LOSS kecil @−1%, N=30, di-backdate 10 minggu supaya observasi lolos)
```
N closed outcome: 30

✅ Expectancy: +2.5000% (ambang >+0.3%)
✅ Profit Factor: 4.00 (ambang >1.2)
❌ Batas bawah bootstrap CI95: -0.3000% (ambang >-0.1%)
✅ Konsentrasi profit: C0 = 20.0% dari total profit (ambang <=50%, wins tersebar coin unik)
✅ Observasi: N=30 closed (ambang ≥60) ATAU 10.0 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: batas bawah bootstrap CI.
```
Ini menggambarkan tepat skenario yang harus ditangkap: rata-rata & PF terlihat bagus, tapi hasilnya didominasi segelintir kemenangan besar — bootstrap CI menangkap risiko itu belum terbukti stabil.

### 5. Gagal konsentrasi coin saja (1 coin "WHALE" +50%, 20 coin lain +1% masing-masing, 10 LOSS −0,5%, di-backdate 10 minggu)
```
N closed outcome: 31

✅ Expectancy: +2.0968% (ambang >+0.3%)
✅ Profit Factor: 14.00 (ambang >1.2)
✅ Batas bawah bootstrap CI95: +0.3226% (ambang >-0.1%)
❌ Konsentrasi profit: WHALE = 71.4% dari total profit (ambang <=50%)
✅ Observasi: N=31 closed (ambang ≥60) ATAU 10.0 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: konsentrasi profit per coin.
```

### 6. Gagal observasi saja (N=15, sinyal baru/recent)
```
N closed outcome: 15

✅ Expectancy: +0.6533% (ambang >+0.3%)
✅ Profit Factor: 9.17 (ambang >1.2)
✅ Batas bawah bootstrap CI95: +0.3067% (ambang >-0.1%)
✅ Konsentrasi profit: C0 = 9.1% dari total profit (ambang <=50%)
❌ Observasi: N=15 closed (ambang ≥60) ATAU 0.0 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: observasi (N/minggu).
```

### 7. N sangat kecil (N=1, meniru kondisi live saat ini persis) — tidak crash
```
❌ Expectancy: -1.7000% (ambang >+0.3%)
❌ Profit Factor: 0.00 (ambang >1.2)
❌ Batas bawah bootstrap CI95: belum bisa dihitung (N=1 < 10 closed outcome minimum untuk bootstrap bermakna)
✅ Konsentrasi profit: belum ada trade profit untuk dihitung
❌ Observasi: N=1 closed (ambang ≥60) ATAU ~0 minggu (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: expectancy, profit factor, batas bawah bootstrap CI, observasi (N/minggu).
```

---

## Output Nyata Terhadap Data Produksi SUNGGUHAN (read-only, dijalankan saat penulisan laporan ini)

Dijalankan langsung terhadap `data/aliza.db` produksi (bukan DB test), tanpa mengubah apa pun:

```python
from engine.shadow import promotion_criteria as pc
result = pc.evaluate_promotion_criteria(source="shadow_e3")
print(pc.format_promotion_check_message(result))
```

```
🔍 SHADOW E3 → PRODUKSI: CEK KRITERIA PROMOSI
(read-only, TIDAK mengubah SHADOW_E3_ENABLED/SHADOW_E3_DISPATCH apa pun)

N closed outcome: 1

❌ Expectancy: -2.4525% (ambang >+0.3%)
❌ Profit Factor: 0.00 (ambang >1.2)
❌ Batas bawah bootstrap CI95: belum bisa dihitung (N=1 < 10 closed outcome minimum untuk bootstrap bermakna)
✅ Konsentrasi profit: belum ada trade profit untuk dihitung
❌ Observasi: N=1 closed (ambang ≥60) ATAU 0.1 minggu sejak sinyal pertama (ambang ≥6 minggu)

❌ BELUM MEMENUHI — kriteria yang belum: expectancy, profit factor, batas bawah bootstrap CI, observasi (N/minggu).

Keputusan promosi tetap manual — command ini tidak mengubah apa pun.
```

**Interpretasi:** persis sesuai dugaan di konteks prompt — shadow_e3 baru punya **1 closed outcome** (1 LOSS, sejak sinyal pertama `2026-07-24T16:05:57 UTC`, ~0,1 minggu observasi). Empat dari lima kriteria gagal (wajar untuk tahap sedini ini), dan **batas bawah bootstrap CI dilaporkan "belum bisa dihitung" — bukan angka palsu** — persis yang diminta prompt. Command ini **tidak** dijalankan lewat Telegram sungguhan (tidak ada akses ke bot token), melainkan memanggil fungsi Python yang identik langsung — hasilnya sama persis dengan yang akan ditampilkan `/shadow_promotion_check` di Telegram karena `shadow_promotion_check_command()` hanya membungkus dua pemanggilan ini tanpa transformasi tambahan.

**Catatan edge-case transparan:** baris "Konsentrasi profit" menampilkan ✅ meski sebenarnya tidak ada data untuk dievaluasi (0 trade profit, karena satu-satunya closed outcome adalah LOSS). Ini `passed=True` secara vakum/vacuously-true (tidak ada risiko konsentrasi karena tidak ada profit sama sekali) — bukan bukti bahwa portofolio sudah terdiversifikasi dengan baik. Pesan teksnya sengaja dibuat eksplisit ("belum ada trade profit untuk dihitung") supaya tidak disalahartikan sebagai kriteria yang "benar-benar teruji lolos".

---

## Yang SENGAJA TIDAK Dikerjakan (sesuai instruksi)

- **Tidak merge/deploy** — semua perubahan di branch `feat/shadow-promotion-checklist`, tidak ada commit, tidak ada restart service.
- **Tidak ada auto-promote** — tidak ada kode yang mengubah `SHADOW_E3_ENABLED`/`SHADOW_E3_DISPATCH` atau memindahkan setup ke jalur produksi, sekarang maupun nanti. Dikonfirmasi statis (grep, tidak ada `INSERT`/`UPDATE`/`DELETE` di modul) dan lewat test (`TestReadOnly`).
- Logika strategi shadow_e3 (`engine/shadow/e3_shadow.py`) tidak disentuh — nol perubahan.
- `.env` produksi tidak disentuh — tidak ada env var baru yang diperlukan fitur ini.

## Rekomendasi Sebelum Merge

1. Review ambang `BOOTSTRAP_MIN_N=10` — kalau user ingin lebih konservatif (mis. 20-30, mendekati ambang "sampel kecil" `backtest/metrics.py::aggregate_metrics()` yang pakai N<30), mudah diubah (satu konstanta).
2. Definisi "kontribusi profit per coin" (Langkah 0.2) adalah interpretasi baru penulis laporan ini karena tidak ada rumus resmi sebelumnya — worth dikonfirmasi ke user apakah definisi ini (share dari total PnL positif) sesuai maksud aslinya, atau user punya definisi lain di pikiran.
3. Command ini akan sering melaporkan "BELUM MEMENUHI" untuk beberapa minggu ke depan (sesuai perkiraan `FASE4_REPORT.md`: observasi ≥6 minggu berakhir sekitar 1 September 2026) — ini perilaku yang diharapkan, bukan bug.
