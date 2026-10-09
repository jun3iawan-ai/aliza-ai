# Audit Read-Only: Perbedaan "Radar Market" (`/radar`) vs "Radar Pro" (`/radarpro`)

**Tipe:** Audit read-only murni. Tidak ada perubahan kode/commit/restart di task ini.
**Tanggal:** 2026-09-18
**Lokasi kode yang diaudit:**
- `interfaces/telegram_bot.py:1603-1651` (handler `radar` dan `radarpro_command`, registrasi `CommandHandler` di baris 7823-7824)
- `engine/market/market_radar_pro_analyzer.py` (162 baris, seluruh file)
- `engine/market/market_radar.py` (267 baris, seluruh file)
- `engine/market/market_radar_pro.py` (129 baris, seluruh file)
- `engine/market/market_snapshot_engine.py` (bagian `update_market_snapshot`, sekitar baris 330-355)
- `engine/market/market_analyzer.py` (bagian `market_signal`, sekitar baris 400-530)
- `engine/market/features.py` (bagian multi-timeframe alignment, baris 100-171)
- `engine/detectors/crash_detector.py`, `whale_accumulation_detector.py`, `altseason_detector.py`, `liquidation_detector.py` (seluruh file, masing-masing di bawah 70 baris)
- `engine/market/global_market_cache.py` (bagian `_fetch_fear_greed`, `_fetch_btc_dominance`, `get_global_market_data`)
- `engine/market/market_universe.py:15-21` (watchlist)

---

## Ringkasan Eksekutif (baca ini dulu)

1. **`/radar` dan `/radarpro` memanggil fungsi data yang PERSIS SAMA**: `generate_radar_pro()` dari `market_radar_pro_analyzer.py`. Keduanya bukan dua sistem radar yang independen — keduanya adalah **dua tampilan berbeda dari satu struktur data yang sama**, dipanggil dua kali secara terpisah (snapshot dibaca dua kali, detector dijalankan dua kali per invocation, boros tapi tidak salah).
2. Perbedaan nyata bukan di sumber data, tapi di **field mana dari struktur data itu yang ditampilkan**:
   - `/radar` menampilkan `trend_alignment` (konsensus tren multi-timeframe 4h+1d, murni teknikal per-coin).
   - `/radarpro` menampilkan `trend` + `label` (label intelijen: Crash Risk, Whale Activity/Accumulation, Momentum, Breakdown Risk, Altseason Signal, Long Liquidation, Short Squeeze, Strong Trend, Neutral).
3. File `engine/market/market_radar_pro.py` (fungsi `analyze_market()`) **adalah dead code** — tidak dipanggil dari mana pun di jalur `/radar`/`/radarpro` maupun modul lain, dan **importnya sendiri rusak** (`from engine.market_cache import get_all_market_data` menunjuk ke path yang tidak ada; modul yang benar ada di `engine/utils/market_cache.py`). Ini sudah pernah ditandai di audit sebelumnya (`docs/reports/2026-07-21-maintenance/REPO_CLEANUP_REPORT.md` baris 186 & 204) sebagai "Tidak ada import; memakai import lama `engine.market_cache`" — temuan saya mengkonfirmasi ulang dan menambahkan bukti bahwa importnya benar-benar akan gagal jika dieksekusi.
4. File `engine/market/market_radar.py` (fungsi `market_radar()`) **BUKAN dead code** — tapi juga **tidak dipanggil langsung oleh `/radar` atau `/radarpro`**. Fungsi ini dipanggil oleh `market_snapshot_engine.py` SEKALI per siklus snapshot untuk menghasilkan sinyal market **global** (whale activity, market risk score, market phase prediction, dst.), yang kemudian disuntikkan ke SETIAP coin di snapshot lewat `market_analyzer.py`. Jadi `market_radar.py` adalah **hulu tidak langsung** dari kedua command, bukan paralel/kompetitor `market_radar_pro_analyzer.py`.
5. **Temuan kualitas data yang perlu diketahui user**: field `whale_activity` dan `market_risk_score` yang dipakai `generate_radar_pro()` untuk memberi label per-coin sebenarnya adalah **nilai global** (dihitung sekali dari transaksi whale BTC on-chain + fear&greed + BTC dominance), lalu **disalin identik ke semua 21 coin** di watchlist. Ditambah ada bug logika di `generate_radar_pro()`: label default "⚠ Crash Risk" (dari `risk == "HIGH"`, baris 75-76) dipasang untuk SEMUA coin sebelum detector kontekstual (`detect_crash_risk`) berjalan, dan detector tersebut **tidak pernah membatalkan** label itu jika hasilnya `False` — hanya menegaskan ulang jika `True` (baris 88-97, tidak ada `else`). Efeknya: begitu kondisi market risk global menjadi HIGH, **seluruh 21 coin di `/radarpro` akan menampilkan label "⚠ Crash Risk"**, termasuk coin yang sebenarnya bullish/tidak berisiko sama sekali. Ini analog dengan pola "auto-alert threshold salah secara diam-diam" yang pernah ditemukan di fitur lain. Detail di bagian 5.
6. Ada juga fallback diam-diam yang belum ditutup di jalur ini: `fear_greed` dan `btc_dominance` fallback ke `50.0` saat API gagal, dengan flag status `"failed"` yang **sudah dibuat** di `global_market_cache.py` untuk fitur lain (Info Coin) — tapi `market_snapshot_engine.py` (yang memanggil `market_radar()`) **tidak membaca flag status ini sama sekali**, jadi kegagalan API fear&greed/dominance akan diam-diam mempengaruhi label radar tanpa indikasi apa pun ke user. Detail di bagian 5.

