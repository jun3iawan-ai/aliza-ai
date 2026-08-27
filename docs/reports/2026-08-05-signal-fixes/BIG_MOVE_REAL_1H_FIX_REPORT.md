# Big Move Alert — Perubahan 1 Jam Sungguhan

Tanggal: 5 Agustus 2026  
Branch: `fix/big-move-real-1h-change`  
Commit: `9dc9782 fix: calculate big move from closed 1h candle`

## Ringkasan eksekutif

Perbaikan telah diimplementasikan dan seluruh regresi lulus. `BIG MOVE ALERT` sekarang menghitung persentase dari **harga snapshot saat ini dibanding penutupan candle Binance 1h yang terakhir sudah closed**, bukan lagi memakai perubahan ticker 24 jam saat field 1h tidak pernah ada. Ambang `abs(change) >= 3%`, cooldown, deduplikasi, arah, dan teks pesan `dalam 1 jam` tidak diubah.

Proxy historis 30 hari menunjukkan sumber bug lama memang penyebab utama volume: kandidat empat coin turun dari 420 pada proxy 24h lama menjadi 10 pada proxy 1h yang benar (turun 97,6%). PEPE masih yang terbanyak (6), tetapi TAO tidak lagi dominan (1). Jadi kalibrasi ambang per-volatilitas layak dipantau setelah data produksi terkumpul, namun **tidak lagi mendesak sebagai tindakan anti-spam pertama**.

Perubahan telah di-merge, di-push, dan di-deploy pada 5 Agustus 2026; `.env` produksi tidak disentuh.

## 0. Diagnosis dan keputusan desain

### Pola caching yang diikuti

Codebase sudah memiliki cache kline tertutup: `engine/shadow/e3_shadow.py:24-29` mendefinisikan endpoint Binance, `CACHE_TTL_SEC=900`, cache, dan lock; `_closed_4h_klines()` memakai cache tersebut pada `:50-58`. Implementasi baru memakai pola yang sama (cache in-memory + `Lock`), tetapi TTL berbasis batas candle karena nilai referensinya secara deterministik hanya berubah pada rollover 1 jam.

### Definisi perubahan “1 jam”

Definisi yang dipilih adalah:

`(harga live pada snapshot / close candle Binance 1h yang paling baru sudah closed - 1) × 100`

Ini konsisten dengan definisi yang diizinkan pada prompt, mudah dijelaskan, dan menghindari penggunaan candle yang masih berjalan. Endpoint dipanggil dengan `interval=1h, limit=2` (`engine/market/market_snapshot_engine.py:244-248`); candle dengan `close_time >= now` secara eksplisit dibuang (`:260-270`). Perhitungan tervalidasi berada di `:281-290`.

Catatan presisi: ini adalah referensi **closed-1h candle**, bukan tick persis 60 menit lalu. Harga pembanding stabil selama candle berjalan, sedangkan pembilang adalah harga live snapshot; maka pesan “dalam 1 jam” sekarang merujuk horizon candle 1h yang nyata, bukan angka 24h.

### Keputusan cache dan fallback

- Hasil close per pair disimpan hingga satu detik setelah batas jam UTC berikutnya (`market_snapshot_engine.py:212-214, 273-278`). Dengan demikian, pada snapshot setiap 60 detik tidak ada request tambahan sampai candle 1h relevan berganti.
- Saat Binance/pair gagal, negative-cache hanya 300 detik (`:235-258`, konstanta `:39`) agar tidak membanjiri API setiap snapshot namun dapat pulih cepat.
- Bila close 1h tidak tersedia, field 1h tidak ditulis (`:293-306`). Checker mempertahankan fallback 24h sebagai safety net: ia mencari tiga nama field 1h lebih dulu (`telegram_bot.py:6098-6105`), baru field 24h (`:6106-6110`).

## 1. Perubahan implementasi

| Berkas | Perubahan | Bukti |
|---|---|---|
| `engine/market/market_snapshot_engine.py` | Menambahkan cache, fetch candle Binance 1h closed, dan kalkulasi persen. | `:31-39`, `:212-306` |
| `engine/market/market_snapshot_engine.py` | Menulis `price_change_1h` dan alias `price_change_pct_1h` ke setiap row snapshot yang memiliki referensi valid. | `:293-306` |
| `engine/market/market_snapshot_engine.py` | Menjalankan enrichment 1h sesudah enrichment 24h sebelum snapshot dipublikasikan. | `:431-434` |
| `tests/test_big_move_real_1h_change.py` | Menambah lima pengujian unit/regresi untuk kalkulasi, cache, prioritas 1h, dan fallback 24h. | `:19-56` |

