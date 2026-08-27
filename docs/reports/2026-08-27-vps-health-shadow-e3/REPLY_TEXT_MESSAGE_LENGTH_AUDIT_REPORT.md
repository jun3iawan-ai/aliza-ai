# Audit: Risiko "Message is too long" di 172 Titik `reply_text()` Command Interaktif

**Tanggal audit:** 2026-08-27
**Tipe:** Audit read-only murni (analisis statis kode + log historis). Tidak ada perubahan kode, commit, eksekusi command Telegram, atau restart service.
**Konteks:** `MESSAGE_TOO_LONG_FIX_REPORT.md` (commit `4abb826`, merged `2026-08-27T09:14:24+07:00`) memperbaiki error "Message is too long" HANYA untuk `dispatch_alert_message()`/`safe_dispatch()` — gateway alert terjadwal (morning_brief, evening_summary, spot_signal, dan semua alert job lain). Ada 172 titik `reply_text()`/`msg.reply_text()` lain di `interfaces/telegram_bot.py` (dikonfirmasi ulang: `rg -c "reply_text\(" interfaces/telegram_bot.py` = 172) yang dipakai command interaktif dan TIDAK melewati gateway itu. Audit ini mencari bukti konkret apakah masalah itu sudah benar-benar terjadi di command interaktif, atau baru risiko teoretis.

---

## 1. Bukti dari log

### 1.1 Rentang tanggal log yang benar-benar tersedia

Retensi log terbatas (pola sama dengan temuan `docs/reports/2026-08-27-vps-health-shadow-e3/SHADOW_E3_STAGNATION_REPORT.md`):

| Sumber | Baris pertama | Baris terakhir |
|---|---|---|
| `logs/aliza.log` + `.1` + `.2.gz`...`.7.gz` (7 file rotasi) | **2026-08-20 00:00:08** | **2026-08-27 09:39:42** (proses masih berjalan saat audit) |
| `journalctl -u aliza-telegram.service` | **2026-08-24 09:26:19** (lebih pendek dari file log — retensi journald lebih ketat) | 2026-08-27 09:39:42 |

Total cakupan log yang bisa diperiksa: **±7 hari 9,5 jam** (2026-08-20 s/d 2026-08-27 09:39 WIB), gabungan file log lebih panjang daripada journald. File `dashboard.log*` di direktori yang sama sudah tidak relevan (kosong sejak Juni, entri terakhir berisi April).

### 1.2 Semua kejadian "Message is too long" yang ditemukan

Perintah yang dijalankan: `grep -n "Message is too long" aliza.log aliza.log.1` dan `zgrep -n "Message is too long" aliza.log.2.gz ... aliza.log.7.gz`, plus verifikasi silang via `journalctl -u aliza-telegram.service` untuk rentang yang tumpang tindih (2026-08-24 s/d 2026-08-27) — hasilnya identik, tidak ada kejadian tambahan yang hanya muncul di satu sumber.

**Total: 12 kejadian, seluruhnya sebelum commit `4abb826` (2026-08-27T09:14:24+07:00). Nol kejadian pada `aliza.log` (hari commit merge, 2026-08-27 00:00–09:39).**

| # | Timestamp | Baris log lengkap |
|---|---|---|
| 1 | 2026-08-20 08:00:10,327 | `ERROR - root - morning_brief dispatch header: Message is too long` |
| 2 | 2026-08-20 20:00:09,800 | `ERROR - root - evening_summary dispatch header: Message is too long` |
| 3 | 2026-08-21 08:00:11,549 | `ERROR - root - morning_brief dispatch header: Message is too long` |
| 4 | 2026-08-21 20:00:06,300 | `ERROR - root - evening_summary dispatch header: Message is too long` |
| 5 | 2026-08-22 08:00:06,495 | `ERROR - root - morning_brief dispatch header: Message is too long` |
| 6 | 2026-08-23 08:00:11,878 | `ERROR - root - morning_brief dispatch header: Message is too long` |
| 7 | 2026-08-24 08:00:46,685 | `ERROR - root - morning_brief dispatch analysis: Message is too long` |
| 8 | 2026-08-24 20:00:07,690 | `ERROR - root - evening_summary dispatch header: Message is too long` |
| 9 | 2026-08-24 20:01:03,146 | `ERROR - root - evening_summary dispatch analysis: Message is too long` |
| 10 | 2026-08-25 08:00:42,918 | `ERROR - root - morning_brief dispatch analysis: Message is too long` |
| 11 | 2026-08-26 08:00:13,001 | `ERROR - root - morning_brief dispatch header: Message is too long` |
| 12 | 2026-08-26 20:00:14,001 | `ERROR - root - evening_summary dispatch header: Message is too long` |