---

## 1. Alur kode masing-masing command

### 1.1 `/radar` → `radar()` (`interfaces/telegram_bot.py:1623-1640`)

```python
async def radar(update, context):
    radar_data = generate_radar_pro()
    if not radar_data:
        await update.message.reply_text("Radar market tidak tersedia.")
        return
    lines = ["📡 ALIZA MARKET RADAR\n"]
    for item in radar_data:
        coin = item.get("coin", "")
        alignment = item.get("trend_alignment", "UNKNOWN")
        label = _format_alignment_label(alignment)   # baris 1605-1620
        lines.append(f"{coin} → {label}")
    lines.append(f"\n🕒 Market Snapshot : {get_snapshot_timestamp_str()}")
    await update.message.reply_text("\n".join(lines))
```

- Memanggil `generate_radar_pro()` — **fungsi yang sama** yang dipakai `/radarpro`, diimpor dari `engine.market.market_radar_pro_analyzer` (import di `interfaces/telegram_bot.py:79-81`).
- Hanya memakai field `trend_alignment` dari tiap item, dipetakan lewat helper lokal `_format_alignment_label()` ke label tampilan:
  - `STRONG_BULLISH` → `STRONG_BULLISH 🔥`
  - `STRONG_BEARISH` → `STRONG_BEARISH ❄️`
  - `BULLISH` → `BULLISH ↑`
  - `BEARISH` → `BEARISH ↓`
  - `MIXED` → `MIXED ⚠️`
  - `PARTIAL` → `PARTIAL`
  - default → `UNKNOWN`
- **Field `label` (Crash Risk/Whale/Momentum/dst.) dari `generate_radar_pro()` SAMA SEKALI TIDAK DIPAKAI** oleh `/radar`. Command ini murni menampilkan konsensus tren multi-timeframe.
- Modul `market_radar.py` **tidak dipanggil langsung** di sini.

### 1.2 `/radarpro` → `radarpro_command()` (`interfaces/telegram_bot.py:1643-1651`)

```python
async def radarpro_command(update, context):
    radar = generate_radar_pro()
    message = format_radar_pro_report(radar)
    await update.message.reply_text(message)
```

- Memanggil `generate_radar_pro()` — sumber data identik dengan `/radar` (dipanggil ulang, bukan reuse hasil dari `/radar`).
- Memformat lewat `format_radar_pro_report()` (`market_radar_pro_analyzer.py:143-162`), yang menampilkan `trend` (+ arrow) dan `label` (Crash Risk/Whale/dst.) — bukan `trend_alignment`.
- Tidak ada pemanggilan ke `market_radar_pro.py` di jalur ini — dikonfirmasi lewat pencarian import (lihat bagian 2).

**Kesimpulan bagian 1:** Kedua command 100% berbagi sumber data (`generate_radar_pro()` dari `market_radar_pro_analyzer.py`), tapi menampilkan dua field berbeda dari struktur data yang sama. `market_radar_pro.py` tidak terlibat sama sekali di kedua jalur ini.

---

## 2. Peran `market_radar_pro.py` — dead code candidate

Pencarian menyeluruh:

```
$ grep -rn "market_radar_pro\b" --include="*.py" .   # tanpa _analyzer
(tidak ada hasil di luar file itu sendiri)

$ grep -rn "analyze_market\b" --include="*.py" .
engine/market/market_radar_pro.py:8:def analyze_market():
(tidak ada caller lain, termasuk tidak ada di tests/)
```

