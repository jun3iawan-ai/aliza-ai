# Audit Menyeluruh Menu & Command Telegram

Tanggal audit: 5 Agustus 2026  
Target yang diaudit: `main@83fee99075c42df57cb8b6a03590b4ffe8eb9450`  
Metode: pembacaan kode statis saja; tidak ada command bot, perubahan kode/config, commit, atau restart.

## Ringkasan eksekutif

Struktur saat ini fungsional tetapi belum terorganisasi untuk pengguna awam. Ada **45 slash command terdaftar**, hanya **13** yang muncul di menu slash Telegram (`set_my_commands()`), dan navigasi reply keyboard aktif tidak memuat beberapa fitur penting. Temuan paling kuat:

- `/levels` **bukan duplikat persis** tombol Near Support/Near Resistance. Ia memberi satu laporan gabungan dari helper yang lebih baru, tetapi dua tombol Sistem memakai dua loop lama yang berbeda. Ketiganya sebaiknya disatukan ke satu tombol **📍 Levels** di menu Market Monitor/Alert, bukan di Sistem.
- Tombol **💥 Big Move** dan checker otomatis memakai helper persen yang sama, namun tombol hanya melakukan pembacaan on-demand—bukan memanggil checker atau mengirim alert. Pada `main` helper masih fallback ke data 24h karena snapshot hanya menulis field 24h. Jika branch `fix/big-move-real-1h-change` digabung, perbaikan helper/snapshot akan berlaku bagi keduanya.
- Tombol **🔵 RSI Extreme** juga merupakan pembacaan on-demand, terpisah dari checker yang terjadwal dan memakai notification governor. Hasilnya dapat tidak identik karena path manual tidak melakukan blacklist/freshness/cooldown yang sama.
- Submenu **🔔 Alert & Monitor** ada di kode tetapi tak memiliki tombol dari menu utama; tiga fiturnya praktis tersembunyi. Sebaliknya Sistem memuat empat fitur market-monitor (levels, RSI, big move) yang bukan fungsi administrasi.
- `/performance`, `/alert_stats`, `/health`, `/weekly_winrate`, dan `/shadow_promotion_check` tidak ada pada menu slash maupun keyboard aktif. Sebagian hanya disebut `/help`; `/health`, `/weekly_winrate`, dan `/shadow_promotion_check` tidak disebut bahkan di sana.

## 1. Inventaris lengkap command terdaftar

Semua baris di bawah berasal dari registrasi `CommandHandler` di `interfaces/telegram_bot.py:7378-7424`. Kolom **Slash** berarti tercantum di `set_my_commands()` (`:7322-7338`). **Keyboard** hanya dihitung bila ada tombol aktif yang akhirnya memanggil handler yang sama; tombol navigasi yang hanya namanya mirip diberi catatan tersendiri.

