# Mitigasi Fitur Berita — Migrasi Governor, Diagnosa `alerts_sent=0`, Nonaktifkan FMP

Repo: `/opt/aliza-ai`, branch `fix/breaking-news-governor` (dibuat dari `main` @ `aded2b3`, sudah termasuk `907930b`).
Referensi: `AUDIT_FITUR_BERITA_REPORT.md` (21 Juli).

## Ringkasan

Tiga item wajib dari prompt sudah dieksekusi dan diverifikasi lewat test (22 test lama + 9 test baru, semua lulus; 64/64 test di seluruh `tests/` juga lulus, tanpa regresi). Item 2 (observability logging) sudah ditambahkan dan diuji lewat unit test, tapi **belum bisa dilaporkan hasil observasi live-nya** — itu perlu deploy sungguhan yang di luar cakupan prompt ini (lihat catatan di bagian item 2). Semua perubahan ada di branch `fix/breaking-news-governor`, **belum di-merge ke `main`, belum di-push, belum restart service** — konsisten dengan pola kerja audit → fix-di-branch → deploy/merge/push terpisah yang sudah berjalan sebelumnya.

---

## 1. Migrasi `breaking_news_job` ke `notification_governor`

### Perubahan

- **`interfaces/telegram_bot.py`**
  - Dihapus: `SENT_NEWS_TITLES: dict[str, float]` dan `_SENT_NEWS_RETENTION_SEC` (module-level dict, hilang tiap restart). Diganti konstanta `_NEWS_TITLE_DEDUP_SEC = 86400` (nilai sama, cuma bukan lagi bagian dari state itu sendiri).
  - `_cleanup_sent_news_titles()` → diganti `_prune_sent_news_titles()`, memanggil `ngov.prune_cooldown_namespace("news_title", _NEWS_TITLE_DEDUP_SEC)` (lihat poin di bawah kenapa perlu fungsi baru di `ngov`).
  - `_is_breaking_news()` di-refactor jadi dua helper terpisah `_hits_breaking_blacklist()` dan `_hits_breaking_keyword()`, dipanggil berurutan oleh `_is_breaking_news()` — **perilaku identik**, cuma dipecah supaya `breaking_news_job` bisa menghitung berapa item yang kena blacklist vs tidak match keyword secara terpisah (dibutuhkan item 2). Keyword/blacklist list itu sendiri **tidak diubah sama sekali**.
  - `breaking_news_job()`: dedup check `if key in SENT_NEWS_TITLES` → `if not ngov.is_cooldown_allowed("news_title", key, _NEWS_TITLE_DEDUP_SEC)`; setelah dispatch sukses, `SENT_NEWS_TITLES[key] = _now_ts()` → `ngov.record_cooldown("news_title", key)`.
- **`engine/alerts/notification_governor.py`**: tambah `prune_cooldown_namespace(namespace, older_than_sec, now=None) -> int` — hapus entri `cooldown:{namespace}` yang lebih tua dari `older_than_sec`, return jumlah yang dihapus.

### Kenapa `is_cooldown_allowed`/`record_cooldown`, bukan `is_duplicate_value`/`record_value` (deviasi dari instruksi)

Prompt eksplisit minta pakai `is_duplicate_value()`/`record_value()` dengan alasan "ini dedup per-judul-berita, bukan cooldown per-coin". Setelah dicek implementasinya di `notification_governor.py`, saya pilih tetap pakai `is_cooldown_allowed`/`record_cooldown` — **deviasi disengaja**, alasannya:

- `is_duplicate_value(namespace, key, value, epsilon)` dirancang untuk bandingkan **nilai numerik** (mis. persentase harga di `big_move`/`snapshot_alert`) terhadap nilai terakhir dengan toleransi epsilon — bukan untuk "pernah dikirim atau belum" per key string. Judul berita bukan angka; tidak ada "value" natural yang bisa dibandingkan.
- Fungsi ini juga **tidak punya TTL** — sekali `record_value` dipanggil, nilai itu tersimpan permanen sampai di-timpa `record_value` lagi (bukan di-expire otomatis). Perilaku lama (`SENT_NEWS_TITLES`) butuh entri "lupa" lagi setelah 24 jam supaya artikel yang sama boleh terkirim ulang kalau memang masih relevan sehari kemudian — `is_duplicate_value` sama sekali tidak mendukung ini tanpa tambahan logika TTL terpisah.
- `is_cooldown_allowed(namespace, key, cooldown_sec)` justru **persis** primitive yang dibutuhkan: "apakah key ini sudah pernah 'fire' dalam N detik terakhir" — signature-nya generik (`namespace: str, key: str`), tidak ada apa pun yang mengharuskan `namespace` berarti "per-coin"; nama parameternya cuma mencerminkan pemakaian pertamanya (checker harga). Menggunakannya untuk `namespace="news_title"` tidak mengubah semantiknya — hasilnya justru replika 1:1 dari perilaku `SENT_NEWS_TITLES` lama (skip kalau sudah pernah kirim dalam 24 jam terakhir, boleh kirim lagi setelahnya), dengan nol kode baru di `ngov` untuk primitive dedup-nya sendiri.

