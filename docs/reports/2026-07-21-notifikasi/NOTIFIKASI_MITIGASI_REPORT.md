# Laporan Mitigasi Spam Notifikasi/Alert Telegram

Branch: `fix/telegram-notification-noise` (dari `main` terbaru — sudah termasuk seluruh merge Fase 1–1d, 2, 3, 4; `git status` bersih sebelum mulai kecuali `AlizaAI-Crypto/01-hasil-audit-codex/FASE1C_VERIFIKASI_REPORT.md` yang untracked dan tidak disentuh, dan branch `fix/deploy-script` yang punya 1 commit belum di-merge — dibiarkan terpisah, tidak digabung ke branch ini).

Tanggal kerja: 2026-07-21.

---

## Diagnosis

Insiden yang dilaporkan user: 57 pesan Telegram dalam 12:00–15:38 WIB (21 Juli 2026), dengan dua ledakan >19 pesan dalam <1 menit (12:48:07–12:48:37 dan 14:08:23–14:08:37).

### Akar masalah utama: restart proses yang sering + cooldown in-memory

Bukti dari `logs/aliza.log` dan `journalctl -u aliza-telegram`:

```
Jul 21 12:46:50 systemd[1]: Stopping AlizaAI Telegram Bot...
Jul 21 12:47:05 systemd[1]: aliza-telegram.service: State 'stop-sigterm' timed out. Killing.
Jul 21 12:47:05 systemd[1]: aliza-telegram.service: Main process exited, code=killed, status=9/KILL
Jul 21 12:47:05 systemd[1]: Started AlizaAI Telegram Bot.
```

`aliza-telegram.service` (`Restart=always`, `TimeoutStopSec=15`) di-restart **7 kali** pada tanggal ini (07:40, 09:12, 10:10, 10:48, 12:46→12:47, 14:07→14:08, 15:43 WIB) — dikonfirmasi lewat `sudo[...]: session opened for user root(uid=0) by (uid=1000)` tepat sebelum tiap `Stopping AlizaAI Telegram Bot...`, jadi ini restart manual (`sudo systemctl restart`), kemungkinan besar dari deploy/testing aktif Fase 1–4 pada hari yang sama, **bukan** crash-loop. Shutdown graceful sering melebihi `TimeoutStopSec=15` sehingga systemd men-SIGKILL proses (di luar cakupan task ini — infra/deploy, sudah ada branch `fix/deploy-script` & `fix/graceful-shutdown` terpisah untuk ini; dicatat sebagai konteks, tidak diubah di sini).

**Setiap checker (`near_support_checker`, `near_resistance_checker`, `rsi_extreme_checker`, `big_move_checker`, `whale_alert_job`, plus `_last_alert_ts` internal di `volume_spike_detector.py`, `breakout_detector.py`, `funding_rate_monitor.py`) menyimpan cooldown-nya di `dict` module-level murni di memori** (`interfaces/telegram_bot.py:200-213` sebelum perbaikan). Restart proses mengosongkan dict ini. APScheduler menjadwalkan tiap checker jalan pertama kali `first in Ns` detik setelah start (`near_support`=10s, `near_resistance`=15s, `rsi`=20s, `big_move`=25s, `breakout`=30s, `volume_spike`=45s, `funding`=60s, `whale`=120s) — jadi ~7 checker berbeda semuanya menembak dalam ~60 detik pertama setelah tiap restart, masing-masing menganggap **semua** coin yang sedang dekat resistance/support/RSI ekstrem sebagai "belum pernah dialert", karena cooldown-nya baru saja di-reset ke kosong. Log 12:48:08–12:48:23 dan 14:08:24–14:08:39 menunjukkan persis pola ini: `near_resistance_checker` menembak 9-10 alert dalam ~3.5 detik, lalu `big_move_checker` 8-10 alert lagi ~10 detik kemudian, lalu `breakout_checker` 1 lagi — semua langsung berurutan tanpa jeda karena tidak ada throttle lintas-checker. Ini menjelaskan **kedua** temuan #1 dan #2 di prompt sekaligus: dokumentasi cooldown 4 jam benar secara logika (per `(coin, condition)`, sudah scoped dengan benar — bukan bug granularitas), tapi tidak pernah bertahan lebih dari satu siklus restart.