| Command | Handler | Baris daftar | Slash | Keyboard aktif / status UI |
|---|---|---:|---|---|
| `/start` | `start` | 7378 | Ya (`:7324`) | Tidak; justru membangun menu utama (`:334-357`). |
| `/help` | `help_command` | 7379 | Ya (`:7325`) | Tidak; dokumentasi manual (`:854-908`). |
| `/why` | `why_command` | 7380 | Tidak | Ya, **🔎 Penjelasan AI** → selector `why` → handler (`:611-617`, `:842-844`). |
| `/spot` | `spot_command` | 7381 | Tidak | Ya, **🟢 Peluang Spot** (`:556-558`) dan selector Analisis Coin (`:559-565`, `:845-847`). |
| `/btc` | `btc_command` | 7382 | Tidak | Tidak; hanya terdokumentasi di `/help` (`:891-892`). |
| `/market` | `market` | 7383 | Ya (`:7326`) | Tidak secara langsung: **📊 Market** hanya membuka submenu (`:485-495`); route legacy **📊 Market Coin** tidak ada pada keyboard aktif (`:700-704`). |
| `/radar` | `radar` | 7385 | Ya (`:7327`) | Ya, **📡 Radar Market** (`:503-505`). |
| `/radarpro` | `radarpro_command` | 7386 | Tidak | Ya, **📡 Radar Pro** (`:506-508`). |
| `/setfutures` | `setfutures` | 7387 | Ya (`:7328`) | Tidak; **🔎 Scan Futures** memakai scanner selector, bukan handler ini (`:542-548`, `:827-841`). |
| `/entry` | `entry` | 7388 | Ya (`:7329`) | Ya, **📈 Buka Posisi** → selector `entry` → handler (`:566-569`, `:821-824`). |
| `/set_balance` | `cmd_set_balance` | 7389 | Ya (`:7332`) | Tidak; hanya slash/help (`:877-881`). |
| `/balance` | `cmd_get_balance` | 7390 | Ya (`:7333`) | Tidak; hanya slash/help (`:877-881`). |
| `/close` | `close` | 7392 | Ya (`:7330`) | Ya, **📉 Tutup Posisi** → selector `close` (`:570-578`, `:824-826`). |
| `/performance` | `performance_command` | 7393 | Tidak | Tidak aktif; hanya route teks legacy **📊 Performa Trading** (`:621-623`) dan `/help` (`:893-895`). |
| `/portfolio` | `portfolio` | 7394 | Ya (`:7331`) | Ya, **📂 Posisi Aktif** (`:539-541`). |
| `/predict` | `predict` | 7395 | Tidak | Ya, **🔮 Prediksi Market** (`:605-607`). |
| `/quant` | `quant_command` | 7396 | Tidak | Ya, **📊 Skor Quant** (`:608-610`). |
| `/marketstate` | `marketstate_command` | 7397 | Tidak | Ya, **🌐 Kondisi Global** (`:509-511`). |
| `/status` | `status` | 7398 | Ya (`:7334`) | Ya, **⚙️ Status Sistem** (`:678-680`). |
| `/alert_stats` | `alert_stats_command` | 7399 | Tidak | Tidak; hanya `/help` (`:903-904`). |
| `/levels` | `levels_command` | 7400 | Ya (`:7335`) | Tidak; hanya slash/help (`:905-906`, implementasi `:6473-6499`). |
| `/testalert` | `testalert` | 7401 | Tidak | Ya, **🧪 Test Alert** (`:681-683`). |
| `/marketdebug` | `marketdebug` | 7402 | Tidak | Ya, **🛠 Debug Market** (`:684-686`). |
| `/market_context` | `market_context_command` | 7403 | Tidak | Ya, **🎯 Konteks Market** (`:602-604`). |
| `/snapshot` | `snapshot_command` | 7404 | Tidak | Hanya di submenu Alert & Monitor yang tidak bisa dibuka dari keyboard aktif (`:424-433`, `:652-668`). |
| `/health` | `health_command` | 7405 | Tidak | Orphan: tidak ada slash, keyboard, atau `/help`; handler `:2048-2084`. |
| `/morning_brief` | `morning_brief_command` | 7406 | Tidak | Ya, **🌅 Ringkasan Pagi** (`:497-499`). |
| `/evening_summary` | `evening_summary_command` | 7407 | Tidak | Ya, **🌙 Ringkasan Malam** (`:500-502`). |
| `/spot_signal` | `spot_signal_command` | 7408 | Tidak | Ya, **📈 Saran Spot** (`:624-626`). |
| `/check_breakout` | `check_breakout_command` | 7409 | Tidak | Hanya submenu Alert & Monitor tersembunyi (`:660-662`). |
| `/check_volume_spike` | `check_volume_spike_command` | 7410 | Tidak | Hanya submenu Alert & Monitor tersembunyi (`:663-665`). |
| `/check_funding` | `check_funding_command` | 7411 | Tidak | Ya, **🔄 Funding Rate & OI** (`:639-641`). |
| `/cfra` | `cfra_command` | 7412 | Tidak | Ya, **📊 CFRA** (`:642-644`). |
| `/check_macro` | `check_macro_command` | 7413 | Tidak | Ya, **🌐 Data Makro** (`:636-638`). |
| `/check_calendar` | `check_calendar_command` | 7414 | Tidak | Ya, **📅 Kalender Ekonomi** (`:645-647`). |
| `/check_whale` | `check_whale_command` | 7415 | Tidak | Ya, **🐋 Monitor Whale** (`:648-650`). |
| `/check_near_support` | `check_near_support_command` | 7416 | Tidak | Ya, **📉 Near Support** (`:687-689`). |
| `/check_near_resistance` | `check_near_resistance_command` | 7417 | Tidak | Ya, **📈 Near Resistance** (`:690-692`). |
| `/check_rsi_extreme` | `check_rsi_extreme_command` | 7418 | Tidak | Ya, **🔵 RSI Extreme** (`:693-695`). |
| `/check_big_move` | `check_big_move_command` | 7419 | Tidak | Ya, **💥 Big Move** (`:696-698`). |
| `/signal_stats` | `signal_stats_command` | 7420 | Tidak | Ya, **📊 Performa Sinyal** (`:618-620`). |
| `/stats` | `signal_stats_command` | 7421 | Tidak | Alias manual dari `/signal_stats`; tidak ada tombol berbeda. |
| `/shadow_stats` | `shadow_stats_command` | 7422 | Ya (`:7336`) | Tidak; handler sendiri memisahkan source `shadow_e3` (`:6799-6817`). |
| `/weekly_winrate` | `weekly_winrate_summary_command` | 7423 | Tidak | Orphan manual; job otomatis Senin 08:10 WIB (`:6973-6975`, `:7475-7483`). |
| `/shadow_promotion_check` | `shadow_promotion_check_command` | 7424 | Tidak | Orphan manual; evaluasi promosi shadow read-only (`:6978-6995`). |