Checker sendiri tidak diubah. Ia tetap memakai threshold 3% (`interfaces/telegram_bot.py:6379-6381`), key cooldown per `(coin, arah)` (`:6392-6401`), dan teks alert tetap `dalam 1 jam` (`:6404-6424`). Default cooldown tetap `7200` detik di `engine/alerts/notification_governor.py:44`.

## 2. Hasil test

| Verifikasi | Hasil / bukti |
|---|---|
| Harga naik/turun | Test sintetis membuktikan `110/100 → +10%` dan `90/100 → -10%`; nilai nol/tidak valid ditolak. `tests/test_big_move_real_1h_change.py:19-23`. |
| Field snapshot ditulis | Enrichment menghasilkan `+5%` dan `-5%`, serta tidak menulis field jika referensi tidak ada. `:25-36`. |
| Cache | Dua lookup sebelum rollover menghasilkan satu request HTTP. `:38-47`. |
| Prioritas 1h | `price_change_1h=-3.25` dipilih alih-alih 24h `+18`. `:50-53`. |
| Fallback 24h | Saat field 1h absen, 24h `+4.5` masih dipakai. `:55-56`. |
| Test khusus baru | `venv/bin/python -m pytest tests/test_big_move_real_1h_change.py -q` → **5 passed**. |
| Regresi penuh | Di worktree terisolasi: `pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q` → **294 passed, 3 warnings, 74 subtests passed** (34,19 dtk). |

## 3. Analisis proxy: 1h benar vs proxy 24h lama

### Metode

Data retained: `backtest/data/{TAO,PEPE,BTC,ETH}USDT_1h.csv`; rentang yang sama dengan audit sebelumnya: 21 Juni 2026 10:00 sampai 21 Juli 2026 09:00 WIB. Untuk setiap close candle 1h, dihitung `close[t]/close[t-1]-1`; hanya `abs(pct) >= 3%` yang lolos. Cooldown disimulasikan `7200` detik, terpisah bagi `UP` dan `DOWN`, seperti checker produksi. Kolom “24h lama” adalah angka basis audit sebelumnya (grid proxy 5 menit, perubahan rolling 24h), sehingga ini perbandingan sumber-horizon; bukan jumlah Telegram aktual.

| Coin | Raw hit 1h ≥3% | Kandidat 1h sesudah cooldown | Proxy salah 24h sebelumnya | Perubahan kandidat |
|---|---:|---:|---:|---:|
| TAO | 1 | 1 | 115 | -99,1% |
| PEPE | 7 | 6 | 155 | -96,1% |
| BTC | 1 | 1 | 51 | -98,0% |
| ETH | 2 | 2 | 99 | -98,0% |
| **Total** | **11** | **10** | **420** | **-97,6%** |

Raw qualifying rows/candidate 1h (close sebelumnya → close saat ini):

```text
TAO  2026-06-25 20:00 WIB  DOWN  217.3 → 205.6             -5.3843%
PEPE 2026-06-25 20:00 WIB  DOWN  0.00000248 → 0.00000232  -6.4516%
PEPE 2026-07-04 03:00 WIB  UP    0.00000261 → 0.00000270  +3.4483%
PEPE 2026-07-06 22:00 WIB  UP    0.00000266 → 0.00000274  +3.0075%
PEPE 2026-07-10 23:00 WIB  UP    0.00000275 → 0.00000284  +3.2727%
PEPE 2026-07-11 00:00 WIB  DOWN  0.00000284 → 0.00000275  -3.1690%
PEPE 2026-07-14 20:00 WIB  UP    0.00000278 → 0.00000287  +3.2374%
BTC  2026-06-25 20:00 WIB  DOWN  61244.01 → 58290.17     -4.8231%
ETH  2026-06-25 20:00 WIB  DOWN  1635.81 → 1538.15       -5.9701%
ETH  2026-07-14 19:00 WIB  UP    1798.09 → 1861.04       +3.5009%
```

Satu raw PEPE tambahan tidak menjadi kandidat karena cooldown arah yang sama. Sebaliknya, PEPE `UP` pukul 23:00 lalu `DOWN` pukul 00:00 tetap keduanya muncul pada proxy, sesuai key per arah.

### Interpretasi dan rekomendasi

Dominasi PEPE/TAO terhadap BTC/ETH **berkurang tajam**. PEPE masih relatif tertinggi (6 dari 10), namun TAO berubah dari 115 menjadi 1 dan total frekuensi empat coin menjadi kira-kira 0,33 kandidat/hari. Dengan bukti ini, menaikkan threshold khusus coin volatil atau mengganti dengan ATR tidak perlu diburu untuk menyelesaikan spam yang berasal dari bug horizon 24h.

