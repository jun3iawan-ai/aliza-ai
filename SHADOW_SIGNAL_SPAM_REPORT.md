# Laporan Audit & Perbaikan Spam Shadow Signal (🧪 SHADOW/RISET)

Branch: `fix/shadow-signal-spam` (dari `main` terbaru, `git status` bersih sebelum mulai kecuali beberapa file laporan `*_REPORT.md` untracked yang tidak disentuh).

Tanggal kerja: 2026-07-25.

---

## Langkah 0 — Diagnosis

### Kesimpulan singkat

1. **Kode**: pesan dibentuk di `engine/shadow/e3_shadow.py` (`format_shadow_message`), dan dikirim dari `_run_shadow_e3()` di `interfaces/telegram_bot.py:6774` (sebelum perbaikan).
2. **Interval**: bukan job terpisah — `_run_shadow_e3()` dipanggil langsung di dalam `snapshot_job` (`interfaces/telegram_bot.py:6893`, sebelum perbaikan), yang di-schedule `run_repeating(snapshot_job, interval=60, first=5)` (`interfaces/telegram_bot.py:7073`). Jadi shadow_e3 ikut siklus snapshot utama, tiap 60 detik.
3. **Cooldown**: **tidak ada sama sekali**, dikonfirmasi. `_run_shadow_e3()` (kode lama) memanggil `safe_dispatch()` untuk setiap kandidat setiap kali dipanggil, tanpa pengecekan cooldown/dedup apa pun — tidak memanggil `notification_governor` (ngov), tidak memanggil `engine.trading.signal_engine.can_send_signal`. Selama `TradingBrain` masih mendeteksi setup "OVERSOLD BOUNCE" untuk suatu coin di siklus snapshot, pesan riset dikirim ulang tiap menit tanpa batas.
4. **Perbandingan dengan `[TRADE SIGNAL]` resmi**: jalur produksi (`scan_for_signals()` → `_dispatch_and_record_deterministic_signal()` → `engine/signal_engine.py:process_signal()`) memanggil `engine.trading.signal_engine.can_send_signal(key, signal)` (`engine/trading/signal_engine.py:84-93`), yang menolak sinyal identik `(coin, setup)` dalam `SIGNAL_TTL_SECONDS = 900` (15 menit), **dan state-nya persisted ke disk** lewat `engine.state_store.save_state/load_state` (`engine/trading/signal_engine.py:12, 72, 101, 104-113`) — jadi tahan restart proses. Ini **bukan** `notification_governor`, melainkan mekanisme dedup terpisah yang sudah ada sejak sebelum migrasi 21 Juli, dan **sudah berfungsi benar** (dikonfirmasi di log: baris `[BLOCKED] duplicate signal SUI|OVERSOLD BOUNCE` berulang di antara satu `[SIGNAL] SUI|OVERSOLD BOUNCE` yang lolos tiap ~15 menit). Inilah yang menjelaskan kenapa `[TRADE SIGNAL]` muncul ~tiap 15-16 menit sementara shadow muncul tiap menit: **bukan** karena TRADE SIGNAL "lebih jarang match", tapi karena ia punya cooldown TTL 15 menit dan shadow tidak punya cooldown apa pun. **Kesimpulan item 3 di prompt: TRADE SIGNAL resmi tidak punya gap yang sama — tidak perlu diperbaiki.**
5. **Bug ATR14 4h "beku"**: **diinvestigasi, dan ini BUKAN bug.** `_closed_4h_klines()` (`engine/shadow/e3_shadow.py`) secara sengaja hanya mengembalikan candle 4h yang **sudah closed** (`close_time < now_ms`, baris 66-67 kode lama/baru — tidak diubah). ATR14 dihitung dari 14 candle 4h closed terakhir, jadi **secara desain** hanya berubah ketika candle 4h baru closed (tiap 4 jam: 00:00/04:00/08:00/... UTC = 07:00/11:00/15:00/... WIB), bukan tiap menit mengikuti harga live seperti Entry. Dikonfirmasi empiris di VPS:
   - Window laporan user (03:42–04:59 WIB, 24-25 Juli) = 20:42–21:59 UTC (24 Juli) — seluruhnya berada **di dalam satu window candle 4h yang sama** (20:00–24:00 UTC), yang baru closed jam 00:00 UTC (07:00 WIB) — jauh setelah window laporan berakhir. Jadi tidak ada candle baru yang closed selama 77 menit itu → ATR **wajib** identik secara matematis, walau `_closed_4h_klines()` sendiri di-refetch dari Binance tiap ≤15 menit (`CACHE_TTL_SEC = 900`).
   - Dijalankan langsung di VPS: candle 4h SUI terakhir yang closed adalah `2026-07-24 23:59:59.999 UTC` (saat pengecekan dilakukan, `now` = `2026-07-25 00:28 UTC` / `07:28 WIB`) — persis di boundary 4 jam berikutnya setelah window user, mengonfirmasi pola boundary di atas.
   - Ditambahkan test regresi (`tests/test_fase4.py::test_shadow_atr_stable_within_same_4h_window_not_a_freshness_bug`) yang membuktikan: refetch candle (cache dipaksa "basi") tanpa ada candle baru closed di sisi exchange → ATR & `close_time` candle terakhir tetap identik. Ini bukan bug cache/freshness terpisah seperti insiden epoch/freshness yang diperbaiki 21 Juli (itu soal *filter* freshness yang tidak pernah jalan sama sekali karena exception ditelan; di sini filter freshness-nya justru berjalan benar dan itulah yang membuat nilainya identik).
   - **Tidak ada perubahan kode untuk item ini** — didokumentasikan sesuai instruksi prompt untuk kasus root cause yang jelas dan bukan bug.