## 2. Inventaris keyboard, callback, dan hierarki aktual

### Reply keyboard aktif

Semua keyboard di bawah adalah `ReplyKeyboardMarkup`; definisinya berurutan di `telegram_bot.py:323-447`. Tombol **⬅ Kembali** pada semua submenu kembali ke menu utama (`:477-483`).

```text
Menu Utama (:323-331)
├─ 📊 Market (:363-373)
│  ├─ 🌅 Ringkasan Pagi → morning_brief_command (:497-499)
│  ├─ 🌙 Ringkasan Malam → evening_summary_command (:500-502)
│  ├─ 📡 Radar Market → radar (:503-505)
│  ├─ 📡 Radar Pro → radarpro_command (:506-508)
│  └─ 🌐 Kondisi Global → marketstate_command (:509-511)
├─ 💹 Trading (:384-395)
│  ├─ 📈 Saran Spot → spot_signal_command (:624-626)
│  ├─ 🟢 Peluang Spot → spot_command (:556-558)
│  ├─ 🔎 Scan Futures → inline selector scan (:542-548)
│  ├─ 🔍 Analisis Coin → inline selector spot (:559-565)
│  ├─ 📂 Posisi Aktif → portfolio (:539-541)
│  ├─ 📈 Buka Posisi → inline selector entry (:566-569)
│  └─ 📉 Tutup Posisi → inline selector close (:570-578)
├─ 📈 Analisis (:398-408)
│  ├─ 🎯 Konteks Market → market_context_command (:602-604)
│  ├─ 🔮 Prediksi Market → predict (:605-607)
│  ├─ 📊 Skor Quant → quant_command (:608-610)
│  ├─ 🔎 Penjelasan AI → inline selector why (:611-617)
│  └─ 📊 Performa Sinyal → signal_stats_command (:618-620)
├─ 🌍 Makro & Sentimen (:411-421)
│  ├─ 🌐 Data Makro → check_macro_command (:636-638)
│  ├─ 🔄 Funding Rate & OI → check_funding_command (:639-641)
│  ├─ 📊 CFRA → cfra_command (:642-644)
│  ├─ 📅 Kalender Ekonomi → check_calendar_command (:645-647)
│  └─ 🐋 Monitor Whale → check_whale_command (:648-650)
└─ ⚙️ Sistem (:436-447)
   ├─ ⚙️ Status Sistem → status (:678-680)
   ├─ 🧪 Test Alert → testalert (:681-683)
   ├─ 📉 Near Support → check_near_support_command (:687-689)
   ├─ 📈 Near Resistance → check_near_resistance_command (:690-692)
   ├─ 🔵 RSI Extreme → check_rsi_extreme_command (:693-695)
   ├─ 💥 Big Move → check_big_move_command (:696-698)
   └─ 🛠 Debug Market → marketdebug (:684-686)
```

