# Near Level On-Demand — Deploy Report

Tanggal: 2026-08-05 WIB  
Commit deployed: `83fee99075c42df57cb8b6a03590b4ffe8eb9450` — `feat: make near level alerts on-demand`

## Ringkasan

Push individual **NEAR SUPPORT ALERT** dan **NEAR RESISTANCE ALERT** sekarang dimatikan secara default. Deteksi tetap berjalan, tetapi kandidat hanya dicatat di log sebagai suppressed dan tidak masuk antrean Telegram. Informasi level tersedia melalui `/levels [toleransi%]` dan otomatis menjadi satu section ringkas dalam Morning Brief serta Evening Summary; dua laporan terjadwal itu sudah ada, sehingga tidak menambah jumlah pesan harian.

Perubahan telah di-commit, fast-forward merge ke `main`, full regression lulus, service `aliza-telegram.service` di-restart sehat, diverifikasi selama lebih dari lima menit, dan `main` telah dipush ke `origin`.

## Langkah 0 — diagnosis

### Asal level dan trigger lama

- `engine/market/market_analyzer.py:252-256` menghitung fallback support/resistance sebagai minimum/maksimum 20 harga terakhir. Hasil feature yang valid dapat menggantikan nilai itu (`:400-407`); bila nilai tetap kosong, fallback akhir adalah `price × 0,98` / `price × 1,02` (`:439-468`). Tidak ada logika perhitungan level yang diubah.
- Checker lama menghitung `abs(price - level) / level`, hanya menganggap kandidat bila kurang dari 1% dan minimal 0,05% dari level, menolak range support-resistance yang lebih sempit dari 2%, serta mengecek freshness snapshot. Aturan itu dipindahkan tanpa perubahan makna ke `get_coins_near_levels()` (`interfaces/telegram_bot.py:6168-6201`).
- Cooldown individual lama tetap digunakan **hanya bila flag push dinyalakan kembali**: `_near_level_push_checker()` memakai `condition = near_support` atau `near_resistance` dan `_snapshot_alert_allowed()` (`telegram_bot.py:6229-6275`). Helper tersebut memakai namespace persisted `cooldown:snapshot_alert` di notification governor; core governor tidak diubah.
- Command lain memakai global authorization gate; `/levels` juga memeriksa `_authorized_chat()` secara eksplisit (`telegram_bot.py:6473-6499`), sehingga aman bila dipanggil langsung dalam test/handler.
- Morning Brief membangun header di `telegram_bot.py:5189-5222`; Evening Summary di `:5334-5358`. Keduanya adalah titik penyisipan section baru, sebelum preview event.

## Perubahan implementasi

| File | Perubahan |
|---|---|
| `interfaces/telegram_bot.py` | Menambah default tolerance dan flag default-off (`:6135-6147`), scanner reusable `get_coins_near_levels()` (`:6150-6201`), formatter reusable (`:6204-6226`), serta gate push legacy (`:6229-6291`). |
| `interfaces/telegram_bot.py` | Menambah `/levels` (default 1%, override positif seperti `/levels 1.5`) dan registrasi handler/menu (`:6473-6499`, `:7330-7336`, `:7398-7401`). |
| `interfaces/telegram_bot.py` | Menyisipkan formatter yang sama ke Morning Brief (`:5191-5219`) dan Evening Summary (`:5336-5353`). |
| `.env.example` | Mendokumentasikan `NEAR_LEVEL_PUSH_ENABLED=false` dan `NEAR_LEVEL_DEFAULT_TOLERANCE_PCT=1.0` (`:7-10`). `.env` produksi tidak disentuh. |
| `tests/test_near_level_on_demand.py` | Menambah enam test baru: scanner/sisi/toleransi, format kosong/berisi, push default-off, `/levels` default/custom, dan section di kedua summary. |
| `tests/test_notifikasi_mitigasi.py` | Memperbarui satu ekspektasi lama: fresh near-level tidak lagi masuk pending queue saat push default-off, sementara Big Move tetap lolos. |

Tidak ada perubahan pada logika strategi/trade signal, checker Big Move/volume/funding/whale, maupun core `notification_governor`.