6. **Skala spam sebenarnya (dari `logs/aliza.log` + rotasi `.1`/`.2.gz`.../`.7.gz`, ditambah `data/aliza.db` tabel `signal_tracking`)**:
   - Fitur `engine/shadow/e3_shadow.py` ditambahkan **21 Juli 2026, 12:36 WIB** (commit `fe7c18e`, "feat(fase4): add isolated E3 shadow runtime").
   - Dari 21–23 Juli, `shadow_e3 candidates=0` di **setiap** siklus (dikonfirmasi lewat `zgrep -c` di seluruh log terrotasi hari-hari itu) — TradingBrain tidak pernah menemukan setup yang match untuk coin manapun selama 3 hari itu, jadi **tidak ada spam sama sekali** di periode itu.
   - Spam mulai **2026-07-24 23:05:57 WIB** — saat itu ARB dan SUI **bersamaan** pertama kali match "OVERSOLD BOUNCE" (dikonfirmasi lewat `data/aliza.db`: dua baris `signal_tracking` dengan `source='shadow_e3'`, timestamp identik `2026-07-24T16:05:57 UTC` = `23:05:57 WIB`). ARB berhenti match tak lama setelah (hanya 1 baris tercatat, tidak berulang), sementara **SUI terus match tanpa jeda sampai laporan ini ditulis** (2026-07-25 ~07:30 WIB) — inilah yang dilihat user.
   - Total siklus dengan kandidat shadow ≥1 sejak 23:05:57 WIB (24 Juli) sampai akhir log saat ini (~07:27 WIB, 25 Juli, ±8j22m berjalan): **±769 pesan Telegram terkirim** (110 dari sisa 24 Juli + 659 dari 25 Juli, dijumlahkan dari kolom `candidates=N` per baris log — setiap kandidat = satu panggilan `safe_dispatch()` karena `SHADOW_E3_DISPATCH=true` sepanjang periode ini). Tidak ditemukan baris `ALERT DISPATCH SKIPPED` atau `CIRCUIT BREAKER ACTIVE` di window ini, jadi hampir semua percobaan dispatch itu **benar-benar terkirim** ke Telegram, bukan cuma dicoba.
   - **Kenapa DB `signal_tracking` cuma punya 1 baris SUI** padahal pesan terkirim ratusan kali: `record_signal()` (`engine/trading/signal_tracker.py:154-233`) punya guard bawaan sendiri — menolak insert baru kalau masih ada baris `status='OPEN'` untuk `(coin, setup, source)` yang sama (baris 196-211). Guard ini **valid dan tidak diubah** — ia mencegah duplikasi tracking untuk outcome/statistik (`shadow_stats_command`), tapi **sama sekali tidak mencegah pengiriman Telegram**, karena di kode lama dispatch terjadi *sebelum* dan *tidak tergantung* pada hasil `record_signal()`. Ini konfirmasi tambahan bahwa akar masalah murni ada di jalur dispatch, bukan di tracking.
   - Coin lain yang pernah kena pola serupa: hanya **ARB**, dan hanya sekali (1 siklus di 23:05:57 WIB), tidak berulang — bukan pola berkelanjutan seperti SUI.

### Ringkasan akar masalah

