# Laporan Fase 1c — Verifikasi Runtime Pascarest

> **Status: SUPERSEDED.** Snapshot pada 2026-07-21. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

Tanggal observasi: 21 Juli 2026, sekitar 09:12–09:44 WIB.

## Verdict

**PERLU TINDAKAN**.

Deploy commit Fase 1 sudah berjalan di proses Telegram baru dan market service sudah disabled/inactive. Lifecycle, migrasi schema, scheduler dan snapshot dasar berjalan. Namun selama observasi 31 menit tidak ada kandidat setup yang lolos (`passed=0` pada seluruh scan), tidak ada signal deterministic baru, dan `market_analyzer` mengeluarkan error data berulang untuk BONE, FARTCOIN, HYPE dan ZEREBRO. Masalah ini perlu ditindaklanjuti sebelum menyatakan runtime sepenuhnya sehat.

## 1. Proses baru dan commit

### Bukti Git

```text
HEAD: cdaf551e489ade4d75ba2673c054516390cc3b8b
Merge branch 'fix/fase1-signal-integrity'
main...origin/main [ahead 15]
```

### Bukti systemd/proses

- `aliza-telegram.service`: `active (running)`.
- MainPID: `2151364`.
- Waktu start: `Tue Jul 21 09:12:24 WIB`.
- WorkingDirectory: `/opt/aliza-ai`.
- Command: `/opt/aliza-ai/venv/bin/python /opt/aliza-ai/interfaces/telegram_bot.py`.
- Waktu start sesudah merge commit (merge dibuat 09:08:51 WIB), sehingga proses baru memuat kode hasil merge.
- `aliza-market.service`: `disabled`, `inactive`.

Tidak ada restart/service command yang dijalankan oleh Codex pada fase ini; restart dan disable dilakukan manual oleh user sesuai prasyarat.

## 2. Startup dan journal

Journal startup menunjukkan stop proses lama pada 09:12:21–09:12:24, service baru start 09:12:24, lalu proses memuat CrewAI/FAISS/SentenceTransformer dan snapshot awal.

Agregat journal sejak start baru:

| Pola | Jumlah |
|---|---:|
| `Traceback` | 0 |
| `signal_tracker` | 0 |
| `auto_alert_engine` | 0 |
| `market_analyzer` | 348 baris warning/diagnostik |
| `ERROR` total | 54 |
| `Price unavailable` | 54 |
| `Invalid data — skipping signal` | 235 |

Tidak ada traceback. Namun error/invalid data market berulang bukan startup yang benar-benar bersih. Error utama menyangkut price/data untuk BONE, FARTCOIN, HYPE dan ZEREBRO. Error `signal_tracker` dan `auto_alert_engine` tidak muncul.

## 3. Migrasi database

`sqlite3 data/aliza.db "PRAGMA table_info(signal_tracking);"` mengembalikan kolom berikut:

```text
id, coin, setup, entry_price, sl_price, tp_price, confidence, rr,
signal_time, status, close_price, close_time, pnl_pct, market_score,
created_at, regime, side, source, signal_id, dispatch_status
```

Kolom wajib `side`, `source`, `signal_id`, dan `dispatch_status` ada. Query source menghasilkan:

```text
source  n
legacy  10
```

Semua 10 baris lama berlabel `legacy`. Query baris baru sejak waktu restart menghasilkan `new_rows=0`, sehingga tidak ada signal baru untuk diuji dispatch/side.

## 4. Scheduler

Log startup mencatat tepat sekali untuk masing-masing:

```text
09:13:52 Added job "rsi_extreme_checker" to job store "default"
09:13:52 Added job "signal_checker" to job store "default"
```

`signal_checker` adalah nama job scheduler untuk fungsi `signal_check_job()` di `interfaces/telegram_bot.py`. Tidak ditemukan registrasi ganda. Eksekusi RSI juga menunjukkan interval 5 menit; fungsi outcome memakai satu job `signal_checker`.

## 5. Observasi runtime 31 menit

Jendela observasi: start 09:12:24 sampai sekitar 09:43:49 WIB.

