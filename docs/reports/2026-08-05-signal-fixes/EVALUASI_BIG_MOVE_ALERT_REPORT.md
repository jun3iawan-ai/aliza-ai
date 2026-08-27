# Evaluasi Kesehatan & Kualitas BIG MOVE ALERT

Tanggal audit: 2026-08-05 WIB  
Mode: read-only untuk kode, konfigurasi, log, database, dan service. Tidak ada service yang di-restart, kode/config diubah, atau commit dibuat.

## Ringkasan eksekutif

**Putusan: perlu perbaikan desain sebelum ambang per-coin dituning.** Cooldown bukan bocor: pada `main`, ia persisted, 7.200 detik, dan dipisah per `(coin, arah)`. Namun sinyal yang diberi label **"dalam 1 jam" sebenarnya memakai perubahan rolling 24 jam**: field 1-jam tidak pernah diproduksi oleh pipeline snapshot. Karena itu, ambang flat `abs(change) >= 3%` tidak mengukur “big move 1 jam”; ia sangat mudah terus memenuhi syarat selama suatu coin bergerak >3% dalam 24 jam, lalu mengirim kembali sesudah cooldown.

Baseline kline 30 hari terakhir yang tersedia menunjukkan PEPE dan TAO memang lebih volatil daripada BTC/ETH: ATR14-1h masing-masing 1,463% dan 1,101%, versus 0,598% dan 0,784%. Simulasi **proxy** atas aturan 24-jam yang saat ini diterapkan juga menghasilkan PEPE 155 dan TAO 115 kandidat dalam 30 hari, dibanding BTC 51 dan ETH 99. Ini konsisten dengan hipotesis bahwa coin volatil akan mendominasi. Tetapi angka tersebut **bukan jumlah Telegram aktual**.

**BELUM CUKUP DATA** untuk menghitung volume/per-coin, interval antar-alert aktual, atau outcome 30–60 menit untuk alert Telegram tanggal 26–27 Juli: log aplikasi yang tersimpan paling tua mulai 29 Juli, `journalctl` untuk rentang itu tidak mengembalikan event, dan kline lokal berakhir 21 Juli. Tidak ada data yang sah untuk mengganti kekosongan tersebut, sehingga laporan ini tidak menyimpulkan dari sampel Telegram yang tidak tersedia.

Prioritas diskusi: (1) perbaiki sumber/label horizon menjadi 1-jam sungguhan, (2) baru kalibrasi threshold terhadap volatilitas per coin (mis. multiple ATR atau quantile rolling), dan (3) ukur outcome secara persistently sebelum menyatakan sinyal punya nilai momentum.

## Cakupan dan keterbatasan bukti

Checkout aktif saat audit adalah `fix/fase4b-weekly-report`, bukan `main`, dan worktree memiliki sejumlah laporan untracked. Agar tidak berpindah branch atau mengganggu pekerjaan lain, kode diaudit langsung dari referensi Git `main` commit `83b5e6d` (2026-07-27). Semua sitasi kode di bawah merujuk ke isi referensi tersebut.

### Retensi data mentah

| Artefak | Bukti mentah / cakupan | Konsekuensi |
|---|---|---|
| `logs/aliza.log.7.gz` | Berkas arsip tertua yang ada; awal isinya `2026-07-29 00:00:56,388 ... Snapshot processing coin: PEPE`. | Tidak mencakup 26–27 Juli WIB. |
| `logs/aliza.log` dan rotasi `.1`–`.7.gz` | Rotasi yang ada hanya dari 29 Juli sampai 5 Agustus; pencarian `journalctl -u aliza-telegram.service --since 2026-07-26 --until 2026-07-28` tidak menghasilkan baris. | Tidak dapat menghitung alert aktual/rata-rata interval untuk periode yang diminta. |
| `backtest/data/{TAO,PEPE,BTC,ETH}USDT_{5m,1h}.csv` | Rentang keempat file: 2024-05-22 sampai **2026-07-21 10:55 WIB (5m)** / **09:00 WIB (1h)**. Header mentah: `open_time,open,high,low,close,volume,close_time`. | Tidak bisa merekonstruksi harga 26–27 Juli atau follow-through alert pada tanggal itu. |

Pencarian pada log yang tersedia menemukan baris scheduler `Running job "big_move_checker"` dan `Job ... executed successfully`, bukan body/koin/persentase pesan yang dikirim. Karena job selesai sukses tidak berarti ada alert yang lolos, angka total aktual tidak boleh diinferensikan dari baris tersebut.