Rekomendasi: deploy dan amati telemetri aktual terlebih dahulu; setelah sampel alert 1h yang cukup terkumpul, evaluasi lagi distribusi per coin serta continuation/reversal. Jika PEPE tetap mendominasi secara bermakna, threshold relatif ATR/per-coin atau digest simultan dapat dibahas sebagai scope terpisah. Tidak ada perubahan threshold, cooldown, dedup, maupun reversal dalam commit ini.

## 4. Merge, deploy, dan verifikasi live

### Commit, scope, dan push

| Tahap | Hasil |
|---|---|
| Commit feature | `9dc9782 fix: calculate big move from closed 1h candle` |
| Merge commit `main` | `2c283f9 Merge branch fix/big-move-real-1h-change` (non-fast-forward) |
| Scope merge | Tepat dua berkas: `engine/market/market_snapshot_engine.py` dan `tests/test_big_move_real_1h_change.py` (164 insertions). Tidak ada perubahan `interfaces/telegram_bot.py`; threshold 3%, cooldown, dedup, serta key `(coin, arah)` tetap seperti sebelumnya. |
| Push | Berhasil: `83fee99..2c283f9  main -> main`; `origin/main` kini menunjuk `2c283f9`. |
| Cleanup | Branch lokal `fix/big-move-real-1h-change` berhasil dihapus sesudah merge. |

### Test pra- dan pasca-merge

Kedua test dijalankan dalam worktree Git sementara agar test yang me-reset state notifikasi tidak menyentuh state runtime produksi.

| Tahap | Perintah | Hasil |
|---|---|---|
| Pra-merge, commit `9dc9782` | `venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q` | **294 passed, 3 warnings, 74 subtests passed** (37,96 dtk) |
| Pasca-merge, commit `2c283f9` | Perintah sama | **294 passed, 3 warnings, 74 subtests passed** (40,93 dtk) |

### Restart dan log service

`aliza-telegram.service` direstart dan kembali **active** dengan PID `3190325` pada 5 Agustus 2026 07:58:29 WIB. Snapshot setelah restart berjalan sukses untuk 17 coin pada 07:59:27 WIB; `big_move_checker` juga berjalan pada 07:59:43 WIB tanpa error kline/enrichment 1h. Cuplikan journal:

```text
07:59:24  Running job "snapshot_job"
07:59:27  market_snapshot_engine: updated 17 coins
07:59:27  Snapshot completed. Valid coins: 17
07:59:27  Market snapshot updated
07:59:43  Running job "big_move_checker"
07:59:43  Job "big_move_checker ..." executed successfully
```

Tidak ada error `Binance 1h kline HTTP` maupun `Binance 1h kline fetch failed` pada journal pasca-restart yang diperiksa.

### Bukti field 1h live

Snapshot service berada di memori proses dan tidak mem-persist atau melog setiap field per-coin, sehingga field tidak dapat dibaca langsung dari journal tanpa menambah instrumentasi (yang tidak dilakukan). Sebagai verifikasi read-only, fungsi **yang sama dari code deployed** (`_enrich_collected_with_binance_1h`) dijalankan sekali terhadap ticker Binance live untuk 17 pair yang ada pada snapshot service. Hasilnya `live_pairs=17 populated_1h=17 missing_1h=0`:

```text
BTC   -0.1724%   ETH   -0.3107%   BNB   +0.4771%   SOL   -0.3390%
XRP   -0.3352%   ADA   -0.8290%   SUI   -0.5050%   ARB   -1.2210%
PEPE  -0.6944%   JTO   -0.0198%   ETHFI -1.5160%   WLD   -0.5632%
OM    +0.0000%   ASTER +0.3306%   XPL   +0.0256%   TAO   +0.1022%
XAUT  +0.1945%
```

Ini membuktikan endpoint kline, cache/reference, kalkulasi, dan penulisan field berhasil untuk 17/17 pair live; log snapshot terpisah mengonfirmasi service deployed memproses 17 coin di siklus yang sama tanpa error. Nilai PEPE/TAO berada dalam kisaran perubahan satu jam yang wajar, bukan angka 24h dua digit.

Tidak ada `BIG MOVE ALERT` nyata pada window observasi singkat; semua nilai probe di atas berada di bawah ambang 3%, sehingga tidak ada alert yang semestinya dikirim. Tombol **💥 Big Move** otomatis memakai sumber field yang sama karena `check_big_move_command()` memakai `_snapshot_big_move_pct()` (`interfaces/telegram_bot.py:6619-6625`), sama seperti `big_move_checker()` (`:6373-6381`).