Persis pola yang sudah diperbaiki untuk checker lain di PR `fix/telegram-notification-noise` (21 Juli): **dispatch tanpa cooldown, re-fire tiap siklus selama kondisi setup masih terpenuhi.** Bedanya, migrasi 21 Juli itu eksplisit tidak menyertakan `shadow_e3` dalam daftar checker yang dipindah ke `notification_governor` (checker ini baru ditambahkan hari yang sama, dan sengaja diisolasi dari semua state produksi — termasuk, tanpa disengaja, dari cooldown-nya).

---

## Perbaikan

### 1. Cooldown dispatch shadow signal (`engine/alerts/notification_governor.py` / ngov)

Mengikuti pola established yang sama persis dengan `near_support`/`near_resistance`/`whale_alert` (`_snapshot_alert_allowed`, `interfaces/telegram_bot.py:6050-6064`):

- **`engine/shadow/e3_shadow.py`**: tambah `dispatch_cooldown_sec()` — baca env `SHADOW_SIGNAL_COOLDOWN_SEC`, default **14400 detik (4 jam)**, selaras dengan cooldown checker riset lain yang sudah ada (`_SNAPSHOT_ALERT_COOLDOWN_SEC = 4*3600`).
- **`interfaces/telegram_bot.py`**: tambah `_shadow_signal_allowed(coin, setup, side, now_ts)` dan `_record_shadow_cooldown(...)`, memanggil `ngov.is_cooldown_allowed("shadow_e3", key, ...)` / `ngov.record_cooldown("shadow_e3", key, ...)` dengan `key = f"{coin}:{setup}:{side}"` — cooldown per kombinasi **(coin, setup, side)**, sesuai permintaan prompt.
- `_run_shadow_e3()` diubah: sebelum `safe_dispatch()`, cek `_shadow_signal_allowed(...)`. Kalau dalam cooldown → `dispatch_status = "COOLDOWN"`, tidak kirim Telegram (tapi tetap masuk `record_signal()` seperti sebelumnya — guard dedup DB di `signal_tracker.record_signal()` yang sudah ada tetap menjadi otoritas untuk tracking outcome, tidak diubah). Kalau lolos → kirim seperti biasa lalu `record_cooldown()`.

**Kenapa cooldown berbasis waktu (bukan "hanya setup baru terdeteksi")**: ini mengikuti pola yang sama dengan `[TRADE SIGNAL]` resmi (`can_send_signal`, TTL 15 menit) dan checker `ngov` lain (`near_support` dkk, 4 jam) — keduanya *time-based re-arm*, bukan *edge-triggered* (yaitu: setup yang sama boleh notify lagi setelah cooldown habis meski kondisinya tidak pernah "hilang" di antaranya). Konsisten dengan filosofi bot ini secara keseluruhan: cukup jarangkan re-notifikasi untuk kondisi yang bertahan lama, tanpa perlu melacak state transisi "baru muncul" vs "masih berlangsung" secara terpisah (yang akan menambah kompleksitas state tanpa manfaat jelas untuk sinyal riset). Default 4 jam dipilih karena ini jalur **riset**, bukan sinyal trading actionable — lebih longgar dari TTL 15 menit TRADE SIGNAL sudah tepat.

**Environment**: didokumentasikan di `.env.example` (`SHADOW_SIGNAL_COOLDOWN_SEC=14400`, dengan komentar). **`.env` produksi tidak disentuh** — karena env var ini belum pernah di-set di sana, default `14400` dari kode otomatis berlaku begitu deploy.

### 2. Bug ATR beku

Bukan bug (lihat Langkah 0.5) — tidak ada perubahan kode. Ditambahkan test regresi untuk mendokumentasikan perilaku yang benar secara eksplisit (lihat bagian Test).

### 3. TRADE SIGNAL resmi

Sudah punya cooldown yang layak (TTL 15 menit, persisted ke disk) — tidak ada gap, tidak ada perubahan.

---

## Perubahan file

- `engine/shadow/e3_shadow.py`: tambah `dispatch_cooldown_sec()`.
- `interfaces/telegram_bot.py`: import `dispatch_cooldown_sec`; tambah `_shadow_signal_allowed()` / `_record_shadow_cooldown()`; `_run_shadow_e3()` gate dispatch dengan cooldown per `(coin, setup, side)`.
- `.env.example`: dokumentasi `SHADOW_SIGNAL_COOLDOWN_SEC=14400`.
- `tests/test_fase4.py`: 3 test baru (lihat bawah).