Kalau ada alasan lain yang belum saya lihat kenapa harus tetap pakai `is_duplicate_value` (mis. rencana masa depan untuk membedakan "record" dari "cooldown gate" di level API), tolong beri tahu — gampang diubah, tapi berdasarkan kode yang ada saat ini `is_cooldown_allowed` adalah pilihan yang lebih sederhana dan lebih dekat ke perilaku lama.

### Kenapa tetap dispatch langsung (tidak masuk `queue_alert`/digest)

Breaking news **tidak** dialihkan ke jalur `ngov.queue_alert()` + digest buffer yang dipakai `near_support`/`big_move`/dst. Alasan: pembatas breaking-news sudah beda dari checker-checker itu — maks **3 alert per run** ([interfaces/telegram_bot.py:3260](interfaces/telegram_bot.py#L3260) dst, tidak diubah) sudah jadi guard sendiri terhadap burst dalam satu siklus, sementara `queue_alert`/digest dirancang untuk menggabungkan alert dari checker yang beda-beda ke dalam satu pesan ringkasan per siklus flush (60 detik) — breaking news berjalan per jam, bukan per menit, jadi tidak ada "burst dalam satu flush cycle" yang perlu digabung. Menambahkannya ke jalur digest hanya akan menambah kompleksitas tanpa manfaat nyata untuk pola pemakaian job ini. Yang dipindah murni bagian **dedup**-nya ke penyimpanan persisten — itu yang jadi akar masalah (reset saat restart), bukan soal digest/rate-limit.

### Kenapa perlu `prune_cooldown_namespace` baru (bukan pakai pola cleanup yang sudah ada)

Dicek: **tidak ada** mekanisme cleanup/pruning apa pun di `notification_governor.py` untuk namespace manapun sebelum perubahan ini — checker lain (near_support, big_move, dst.) tidak butuh itu karena key mereka terbatas pada daftar coin yang kecil dan tetap (BTC, ETH, SOL, ...), jadi `data/alert_cooldown_state.json` tidak pernah tumbuh tak terbatas untuk mereka. `news_title` beda: key-nya per judul artikel unik, jumlahnya tidak terbatas (berpotensi ratusan/ribuan entri berbeda seiring waktu kalau breaking-news mulai aktif kirim). Tanpa pruning, file state akan tumbuh terus. Ditambahkan `prune_cooldown_namespace()` sebagai primitive generik di `ngov` (bisa dipakai namespace lain di masa depan kalau ada kebutuhan serupa), dipanggil sekali di awal tiap `breaking_news_job` run — pola yang sama seperti `_cleanup_sent_news_titles()` lama (dipanggil di awal job), cuma sekarang membersihkan state persisten, bukan dict in-memory.

---

## 2. Diagnosa `alerts_sent=0` — logging ditambahkan, observasi live tertunda

### Perubahan

- `_fetch_crypto_news()` ([interfaces/telegram_bot.py](interfaces/telegram_bot.py)): tambah `logging.info("_fetch_crypto_news: %d artikel mentah dari NewsAPI", len(articles))` persis setelah `articles = r.json().get("articles") or []`, sebelum difilter jadi `out`.
- `_fetch_macro_news()`: log yang sama (`_fetch_macro_news: %d artikel mentah dari NewsAPI`).
- `breaking_news_job()`: tambah counter `n_total`, `n_blacklisted`, `n_not_breaking`, `n_stale`, `n_dedup_skipped`, `n_dispatch_failed`, diincrement di titik `continue`/`except` yang sesuai sepanjang loop. Baris log akhir diperluas dari `"scan done, alerts_sent=%s"` jadi:
  ```
  breaking_news_job: scan done, alerts_sent=%s (total=%s blacklisted=%s not_breaking=%s stale=%s dedup_skipped=%s dispatch_failed=%s)
  ```
- Logika filter/keyword **tidak diubah** — `_hits_breaking_blacklist`/`_hits_breaking_keyword` cuma memecah `_is_breaking_news` yang sudah ada jadi dua panggilan terpisah dengan hasil identik (diverifikasi lewat test `test_non_breaking_item_is_not_dispatched_or_deduped`).

### Kenapa belum ada hasil observasi live

Prompt bilang: *"Setelah deploy, biarkan berjalan minimal beberapa siklus dan laporkan apa yang log baru ini ungkapkan."* — ini butuh proses `aliza-telegram.service` benar-benar restart dengan kode dari branch ini, lalu menunggu ≥1 siklus (job jalan tiap jam). Prompt task ini eksplisit membuat branch fix (`fix/breaking-news-governor`) dan **tidak** menginstruksikan merge/push/restart — pola yang sama seperti PR mitigasi sebelumnya (`fix/telegram-notification-noise` di-review dulu di branch, baru di-merge+deploy+verifikasi di prompt terpisah, lihat `NOTIFIKASI_DEPLOY_VERIFIKASI_REPORT.md`). Karena itu, service produksi **masih menjalankan kode `main` yang lama** (tanpa logging baru ini) — tidak ada siklus baru untuk diobservasi dari branch ini. **Rekomendasi**: siapkan prompt deploy/verifikasi terpisah (sama seperti pola sebelumnya) untuk merge branch ini, restart service, lalu setelah beberapa siklus jam berjalan, grep log untuk baris `_fetch_crypto_news: %d artikel mentah` dan breakdown `blacklisted=/not_breaking=/stale=` guna akhirnya menjawab kenapa `alerts_sent` selalu 0 selama 7 hari terakhir.

---

## 3. `FMP_CALENDAR_ENABLED` — nonaktifkan panggilan FMP

### Perubahan

- **`engine/market/economic_calendar.py`**: tambah `_fmp_calendar_enabled() -> bool`, baca `os.getenv("FMP_CALENDAR_ENABLED", "false")` **saat dipanggil** (bukan konstanta level-modul di-cache saat import) — supaya gampang di-toggle di test lewat `monkeypatch`/`patch.dict(os.environ, ...)` tanpa perlu reload modul.
- Di `get_upcoming_events()`, kondisi FMP diubah dari `if fmp_key:` jadi `if fmp_key and _fmp_calendar_enabled():`, dengan cabang `elif fmp_key:` yang log `logger.debug(...)` sekali per panggilan kalau key ada tapi flag mati (supaya jelas di debug log kenapa FMP dilewati, tanpa nge-spam level INFO tiap siklus 1 jam).
- Urutan fallback lain (Investing.com → rule-based → Serper enrichment) **tidak diubah sama sekali** — cuma langkah FMP-nya yang di-skip kalau flag mati.
- Docstring `get_upcoming_events()` diperbarui untuk mencerminkan syarat baru (`FMP_API_KEY` **dan** `FMP_CALENDAR_ENABLED=true`).

### `.env.example`

Ditambahkan di bawah `FMP_API_KEY=`:
```
# FMP dipanggil hanya kalau flag ini true DAN FMP_API_KEY terisi. Default
# false: FMP_API_KEY yang ada saat ini mengembalikan HTTP 403 terus-menerus
# (lihat BERITA_MITIGASI_REPORT.md) — set true lagi setelah key diperbarui.
FMP_CALENDAR_ENABLED=false
```
`.env` produksi **tidak disentuh** (sesuai aturan) — karena default kode sudah `"false"` kalau env var tidak diset, perilaku FMP di server saat ini otomatis jadi nonaktif begitu branch ini di-deploy, tanpa perlu mengubah `.env` sama sekali. Kalau user ingin eksplisit menuliskannya di `.env` produksi juga (dokumentasi diri), itu perubahan `.env` yang perlu dilakukan terpisah — di luar cakupan aturan "jangan sentuh .env" pada task ini.

---

## 4. TODO usang di `macro_checker.py`

Docstring modul ([engine/macro/macro_checker.py](engine/macro/macro_checker.py)) diganti — TODO lama ("Plug in a real-time economic calendar API...") dihapus karena menyesatkan (integrasi itu sudah ada di `economic_calendar.py`). Docstring baru menjelaskan kondisi nyata: urutan fallback yang benar-benar berjalan (FMP dinonaktifkan via flag karena 403 terus-menerus; Investing.com juga sedang 403; rule-based jadi sumber utama saat ini; Serper cuma enrichment tambahan), plus catatan eksplisit soal perilaku fail-open `get_upcoming_events()` (exception apa pun ditelan, return `[]`, sehingga "gagal total" dan "genuinely tidak ada event" terlihat identik ke caller) — sesuai temuan poin 6 di `AUDIT_FITUR_BERITA_REPORT.md`. **Fail-open itu sendiri tidak diubah** (di luar cakupan item ini, prompt cuma minta perbarui dokumentasi TODO-nya).

---

## Hasil Test

`tests/test_berita_governor.py` (baru, 9 test):

| Test | Yang diverifikasi |
|---|---|
| `test_same_title_within_24h_is_not_resent` | Dedup: judul sama, run kedua langsung setelah run pertama → tidak dikirim ulang |
| `test_same_title_is_sent_again_after_24h` | Setelah timestamp dedup dimundurkan >`_NEWS_TITLE_DEDUP_SEC` → boleh kirim lagi |
| `test_dedup_survives_simulated_process_restart` | `ngov._state_cache = None` (simulasi restart) → dedup tetap tertekan, tidak seperti `SENT_NEWS_TITLES` lama |
| `test_different_titles_are_independent` | Dua judul berbeda dalam satu run → keduanya terkirim, dedup tidak silang |
| `test_non_breaking_item_is_not_dispatched_or_deduped` | Item yang tidak lolos filter breaking → tidak dikirim, tidak ikut tercatat di dedup store |
| `test_prune_removes_entries_older_than_ttl_keeps_recent` | `ngov.prune_cooldown_namespace` menghapus entri lama, menyisakan yang baru |
| `test_fmp_disabled_by_default_skips_fmp_and_falls_back_to_investing` | `FMP_CALENDAR_ENABLED=false` (default) → `_fetch_from_fmp` nol kali dipanggil, fallback ke Investing.com |
| `test_fmp_enabled_is_still_called_when_flag_true` | `FMP_CALENDAR_ENABLED=true` → FMP tetap dipanggil seperti semula (regresi flag) |
| `test_fmp_not_called_when_key_missing_even_if_flag_true` | Flag true tapi `FMP_API_KEY` kosong → tetap tidak dipanggil (guard lama tidak rusak) |

```
$ ./venv/bin/python -m pytest tests/test_berita_governor.py -v
9 passed in 14.81s
```

Regresi — `tests/test_notifikasi_mitigasi.py` (checker yang sudah dimigrasi ke `ngov` sebelumnya, near_support/near_resistance/rsi/big_move/whale/volume_spike):

```
$ ./venv/bin/python -m pytest tests/test_notifikasi_mitigasi.py -v
22 passed in 9.19s
```

Seluruh suite `tests/`:

```
$ ./venv/bin/python -m pytest tests/ -q
64 passed in 9.21s
```

Tidak ada checker lain yang disentuh ulang; tidak ada regresi.

---

## File yang berubah

```
 .env.example                           |  4 ++
 engine/alerts/notification_governor.py | 27 ++++++++++++
 engine/macro/macro_checker.py          | 16 +++++--
 engine/market/economic_calendar.py     | 18 +++++++-
 interfaces/telegram_bot.py             | 78 ++++++++++++++++++++++++++--------
 tests/test_berita_governor.py          | (baru)
```

Tidak ada perubahan pada logika strategi/sinyal trading, tidak ada checker lain (near_support dkk.) yang disentuh, `BREAKING_KEYWORDS`/`BREAKING_BLACKLIST` tidak diubah, `.env` produksi tidak disentuh.

---

## Status & Langkah Selanjutnya

- Branch `fix/breaking-news-governor` berisi semua perubahan di atas, **belum di-merge ke `main`, belum di-push, service produksi belum di-restart** — menunggu review, konsisten dengan pola audit → fix-branch → deploy-terpisah yang sudah dipakai untuk `NOTIFIKASI_MITIGASI_REPORT.md`.
- Rekomendasi langkah berikut: prompt deploy/merge/push terpisah (pola sama seperti `DEPLOY_MERGE_PUSH_REPORT.md` sebelumnya) untuk: (a) merge branch ini, (b) restart `aliza-telegram.service`, (c) tunggu beberapa siklus breaking-news (tiap jam) dan macro calendar (juga tiap jam), lalu (d) grep log baru untuk akhirnya menjawab kenapa `alerts_sent` selalu 0, dan konfirmasi `economic_calendar: source=` tidak lagi mencoba FMP.
