# Troubleshooting Aliza AI

Runbook ini adalah prosedur diagnosis rinci untuk bot Telegram, pipeline market, signal, SQLite, scheduler, dan dashboard. Mulai dari bukti; jangan mengubah kode, database, konfigurasi, atau service sebelum akar masalah cukup jelas.

## 1. Triage awal

Jalankan dari `/opt/aliza-ai`:

```bash
git status --short --branch
systemctl status aliza-telegram --no-pager
journalctl -u aliza-telegram --since "30 minutes ago" --no-pager
```

Catat waktu kejadian, command/endpoint yang gagal, commit aktif, exception lengkap, dan apakah masalah konsisten atau intermiten. Perintah `journalctl` tertentu dapat membutuhkan hak tambahan; jangan mengubah permission untuk mengakalinya.

## 2. Bot Telegram tidak merespons

1. Pastikan unit authoritative aktif: `systemctl is-active aliza-telegram`.
2. Cari `Traceback`, `Exception`, `Network error`, atau kegagalan token di journal.
3. Konfirmasi proses berasal dari `/opt/aliza-ai/interfaces/telegram_bot.py` melalui `systemctl status`; jangan memakai `ps | grep` sebagai satu-satunya bukti.
4. Pastikan handler yang diuji masih diregistrasikan di `interfaces/telegram_bot.py`.
5. Bila semua command ditolak, periksa authorization gate dan allowlist tanpa mencetak token atau ID sensitif.
6. Bila polling macet setelah restart, lanjutkan ke [graceful-shutdown.md](graceful-shutdown.md).

Jangan menampilkan `TELEGRAM_BOT_TOKEN` atau isi `.env` di terminal yang direkam.

## 3. Snapshot atau data market hilang

Pipeline terjadwal menggunakan `engine.market.market_snapshot_engine`. Fungsi utamanya adalah `update_market_snapshot()` dan `get_market_snapshot()`.

1. Cari log initial update dan job snapshot pada startup.
2. Periksa timestamp snapshot dan isi `snapshot["data"]`.
3. Bila kosong, telusuri error provider, timeout, rate limit, dan coverage coin/timeframe.
4. Verifikasi fungsi analyzer terpisah dengan `engine.market.market_analyzer.market_signal(symbol)`.
5. Jangan membuat fallback API langsung pada opportunity/signal path; jalur terjadwal harus mempertahankan validasi snapshot.

Provider eksternal dapat gagal secara parsial. Pisahkan kegagalan Binance, CoinGecko, Fear & Greed, atau sumber lain berdasarkan log aktual.

## 4. Opportunity atau signal tidak muncul

Fungsi produksi yang relevan:

- `engine.trading.opportunity_scanner.scan_opportunities()`
- `engine.trading.signal_engine.scan_for_signals()`

Periksa berurutan:

1. Snapshot tersedia dan tidak stale.
2. `trade_setup` terbentuk.
3. Opportunity memenuhi RR minimum 1,3.
4. Scan produksi memenuhi RR minimum 3 dan confidence minimum 70.
5. Gateway dispatch memenuhi kontrak RR minimum 2.
6. Coverage gate, universe exclusion, market risk, anti-spam, dan deduplication tidak menolak kandidat.
7. Tracking dilakukan setelah hasil dispatch diketahui; periksa `dispatch_status` dan `source`.

Hasil kosong tanpa exception dapat merupakan filtering yang sah. Gunakan log alasan penolakan sebelum mengubah threshold.

## 5. Entry, portfolio, atau SQLite bermasalah

Database aplikasi berada di `data/aliza.db`. Writer yang sah adalah:

- `engine/trading/trade_manager.py` untuk trade;
- `engine/trading/signal_tracker.py` untuk schema/migrasi dan signal tracking.

Diagnosis:

1. Pastikan file ada, owner/mode benar, dan filesystem tidak penuh.
2. Periksa exception SQLite seperti locked, missing table, atau malformed.
3. Verifikasi `init_trade_db()` dan inisialisasi signal tracking dijalankan saat startup.
4. Untuk jalur trade, telusuri `create_trade()`, `get_active_trades()`, dan `close_trade()`.
5. Jangan menjalankan operasi tulis manual pada DB produksi saat diagnosis. Ambil backup konsisten sebelum migrasi atau remediasi.

## 6. Scheduler atau alert tidak berjalan

Scheduler produksi hidup di proses `aliza-telegram`; `aliza-market` bukan scheduler aktif.

1. Cari registrasi job dan exception callback pada startup.
2. Pastikan snapshot job serta checker bernama hanya terdaftar sekali.
3. Pastikan tidak ada unit legacy lain yang ikut aktif dan menjalankan bot kedua.
4. Untuk alert Telegram, pastikan target chat telah terdaftar melalui alur aplikasi dan dispatcher memang primary.
5. Untuk shadow E3, bedakan candidate generation dari dispatch; mode shadow dapat mengalir tanpa mengirim alert.

## 7. Dashboard/API gagal

Launcher dashboard adalah `scripts/run_dashboard.py`, default loopback `127.0.0.1:8001`.

1. `GET /health` harus mengembalikan JSON `{"status":"ok"}` dan tidak memerlukan Bearer token.
2. `/api/dashboard/market`, `quant`, `predict`, `signals`, dan `portfolio` memerlukan `Authorization: Bearer ...`.
3. Respons 401 tanpa token pada endpoint dashboard adalah perilaku benar, bukan outage.
4. Jika startup gagal, periksa konfigurasi JWT, koneksi database user, binding loopback, dan service dashboard yang berlaku.
5. Jangan menulis credential atau token ke report.

## 8. Kapan melakukan perubahan

Perubahan baru layak dibuat setelah modul, kondisi pemicu, bukti log, dan reproduksi minimum diketahui. Setelah perbaikan, jalankan test terarah lalu suite yang relevan sesuai [testing.md](../architecture/testing.md), dan lakukan [smoke test](smoke-test.md) bila runtime terpengaruh.