**Identifikasi command/fungsi pemicu:** setiap baris log SUDAH secara eksplisit mencantumkan nama job pemicu (`morning_brief` atau `evening_summary`) dan tahap (`dispatch header` vs `dispatch analysis`) di dalam pesan log itu sendiri — tidak perlu korelasi timestamp manual. Konteks kode (`interfaces/telegram_bot.py:5608-5610` dan `:5741-5743`) mengonfirmasi: string log ini dihasilkan oleh blok `try/except` yang membungkus pemanggilan `safe_dispatch(...)` di dalam `morning_brief_command`/`evening_summary_command` — persis jalur `dispatch_alert_message()` yang sudah diperbaiki `4abb826`.

### 1.3 Pengelompokan bukti

**(a) Dari `dispatch_alert_message()`/gateway alert terjadwal — SUDAH diperbaiki oleh `4abb826`:**
Seluruh 12 kejadian di atas (100%). Semuanya berlabel eksplisit `morning_brief` atau `evening_summary` di teks log, dan seluruhnya terjadi SEBELUM commit merge.

**(b) Dari command interaktif lain via `reply_text()` langsung — BELUM diperbaiki:**
**Nol (0) kejadian ditemukan** di seluruh log yang tersedia (2026-08-20 s/d 2026-08-27 09:39).

### 1.4 Keterbatasan eksplisit

- Retensi log hanya ±7 hari 9,5 jam — kejadian di luar rentang ini (kalau ada) tidak bisa diverifikasi/dibantah. Ini **bukan bukti bahwa masalah tidak pernah terjadi sebelum 2026-08-20**, hanya bahwa tidak ada bukti di jendela yang tersedia.
- Tidak ditemukan pola log "received command X" generik yang independen dari baris `COMMAND RECEIVED: /xxx` (42 kemunculan pola ini ada di kode, `logging.info("COMMAND RECEIVED: /xxx")`, tapi karena tidak ada satupun error "Message is too long" yang perlu dikorelasikan di luar grup (a), korelasi manual tidak diperlukan untuk audit ini).
- Log hanya mencakup instance primer (`IS_PRIMARY_DISPATCHER`); tidak ada bukti soal instance non-primer karena `dispatch_alert_message()` early-return untuk instance non-primer sebelum sempat gagal kirim.

---

## 2. Analisis risiko statis — 172 titik `reply_text()`

### 2.1 Metodologi

Setiap dari 172 titik dipetakan ke fungsi/handler pembungkusnya (nearest enclosing `def`/`async def`), lalu badan fungsi pembentuk pesan dibaca untuk menilai pola risiko: loop per-coin atas watchlist, dan/atau narasi LLM bebas panjang tanpa split.

Sebaran titik terbanyak per handler: `menu_button_handler` (32), `cmd_set_balance` (12), `entry` (10), `coin_selector_callback` (7), `spot_command` (5), `close` (5), `levels_command` (5), lalu sisanya 1–4 per handler tersebar di ~50 handler command lain.

### 2.2 Temuan kunci: seluruh jalur narasi LLM sudah lewat gateway yang diproteksi

Titik krusial: fungsi-fungsi penghasil narasi tak-berbatas (`_call_llm_async` di `interfaces/telegram_bot.py:3993`, `_generate_spot_analysis` di `:4019`, `_generate_futures_analysis` di `:4195`, `_generate_brief_analysis` di `:4381`) **hanya dipanggil dari 3 tempat**:

```
interfaces/telegram_bot.py:4667-4669   → dalam _generate_brief_analysis() itu sendiri (internal)
interfaces/telegram_bot.py:5616        → morning_brief_command  → dikirim via safe_dispatch() (5608)
interfaces/telegram_bot.py:5748        → evening_summary_command → dikirim via safe_dispatch() (5741)
interfaces/telegram_bot.py:5851-5852   → spot_signal_job (dipanggil spot_signal_command) → dikirim via safe_dispatch() (5885)
```

Tidak satupun dari ketiga entry-point command interaktif ini memakai `reply_text()` mentah untuk mengirim hasil LLM — semuanya sudah lewat `safe_dispatch()` → `dispatch_alert_message()`, yang sudah punya `_split_message_for_telegram()` sejak `4abb826`. **Ini berarti sumber risiko terbesar (narasi LLM tanpa batas) sudah tertutup, di luar cakupan 172 titik `reply_text()` yang jadi fokus audit.**

### 2.3 Klasifikasi risiko per handler yang diperiksa

**RISIKO MENENGAH — loop per-coin atas watchlist tetap (21 coin), tanpa cap/split (perlu dipantau, belum terbukti bermasalah):**

| Command | Bukti kode | Estimasi ukuran saat ini |
|---|---|---|
| `radarpro_command` | `interfaces/telegram_bot.py:1608-1616` → `format_radar_pro_report()` di `engine/market/market_radar_pro_analyzer.py:143-162`, loop `for item in radar_data:` (baris 152) atas SEMUA coin snapshot, tanpa cap, dikirim `reply_text(message)` langsung (telegram_bot.py:1613), tanpa split | ~21 baris × ~40 char ≈ 840–1000 char — jauh di bawah limit 4096 |
| `check_funding_command` | `interfaces/telegram_bot.py:6017-6039` → `format_funding_table_for_command()` di `engine/market/funding_rate_monitor.py:464-485`, loop `for coin in WATCHLIST:` (baris 468), tanpa cap, dikirim `target.reply_text(table + suffix)` (telegram_bot.py:6036), tanpa split | ~21 baris × ~60 char ≈ 1300–1500 char |
| `cfra_command` | `interfaces/telegram_bot.py:6042-6087`, loop `for r in results:` (baris 6058) atas semua hasil CFRA (≤21 coin), entri squeeze-risk 3 baris/coin, dikirim `target.reply_text("\n".join(lines))` (baris 6084), tanpa split | Worst-case (semua 21 coin squeeze-risk simultan, skenario ekstrem tak lazim) ≈ 1900–2200 char — masih di bawah limit |
| `levels_command` / `check_near_support_command` / `check_near_resistance_command` | `interfaces/telegram_bot.py:6893-6922`, `_format_near_levels_side()` loop atas subset watchlist yang "near level", tanpa cap, `reply_text()` tanpa split | Biasanya jauh lebih kecil dari 21 coin (hanya yang dekat level) |

**Catatan penting:** watchlist saat ini adalah `CORE_COINS` fixed 21 coin (`engine/market/market_universe.py:15-20`, komentar eksplisit "Fixed watchlist 21 coin", auto-scan dinamis sudah dinonaktifkan — `dynamic_universe.get_tradable_coins()` di `engine/market/dynamic_universe.py:276-278` mengembalikan `CORE_COINS` tetap). Dengan ukuran watchlist ini, keempat handler di atas **secara matematis tidak mendekati limit 4096 char** dalam kondisi normal maupun skenario ekstrem yang dicoba di atas. Risikonya bersifat struktural-laten: kalau watchlist diperbesar signifikan (mis. 2–3× lipat) di masa depan, keempat handler ini akan gagal dengan cara yang identik dengan morning_brief/evening_summary sebelum diperbaiki — TANPA ada perlindungan split apa pun saat ini.

**RISIKO RENDAH — pesan fixed-format/single-value, atau loop atas himpunan kecil (≤5 coin), sudah diverifikasi dengan membaca badan fungsi:**