### Submenu yang ada tetapi tidak terjangkau dari menu utama

`_alert_monitor_submenu_keyboard()` mendefinisikan **🚨 Cek Breakout**, **📊 Cek Volume Spike**, dan **📌 Snapshot Market** (`telegram_bot.py:424-433`), dan router memang dapat membuka/menjalankannya (`:652-668`). Namun _main menu_ hanya memuat lima tombol dan tidak ada **🔔 Alert & Monitor** (`:323-331`). Ini bukan bug handler, tetapi dead-end UI: pengguna hanya bisa sampai ke sana jika masih menyimpan keyboard lama atau mengetik teks tersebut sendiri.

### Inline keyboard

Satu builder dinamis membuat `InlineKeyboardMarkup` dua kolom dengan `callback_data="{prefix}_{coin}"` (`telegram_bot.py:450-461`). `CallbackQueryHandler(coin_selector_callback)` didaftarkan pada `:7384`; callback memetakan `market`, `entry`, `close`, `scan`, `why`, dan `spot` ke aksi persisnya (`:815-847`). Ini bukan enam menu berbeda, melainkan satu pola selector yang dipakai dari tombol-tombol pada diagram di atas.

### Route legacy yang bukan bagian keyboard aktif

Router masih menerima label cache lama seperti **🟢 Spot Trading**, **📊 Futures Trading**, **🎯 Sinyal & Trading** (`telegram_bot.py:525-537`), **📊 Market Coin**, **📡 Radar**, **🌐 Market State**, **🎯 Trading**, dan sejumlah label Inggris (`:700-793`). Mereka tidak didefinisikan di keyboard aktif `:323-447`; pertahankan sebagai kompatibilitas sementara, tetapi jangan diperlakukan sebagai struktur menu aktual.

## 3. Verifikasi tumpang tindih / fungsi serupa