## 1. Mekanisme saat ini

### Ambang dan basis hitung

`big_move_checker()` memanggil `_snapshot_big_move_pct()`, lalu menolak hanya bila `abs(pct) < 3.0`; jadi `+3.00%` dan `-3.00%` lolos (`interfaces/telegram_bot.py:6307-6332`). Kode menampilkan pesan **"dalam 1 jam"** pada kedua arah (`:6355-6375`).

Tetapi helper mengutamakan tiga field 1-jam dan, bila semuanya tidak ada, memakai tiga field 24-jam (`interfaces/telegram_bot.py:6086-6098`):

```python
for key in ("price_change_1h", "price_change_pct_1h", "price_change_1h_pct"):
    ...
for key in ("price_change_percentage_24h", "price_change_pct_24h", "price_change_24h"):
    ...
```

Pemeriksaan seluruh `main` menemukan **tidak ada penulis** untuk tiga field 1-jam itu. Sebaliknya, snapshot enrichment melakukan satu request Binance `/api/v3/ticker/24hr`, membaca `priceChangePercent`, lalu menulis hanya `price_change_percentage_24h` dan `price_change_pct_24h` (`engine/market/market_snapshot_engine.py:153-200`; pemanggilan enrichment `:325-351`). Dengan demikian, jalur produksi yang dapat dibuktikan adalah:

`Binance rolling-24h ticker → snapshot field 24h → threshold absolut 3% → pesan berlabel 1 jam`.

Ini bukan return candle-close 1-jam, juga bukan snapshot terakhir versus N snapshot sebelumnya. Ticker Binance di-fetch ulang setiap siklus snapshot, tetapi nilainya tetap ukuran rolling 24 jam. Snapshot baru sendiri ditukar atomically (`market_snapshot_engine.py:345-370`).

### Cooldown, dedup, dan dispatch

Nilai default adalah `BIG_MOVE_COOLDOWN_SEC = int(os.getenv(..., "7200"))` (`engine/alerts/notification_governor.py:41-47`; `.env.example:7-10`). Tidak ada override `BIG_MOVE_COOLDOWN_SEC` di `.env` yang dapat dibaca pada checkout ini, sehingga bukti konfigurasi yang ada hanya default 7.200 detik.

Checker membentuk `direction = "up" if pct > 0 else "down"`, key `f"{coin}:{direction}"`, lalu menggunakan namespace `big_move` (`interfaces/telegram_bot.py:6343-6354`). Timestamp cooldown dicatat sebelum item dimasukkan ke antrean (`:6373-6375`). Governor menolak key yang sama hingga elapsed time `>= cooldown_sec` dan menyimpan nilai ke `data/alert_cooldown_state.json` (`engine/alerts/notification_governor.py:41-44, 123-139`). Jadi granularity-nya tepat **per coin + arah**, state tahan restart, serta ada dedup tambahan bila nilai persentase untuk key yang sama hampir identik (`:168-180`).

Checker dijalankan tiap 300 detik (`interfaces/telegram_bot.py:7373-7379`), tetapi polling 5 menit bukan interval pengiriman; cooldown 2 jam merupakan pembatas utamanya. Tidak ada penyesuaian threshold terhadap coin, ATR, stdev, likuiditas, atau regime dalam jalur ini: literal `3.0` berlaku untuk seluruh universe. Universe sendiri merupakan watchlist tetap 21 coin termasuk `PEPE` dan `TAO` (`engine/market/market_universe.py:14-28`).

Sesudah lolos, alert tidak langsung dikirim: masuk `ngov.queue_alert` (`telegram_bot.py:6373-6375`) dan flush setiap 60 detik. Bila terdapat >=5 item dari semua checker dalam siklus yang sama, governor membuat satu digest; jika kurang, dikirim individual (`notification_governor.py:288-304`). Sebagai pagar gabungan, rate limit juga membatasi noise alert sampai 15 pesan/jam secara default (`:44-46, 321-346`). Digest/rate limit mengurangi jumlah pesan Telegram, tetapi **tidak mengubah** fakta bahwa setiap calon Big Move per coin dapat tetap re-arm setelah 2 jam.

## 2. Volume, distribusi, dan volatilitas

### Volume aktual 26–27 Juli: BELUM CUKUP DATA

Tidak ada tabel total per hari/per coin yang dapat dihitung dengan jujur dari artefak tersisa. Khususnya:

- body/metadata `BIG MOVE ALERT` 26–27 Juli tidak ada pada arsip aplikasi yang ada;
- system journal untuk rentang itu kosong pada host saat audit;
- state cooldown saat ini hanya menyimpan keadaan terakhir, bukan event log historis;
- bahkan jika ada baris scheduler, ia tidak menyatakan bahwa threshold/cooldown/dedup menghasilkan pengiriman.

Karena itu, coin dominan aktual dan rata-rata jarak antar-alert aktual untuk 26–27 Juli adalah **BELUM CUKUP DATA**, bukan nol. Pola TAO/PEPE sekitar 2 jam yang disebut pada konteks pengguna konsisten dengan cooldown 7.200 detik, namun tidak dapat dihitung ulang atau diverifikasi dari log retained saat ini.

### Baseline volatilitas historis yang tersedia

Berikut hasil hitung dari CSV 1-jam untuk window 30 hari terakhir yang tersedia: 2026-06-21 11:00 hingga 2026-07-21 09:00 WIB (719 return per coin). `mean_abs_1h` dan `sd_1h` adalah return close-to-close 1-jam; `ATR14_1h%` adalah mean True Range 14 candle 1-jam / close. Ini bukan data alert dan bukan periode 26–27 Juli.

| Coin | Mean abs return 1h | Stdev return 1h | ATR14-1h% | Candle dengan abs return 1h >=3% |
|---|---:|---:|---:|---:|
| TAO | 0,501% | 0,704% | 1,101% | 1 / 719 |
| PEPE | 0,576% | 0,856% | 1,463% | 7 / 719 |
| BTC | 0,291% | 0,460% | 0,598% | 1 / 719 |
| ETH | 0,367% | 0,586% | 0,784% | 2 / 719 |

Jadi, pada baseline yang tersedia, PEPE memiliki ATR14 sekitar 2,45x BTC dan TAO sekitar 1,84x BTC; keduanya juga lebih volatil dari ETH. Ini mendukung arah hipotesis volatilitas, tetapi **tidak membuktikan** jumlah Telegram pada 26–27 Juli.

### Proxy aturan produksi 24-jam (bukan log aktual)

Untuk menguji konsekuensi desain yang sudah terbukti, saya melakukan simulasi read-only pada grid close 5-menit dalam window 30 hari yang sama: return rolling 24 jam close-to-close, threshold `abs >=3%`, initial state kosong, dan cooldown 7.200 detik per arah. Digest/rate-limit tidak diterapkan karena hasil yang diukur adalah kandidat per-coin sebelum penggabungan lintas checker.

| Coin | Kandidat proxy / 30 hari | Rata-rata jarak | Minimum jarak | <120 menit |
|---|---:|---:|---:|---:|
| TAO | 115 | 376,9 menit | 120 menit | 0 |
| PEPE | 155 | 259,1 menit | 120 menit | 0 |
| BTC | 51 | — | — | — |
| ETH | 99 | — | — | — |

Raw tail proxy TAO memperlihatkan mekanisme re-arm: `2026-07-17 05:25 WIB DOWN p24=-3,11%`, lalu 07:25 `-4,06%`, 09:25 `-5,68%`, 11:25 `-4,87%`, 13:25 `-5,12%`, 15:25 `-3,85%`. Karena angka 24-jam tetap melewati -3%, cadence 2 jam adalah perilaku yang diharapkan, bukan bukti cooldown bocor. Raw tail PEPE menunjukkan pola sama: 19 Juli 18:10 `UP +4,03%`, 20:10 `+4,03%`, 22:10 `+4,01%`, 20 Juli 00:10 `+3,28%`, lalu 02:55 `+3,26%` dan 06:55 `+3,27%` WIB.

Catatan penting: gap minimum proxy 120 menit tidak menunjukkan bug; simulator menerapkan key yang sama dengan kode. Ia juga tidak menemukan contoh perubahan arah yang terjadi lebih cepat pada window tersebut. Kode tetap akan mengizinkannya bila terjadi karena key `TAO:up` dan `TAO:down` berbeda.

## 3. Kualitas sinyal / follow-through

**Kesimpulan resmi untuk alert Telegram 26–27 Juli: BELUM CUKUP DATA.** Timestamp pengiriman alert aktual tidak tersedia, sehingga tidak mungkin memasangkan alert real dengan harga +30/+60 menit secara valid.

Sebagai exploratory proxy terbatas (bukan evaluasi produksi), kandidat simulasi 24-jam di atas dipasangkan dengan close 5m +30 dan +60 menit. "Continuation" hanya berarti return pasca-event bertanda sama dengan arah kandidat; tidak ada biaya, ambang materialitas, stop, atau pengujian statistik.