- **Tidak ada satu pun pemanggil** untuk modul `market_radar_pro.py` maupun fungsi `analyze_market()` di seluruh repo (termasuk `tests/`).
- Modul ini mengimpor `from engine.market_cache import get_all_market_data` (baris 1) — path `engine/market_cache.py` **tidak ada** di repo; modul yang benar-benar ada adalah `engine/utils/market_cache.py`. Verifikasi:
  ```
  $ python3 -c "import engine.market_cache"
  ModuleNotFoundError: No module named 'engine.market_cache'
  ```
  Artinya kalau modul ini pernah dipanggil, ia akan langsung crash dengan `ImportError` saat load — bukan cuma "tidak terpakai", tapi **rusak** jika dipaksa dijalankan.
- Sudah pernah ditandai di audit sebelumnya: `docs/reports/2026-07-21-maintenance/REPO_CLEANUP_REPORT.md:186,204` — "Tidak ada import; memakai import lama `engine.market_cache`", status "PERLU KONFIRMASI USER". Temuan saya mengkonfirmasi status itu masih berlaku dan menambah detail bahwa importnya definitif rusak (bukan cuma "lama").
- **Rekomendasi:** tandai sebagai kandidat dead code untuk dihapus atau diarsipkan — TIDAK dihapus di task ini sesuai instruksi (read-only). Isi fungsional modul ini (`analyze_market()`: BTC bottom detector, crash alert, whale tracker, altseason signal, elite trade scanner — berbasis `get_all_market_data()` dan format pesan alert siap-kirim) tumpang tindih konsep dengan detector-detector yang sekarang dipakai `market_radar_pro_analyzer.py` (`crash_detector.py`, `whale_accumulation_detector.py`, `altseason_detector.py`, `liquidation_detector.py`), jadi kemungkinan besar ini adalah versi lama/prototipe yang sudah digantikan oleh arsitektur detector saat ini, tapi filenya tidak pernah dibersihkan.

---

## 3. Tabel Perbandingan Sisi-Berdampingan