| Pasangan | Bukti dan putusan |
|---|---|
| `/levels` vs Near Support / Near Resistance | **Mirip, bukan fungsi sama.** `/levels` memanggil `get_coins_near_levels(tolerance)` dan menampilkan kedua sisi (`telegram_bot.py:6473-6499`). Helper mengabaikan blacklist, data stale, level yang terlalu berdekatan, dan jarak <0,05% (`:6150-6201`). Tombol Sistem memanggil dua loop tersendiri, dengan batas hard-coded ≤1%, tanpa filter blacklist/freshness/helper tersebut (`:6502-6533`, `:6536-6567`). Jadi ada duplikasi logika dan hasil bisa berbeda. |
| Tombol Big Move vs `big_move_checker()` | **Berbagi helper, bukan fungsi checker yang sama.** On-demand memanggil `_snapshot_big_move_pct()` dan threshold 3% (`:6609-6658`); checker terjadwal juga memakai helper/threshold itu (`:6356-6381`) lalu menerapkan freshness, cooldown per coin+arah, dedup, dan `queue_alert` (`:6385-6424`). Tombol tidak mengantrikan alert/cooldown. Pada `main`, helper mencoba field 1h lalu fallback 24h (`:6098-6110`), sedangkan snapshot hanya menulis `price_change_*_24h` (`engine/market/market_snapshot_engine.py:153-200`), sehingga keduanya masih fallback 24h. Branch fix yang belum digabung akan memperbaiki field yang dibaca bersama ini. |
| Tombol RSI Extreme vs `rsi_extreme_checker()` | **Mirip, tidak sama.** Tombol hanya membagi snapshot menjadi RSI <30 dan >75 (`telegram_bot.py:6570-6606`). Checker terjadwal memakai batas sama namun juga menolak blacklist/stale, menjalankan cooldown+dedup `notification_governor`, dan mengantrikan alert (`:6294-6353`); dijadwalkan setiap 300 detik (`:7446-7452`). Jadi tombol adalah query on-demand, bukan trigger checker. |
| `/signal_stats`/`/stats` vs `/shadow_stats` | **Terpisah dengan jelas.** `/stats` hanya alias handler `/signal_stats` (`:7420-7422`). Default `get_signal_stats()` adalah `deterministic` dan secara eksplisit mengecualikan shadow (`engine/trading/signal_tracker.py:576-584`); `/shadow_stats` melewatkan `source="shadow_e3"` (`telegram_bot.py:6799-6814`). Rekomendasi: pertahankan terpisah, namun tampilkan berdekatan sebagai “Produksi” dan “Riset”. |
| `/signal_stats` vs `/performance` | **Overlap data produksi, metrik berbeda.** `/signal_stats` menunjukkan total/open/expired, average P&L, best/worst, dan per coin (`telegram_bot.py:6740-6792`). `/performance` membaca closed deterministic history (`engine/learning/trade_history_tracker.py:98-120`), lalu menghitung average RR dan profit factor (`telegram_bot.py:1632-1656`, `engine/analytics/performance_analyzer.py:11-75`). Bukan duplikat, tetapi “Performa Sinyal” berpotensi membuat user menduga hasilnya sama. |
| `/weekly_winrate` vs `/signal_stats` | **Terpisah, tetapi ringkasan agregat berulang.** Weekly menampilkan blok produksi dan shadow, disclaimer jumlah sampel, Avg RR/PF, catatan sinyal baru, dan circuit breaker (`telegram_bot.py:6839-6942`); `/signal_stats` adalah drill-down produksi per coin. Weekly juga dikirim otomatis tiap Senin 08:10 WIB (`:7475-7483`). Pertahankan keduanya, ubah label agar perbedaan horizon jelas. |
| `/shadow_stats` vs `/shadow_promotion_check` | **Terpisah.** Yang pertama statistik outcome shadow (`:6799-6817`); yang kedua mengevaluasi kriteria promosi dan eksplisit read-only (`:6978-6995`). Tidak digabungkan agar keputusan promosi tidak tersamar sebagai statistik biasa. |
| `/marketstate`, `/market_context`, `/quant`, `/predict` | **Berdekatan tetapi berbeda layer analisis.** Router memisahkan ke empat handler (`:602-610`); mereka berturut-turut lingkungan market (`:1758-1781`), komponen score (`:1894` dst.), score quant (`:1697-1753`), dan probabilitas prediksi (`:1664` dst.). Pengelompokan di submenu Analisis sudah tepat; perlu deskripsi yang lebih konsisten. |

## 4. Item salah tempat dan inkonsistensi

1. **Sistem tercampur dengan Market Monitor.** Status, Test Alert, dan Debug memang operasional; Near levels, RSI, dan Big Move adalah observasi market (`telegram_bot.py:436-447`, `:687-698`). Pindahkan tiga terakhir ke submenu **Monitor Pasar / Alert**.
2. **Alert & Monitor tidak dapat dinavigasi.** Definisi ada tetapi root trigger tidak ada (`:323-331`, `:424-433`, `:652-668`). Tambahkan ke menu utama atau pindahkan seluruh isinya ke Market.
3. **Levels tidak terlihat di keyboard.** Ia sudah ada di slash menu dan `/help` (`:7324-7337`, `:854-908`) tetapi bukan reply keyboard. Ini akar kebingungan `/levels` vs Sistem.
4. **Dua implementasi near-level.** Selain penamaan tidak konsisten (“Near Support”, “Near Resistance”, “Levels”), validasi hasilnya berbeda. Satu helper bersama akan menghindari angka saling bertentangan (`:6150-6201`, `:6502-6567`).
5. **Fitur observability dan riset sulit ditemukan.** `/alert_stats` hanya help; `/health`, `/weekly_winrate`, `/shadow_promotion_check` tidak ada UI maupun help. Cek promosi shadow bersifat admin/research, jadi tidak perlu menu utama, tetapi perlu submenu Sistem/Riset atau dokumentasi admin.
6. **Performance tidak memiliki jalur aktif.** “📊 Performa Trading” hanya route legacy (`:621-623`) dan `/performance` tidak muncul di menu slash, sementara Signal Stats muncul sebagai “Performa Sinyal”. Ini mudah tertukar.

## 5. Rekomendasi tanpa implementasi

### Jawaban inti: `/levels` vs Sistem

