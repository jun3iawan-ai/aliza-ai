# Audit Re-fire `[TRADE SIGNAL]` Setup Sama Berulang

Tanggal audit: 27 Juli 2026, data/log dibaca sampai sekitar 08:11 WIB.  
Mode: read-only untuk kode, konfigurasi, database, Git, dan service. Laporan ini adalah satu-satunya artefak yang dibuat.

## Ringkasan eksekutif

**Putusan: bukan bug cooldown yang bocor, tetapi gap desain notifikasi produksi yang perlu didiskusikan/diperbaiki.** `SIGNAL_TTL_SECONDS=900` berfungsi persis sesuai kode: blok hanya selama 15 menit per key `coin|setup`, lalu kondisi yang tetap valid dapat mengirim lagi. State bahkan dipersist ke disk. Karena setup dapat menetap jauh lebih lama dari 15 menit, ini bukan jaminan bahwa notifikasi setelah TTL adalah peluang/substansi baru.

Kasus ETH bukan pertama atau jarang pada kanal Telegram. Log yang masih dipertahankan menunjukkan 99 pengiriman deterministic: **90 SUI|OVERSOLD BOUNCE**, 5 ARB|OVERSOLD BOUNCE, dan 4 ETH|OVERBOUGHT REJECTION. SUI berulang kira-kira tiap 15–16 menit selama periode panjang. Jadi pola ETH tiga kali dalam 50 menit adalah manifestasi normal dari TTL, tetapi normal tersebut tidak tampak cocok untuk UX sinyal actionable yang berarti “setup baru”.

Namun, kekhawatiran spesifik bahwa tiga notifikasi ETH tersebut akan menjadi tiga `LOSS`/tiga observasi winrate **tidak terjadi pada implementasi saat ini**. Ketiganya dikirim, tetapi hanya pengiriman pertama menjadi satu row `signal_tracking`; guard menolak row baru selama row `(coin, setup, source)` yang sama masih `OPEN`. Dengan demikian, untuk tiga pengiriman ETH ini, hanya satu outcome yang dapat masuk winrate dan circuit breaker. Tidak ada merge atau replacement: percobaan insert kedua/ketiga diabaikan.

## 1. Skala pola sejak Fase 1 deploy

Fase 1 menempatkan persist tracking deterministic setelah dispatch pada commit `4760d76` (21 Juli 2026); provenance commit Fase 1 tercatat di `docs/reports/phases/2026-07-21/fase-1/FASE1_REPORT.md:73-84`. Query di bawah dijalankan terhadap `data/aliza.db` pada saat audit.

```sql
WITH ordered AS (
  SELECT id, coin, setup, signal_time,
         LAG(signal_time) OVER (
           PARTITION BY coin, setup ORDER BY julianday(signal_time), id
         ) AS prev
  FROM signal_tracking
  WHERE source = 'deterministic'
)
SELECT id, coin, setup, prev AS prev_signal_time, signal_time,
       ROUND((julianday(signal_time)-julianday(prev))*1440, 2) AS gap_min
FROM ordered
WHERE prev IS NOT NULL
  AND (julianday(signal_time)-julianday(prev))*24 < 2
ORDER BY julianday(signal_time), id;
```

**Hasil mentah: 0 baris** (`refire_events_lt_2h = 0`). Artinya tidak ada satu pun pasangan row `signal_tracking` deterministic dengan `(coin, setup)` sama dan jarak di bawah dua jam. Ini bukan bukti tidak ada re-fire Telegram; justru guard `OPEN` membuat tracking tidak merekam pengulangan pengiriman tersebut.

Semua row deterministic pasca-Fase 1 yang ada saat audit adalah:

| id | coin | setup | waktu sinyal WIB | status | dispatch |
|---:|---|---|---|---|---|
| 33 | ARB | OVERSOLD BOUNCE | 2026-07-24T23:05:52.182511+07:00 | LOSS | SENT |
| 36 | SUI | OVERSOLD BOUNCE | 2026-07-24T23:40:49.264659+07:00 | LOSS | SENT |
| 38 | ARB | OVERSOLD BOUNCE | 2026-07-25T12:02:41.348714+07:00 | OPEN | SENT |
| 40 | SUI | OVERSOLD BOUNCE | 2026-07-25T14:39:45.099455+07:00 | OPEN | SENT |
| 45 | ETH | OVERBOUGHT REJECTION | 2026-07-27T07:05:47.332192+07:00 | OPEN | SENT |

Sebagai kontrol silang terhadap delivery, seluruh log retained yang cocok dengan `[SIGNAL] ... from deterministic` berjumlah 99: 90 `SUI|OVERSOLD BOUNCE`, 5 `ARB|OVERSOLD BOUNCE`, 4 `ETH|OVERBOUGHT REJECTION`. Contoh raw SUI ada di `logs/aliza.log.2.gz:1211,3077,4720,...`; `logs/aliza.log.2.gz:2860` adalah contoh ARB. Contoh ETH di bawah. Log rotasi yang tersedia tidak membuktikan jumlah absolut seluruh waktu sebelum arsip tertua, tetapi cukup membuktikan pola tidak langka.