| Aspek | 📡 Radar Market (`/radar`) | 📡 Radar Pro (`/radarpro`) |
|---|---|---|
| **Sumber data mentah** | `generate_radar_pro()` di `market_radar_pro_analyzer.py:48-140`, yang membaca `get_market_snapshot()` dari `market_snapshot_engine.py` (snapshot per-coin di-refresh oleh job background, bukan fetch API langsung saat command dipanggil). **Identik dengan `/radarpro`.** | Sama persis: `generate_radar_pro()` dari `market_radar_pro_analyzer.py`, dipanggil ulang secara terpisah (baca snapshot & jalankan semua detector kedua kalinya, bukan reuse hasil `/radar`). |
| **Field yang benar-benar ditampilkan per coin** | Hanya `trend_alignment` (multi-timeframe 4h+1d, dari `features.py:159,171` via `analyze_multi_timeframe()`), dipetakan ke label lewat `_format_alignment_label()` (`telegram_bot.py:1605-1620`). | `trend` (BULLISH/BEARISH/SIDEWAYS, dari moving-average `trend_from_ma()` di `market_analyzer.py`) + arrow (`_trend_arrow()`) + `label` intelijen (Crash Risk/Whale Activity/Whale Accumulation/Momentum/Breakdown Risk/Altseason Signal/Long Liquidation/Short Squeeze/Strong Trend/Neutral) hasil kaskade 5 pengecekan di `generate_radar_pro()` baris 74-128. |
| **Indikator/metrik yang mendasari label** | Konsensus tren 4h vs 1d murni (tidak melibatkan RSI, whale, risk score, liquidation). | Kombinasi: `market_risk_score` (global), `whale_activity` (global), RSI per-coin, `trend` per-coin, plus 4 detector kontekstual: `detect_crash_risk` (risk HIGH + bearish/overbought/liquidation kuat), `detect_altseason` (BTC sideways + alt bullish + RSI≥60), `detect_whale_accumulation` (whale HIGH/EXTREME + sideways + RSI 45-60), `detect_liquidation_cascade` (risk HIGH + RSI ekstrem + trend searah). |
| **Jumlah coin yang dicakup** | Watchlist tetap 21 coin (`market_universe.py:15-21`: BTC, ETH, BNB, SOL, XRP, ADA, SUI, ARB, PEPE, JTO, ETHFI, WLD, OM, ASTER, XPL, TAO, BONE, FARTCOIN, HYPE, ZEREBRO, XAUT), minus coin yang snapshot-nya error (`data.get("error")` truthy, di-skip di `generate_radar_pro()` baris 65-66). | **Identik** — sama-sama lewat `generate_radar_pro()`, tidak ada filter tambahan di level handler. |
| **Kriteria sorting/filtering** | Tidak ada sorting — urutan dict `markets.items()` = urutan watchlist/insertion order snapshot. Tidak ada top-N. | Sama — tidak ada sorting/filtering tambahan, urutan sama persis dengan `/radar` (karena sumber data sama). |
| **Format output** | Satu baris ringkas per coin: `"{COIN} → {ALIGNMENT_LABEL}"`, contoh `BTC → STRONG_BULLISH 🔥`. Header `📡 ALIZA MARKET RADAR`. | Satu baris per coin dengan kolom rata (fixed-width `{coin:4}  {trend:12}  {label}"`), contoh `BTC   BULLISH ↑     🐋 Whale Accumulation`. Header `📡 ALIZA MARKET RADAR PRO`. Ada fallback pesan khusus `"Tidak ada data market."` jika `radar_data` kosong (baris 148-149) — `/radar` hanya balas `"Radar market tidak tersedia."` tanpa header. |
| **Ada scoring/ranking gabungan, atau murni tampilan?** | Murni tampilan satu metrik teknikal (trend alignment) — tidak ada scoring gabungan, tidak ada ranking. | Juga bukan scoring numerik/ranking — tapi labelnya adalah HASIL dari beberapa aturan kondisional berlapis (bukan raw metric tunggal), jadi lebih ke arah "klasifikasi kategori kondisi market" daripada skor. Tidak ada urutan berdasarkan skor risiko (coin dengan risk lebih tinggi tidak dipindah ke atas). |
| **Kapan lebih berguna dipakai** | Cek cepat "arah tren" 21 coin dalam satu pandangan — cocok untuk scan awal harian, tidak butuh detail kenapa. | Untuk menggali "apa yang sedang terjadi" per coin (ada whale? ada risiko crash? ada sinyal altseason?) — cocok sebagai langkah lanjutan setelah `/radar` menunjukkan tren menarik, sebelum masuk ke `/entry` atau `/setfutures`. |

---

## 4. Tumpang tindih / redundansi — analisis

**Kesimpulan: keduanya BUKAN duplikasi murni, tapi juga bukan sepenuhnya "quick view vs deep dive" yang bersih — ada inefisiensi dan satu bug tersembunyi yang mengurangi nilai "Pro".**

- **Bukan duplikasi konten**: field yang ditampilkan (`trend_alignment` vs `trend`+`label`) benar-benar berbeda secara substansi, jadi dari sisi *user-facing value* kedua command tidak redundan — user dapat informasi berbeda dari masing-masing.
- **Redundansi teknis (bukan bug, tapi boros)**: karena keduanya independen memanggil `generate_radar_pro()`, setiap kali user menjalankan `/radar` lalu `/radarpro` (atau sebaliknya) dalam waktu berdekatan, seluruh snapshot dibaca ulang dan ke-4 detector (`crash`, `altseason`, `whale_accumulation`, `liquidation`) dijalankan ulang untuk 21 coin — tidak ada caching/reuse antar command dalam satu request cycle. Ini tidak menyebabkan data beda (snapshot sama karena keduanya baca cache yang sama, bukan fetch API baru), hanya CPU/logging berulang secara sia-sia.
- **Nama membingungkan**: `/radar` (fungsi handler bernama `radar`) dan `/radarpro` (fungsi handler `radarpro_command`) sama-sama bersumber dari file bernama `market_radar_pro_analyzer.py` — nama file ini menyebut "pro" padahal dipakai juga oleh command yang BUKAN "pro". Ini murni penamaan yang membingungkan untuk siapa pun yang membaca kode, meski tidak berdampak fungsional.
- **`market_radar.py` vs `market_radar_pro_analyzer.py`**: ini bukan tumpang tindih — `market_radar.py` adalah hulu (upstream, dipanggil oleh snapshot engine untuk hasilkan sinyal global), `market_radar_pro_analyzer.py` adalah hilir (downstream, konsumsi snapshot yang sudah diperkaya). Relasinya berurutan (pipeline), bukan paralel/kompetitif.
- **`market_radar_pro.py`**: seperti dibahas di bagian 2, ini kandidat dead code yang konsepnya tumpang tindih dengan detector-detector aktif saat ini, tapi tidak dipakai — bukan redundansi aktif, melainkan sisa kode lama yang belum dibersihkan.