| Coin | n proxy | Continuation +30m | Continuation +60m |
|---|---:|---:|---:|
| TAO | 115 | 51 / 115 (44,3%) | 46 / 115 (40,0%) |
| PEPE | 155 | 61 / 155 (39,4%) | 57 / 155 (36,8%) |

Raw tail contoh TAO: 17 Juli 05:25 `DOWN p24=-3,11%, post30=-0,62%, post60=-1,03%` berlanjut; tetapi 07:25 `DOWN -4,06%, post30=+0,42%, post60=+0,47%` berbalik. Contoh PEPE: 20 Juli 08:55 `UP +3,64%, post30=+0,70%, post60=+1,75%` berlanjut; 10:55 `UP +4,73%, post30=-0,35%, post60=-0,69%` berbalik.

Proxy ini tidak mendukung klaim bahwa ambang rolling-24h 3% secara konsisten memberi momentum lanjutan jangka 30–60 menit; mayoritas proxy TAO/PEPE tidak bertanda searah pada kedua horizon. Namun ia tidak boleh dipromosikan menjadi kesimpulan kualitas alert real karena horizon/ticker/dispatch nyata dan state awal tidak dapat direkonstruksi sepenuhnya.

## 4. Perilaku perubahan arah

Tidak ada penekanan reversal antar-arah pada implementasi `main`. Key eksplisit `f"{coin}:{direction}"` (`interfaces/telegram_bot.py:6343-6351`) membuat `TAO:up` dan `TAO:down` dua cooldown independen; dedup nilai juga memakai key yang sama (`:6351-6354`). Dengan demikian alert naik kemudian turun untuk coin sama **dapat** lolos walaupun alert arah pertama masih berada dalam cooldownnya. Ini sudah menangani masalah desain lama yang cooldown-nya hanya per coin/condition.

Trade-off yang tersisa: ketika pasar whipsaw, dua arah dapat terkirim berdekatan. Digest lintas-checker dan rate limit global membantu pengalaman chat, tetapi tidak memberi konteks bahwa alert kedua adalah reversal dari alert pertama.

## Rekomendasi untuk didiskusikan (tanpa implementasi)

1. **Perbaiki definisi terlebih dahulu.** Hitung return 1-jam sungguhan dari close kline/snapshot yang tersimpan dan ubah label sesuai sumber. Jika produk memang ingin sinyal 24 jam, ubah pesannya menjadi “perubahan 24 jam”; jangan mempertahankan label 1 jam.
2. **Jangan mempertahankan 3% flat setelah horizon benar.** Untuk 1-jam, gunakan ambang relatif per coin, misalnya `max(floor_persen, k × ATR%_1h)` atau percentile rolling return per coin. Tetapkan floor agar aset sangat tenang tidak memicu noise, dan cap agar aset sangat volatil tetap membutuhkan gerak yang bermakna. Kalibrasikan out-of-sample; tabel volatilitas hanya menunjukkan arah, bukan angka `k` yang optimal.
3. **Re-arm berbasis perubahan keadaan, bukan waktu saja.** Setelah satu event, minta metrik kembali di bawah re-arm band (mis. threshold yang lebih rendah) atau ada ekstrem baru sebelum event searah berikutnya. Ini lebih dekat dengan arti “big move baru” daripada mengirim ulang karena 2 jam berlalu sementara return 24 jam tetap >3%.
4. **Pertahankan cooldown per arah, tetapi beri konteks reversal.** Jika arah berlawanan terjadi dalam 2 jam, pesan/digest dapat menandainya sebagai reversal terhadap event terakhir coin tersebut, bukan event independen.
5. **Gunakan digest untuk burst lintas-coin.** Digest saat ini hanya aktif bila >=5 alert lintas-checker dalam ~60 detik. Pertimbangkan mode ringkasan bagi beberapa Big Move volatil yang muncul dalam jendela lebih lebar, dengan daftar coin/arah/return dan satu konteks pasar; jangan menyembunyikan reversal besar.
6. **Tambahkan observabilitas yang retensi-nya cukup.** Persist minimal: `event_id`, waktu checker, waktu dispatch, coin, arah, nilai/horizon sumber, keputusan cooldown/dedup/digest/rate-limit, dan harga +30/+60 menit. Dengan itu audit berikutnya dapat menjawab volume, dominasi coin, gap aktual, dan precision continuation tanpa rekonstruksi proxy.

Tidak ada rekomendasi di atas yang diimplementasikan dalam audit ini.