**Koreksi terhadap dugaan di prompt (item 2):** `big_move_checker` **bukan** tanpa cooldown. Kode (`interfaces/telegram_bot.py`, sebelum perbaikan) memanggil helper cooldown+dedup yang sama (`_snapshot_alert_allowed`, 4 jam) yang dipakai near_support/near_resistance/rsi. Sitasi `03-logika-sinyal.md` baris 212 di prompt salah baris — baris 212 dokumen itu membahas near_support/resistance, bukan big_move; baris 214 (soal big_move) tidak menyebut "tanpa cooldown". Root cause riil untuk big_move: (a) cooldown-nya berbagi dict in-memory yang sama dengan checker lain → kena bug restart yang sama, dan (b) key cooldown-nya `(coin, "big_move")` **tidak** dipisah per arah naik/turun sehingga alert naik & turun untuk coin yang sama saling menekan satu sama lain selama 4 jam — bukan penyebab spam, tapi gap correctness yang nyata. Perbaikan tetap mengikuti spesifikasi item 2 (cooldown khusus `BIG_MOVE_COOLDOWN_SEC`, per-arah, persisted) karena itu tujuan yang benar terlepas dari sitasi yang salah.

### Kasus OM (BIG MOVE identik 80 menit): bukan bug cache aplikasi

Investigasi menyeluruh (`engine/market/market_snapshot_engine.py:153-357`, `engine/market/market_analyzer.py:269-494`) mengonfirmasi:
- `price_change_1h` **tidak pernah ditulis di mana pun** di codebase — `_snapshot_big_move_pct()` (`telegram_bot.py`) selalu fallback ke field 24h dari `_enrich_collected_with_binance_24h()`, yang melakukan **fetch HTTP live ke Binance tiap siklus snapshot (~60s)**, bukan baca dari cache.
- Tidak ada cache disk atau in-memory yang bisa bertahan lintas restart proses — semua cache yang ada (`_last_known_price`, `_klines_cache`, `market_cache.CACHE`, dict `market_snapshot`) adalah objek module-level murni, dan restart antara pembacaan 12:48 dan 14:08 (proses berbeda) menghapus semuanya.
- Kesimpulan: angka OM yang identik ($0.0669, -5.11%) paling mungkin mencerminkan **kondisi pasar OM yang genuinely flat/thin di Binance** selama 80 menit itu — didukung warning berulang `funding_rate_monitor: openInterest HTTP 400 OMUSDT` yang menunjukkan OM punya keanehan API/likuiditas di Binance Futures saat itu (walau ini modul terpisah, tidak terhubung ke pipeline harga).

**Namun ditemukan bug nyata yang terkait**: guard freshness 30-menit di `big_move_checker` (`interfaces/telegram_bot.py`, kode lama baris 6328-6339) **tidak pernah benar-benar berjalan, untuk coin apa pun**. `market_analyzer.py` menyimpan `"timestamp": time.time()` (float epoch), tapi guard lama mengecek `hasattr(coin_ts, "timestamp")` (selalu `False` untuk float) lalu jatuh ke `datetime.fromisoformat(str(coin_ts))` yang selalu `ValueError` pada string epoch — dan exception itu ditelan diam-diam oleh `except Exception: pass`. Jadi walau bukan penyebab langsung insiden OM, ini adalah persis kelas bug yang diminta item 3 untuk diperbaiki, dan sekarang sudah ada bukti konkretnya.

### Temuan lain per item