## Perilaku baru

`get_coins_near_levels(tolerance_pct=1.0, snapshot=None)` mengembalikan row terstruktur `coin`, `side`, `price`, `level`, dan `distance_pct`. Formatter selalu menampilkan dua kelompok:

- `🔻 Dekat Support`
- `🔺 Dekat Resistance`

Jika suatu kelompok kosong, formatter menyatakannya eksplisit; jika keduanya kosong, ia juga menampilkan `Tidak ada coin dekat level saat ini.`. `/levels` menolak argumen nonnumerik/nonpositif dengan pesan penggunaan dan tidak mengubah tolerance global.

## Hasil test

- Test khusus: `venv/bin/python -m pytest tests/test_near_level_on_demand.py -q` → **6 passed**.
- Full regression pra-merge dan pasca-merge dijalankan pada worktree sementara terisolasi agar `tests/test_notifikasi_mitigasi.py` tidak menyentuh state cooldown produksi:  
  `289 passed, 3 warnings, 74 subtests passed`.

Kegagalan awal satu test lama (`FreshnessCheckTests.test_fresh_data_is_not_blocked`) mengharapkan near-resistance masih mengantrekan pesan. Ekspektasi itu diperbarui menjadi satu pending Big Move saja karena near-level memang sengaja default-off; full suite kemudian hijau.

## Verifikasi live `/levels`

Pemindai dipanggil read-only terhadap snapshot market live baru pada 2026-08-05 sekitar 07:28 WIB. Output nyata:

```text
📍 LEVEL TERDEKAT (toleransi ±1.00%)

🔻 Dekat Support
• ETHFI — Harga $0.3560 | Support $0.3562 | Jarak 0.06%

🔺 Dekat Resistance
• BNB — Harga $594.1300 | Resistance $593.7800 | Jarak 0.06%
• BTC — Harga $64,010.01 | Resistance $64,233.36 | Jarak 0.35%
• ETH — Harga $1,866.68 | Resistance $1,885.36 | Jarak 0.99%
• SOL — Harga $73.5700 | Resistance $74.1900 | Jarak 0.84%
• SUI — Harga $0.6911 | Resistance $0.6980 | Jarak 0.99%
• XPL — Harga $0.0781 | Resistance $0.0785 | Jarak 0.59%
```

Output ini sesuai dengan log checker sesudah deploy: satu kandidat support dan enam kandidat resistance. Tidak ada Telegram yang dikirim individual.

## Deploy dan safety check

1. Branch `feat/near-level-on-demand` dibuat dari `main`; commit dibuat sebagai `83fee99`.
2. Scope merge terkonfirmasi hanya empat file: `.env.example`, `interfaces/telegram_bot.py`, dua file test. Fast-forward ke `main` berhasil.
3. `aliza-telegram.service` di-restart pada 07:25:16 WIB dan tetap `active`.
4. Setelah 60 detik startup, journal tidak memuat error/traceback aplikasi. Ada satu warning APScheduler `near_support_checker` missed by 1,62 detik tepat saat startup; siklus normal berikutnya berjalan sehat.
5. Bukti gate nyata dari journal:

```text
07:26:19 near_level_push disabled: suppressed 5 resistance candidate(s)
07:31:14 near_level_push disabled: suppressed 1 support candidate(s)
07:31:19 near_level_push disabled: suppressed 6 resistance candidate(s)
```

   Ketiga job selesai sukses. Observasi mencakup lebih dari lima menit pasca-restart dan membuktikan kandidat deteksi tetap ada tetapi tidak di-dispatch individual.
6. `git push origin main` berhasil: `83b5e6d..83fee99 main -> main`. Branch fitur lokal telah dihapus setelah merge; branch tersebut tidak pernah dipush terpisah.

## Status akhir

- Branch aktif: `main`, sinkron dengan `origin/main`.
- Deploy: **berhasil**.
- Service: **active**.
- Push individual near support/resistance: **OFF default**.
- Akses on-demand `/levels` dan section dua kali sehari: **aktif**.