Raw log ETH:

```text
logs/aliza.log:43719  2026-07-27 07:05:46,625 ... [SIGNAL] ETH|OVERBOUGHT REJECTION from deterministic
logs/aliza.log:43720  2026-07-27 07:05:47,331 ... ALERT DISPATCHED via CENTRAL GATEWAY
logs/aliza.log:45374  2026-07-27 07:21:44,542 ... [SIGNAL] ETH|OVERBOUGHT REJECTION from deterministic
logs/aliza.log:45375  2026-07-27 07:21:45,244 ... ALERT DISPATCHED via CENTRAL GATEWAY
logs/aliza.log:48515  2026-07-27 07:52:46,753 ... [SIGNAL] ETH|OVERBOUGHT REJECTION from deterministic
logs/aliza.log:48516  2026-07-27 07:52:47,457 ... ALERT DISPATCHED via CENTRAL GATEWAY
logs/aliza.log:50067  2026-07-27 08:08:44,463 ... [SIGNAL] ETH|OVERBOUGHT REJECTION from deterministic
logs/aliza.log:50068  2026-07-27 08:08:45,156 ... ALERT DISPATCHED via CENTRAL GATEWAY
```

Jeda aktual: 15m57.917s, 31m02.211s, lalu 15m57.710s. Pengiriman keempat pada 08:08 berada di luar tiga pesan yang dilaporkan user, tetapi memperkuat diagnosis.

## 2. Tracking, winrate, dan circuit breaker

### Tiga ETH bukan tiga row

Query target menghasilkan tepat satu row:

```text
id=45 | ETH | OVERBOUGHT REJECTION | SHORT
entry=1951.99 | sl=1974.2672 | tp1=1856.02 | confidence=75.0 | rr=4.31
signal_time=2026-07-27T07:05:47.332192+07:00 | status=OPEN
source=deterministic | dispatch_status=SENT
signal_id=be781690-345f-4064-aa2c-fd42520f9871
```

Nilai Entry/RR/Confidence 07:21 dan 07:52 dari pesan Telegram yang diberikan user konsisten dengan payload live yang dapat berubah. **BELUM CUKUP DATA untuk mengekstrak ulang nilai payload tersebut dari server**: log aplikasi merekam key, waktu, dan keberhasilan dispatch, bukan isi pesan/Entry/RR lengkap. Delivery-nya sendiri terverifikasi oleh log di atas.

Alur kode menjelaskan hasil ini:

- `interfaces/telegram_bot.py:6957-7017` memanggil `process_signal()` lebih dulu dan baru memanggil `record_signal()` setelah pengiriman/gate berhasil.
- `engine/trading/signal_tracker.py:196-211` mencari `status='OPEN'` dengan coin, setup, dan source yang sama; bila ada, koneksi ditutup dan fungsi mengembalikan `None` tanpa `INSERT`.
- Tidak ada kode merge, update Entry, atau penutupan row lama dalam jalur itu. Baris baru baru mungkin diinsert setelah row lama sudah tidak `OPEN`.
- `signal_check_job` mengevaluasi row `OPEN` setiap 10 menit (`interfaces/telegram_bot.py:6638-6659,7481-7485`). Untuk ETH ini hanya id 45 yang dievaluasi.

### Konsekuensi winrate

Untuk ETH 07:05/07:21/07:52: **N dan winrate resmi tidak bertambah tiga kali**. Jika stop/target id 45 tercapai, hanya id itu yang berubah menjadi `WIN` atau `LOSS`; tidak ada dua kandidat row lain yang menunggu evaluasi. Guard ini mencegah distorsi statistik yang dikhawatirkan, tetapi menciptakan ketidaksesuaian lain: pengguna menerima beberapa “trade signal”, sementara statistik menganggap satu observasi.

Secara kontrafaktual, bila row pertama sudah closed sebelum re-fire berikutnya, guard tidak lagi menolak insert dan masing-masing signal dapat menjadi observasi independen. Dalam keadaan itu, tiga loss dari satu gerak pasar dapat menaikkan N dan menurunkan winrate secara tidak proporsional. Ini adalah alasan untuk membedakan *notification refresh* dari *setup/trade instance*, tetapi bukan keadaan tiga ETH ini.

### Circuit breaker

Circuit breaker memang menggunakan closed outcome deterministic dari `signal_tracking`: `engine/learning/trade_history_tracker.py:99-138` memfilter `source=deterministic` dan status `WIN/LOSS` secara kronologis; `engine/portfolio/drawdown_protector.py:14-41` menghitung LOSS beruntun tanpa grouping coin/setup/waktu, dengan ambang tiga. Gate dispatch memeriksa breaker sebelum dispatch (`interfaces/telegram_bot.py:6966-6982`).

Jadi untuk tiga notifikasi ETH yang masih berada di bawah satu row OPEN, **tidak dapat memicu breaker sebagai tiga LOSS**. Tetapi pada skenario kontrafaktual di atas, ya: tiga row LOSS berdekatan dari setup/pergerakan sama akan memenuhi ambang tiga dan dapat memicu breaker tanpa mengetahui korelasinya. Itu risiko desain valid untuk data masa depan, walaupun bukan insiden yang sedang terjadi.