- **Item 6 (volume spike)**: dikonfirmasi persis seperti dugaan prompt. `volume_spike_detector.py:check_volume_spike()` trigger `>2x` dengan cooldown 4 jam sendiri; `telegram_bot.py:volume_spike_job` menambah gate kedua `>=4x` + cooldown 8 jam **terpisah**; `/check_volume_spike` (command manual) bahkan mem-bypass gate kedua itu sepenuhnya. Tiga perilaku berbeda untuk satu sinyal.
- **Item 7 (funding ganda)**: `crypto_intelligence.py:analyze_funding()` (ambang ±5% desimal, hampir mustahil tercapai) **dikonfirmasi masih dipanggil**, tapi hanya dari `market_radar.py` (jalur tampilan `/radar`), **tidak pernah** diimpor ke `interfaces/telegram_bot.py` dan tidak pernah mencapai jalur dispatch Telegram. Jadi ini bukan dead code, tapi juga **bukan** sumber duplikasi alert — tidak ada tumpang-tindih nyata dengan `funding_rate_monitor.py:check_funding_extremes()` (sumber tunggal yang benar untuk alert funding). Tidak ada perubahan dibuat di `analyze_funding()`; dicatat sebagai temuan sesuai instruksi prompt untuk kasus ini.
- **Scheduler (Fase 1 regresi check)**: dikonfirmasi **tidak ada** registrasi job duplikat untuk checker mana pun (termasuk `rsi_extreme_checker`) — fix Fase 1 masih utuh, tidak disentuh ulang.
- **Item 8 (spot signal berulang)**: `spot_signal_1` pada 21 Juli hanya berjalan **satu kali** tepat di jadwal resmi 12:00 WIB (`spot_signal_1 ... scheduled at 2026-07-21 05:00:00 UTC`) — **tidak ditemukan** bukti duplikasi pengiriman "SARAN SPOT TERBAIK" di luar jadwal resmi pada insiden ini. Mitigasi tetap ditambahkan (dedup konten identik <2 jam) sebagai pagar preventif terhadap skenario restart yang bisa memicu double-fire di masa depan, tanpa mengubah jadwal 06:00/12:00/21:05 WIB.

---

## Perubahan per file/fungsi

### Baru: `engine/alerts/notification_governor.py`
Modul tunggal yang menjadi dasar semua perbaikan berikut:
- **Persisted cooldown store** (`data/alert_cooldown_state.json`, atomic write via `os.replace` — tahan terhadap SIGKILL saat shutdown timeout, skenario yang persis terjadi di insiden ini): `is_cooldown_allowed()` / `record_cooldown()`, `is_duplicate_value()` / `record_value()`, `get_value()` / `set_value()` generik.
- **Freshness check yang benar** (`is_coin_snapshot_fresh()`, `coin_snapshot_age_sec()`) — memperbaiki bug epoch-float vs ISO-string di atas; unknown timestamp diperlakukan sebagai "tidak bisa dibuktikan stale" (tidak memblokir), bukan default-fail.
- **Digest buffer** (`queue_alert()`, `flush_pending()`, `ALERT_DIGEST_THRESHOLD` env, default 5) — in-memory (bukan persisted; kehilangan buffer parsial saat restart di tengah siklus dianggap dapat diterima, tidak berisiko spam).
- **Rate limiter per jam** (`allow_rate_limited_dispatch()`, `pop_previous_hour_summary()`, `MAX_ALERTS_PER_HOUR` env, default 15) — persisted (supaya tetap efektif meski restart terjadi di tengah jam).
- **Stats in-memory** (`get_stats_snapshot()`) untuk `/alert_stats`.