Tidak ada perubahan pada logika strategi shadow_e3 (ATR multiplier, RR, threshold oversold) — sesuai batasan prompt. Tidak ada checker lain yang sudah dimigrasi ke `ngov` sebelumnya yang disentuh.

---

## Test

Ditambahkan ke `tests/test_fase4.py`:

1. **`test_shadow_dispatch_cooldown_suppresses_repeat_within_window`** — simulasi setup yang tetap terpenuhi selama 12 siklus snapshot berturut-turut (60 detik antar siklus, jam palsu lewat `monkeypatch` pada `time_module.time`): hanya dispatch pertama yang terkirim (`sent == 1`), semua siklus berikutnya (termasuk tepat di bawah batas 4 jam) tertekan cooldown; setelah cooldown lewat dan kondisi masih terpenuhi, dispatch kedua terkirim (`sent == 2`).
2. **`test_shadow_dispatch_cooldown_scoped_per_coin_setup_side`** — dua coin berbeda (SUI, ARB) dengan setup sama di siklus yang sama: keduanya lolos cooldown independen (tidak saling menekan), tapi pengulangan langsung untuk masing-masing tertekan.
3. **`test_shadow_atr_stable_within_same_4h_window_not_a_freshness_bug`** — regresi untuk temuan Langkah 0.5: refetch candle 4h (cache dipaksa basi) tanpa ada candle baru closed di ekschange → ATR14 & `close_time` candle terakhir tetap identik, membuktikan ini perilaku yang benar, bukan bug.

### Hasil

```
$ ./venv/bin/python -m pytest tests/test_fase4.py -v
tests/test_fase4.py::test_shadow_disabled_does_not_change_snapshot_payload PASSED
tests/test_fase4.py::test_shadow_signal_source_excluded_from_default_stats PASSED
tests/test_fase4.py::test_shadow_dispatch_cooldown_suppresses_repeat_within_window PASSED
tests/test_fase4.py::test_shadow_dispatch_cooldown_scoped_per_coin_setup_side PASSED
tests/test_fase4.py::test_shadow_atr_stable_within_same_4h_window_not_a_freshness_bug PASSED
tests/test_fase4.py::test_shadow_levels_one_and_three_atr PASSED
6 passed in 18.13s
```

Regresi penuh (`tests/` + file test root yang diminta):

```
$ ./venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_binding.py \
    test_dashboard_docs.py test_dashboard_dotenv_isolation.py test_dashboard_endpoint_auth.py \
    test_dashboard_execution_limit.py test_dashboard_passwords.py test_dashboard_rate_limit.py \
    test_dashboard_security.py -q
218 passed, 3 warnings, 74 subtests passed in 18.61s
```

---

## Deploy & Verifikasi

**Status: sudah di-deploy ke VPS dan diverifikasi live, spam sudah berhenti.**

### Commit & merge

- Commit fix di branch `fix/shadow-signal-spam`: `bff3128` — "fix: add persisted cooldown to shadow_e3 dispatch, stop SUI spam" (6 file: `.env.example`, `engine/shadow/e3_shadow.py`, `interfaces/telegram_bot.py`, `tests/test_fase4.py`, `SHADOW_SIGNAL_SPAM_REPORT.md`, `AlizaAI-Crypto/01-hasil-audit-codex/SHADOW_SIGNAL_SPAM_REPORT.md`).
- Merge ke `main`: fast-forward `3e87ad2..bff3128` (tidak perlu merge commit — branch dibuat dari `main` terbaru dan tidak ada commit lain masuk ke `main` di antaranya).
- `git diff --stat 3e87ad2 bff3128` dikonfirmasi hanya 6 file di atas yang berubah — **tidak ada** logika strategi shadow_e3 (ATR multiplier/RR/threshold) atau checker `ngov` lain (near_support, near_resistance, whale, dll.) yang tersentuh.
- Push ke `origin/main`: `3e87ad2..bff3128 main -> main` — berhasil.
- Branch lokal `fix/shadow-signal-spam` dihapus (`git branch -d`) setelah dipastikan fully merged & pushed.

### Full test scope (dijalankan 2×: sebelum merge di branch, dan lagi setelah merge di `main`)

```
$ ./venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_binding.py \
    test_dashboard_docs.py test_dashboard_dotenv_isolation.py test_dashboard_endpoint_auth.py \
    test_dashboard_execution_limit.py test_dashboard_passwords.py test_dashboard_rate_limit.py \
    test_dashboard_security.py -q
218 passed, 3 warnings, 74 subtests passed in 22.52s
```