| Metrik | Hasil |
|---|---:|
| Snapshot completed | 31 |
| Scan `scan_for_signals` | 30 |
| Coin valid per snapshot | 17 atau 18 |
| Scan total | 17 atau 18 |
| `no_valid_setup` | 16 atau 17 |
| `passed` | 0 pada seluruh scan |
| `reject_rr` | 0 |
| `reject_conf` | 0 |
| Signal tracking baru | 0 |
| Signal baru `dispatch_status='SENT'` | 0 |

Baseline pra-deploy adalah `total=17`, `no_valid_setup=17`, `passed=0`. Pascadeploy menjadi 17–18 total dan 16–17 `no_valid_setup`, tetapi tetap `passed=0`. Penurunan signal memang diharapkan setelah filter candle/MTF lebih ketat; nol kandidat selama seluruh jendela berarti perlu investigasi lebih lanjut.

### Coin yang terdampak data

- `BONE`: berulang `Price unavailable`/invalid data.
- `FARTCOIN`: harga CoinGecko fallback tersedia, tetapi tetap `Invalid data — skipping signal`.
- `HYPE`: kadang valid dan menghasilkan `NO SETUP`, tetapi sering invalid data; tujuh observasi memiliki `alignment_weak` sebelum gagal pada siklus lain.
- `ZEREBRO`: berulang `Price unavailable` atau invalid data; kadang fallback harga muncul.

**TIDAK PASTI** apakah setiap kegagalan tepat disebabkan threshold 4h≥30/1d≥50; journal tidak mencetak panjang kline. Bukti konsisten dengan kombinasi data candle/price fallback yang tidak cukup untuk pipeline baru. Jangan melonggarkan threshold tanpa pemeriksaan data source dan backtest.

Alasan `NO SETUP` pada coin yang valid didominasi `proximity_filter`, `no_condition_met`, dan `alignment_weak`; bukan error exception.

## 6. Signal baru

Tidak ada signal baru selama observasi. Tabel `signal_tracking` tetap 10 baris lama, seluruhnya `source='legacy'`; karena itu belum ada baris pascadeploy yang dapat diverifikasi memiliki `dispatch_status='SENT'`, side benar, dan `source='deterministic'`.

## 7. Baseline metrik

Query yang diminta:

```sql
SELECT source, side, setup, status, COUNT(*) n, ROUND(AVG(pnl_pct),2) avg_pnl
FROM signal_tracking GROUP BY source, side, setup, status;
```

Hasil:

```text
source  side   setup            status  n  avg_pnl
legacy         SPOT             OPEN    2  NULL
legacy  LONG   LONG             OPEN    3  NULL
legacy  LONG   OVERSOLD BOUNCE  LOSS    3  -1.17
legacy  LONG   PULLBACK LONG    LOSS    1  -3.55
legacy  SHORT  SHORT            LOSS    1  -5.45
```

Tidak ada WIN dan tidak ada source deterministic/llm baru pada baseline ini. Data adalah baseline legacy sebelum signal baru pascadeploy; bukan winrate pascadeploy.

## 8. Rekomendasi push

`main` berada 15 commit di depan `origin/main`. Push ke remote belum dijalankan oleh Codex. User perlu melakukan review dan push secara eksplisit, misalnya:

```text
git push origin main
```

Perintah tersebut adalah tindakan yang perlu dilakukan user setelah menyetujui merge/deploy dan memeriksa remote target.

## Tindakan yang direkomendasikan

1. Investigasi availability Binance/CoinGecko dan panjang kline untuk BONE, FARTCOIN, HYPE, ZEREBRO; tampilkan alasan data secara terukur sebelum mengubah threshold.
2. Tambahkan observability untuk panjang kline 4h/1d dan alasan `UNKNOWN`/invalid per coin.
3. Tinjau mengapa seluruh kandidat tetap `passed=0` selama 30 menit; bedakan efek filter alignment/proximity dari efek data.
4. Setelah ada signal deterministic, verifikasi row `source`, `side`, `signal_id`, dan `dispatch_status` end-to-end.
5. Push `main` ke `origin` hanya setelah review user.

Tidak ada kode, service, env, token, atau data SQLite yang diubah selama verifikasi ini; hanya query read-only dan penulisan laporan.