---

## 5. Kualitas Data — dua temuan konkret

### 5.1 Label "⚠ Crash Risk" bisa menempel ke SEMUA coin secara keliru (mempengaruhi `/radarpro` saja, tidak `/radar`)

Di `generate_radar_pro()` (`market_radar_pro_analyzer.py:74-97`):

```python
# Default label dari kondisi existing
if risk == "HIGH":
    label = "⚠ Crash Risk"          # (a) dipasang untuk SEMUA coin jika risk global == HIGH
elif whale in ["HIGH", "EXTREME"]:
    label = "🐋 Whale Activity"
...

crash_risk_flag = False
if detect_crash_risk is not None:
    try:
        crash = detect_crash_risk(data)
        crash_risk_flag = bool(crash.get("crash_risk"))
        if crash_risk_flag:
            label = "⚠ Crash Risk"   # (b) hanya MENEGASKAN ulang jika True — TIDAK ADA else untuk membatalkan (a)
    except Exception as e:
        ...
```

- `risk` (`market_risk_score`) adalah **nilai global**, sama untuk 21 coin dalam satu siklus snapshot (lihat 5.2 untuk buktinya).
- Begitu `risk == "HIGH"` secara global, baris (a) memasang label "⚠ Crash Risk" untuk **setiap** coin di loop, sebelum `detect_crash_risk()` (kontekstual, per-coin, butuh trend BEARISH atau RSI≥70 atau liquidation kuat) sempat menilai.
- `detect_crash_risk()` di baris (b) **tidak punya cabang `else`** untuk mengembalikan label ke kondisi lain (Momentum/Strong Trend/Neutral) kalau hasilnya `False` untuk coin tertentu. Jadi walau `detect_crash_risk()` menyimpulkan coin X sebenarnya TIDAK berisiko crash (misalnya X sedang BULLISH kuat), label X tetap "⚠ Crash Risk" karena sudah kadung dipasang di baris (a).
- **Dampak nyata**: setiap kali kondisi global memicu `market_risk_score == "HIGH"` (lihat 5.2 — butuh fear&greed sangat rendah DAN BTC dominance tinggi secara bersamaan), `/radarpro` akan menampilkan "⚠ Crash Risk" untuk semua 21 coin di watchlist, termasuk coin yang sedang bullish/momentum kuat/altseason — informasi yang menyesatkan untuk fitur yang namanya "Pro".
- **`/radar` tidak terpengaruh** oleh bug ini karena hanya membaca `trend_alignment`, bukan `label`.

### 5.2 `whale_activity` & `market_risk_score` adalah nilai GLOBAL, bukan per-coin

Alur pembuktian:
1. `market_snapshot_engine.py` (baris ~348-354) memanggil `market_radar(fear, dominance)` **sekali per siklus snapshot** (bukan per coin) dan menyimpan hasilnya di variabel `radar_data`.
2. `radar_data` yang sama itu diteruskan ke `generate_signal(symbol, radar_data)` untuk **setiap** coin di watchlist (`engine/market_signal.py:10-11` → `market_analyzer.py:market_signal()`).
3. Di `market_analyzer.py:481-493`, field-field berikut disalin **langsung dari `radar` (objek global yang sama)** ke output tiap coin tanpa modifikasi per-coin:
   ```python
   "whale_activity": radar.get("whale_activity", "UNKNOWN"),
   "market_phase_prediction": radar.get("market_phase_prediction", "UNKNOWN"),
   "market_risk_score": radar.get("market_risk_score", "UNKNOWN"),
   ```
4. Nilai `whale_activity` sendiri berasal dari `whale_intensity(get_large_transactions())` di `market_radar.py:79-92` — jumlah transaksi BTC on-chain bernilai >300 BTC (lewat Blockchair API), **tidak spesifik per altcoin**. `market_risk_score` berasal dari `crash_risk_model(fear, dominance)` — fungsi dari fear&greed dan BTC dominance global, juga tidak spesifik per coin.

