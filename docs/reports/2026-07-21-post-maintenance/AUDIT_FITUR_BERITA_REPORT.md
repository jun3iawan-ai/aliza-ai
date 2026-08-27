# Audit Fitur Berita/News ke Telegram

Repo: `/opt/aliza-ai`, branch `main` (audit read-only, tidak ada file yang diubah).
Tanggal audit: 2026-07-21.

## Ringkasan

Fitur berita **berjalan** (job terjadwal, API key terisi, tidak ada exception), tapi **belum sehat sepenuhnya**:

- **Gap konfirmasi**: `breaking_news_job` di `interfaces/telegram_bot.py` **tidak ikut dimigrasi** ke `engine/alerts/notification_governor.py` pada PR mitigasi spam (`2b62ce8`, 21 Juli). Dia masih pakai dedup in-memory (`SENT_NEWS_TITLES`) persis pola lama yang menyebabkan insiden burst pada checker lain — restart proses (terjadi 11x pada 21 Juli saja) mereset dedup-nya. **Belum ada bukti burst nyata** karena job ini belum pernah berhasil kirim alert sama sekali dalam 7 hari terakhir (lihat poin 4), jadi risikonya masih laten, bukan aktif.
- **Anomali signifikan**: `breaking_news_job` berjalan tiap jam (~24x/hari × 7 hari = ±168 kali run) dan **selalu `alerts_sent=0`**, tanpa satu pun error/exception NewsAPI tercatat di log. Ini janggal karena beberapa keyword breaking cukup umum (mis. "binance", "coinbase", "bitcoin etf"). Tidak bisa dipastikan penyebabnya dari log yang tersedia (lihat poin 4) — kandidat: NewsAPI mengembalikan artikel yang genuinely tidak match, atau selalu mengembalikan list kosong tanpa itu tercatat sebagai error (HTTP 200 dengan `articles: []` tidak logged secara eksplisit).
- **Dokumentasi usang, bukan bug**: TODO "kalender ekonomi real-time" di `engine/macro/macro_checker.py` sudah **tidak akurat** — modul kalender penuh (`engine/market/economic_calendar.py`, 502 baris, multi-source: FMP → Investing.com → rule-based + enrichment Serper) sudah dibangun. Tapi kondisi live saat ini: **FMP HTTP 403 dan Investing.com HTTP 403 terus-menerus** (kemungkinan API key FMP invalid/expired atau scraping Investing.com diblokir), sehingga sistem sedang berjalan di mode fallback rule-based/estimasi, bukan sumber real-time yang sebenarnya sudah dibangun untuk menggantikannya.
- Kedua job berita berdiri sendiri (`breaking_news_job`, `_generate_brief_analysis` untuk morning/evening brief) memanggil NewsAPI **tanpa cache** sama sekali, tapi volume panggilan totalnya (~28 request/hari) masih wajar.

---

## 1. Job Breaking News — definisi & scheduler