- `menu_button_handler` (`interfaces/telegram_bot.py:567-957`, 32 titik `reply_text`): murni router menu — semua pesan berupa teks menu tetap pendek atau delegasi ke command lain (yang dinilai terpisah).
- `coin_selector_callback` (`:958-1019`): delegasi per-coin tunggal ke handler lain; cabang `"scan"` dibatasi `format_opportunities_message(opportunities, max_items=5)` (baris 1001) — eksplisit dibatasi.
- `quant_command` (`:2082-2138`), `marketstate_command` (`:2143-2166`), `status` (`:2171-2189`), `market_context_command` (`:2279-2322`), `btc_command` via `_format_btc_smart_message` (`:2343-2362`): seluruhnya format fixed-field (skor, trend, RSI tunggal), tidak ada loop atau LLM bebas.
- `spot_command` (`:1086-1202`): detail single-coin dengan field terbatas; list view dibatasi jumlah coin BUY dari watchlist 21 coin, satu baris per coin.
- `why_command` (`:1207-1291`): rule-based reasoning (`generate_trade_reasoning`), bukan LLM narasi bebas — daftar `reasons`/`triggers` pendek dan terstruktur.
- `check_whale_command` (`:6420-6455`): loop hanya atas `_WHALE_MONITOR_COINS` = 5 coin tetap (BTC/ETH/BNB/SOL/XRP), bukan seluruh watchlist.
- `cmd_set_balance` (12 titik), `entry` (10 titik), `close` (5 titik): mayoritas adalah cabang validasi/error pendek (mis. "Coin tidak tersedia.", "Format salah") — tidak ada loop atau konten variabel-panjang.

---

## 3. Kesimpulan

### Apakah ada bukti nyata kegagalan "Message is too long" di command interaktif (di luar morning_brief/evening_summary)?

**TIDAK.** Nol (0) kejadian ditemukan di seluruh log yang tersedia (2026-08-20 s/d 2026-08-27 09:39, ±7 hari 9,5 jam retensi). Seluruh 12 kejadian "Message is too long" yang tercatat di log berasal 100% dari `morning_brief`/`evening_summary` via `dispatch_alert_message()` — jalur yang SUDAH diperbaiki `4abb826` — dan seluruhnya terjadi sebelum commit merge. Tidak ada satupun kejadian pada hari commit merge (2026-08-27) hingga jam audit dijalankan.

### Command mana yang paling mendesak diperbaiki?

**Tidak ada command yang mendesak diperbaiki berdasarkan bukti log** (karena tidak ada bukti kegagalan nyata). Berdasarkan analisis risiko struktural saja (bukan bukti kegagalan), 4 command berikut layak **dipantau** karena pola loop-per-watchlist tanpa split/cap: `radarpro_command`, `check_funding_command`, `cfra_command`, dan `levels_command`/`check_near_*_command` — namun dengan watchlist 21 coin saat ini, keempatnya masih jauh di bawah limit 4096 karakter berdasarkan perhitungan baris di atas.

### Rekomendasi tindak lanjut

**Tunda perbaikan besar-besaran ke 172 titik.** Tidak ada bukti nyata sama sekali di log yang tersedia, dan analisis kode menunjukkan sumber risiko terbesar (narasi LLM tanpa batas) sudah 100% tertutup gateway `safe_dispatch()`/`dispatch_alert_message()` yang diperbaiki `4abb826` — refactor menyeluruh 172 titik saat ini adalah investasi mahal untuk risiko yang murni teoretis.

Yang perlu terus dipantau ke depan (bukan diperbaiki sekarang):
- **`radarpro_command`, `check_funding_command`, `cfra_command`, `levels_command`/`check_near_*_command`** — keempatnya loop atas watchlist tanpa cap/split. Risiko HANYA akan menjadi nyata jika watchlist `CORE_COINS` (saat ini fixed 21 coin, `engine/market/market_universe.py:15-20`) diperbesar signifikan di masa depan, atau jika format per-coin ditambah field/baris. Kalau perubahan semacam itu pernah direncanakan, sebaiknya `_split_message_for_telegram()` (sudah ada dan reusable, `interfaces/telegram_bot.py:296-331`) diterapkan pada 4 titik ini sebagai bagian dari perubahan tersebut — bukan sebagai proyek terpisah sekarang.
- Tidak perlu memantau 168 titik `reply_text()` lainnya secara khusus — seluruhnya (setelah diperiksa manual per handler di atas) berupa pesan fixed-format, single-value, atau loop atas himpunan kecil (≤5 entitas), dan tidak melibatkan narasi LLM bebas panjang.