## 3. TTL 15 menit: asal, pembanding, dan kecukupan

`SIGNAL_TTL_SECONDS = 900` ada di `engine/trading/signal_engine.py:57-59`; `can_send_signal()` menolak hanya ketika `now-last_time < 900` (`:84-93`), dan `record_signal_sent()` menyimpan waktu setelah pengiriman (`:96-101`). State dimuat/dibersihkan dari disk (`:62-72,104-113`), sehingga restart bukan penyebab re-fire ini.

Git blame menempatkan nilai 900 pada commit `2693116` tanggal 21 Mei 2026. Tidak ditemukan dokumentasi atau commit message yang menjelaskan **mengapa tepat 15 menit** dipilih. Perubahan relevan `5e4ad91` (17 Juli) menghapus perbandingan payload karena Entry/RR/Confidence live selalu berubah; commit itu secara eksplisit mempertahankan nilai TTL dan mengubah dedup menjadi key+TTL. Dengan kata lain, histori secara sadar menyelesaikan bug payload-dedup, tetapi tidak menunjukkan evaluasi ulang apakah 15 menit bermakna “setup baru”.

Pembanding riset jauh lebih panjang:

- `_SNAPSHOT_ALERT_COOLDOWN_SEC = 4 * 3600` di `interfaces/telegram_bot.py:218-220`; gate persisted-nya di `:6060-6074`.
- `SHADOW_SIGNAL_COOLDOWN_SEC` default 14.400 di `engine/shadow/e3_shadow.py:42-47` dan `.env.example:16-18`.

**BELUM CUKUP DATA untuk menyatakan perbedaan 15 menit vs 4 jam sengaja didasarkan pada filosofi “produksi=fresh/actionable, riset=notifikasi longgar”.** Kode memperlihatkan perbedaan durasi dan histori menunjukkan 15 menit tidak direvisi pada 17 Juli; tidak ada ADR/dokumen/commit yang memberi rasional produk tersebut. Penjelasan itu masuk akal sebagai hipotesis, bukan bukti.

Penilaian audit: TTL 15 menit mungkin cocok sebagai *refresh quote* untuk kondisi cepat, tetapi terlalu pendek sebagai satu-satunya definisi “sinyal baru” bagi setup seperti rejection/oversold yang tetap valid selama berjam-jam. Bukti SUI (90 send) menunjukkan ini bukan kasus hipotetis.

## 4. Kesimpulan dan opsi tanpa implementasi

Pola ETH adalah **perilaku yang diharapkan oleh implementasi TTL**, bukan bug state/cooldown. Namun secara produk ia adalah **gap yang perlu diperbaiki/diputuskan**, karena pesan yang sama re-arm otomatis hanya karena waktu lewat, bukan karena transisi setup atau perubahan pasar material. Prioritas perbaikan adalah jalur notifikasi; tracking saat ini sudah menghindari tripling winrate untuk row OPEN.

Opsi untuk dibahas (tidak ada yang diimplementasikan oleh audit ini):

1. **Cooldown production per setup** — gunakan durasi berbeda, misalnya 1–4 jam untuk `OVERBOUGHT REJECTION`/`OVERSOLD BOUNCE`, dan pertahankan 15 menit hanya untuk setup yang benar-benar intraday. Persist key `(coin, setup, side)` agar perubahan side tidak tertahan salah.
2. **Edge-triggered re-arm** — hanya kirim ketika setup berubah dari tidak-valid ke valid; re-arm setelah setup benar-benar hilang selama sejumlah scan/candle. Ini paling dekat dengan makna “baru”, tetapi perlu state dan aturan reset eksplisit.
3. **Re-arm berbasis perubahan material** — setelah cooldown minimal, izinkan pesan baru hanya bila candle timeframe acuan selesai, regime/side berubah, atau level/entry bergerak melewati threshold yang ditetapkan. Ini memberi pembaruan saat memang ada informasi baru.
4. **Pisahkan refresh dari trade instance** — bila tetap ingin update, kirim “update setup yang sama” (atau ringkas di digest) dan jangan mempresentasikannya sebagai trade baru. Tetap pertahankan guard tracking OPEN seperti sekarang.
5. **Supersede hanya bila kebijakan tracking berubah** — menutup/mengganti row lama dengan row baru dapat membuat tracking mengikuti pesan terakhir, tetapi mengubah definisi outcome dan berisiko menghapus observasi; bukan rekomendasi pertama. Jika dipilih, perlu aturan eksplisit untuk winrate dan circuit breaker agar tidak menilai satu episode pasar beberapa kali.

Rekomendasi awal: opsi 2 atau kombinasi opsi 1+3, lalu tambahkan observability yang mencatat setiap dispatch sebagai `new`, `refresh`, atau `suppressed`. Setelah itu barulah evaluasi apakah breaker perlu grouping episode/setup untuk kasus row yang memang boleh berulang setelah close.