**Implikasi**: label "🐋 Whale Activity" atau nilai risk "HIGH" yang tampak di baris per-coin `/radarpro` sebenarnya mencerminkan kondisi pasar BTC/global secara keseluruhan, bukan aktivitas whale spesifik pada coin tersebut (misal PEPE atau FARTCOIN). Ini bukan bug per se (arsitekturnya memang dirancang begitu — detector kontekstual menggabungkan sinyal global ini dengan trend/RSI per-coin), tapi **tidak jelas dari tampilan Telegram** bahwa "Whale Activity" pada baris SOL sebenarnya adalah sinyal whale BTC, bukan whale SOL. Berpotensi menyesatkan user yang mengira setiap baris murni analisis per-koin.

### 5.3 Fallback diam-diam fear&greed / BTC dominance ke 50.0 — flag status ada tapi tidak dipakai di jalur radar

`engine/market/global_market_cache.py`:
```python
def _fetch_fear_greed():
    """... value defaults to 50.0 on failure ... status ("ok"/"failed") lets callers
    that care (e.g. the Info Coin display) distinguish a real 50 from "fetch gagal, ini default" """
    ...
    return 50.0, "failed"

def _fetch_btc_dominance():
    """... value defaults to 50.0 on failure ..."""
```

`get_global_market_data()` mengembalikan `fear_greed_status`/`btc_dominance_status` ("ok"/"failed") — sengaja ditambahkan (komentar eksplisit menyebut dipakai fitur "Info Coin") supaya konsumen yang peduli bisa membedakan nilai asli 50 dari fallback gagal-fetch.

Tapi di `market_snapshot_engine.py`:
```python
global_data = get_global_market_data()
radar_data = market_radar(global_data.get("fear_greed"), global_data.get("btc_dominance"))
```
**Tidak ada pengecekan `fear_greed_status`/`btc_dominance_status`** sebelum nilainya dipakai untuk `market_radar()`. Jadi kalau Fear&Greed API dan/atau CoinGecko+CoinPaprika (BTC dominance) sama-sama gagal, `market_radar()` akan diam-diam menghitung `cycle_phase`, `crash_risk_model`, dst. dari `fear=50.0, dominance=50.0` seolah itu data pasar riil — persis pola "fallback ke 50 tanpa keterangan" yang disebut user sudah pernah ditemukan di fitur lain, dan di jalur radar ini **belum ditutup** meski flag status-nya sudah ada di layer bawahnya untuk keperluan fitur lain.

**Dampak ke `/radar` dan `/radarpro`**: keduanya sama-sama terkena, karena keduanya membaca snapshot yang sama yang diperkaya oleh `market_radar()` yang sama.

---

## Jawaban Ringkas untuk Dijelaskan ke User

- **`/radar`** = tampilan cepat arah tren 21 coin (bullish/bearish/mixed, dari multi-timeframe 4h+1d), satu baris per coin, tanpa detail lain.
- **`/radarpro`** = tampilan yang sama snapshot-nya, tapi menunjukkan tren + label kondisi intelijen (whale, crash risk, altseason, liquidation) hasil kombinasi sinyal global (whale BTC, fear&greed, dominance) dengan RSI/trend per coin.
- Keduanya **memanggil fungsi sumber data yang identik** (`generate_radar_pro()`), bukan dua sistem radar terpisah — jadi tidak ada risiko data "beda versi" antara keduanya, hanya beda tampilan.
- File `market_radar_pro.py` (fungsi `analyze_market()`) tidak dipakai sama sekali dan importnya rusak — aman diabaikan/dihapus, tapi butuh keputusan user karena pernah ditandai sebagai "PERLU KONFIRMASI USER" di audit sebelumnya.
- Ada satu bug nyata di `/radarpro`: saat kondisi market secara global dianggap "HIGH risk", **semua 21 coin** akan diberi label "⚠ Crash Risk" tanpa memandang kondisi masing-masing coin — mengurangi kegunaan fitur "Pro" pada saat-saat volatil justru ketika fitur ini paling dibutuhkan akurat.
- Ada juga celah fallback diam-diam (fear&greed/BTC dominance ke 50.0 saat API gagal) yang mempengaruhi kualitas data di kedua command tanpa ada indikasi ke user bahwa data sedang berbasis fallback.

---

## Catatan Metodologi

- Task ini murni audit read-only: tidak ada file kode yang diubah, tidak ada commit, tidak ada restart service.
- Semua klaim di atas diverifikasi lewat pembacaan langsung isi file (bukan asumsi dari nama file/audit sebelumnya) dan lewat `grep`/`python3 -c "import ..."` untuk memverifikasi keberadaan/kerusakan import.
- Baris kode yang dirujuk mengikuti state repo saat audit dijalankan (2026-09-18); nomor baris berpotensi bergeser jika file diedit setelah ini.