Definisi: `breaking_news_job()` di [interfaces/telegram_bot.py:3244](../../../interfaces/telegram_bot.py#L3244) — async function, docstring: *"Cek berita breaking ~1 jam; maks 3 alert per run; dedup 24h."*

Registrasi scheduler di [interfaces/telegram_bot.py:7191-7197](../../../interfaces/telegram_bot.py#L7191-L7197):

```python
app.job_queue.run_repeating(
    breaking_news_job,
    interval=3600,
    first=300,
    name="breaking_news_checker",
)
logging.info("Breaking news job scheduled (every 3600s, first in 300s).")
```

**Konfirmasi**: masih terdaftar, interval **3600 detik = 1 jam persis** (sesuai dokumentasi lama), first run 300 detik (5 menit) setelah proses start. Tidak ada modul terpisah `engine/news/*` — semua logika berita ada di dalam `interfaces/telegram_bot.py` (dikonfirmasi via pencarian `*news*` di seluruh repo, hanya ada file pihak ketiga di `venv/`).

Log runtime mengonfirmasi job benar-benar jalan tiap jam secara konsisten selama 7 hari terakhir (lihat poin 4).

---

## 2. Sumber & logika berita

### Sumber data

Ada **dua fungsi fetch berbeda**, keduanya pakai `NEWSAPI_KEY` (bukan Serper):

- `_fetch_crypto_news()` — [interfaces/telegram_bot.py:3093-3134](../../../interfaces/telegram_bot.py#L3093-L3134): query `"bitcoin OR ethereum OR crypto"` ke `https://newsapi.org/v2/everything`, `from=now-3h`, `pageSize=10`.
- `_fetch_macro_news()` — [interfaces/telegram_bot.py:3137-3178](../../../interfaces/telegram_bot.py#L3137-L3178): query `"Federal Reserve OR interest rate OR inflation OR economy"`, `pageSize=5`.

**Temuan menarik**: ada juga `_serper_news_fetch()` di [interfaces/telegram_bot.py:3049-3090](../../../interfaces/telegram_bot.py#L3049-L3090) yang lengkap (pakai `SERPER_API_KEY`, endpoint `google.serper.dev/news`) — **tapi fungsi ini didefinisikan dan tidak pernah dipanggil di mana pun** (dikonfirmasi via grep `_serper_news_fetch(` — hanya muncul di baris definisinya sendiri). Jadi meski `SERPER_NEWS_URL`/`SERPER_API_KEY` disebut di kode terkait breaking news, breaking-news job yang aktual **tidak pakai Serper sama sekali** — dead code. Tidak ada fallback antara Serper dan NewsAPI untuk breaking news; hanya NewsAPI yang dipakai, tanpa fallback lain kalau NewsAPI gagal (return list kosong saja, lihat poin 5).

(Catatan: `SERPER_API_KEY` tetap dipakai fitur lain — search umum [interfaces/telegram_bot.py:2359](../../../interfaces/telegram_bot.py#L2359), data institutional ETF/liquidation [interfaces/telegram_bot.py:4516](../../../interfaces/telegram_bot.py#L4516), dan economic calendar [engine/market/economic_calendar.py:349](../../../engine/market/economic_calendar.py#L349) — lihat poin 6.)

### Filter "breaking"

`_is_breaking_news(title, snippet)` di [interfaces/telegram_bot.py:3209-3215](../../../interfaces/telegram_bot.py#L3209-L3215): cocokkan substring lowercase terhadap `BREAKING_KEYWORDS` (±50 keyword, [interfaces/telegram_bot.py:2948-3019](../../../interfaces/telegram_bot.py#L2948-L3019): Fed/rate, regulasi SEC/ETF, exchange hack, market crash/ATH, macro CPI/NFP, institutional buys, geopolitik). Ada `BREAKING_BLACKLIST` ([interfaces/telegram_bot.py:3022-3039](../../../interfaces/telegram_bot.py#L3022-L3039)) yang di-cek lebih dulu — kalau match blacklist (mis. "mortgage", "how to buy", "what is bitcoin"), langsung skip meski ada breaking keyword.

**Tidak ada scoring/severity** — begitu lolos filter keyword + blacklist + umur berita (skip kalau lebih dari 3 jam, [interfaces/telegram_bot.py:3283-3308](../../../interfaces/telegram_bot.py#L3283-L3308)) + belum pernah dikirim, langsung dikirim. Dibatasi maks 3 alert per run ([interfaces/telegram_bot.py:3275-3276](../../../interfaces/telegram_bot.py#L3275-L3276): `if sent >= 3: break`). Judul & snippet diterjemahkan ke Bahasa Indonesia via LLM sebelum dikirim (`_translate_news_to_id`, [interfaces/telegram_bot.py:3218-3241](../../../interfaces/telegram_bot.py#L3218-L3241)).

---

## 3. Cooldown/dedup — GAP dikonfirmasi

**Breaking news job memakai dedup in-memory murni, BUKAN `notification_governor`:**

```python
# interfaces/telegram_bot.py:2945-2946
SENT_NEWS_TITLES: dict[str, float] = {}
_SENT_NEWS_RETENTION_SEC = 86400
```

Dedup dilakukan dengan cek `key = title[:400]` terhadap dict module-level ini ([interfaces/telegram_bot.py:3309-3311](../../../interfaces/telegram_bot.py#L3309-L3311)), retensi 24 jam via `_cleanup_sent_news_titles()` ([interfaces/telegram_bot.py:3042-3046](../../../interfaces/telegram_bot.py#L3042-L3046)). **Tidak ada satu pun referensi `ngov`/`notification_governor` di sekitar `breaking_news_job`** (dikonfirmasi via grep — semua 30+ pemakaian `ngov.*` di file ini berasal dari checker lain: `near_support`, `near_resistance`, `rsi_extreme`, `big_move`, `whale_alert`, `volume_spike`/`breakout`/`funding` via `ngov.queue_alert`, dan `spot_signal` via `ngov.get_value`/`set_value`).

**Konfirmasi via git log**: commit mitigasi spam `2b62ce8` ("fix: mitigate Telegram alert notification spam") secara eksplisit menyebutkan daftar checker yang dimigrasi di commit message: *"near_support, near_resistance, rsi_extreme, big_move, whale, volume_spike, breakout, funding"* — **breaking_news tidak ada dalam daftar**. Diff aktual commit ini (`git show 2b62ce8 -- interfaces/telegram_bot.py`) dicek dengan grep untuk `breaking_news|SENT_NEWS_TITLES` — **nol hasil**, memastikan file `breaking_news_job` maupun `SENT_NEWS_TITLES` sama sekali tidak tersentuh oleh commit ini. Commit susulan `907930b` (fix epoch UTC) juga tidak menyentuhnya (perbaikan itu spesifik untuk 3 call site di `_snapshot_alert_allowed`, `_whale_alert_allowed`, `big_move_checker`).

Bukti tambahan: `data/alert_cooldown_state.json` (state persisten milik `notification_governor`) hanya berisi key `cooldown:snapshot_alert`, `cooldown:big_move`, `dedup:big_move`, `breakout_level`, `cooldown:breakout`, `rate_limit_sent` — **tidak ada key terkait news/breaking sama sekali**.

**Implikasi**: kalau proses Telegram bot restart (systemd `Restart=always`, sudah terjadi **11 kali** pada 21 Juli 2026 saja — lihat poin 4), `SENT_NEWS_TITLES` di-reset kosong. Kalau breaking-news job kebetulan menemukan artikel yang sama lagi di scan jam berikutnya (masih dalam window 3 jam), artikel itu bisa terkirim ulang — bug arsitektur yang **identik** dengan root cause insiden 57-pesan/3.5-jam yang baru diperbaiki untuk checker lain (lihat `NOTIFIKASI_MITIGASI_REPORT.md`).

**Status risiko saat ini: laten, belum aktif** — karena `alerts_sent` selalu 0 (poin 4), belum ada bukti langsung breaking-news job pernah benar-benar mengirim, apalagi mengirim duplikat.

---

## 4. Bukti live dari log (7 hari terakhir, `logs/aliza.log` + rotasi `.1` s/d `.7.gz`, mencakup 15–21 Juli 2026)

| Tanggal | `breaking_news_job: scan start` count | `alerts_sent` |
|---|---|---|
| 2026-07-14/15 (`.7.gz`) | 25 | selalu 0 |
| 2026-07-15/16 (`.6.gz`) | 27 | selalu 0 |
| 2026-07-16/17 (`.5.gz`) | 25 | selalu 0 |
| 2026-07-17/18 (`.4.gz`) | 24 | selalu 0 |
| 2026-07-18/19 (`.3.gz`) | 24 | selalu 0 |
| 2026-07-19/20 (`.2.gz`) | 24 | selalu 0 |
| 2026-07-20/21 (`.1`) | 24 | selalu 0 |
| 2026-07-21 (`.log`, s/d ~19:31) | 24 | selalu 0 |

Query: `grep "breaking_news_job: scan done"` di semua file → **~197 baris, seluruhnya `alerts_sent=0`**. Tidak ada satu pun baris `breaking_news_job: scan done, alerts_sent=1/2/3` dalam 7 hari. Tidak ada pola duplikat/berulang mencurigakan (mis. kasus OM) karena **tidak ada satupun alert yang pernah terkirim** dalam periode ini — jadi tidak ada spam breaking-news yang teramati, tapi juga tidak ada bukti fitur ini pernah benar-benar berguna dalam 7 hari terakhir.

**Anomali yang perlu dicatat** (TIDAK PASTI penyebabnya): 197 kali run tanpa satu pun match adalah janggal secara statistik mengingat sebagian keyword breaking cukup generik ("binance", "coinbase", "bitcoin etf", "million bitcoin") terhadap query NewsAPI `"bitcoin OR ethereum OR crypto"`. Dicek:
- `grep "NEWSAPI_KEY tidak ada"` → 0 hasil di semua file (key terbaca, bukan kosong).
- `grep "NewsAPI.*HTTP"` (kode HTTP != 200) → 0 hasil (tidak ada error HTTP tercatat).
- `grep "breaking_news_job crypto/macro/dispatch"` (baris exception try/except di job ini) → 0 hasil (tidak ada exception).

Karena `_fetch_crypto_news`/`_fetch_macro_news` **tidak pernah log jumlah artikel yang berhasil di-fetch** (hanya log kalau HTTP != 200 atau exception), log yang ada **tidak cukup untuk membedakan** dua skenario: (a) NewsAPI mengembalikan artikel asli tapi genuinely tidak ada yang match keyword selama 7 hari penuh, atau (b) NewsAPI selalu mengembalikan `articles: []` (HTTP 200 tapi kosong — mis. karena batasan window `from=now-3h` di paket API yang dipakai) tanpa itu pernah tercatat sebagai anomali. **TIDAK PASTI — perlu observability tambahan (log jumlah artikel per fetch) untuk memastikan; di luar cakupan audit read-only ini.**

---

## 5. Status API Key

- `SERPER_API_KEY`: **ada isinya** di `.env` (40 karakter, format konsisten dengan Serper key).
- `NEWSAPI_KEY`: **ada isinya** di `.env` (32 karakter, format konsisten dengan NewsAPI key). Catatan: `NEWSAPI_KEY` **tidak terdaftar** di `.env.example` (hanya `SERPER_API_KEY` yang ada) — gap dokumentasi kecil, bukan bug fungsional.
- Tidak ditemukan error HTTP 401/403/429 dari `newsapi.org` di log 7 hari terakhir (grep `NewsAPI.*HTTP` dan `newsapi` case-insensitive → nol match selain baris info job biasa).
- Tidak ada fallback eksplisit antar-API untuk breaking news (lihat poin 2) — kalau `NEWSAPI_KEY` kosong/invalid, `_fetch_crypto_news`/`_fetch_macro_news` mengembalikan list kosong dan log warning `"NEWSAPI_KEY tidak ada di env"` (tidak pernah muncul di 7 hari ini, jadi key valid ada isinya) atau `"NewsAPI crypto/macro HTTP %s"` bila API menolak (tidak pernah muncul juga). Kesimpulan: **kalau key invalid/quota habis, job akan gagal diam-diam** — hanya `alerts_sent=0` tanpa Telegram atau operator diberi tahu eksplisit bahwa sumber data bermasalah (job hanya log `logging.warning` ke file log lokal, tidak ada notifikasi Telegram terpisah untuk kegagalan fetch).

---

## 6. `macro_checker.py` TODO — status aktual

TODO di [engine/macro/macro_checker.py:7-8](../../../engine/macro/macro_checker.py#L7-L8) **masih ada secara tekstual**:

```python
TODO: Plug in a real-time economic calendar API (e.g. ForexFactory, Investing.com feed)
if rule-based dates drift from actual release times.
```

**Tapi TODO ini sudah usang/tidak akurat** — sejak audit baseline lama, `macro_checker.py` sudah di-refactor total. Isinya sekarang hanya 82 baris tipis yang mendelegasikan ke `engine.market.economic_calendar` ([engine/macro/macro_checker.py:38](../../../engine/macro/macro_checker.py#L38): `from engine.market.economic_calendar import get_upcoming_events`), dan `economic_calendar.py` (502 baris, [engine/market/economic_calendar.py](../../../engine/market/economic_calendar.py)) **sudah** mengimplementasikan tepat apa yang diminta TODO: sumber real API dengan urutan fallback —

1. **FMP** (Financial Modeling Prep, perlu `FMP_API_KEY`) — [engine/market/economic_calendar.py:238-286](../../../engine/market/economic_calendar.py#L238-L286)
2. **Investing.com** (scraping, `engine/market/investing_calendar.py`) — [engine/market/economic_calendar.py:424-434](../../../engine/market/economic_calendar.py#L424-L434)
3. **rule-based** (jadwal perkiraan hardcoded: NFP Jumat pertama, CPI Rabu kedua, FOMC 2026 hardcoded, dst.) — hanya dipakai kalau (1) dan (2) sama-sama kosong ([engine/market/economic_calendar.py:436-439](../../../engine/market/economic_calendar.py#L436-L439))
4. **Serper** sebagai enrichment tambahan (selalu dicoba, hasil di-`extend`, bukan pengganti) — [engine/market/economic_calendar.py:443](../../../engine/market/economic_calendar.py#L443)

**Kondisi live saat ini (dari log 21 Juli, siklus per-jam)**: kedua sumber real-time sedang **gagal terus-menerus**:

```
economic_calendar: FMP HTTP 403
Investing.com calendar returned 403 — fallback elsewhere
economic_calendar: using rule-based calendar (FMP/Investing empty)
economic_calendar: Serper HTTP 400   (enrichment tambahan, juga gagal)
```

Pola ini konsisten di setiap siklus 1-jam yang tercatat pada 21 Juli (`FMP HTTP 403` → `Investing.com ... 403` → fallback rule-based → `Serper HTTP 400`). `FMP_API_KEY` **ada isinya** di `.env` (32 karakter) tapi menghasilkan HTTP 403 di setiap panggilan — kemungkinan besar key invalid/expired atau plan tidak mengizinkan endpoint tersebut. **TIDAK PASTI penyebab pasti 403-nya** (bisa dicek lebih lanjut lewat FMP dashboard, di luar cakupan audit ini).

Pada 20 Juli, `merged_events=0` tercatat di **setiap** baris log `economic_calendar: source=rule_based` sepanjang hari (04:38–23:49 WIB). Ini **bisa jadi wajar** (rule-based generator memang cuma menghasilkan event pada tanggal tertentu — NFP Jumat pertama, CPI Rabu kedua, dst. — window 2-3 hari ke depan kadang memang kosong), **atau** bisa jadi window itu memang tidak beririsan dengan tanggal rule manapun. Tidak bisa dipastikan tanpa membandingkan ke kalender ekonomi riil independen — **di luar cakupan audit read-only ini**.

**Fail-open dikonfirmasi**: `get_upcoming_events()` di [engine/market/economic_calendar.py:466-468](../../../engine/market/economic_calendar.py#L466-L468) membungkus seluruh isi fungsi dalam `try/except` dan **return `[]` kalau ada exception apa pun** — tidak ada sinyal terpisah yang membedakan "genuinely tidak ada event" vs "gagal total fetch data". Ini dikonsumsi oleh `is_macro_safe_to_trade()` di `engine/trading/signal_engine.py:140-152`, yang kalau macro check gagal (exception) hanya `logger.warning(...)` lalu **scan sinyal tetap lanjut** (tidak diblokir) — dan kalau `get_upcoming_events()` sendiri return `[]` (baik karena benar-benar kosong maupun karena degradasi), maka `is_macro_safe_to_trade` akan bilang **"aman untuk trading"** tanpa pembeda. Untuk pengiriman ke Telegram: `evening_calendar_job` ([interfaces/telegram_bot.py:5893-5909](../../../interfaces/telegram_bot.py#L5893-L5909)) eksplisit `if not events: return` — **tidak mengirim placeholder/pesan kosong ke Telegram**, jadi user tidak menerima laporan macro palsu yang terlihat kosong tanpa keterangan; tapi user (dan `scan_for_signals`) juga tidak pernah diberi tahu bahwa sumber data real-time (FMP, Investing.com) sedang down dan sistem berjalan di mode estimasi.

---

## 7. Berita sebagai konteks laporan (morning/evening/macro)

Ya — morning brief dan evening summary menyisipkan hasil pencarian berita ke prompt LLM, **terpisah dari `breaking_news_job`**:

- `_generate_brief_analysis()` ([interfaces/telegram_bot.py:3839](../../../interfaces/telegram_bot.py#L3839)) memanggil `_fetch_crypto_news()` dan `_fetch_macro_news()` lagi ([interfaces/telegram_bot.py:3925-3931](../../../interfaces/telegram_bot.py#L3925-L3931)), digabung jadi `all_news[:8]`, diringkas via `_summarize_news_for_brief()` ([interfaces/telegram_bot.py:3181-3208](../../../interfaces/telegram_bot.py#L3181-L3208)) lalu disisipkan ke prompt LLM sebagai `{news_block}` ([interfaces/telegram_bot.py:4038](../../../interfaces/telegram_bot.py#L4038)).
- Dipanggil dari `morning_brief_job` ([interfaces/telegram_bot.py:5300](../../../interfaces/telegram_bot.py#L5300)) dan `evening_summary_job` ([interfaces/telegram_bot.py:5427](../../../interfaces/telegram_bot.py#L5427)) — masing-masing **1x/hari** (dijadwalkan `run_daily`, 01:00 UTC dan 13:00 UTC).

**Risiko rate-limit/biaya**: `_fetch_crypto_news`/`_fetch_macro_news` **tidak punya cache TTL sama sekali** — setiap pemanggilan selalu hit NewsAPI fresh. Total panggilan NewsAPI/hari: breaking_news_job (24 run × 2 call = 48) + morning brief (1× × 2 call) + evening summary (1× × 2 call) ≈ **52 request/hari**. Ini masih dalam batas wajar untuk kebanyakan paket NewsAPI free/developer (biasanya 100/hari), tapi **tidak ada guard/cache** kalau paket API di-downgrade atau limitnya lebih ketat — kalau breaking_news_job sendiri sudah menghabiskan ~48/52 dari kuota harian, morning/evening brief berisiko kena limit di saat-saat penting (laporan pagi/sore).

Untuk Serper (dipakai `_serper_search_snippet` untuk data institutional ETF/liquidation di [interfaces/telegram_bot.py:4516](../../../interfaces/telegram_bot.py#L4516) dan economic calendar di poin 6): **ada cache**, masing-masing punya TTL sendiri — institutional data di-cache 30 detik (`_INSTITUTIONAL_SERPER_CACHE_TTL_SEC = 30.0`, [interfaces/telegram_bot.py:4744](../../../interfaces/telegram_bot.py#L4744)), economic calendar di-cache 3600 detik (`ECONOMIC_CALENDAR_CACHE_SEC`, [engine/market/economic_calendar.py:21](../../../engine/market/economic_calendar.py#L21)) — jadi risiko biaya/rate-limit Serper relatif terkendali dibanding NewsAPI.

---

## Rekomendasi

1. **Migrasi `breaking_news_job` ke `notification_governor`** — ganti `SENT_NEWS_TITLES` (in-memory) dengan `ngov.is_cooldown_allowed`/`ngov.record_cooldown` atau pola dedup persisten serupa, supaya konsisten dengan checker lain dan tidak rentan reset-saat-restart. Prioritas: **sedang** — risiko saat ini laten (belum ada bukti burst nyata karena `alerts_sent` selalu 0), tapi begitu keyword match mulai kena (mis. saat ada breaking news sungguhan), risiko jadi identik dengan insiden 21 Juli yang baru diperbaiki untuk checker lain. Siapkan sebagai prompt perbaikan terpisah sesuai pola kerja yang sudah berjalan.
2. **Investigasi kenapa `alerts_sent=0` selama 7 hari penuh** — tambahkan log jumlah artikel yang berhasil di-fetch di `_fetch_crypto_news`/`_fetch_macro_news` (mis. `logging.info("_fetch_crypto_news: %d artikel", len(out))`) supaya bisa dibedakan "NewsAPI kosong" vs "tidak match keyword". Tanpa ini, tidak mungkin tahu apakah fitur breaking-news benar-benar berfungsi atau sudah lama diam-diam mati.
3. **Cek `FMP_API_KEY`** — HTTP 403 konsisten di setiap siklus mengindikasikan key invalid/expired/plan tidak sesuai. Kalau memang tidak terpakai lagi, pertimbangkan nonaktifkan pemanggilannya supaya tidak membuang request tiap jam; kalau masih ingin dipakai, perbarui key-nya.
4. **Perbarui/hapus TODO di `macro_checker.py:7-8`** — TODO ini sudah usang secara teknis (fitur yang diminta sudah dibangun di `economic_calendar.py`), tapi menyesatkan pembaca kode yang mengira integrasi real-time belum ada. Ganti dengan catatan status real (FMP/Investing.com sedang down, sistem jalan di mode rule-based).
5. **(Opsional, prioritas rendah)** Tambahkan cache TTL pendek (mis. 5-10 menit) ke `_fetch_crypto_news`/`_fetch_macro_news` supaya morning/evening brief tidak bersaing kuota dengan breaking_news_job di hari yang sama.

Semua temuan di atas didokumentasikan untuk keperluan prompt perbaikan terpisah — **tidak ada perubahan kode yang dilakukan dalam audit ini.**