**Satukan, jangan hapus kemampuan.** Jadikan `/levels` dan satu tombol **📍 Levels (S/R)** sebagai UI kanonik yang memakai `get_coins_near_levels()`. Tombol terpisah Near Support/Resistance tidak perlu dipertahankan sebagai dua loop independen; bila filter sisi masih berguna, jadikan pilihan tampilan dari helper yang sama. Tempat yang tepat adalah **📊 Market → 🔔 Monitor Pasar**, bukan ⚙️ Sistem.

Alasan: `/levels` memberi dua sisi dalam satu laporan dan mendukung tolerance argumen (`telegram_bot.py:6482-6496`), sementara helper mengandung guard kualitas snapshot yang tidak dimiliki dua loop lama (`:6170-6201`). Ini menghilangkan duplikasi dan konsistensi hasil tanpa mengurangi informasi.

### Rekomendasi overlap lain

- Pertahankan **Big Move** dan **RSI Extreme** sebagai query manual, tetapi beri label **“Cek Big Move (snapshot)”** dan **“Cek RSI Ekstrem (snapshot)”** untuk membedakannya dari push otomatis. Setelah branch 1h digabung, keduanya otomatis menggunakan data 1h karena helper bersama—tidak perlu fitur duplikat.
- Pertahankan `/signal_stats`, `/performance`, `/shadow_stats`, dan `/weekly_winrate`, tetapi ubah label: **Akurasi Sinyal (produksi)**, **Kinerja Trade (RR/PF)**, **Riset Shadow E3**, dan **Ringkasan Mingguan**. Letakkan tiga pertama dalam Analisis/Performance; promotion check di Riset/Admin.
- Jangan jadikan `/stats` menu terpisah: dokumentasikan sebagai alias kompatibilitas saja.
- Hapus secara bertahap route label legacy sesudah periode kompatibilitas dan telemetry penggunaan; saat ini banyak jalur “menu lama” yang memperbesar mental model tanpa memberi UI aktual (`telegram_bot.py:525-537`, `:700-793`).

### Struktur menu yang disarankan

```text
📊 Market
├─ Ringkasan Pagi / Ringkasan Malam / Radar / Radar Pro / Kondisi Global
└─ 🔔 Monitor Pasar
   ├─ 📍 Levels (S/R)                 → /levels, satu helper
   ├─ 💥 Cek Big Move (snapshot)      → /check_big_move
   ├─ 🔵 Cek RSI Ekstrem (snapshot)   → /check_rsi_extreme
   ├─ 🚨 Cek Breakout
   ├─ 📊 Cek Volume Spike
   └─ 📌 Snapshot Market

💹 Trading
└─ [struktur sekarang; tambahkan Performance Trade bila tetap dipakai]

📈 Analisis
├─ Konteks / Prediksi / Quant / Penjelasan AI
└─ 📊 Performance
   ├─ Akurasi Sinyal (produksi)
   ├─ Kinerja Trade (RR/PF)
   ├─ Ringkasan Mingguan
   └─ Riset Shadow E3

🌍 Makro & Sentimen
└─ [struktur sekarang]

⚙️ Sistem
├─ Status Sistem / Health / Alert Stats
├─ Test Alert / Debug Market
└─ Admin Riset: Shadow Promotion Check
```

Tambahkan ke `set_my_commands()` minimal command user-facing yang saat ini orphan/tersembunyi: `performance`, `alert_stats`, `snapshot`, `health`, `weekly_winrate`, serta `shadow_promotion_check` bila memang boleh diakses pengguna biasa. Command teknis `check_*` dapat tetap disembunyikan jika keyboard kanonik tersedia; jangan mendaftarkan semua agar menu slash tidak kembali penuh.

## Batas kepastian

Audit ini memverifikasi routing dan pemanggilan fungsi dari kode statis. Respons aktual provider/API, tampilan keyboard yang masih dicache oleh client Telegram, dan apakah semua handler sukses pada data live **BELUM DAPAT DIPASTIKAN** tanpa menjalankan bot secara interaktif. Temuan “submenu tak terjangkau” didasarkan pada tidak adanya label `🔔 Alert & Monitor` di `_main_menu_keyboard()` dan tidak adanya route lain yang membangun keyboard tersebut, bukan pada observasi UI live.