### `interfaces/telegram_bot.py`
- `near_support_checker`, `near_resistance_checker`, `rsi_extreme_checker`, `big_move_checker`, `whale_alert_job`: cooldown dipindah ke `ngov` (persisted), tambah freshness check per-coin sebelum membentuk pesan, dan dispatch diganti dari `safe_dispatch()` langsung menjadi `ngov.queue_alert()` (dikumpulkan, di-flush oleh job baru).
- `big_move_checker`: cooldown khusus `BIG_MOVE_COOLDOWN_SEC` (default 7200s) per `(coin, arah)`, terpisah dari cooldown 4 jam checker lain; guard freshness lama yang mati diganti `ngov.is_coin_snapshot_fresh()`.
- `volume_spike_job`, `breakout_check_job`, `funding_alert_job`: gate/cooldown duplikat di sisi Telegram dihapus (sekarang otoritas tunggal ada di detector masing-masing); dispatch diganti `ngov.queue_alert()`.
- **Job baru** `alert_digest_flush_job` (interval 60s, first 65s): drain buffer `ngov`, terapkan rate limit per pesan, kirim ringkasan jam sebelumnya jika ada yang tersaring. Ini titik tunggal tempat item 4 & 5 ditegakkan lintas-checker.
- `spot_signal_job`: tambah dedup konten identik <2 jam (persisted via `ngov`), dengan `_bypass_dedup=True` untuk `/spot_signal` manual supaya command tetap selalu merespons.
- Command baru `/alert_stats` (+ entri di `/help`).
- Dict in-memory `_whale_alert_last_sent`, `_snapshot_alert_last_sent`, `_snapshot_alert_last_pct`, `_volume_spike_last_sent` dan konstanta `_VOLUME_SPIKE_MIN_MULTIPLIER`/`_VOLUME_SPIKE_COOLDOWN_SEC` dihapus (digantikan `ngov`).

### `engine/market/volume_spike_detector.py`
- `SPIKE_MULTIPLIER`: `2.0` → `4.0` (satu-satunya ambang sekarang; sebelumnya ada gate kedua `>=4.0` di `telegram_bot.py`).
- `COOLDOWN_HOURS`: `4` → `8` (mempertahankan kadensi efektif sebelumnya, karena gate 8 jam sisi Telegram yang dihapus dulunya adalah otoritas cooldown yang benar-benar berlaku di produksi).
- `_last_alert_ts` in-memory → `ngov.is_cooldown_allowed`/`record_cooldown`.
- `run_volume_spike_check()`: tambah freshness check per-coin sebelum evaluasi spike.

### `engine/market/breakout_detector.py`
- `_last_alert_ts` dan `_broken_levels` in-memory → `ngov` (cooldown + `get_value`/`set_value` untuk level terakhir).
- `run_breakout_check()`: tambah freshness check per-coin.
- Docstring "cooldown 4 jam" diperbaiki jadi "8 jam" (sudah tidak sesuai kode sejak awal — `ALERT_COOLDOWN_SEC = 8*3600`).

### `engine/market/funding_rate_monitor.py`
- `_last_alert_ts` in-memory → `ngov.is_cooldown_allowed`/`record_cooldown` di `check_funding_extremes()`.
- **Tidak** ditambahkan freshness check per-coin di sini: `get_all_funding_data()` melakukan fetch HTTP live ke Binance Futures tiap kali dipanggil (bukan baca dari snapshot cache), sehingga risiko stale-cache yang jadi motivasi item 3 tidak berlaku dengan cara yang sama seperti checker berbasis `get_market_snapshot()`. Dicatat di sini sesuai instruksi "ikuti bukti kode" — freshness check ditambahkan di keempat checker yang memang membaca dari snapshot cache (near_support, near_resistance, rsi_extreme, big_move) plus volume_spike dan breakout (yang juga baca `row` dari snapshot sebelum fetch tambahan).

### `.env.example`
Tambah `BIG_MOVE_COOLDOWN_SEC=7200`, `ALERT_DIGEST_THRESHOLD=5`, `MAX_ALERTS_PER_HOUR=15` dengan komentar. Tidak menyentuh `.env` asli atau secret apa pun.

### Tidak diubah (di luar cakupan / tidak ada temuan yang mengharuskan)
- `crypto_intelligence.py:analyze_funding()` — lihat Diagnosis di atas.
- Parameter strategi/sinyal (RSI 30/70, SL/TP, RR minimum, `AUTO_ALERT_MIN_SCORE`, single-registration `rsi_extreme_checker`) — tidak disentuh, tidak ditemukan regresi.
- `core/graceful_shutdown.py` / penyebab restart sering — di luar cakupan task ini (notifikasi & freshness data, bukan infra deploy); dicatat sebagai konteks penting di Diagnosis karena ini akar penyebab insiden, tapi perbaikannya ada di branch terpisah (`fix/deploy-script`, `fix/graceful-shutdown`).

---

## Cara verifikasi manual di Telegram