Hasil identik (218 passed) di kedua run — tidak ada regresi dari merge.

### Restart & startup bersih

`sudo systemctl restart aliza-telegram.service` pada **2026-07-25 07:37:48 WIB**. `journalctl -u aliza-telegram -n 150` pasca-restart: startup normal (snapshot job, alert_digest_flush, TradingBrain per coin berjalan seperti biasa), **tidak ada error/exception/traceback baru**.

### Bukti cooldown menekan dispatch berulang (real production log, bukan test)

Sebelum fix, tiap siklus snapshot (~60s) dengan kandidat shadow selalu mengirim pesan Telegram sungguhan (jeda `candidates=N` → `recorded=` berkisar 600–1300ms, sesuai waktu tempuh network call `bot.send_message`). Setelah restart dengan fix:

```
2026-07-25 07:38:52,726 - shadow_e3 candidates=2
2026-07-25 07:38:53,957 - shadow_e3 recorded=0 dispatch=True     ← jeda 1231ms: DIKIRIM (siklus pertama, cooldown kosong — wajar, ini kali pertama kombinasi coin+setup+side ini pernah tercatat sejak fitur cooldown aktif)

2026-07-25 07:39:43,810 - shadow_e3 candidates=2
2026-07-25 07:39:43,812 - shadow_e3 recorded=0 dispatch=True     ← jeda 2ms: DITEKAN cooldown, tidak ada network call
2026-07-25 07:40:43,637 → 07:40:43,638   (jeda 1ms — ditekan)
2026-07-25 07:41:43,530 → 07:41:43,531   (jeda 1ms — ditekan)
2026-07-25 07:42:43,658 → 07:42:43,664   (jeda 6ms — ditekan)
2026-07-25 07:43:47,465 → 07:43:47,466   (jeda 1ms — ditekan)
2026-07-25 07:44:43,638 → 07:44:43,639   (jeda 1ms — ditekan)
2026-07-25 07:45:43,944 → 07:45:43,945   (jeda 1ms — ditekan)
2026-07-25 07:46:43,553 → 07:46:43,554   (jeda 1ms — ditekan)
2026-07-25 07:47:43,582 → 07:47:43,583   (jeda 1ms — ditekan)
2026-07-25 07:48:47,608 → 07:48:47,608   (jeda 0ms — ditekan)
2026-07-25 07:49:45,842 → 07:49:45,843   (jeda 1ms — ditekan)
2026-07-25 07:50:43,786 → 07:50:43,787   (jeda 1ms — ditekan)
2026-07-25 07:51:43,628 → 07:51:43,629   (jeda 1ms — ditekan)
2026-07-25 07:52:44,019 → 07:52:44,020   (jeda 1ms — ditekan)
2026-07-25 07:53:44,969 → 07:53:44,971   (jeda 2ms — ditekan)
```

15 siklus berturut-turut (07:39–07:53 WIB, ~15 menit, SUI & ARB tetap match "OVERSOLD BOUNCE" tiap kali) — **hanya siklus pertama yang benar-benar mengirim ke Telegram**, sisanya ditekan cooldown dalam hitungan milidetik (bukan network call). Dikonfirmasi juga lewat `data/alert_cooldown_state.json`:

```json
"cooldown:shadow_e3": {
    "SUI:OVERSOLD BOUNCE:LONG": 1784939932.7273958,
    "ARB:OVERSOLD BOUNCE:LONG": 1784939932.7273958
}
```

(`1784939932.727` = `2026-07-25 07:38:52.727 WIB`, persis siklus pertama pasca-restart). Cooldown 4 jam berarti pesan shadow SUI berikutnya — jika setup-nya masih match saat itu — baru boleh terkirim lagi sekitar **11:38 WIB**, bukan lagi tiap menit.

### Ringkasan status

| Tahap | Status |
|---|---|
| Commit fix | `bff3128` |
| Merge ke `main` | fast-forward `3e87ad2..bff3128` |
| Full test (branch) | 218 passed |
| Full test (main pasca-merge) | 218 passed |
| Restart service | 2026-07-25 07:37:48 WIB, startup bersih |
| Spam berhenti (bukti log) | dikonfirmasi — 15/15 siklus pasca-siklus-pertama ditekan cooldown |
| Push ke `origin/main` | berhasil |
| Cleanup branch lokal | `fix/shadow-signal-spam` dihapus |