1. `/alert_stats` — tampilkan counter (kosong di awal proses baru, terisi setelah checker jalan).
2. `/check_near_resistance`, `/check_big_move`, dll — command manual tetap bekerja seperti biasa (tidak melalui digest/rate-limit, sesuai desain — ini on-demand, bukan polling otomatis).
3. Simulasikan restart: `sudo systemctl restart aliza-telegram` dua kali berturut-turut dalam <4 jam, amati bahwa alert near_resistance/near_support/big_move untuk coin yang sama **tidak** muncul ulang pada siklus checker pertama setelah restart kedua (sebelumnya: langsung muncul ulang, ini bug yang diperbaiki).
4. `/spot_signal` dua kali berturut-turut dalam kondisi pasar tidak berubah — response kedua tetap terkirim (manual command bypass dedup); tapi run **terjadwal** kedua dalam <2 jam dengan isi identik akan di-skip (lihat log `spot_signal skipped: konten identik...`).
5. Amati `logs/aliza.log` untuk baris baru: `skip <COIN> — stale snapshot data`, `alert_digest_flush_job: MAX_ALERTS_PER_HOUR (...) reached`, `RINGKASAN ALERT (...)`.

## Hasil test

`tests/test_notifikasi_mitigasi.py` — 20 test, semua PASS, mencakup ketujuh skenario wajib (cooldown near-resistance persisted + expiry 4 jam; cooldown big-move per arah + persisted + configurable; freshness untuk near-resistance & big-move, termasuk kasus fresh yang tidak diblokir; digest 6→1 pesan dan 4→4 pesan; rate limit >15/jam dengan ringkasan jam sebelumnya; threshold volume spike tunggal 4x + cooldown persisted) ditambah beberapa test pendukung (scoping per coin+condition, arah berlawanan tidak saling blokir).

Regresi: full suite (`tests/`, `test_telegram_authorization.py`, `test_dashboard_*.py`) — **158 passed, 74 subtests passed, 0 failed**.

```
venv/bin/python -m pytest tests/ test_telegram_authorization.py test_dashboard_*.py -q
158 passed, 3 warnings, 74 subtests passed in 16.44s
```

## PENDING KEPUTUSAN USER

1. **Default `MAX_ALERTS_PER_HOUR=15`, `ALERT_DIGEST_THRESHOLD=5`, `BIG_MOVE_COOLDOWN_SEC=7200`** — dipakai sesuai nilai yang direkomendasikan eksplisit di prompt, bukan ditebak. Kalau setelah beberapa hari observasi angka ini terasa terlalu longgar/ketat, tinggal ubah via `.env` (tidak perlu redeploy kode).
2. **`volume_spike_detector.py` `COOLDOWN_HOURS` dinaikkan dari 4→8 jam** untuk mempertahankan kadensi yang selama ini efektif berlaku di produksi (karena gate 8 jam sisi Telegram yang dihapus). Kalau yang diinginkan sebenarnya adalah cooldown 4 jam yang lebih sering (sesuai nilai asli detector, bukan nilai efektif gate ganda lama), ini perlu dikonfirmasi — saat ini dibiarkan 8 jam sebagai pilihan yang lebih konservatif/aman.
3. **Root cause restart yang sering (7x dalam ±8 jam)** bukan bug kode notifikasi, tapi ini yang memicu insiden. Task ini sengaja tidak menyentuh `core/graceful_shutdown.py` atau `scripts/deploy/deploy.sh` (di luar cakupan "notifikasi & data freshness"), tapi persisted-cooldown di laporan ini membuat sistem **tahan** terhadap restart sesering apa pun — restart itu sendiri tetap sebaiknya diselidiki terpisah kalau memang bukan aktivitas deploy yang disengaja.
4. **`analyze_funding()` di `crypto_intelligence.py`** dibiarkan apa adanya (dipakai di `/radar`, tidak di jalur alert) — kalau ke depannya ambang ±5%-nya yang hampir mustahil tercapai itu memang dianggap membingungkan di layar `/radar`, itu perbaikan terpisah di luar cakupan mitigasi spam ini.
