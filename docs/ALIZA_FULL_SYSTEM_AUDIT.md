# ALIZA AI — FULL SYSTEM AUDIT

> **Status: SUPERSEDED.** Snapshot pada 2025-03-13. Kondisi sistem terkini ada di `docs/README.md` dan report Fase 1–4 (`docs/reports/` — lihat Bagian 3). Jangan jadikan dokumen ini sebagai acuan status aktif.

**Tanggal:** 2025-03-13  
**Scope:** Market Data Layer, Snapshot Engine, Detectors, Trading Brain, Opportunity System, Auto Alert, Telegram Bot, Performance.

---

## 1. SYSTEM HEALTH SUMMARY

| Area | Status | Catatan |
|------|--------|--------|
| Market Data Layer | ⚠️ WARNING | Tanpa penanganan 429; fallback CoinGecko tanpa retry |
| Klines Cache | ✅ OK | TTL konsisten; tidak ada eviction → memory bounded by (symbol × interval) |
| Snapshot Engine | ⚠️ WARNING | Race kecil saat assign data vs timestamp; retry 30s blocking |
| Detector Layer | ⚠️ WARNING | btc_bottom_detector tidak ada; label radar bisa tertimpa berurutan |
| Trading Brain | ⚠️ WARNING | SL/TP bisa 0 jika support/resistance = 0 |
| Opportunity System | ✅ OK | Ranking dan score konsisten; tidak ada duplikat per coin |
| Auto Alert | ⚠️ WARNING | `_last_alerts` tidak pernah dibersihkan → pertumbuhan key unbounded |
| Telegram Bot | ✅ OK | Handler aman; snapshot job terintegrasi dengan benar |
| Performance | ⚠️ WARNING | Banyak API call per cycle; market_radar dipanggil per coin |

**Kesimpulan singkat:** Tidak ada critical bug yang mematikan sistem. Ditemukan beberapa warning (429, race, memory, SL/TP edge case) dan satu modul detector yang tidak ada (btc_bottom). Pipeline market_cache → market_analyzer → market_radar → TradingBrain → trade_setup tetap utuh dan sesuai arsitektur.

---

## 2. CRITICAL BUG

### 2.1 Tidak ada critical bug yang teridentifikasi

Tidak ada bug yang menyebabkan crash langsung atau kehilangan data permanen. Yang mendekati:

- **TradingBrain SL/TP = 0:** Jika `support` atau `resistance` bernilai `0`, maka `sl = support * 0.99` atau `tp1 = resistance` bisa menghasilkan `sl = 0` atau `tp1 = 0`. Kontrak engine mengharapkan nilai numerik valid; downstream (entry, close) bisa bingung. Masuk kategori **warning** (edge case).

---

## 3. WARNING

### 3.1 Market Data Layer

**File:** `engine/market/market_analyzer.py`, `engine/market/klines_cache.py`

- **Error handling API**
  - Binance: hanya `status_code != 200` → return `[]`. **Tidak ada pengecekan 429** (rate limit). Respons 429 tidak di-handle khusus (no backoff/retry).
  - CoinGecko `get_coin_market_chart`: exception di-catch dan return `{}`; tidak ada retry.
- **Fallback CoinGecko**
  - Sudah pakai `days=90` → cukup untuk MA/RSI.
  - Jika Binance 429, fallback ke CoinGecko untuk semua coin dalam satu cycle bisa memicu rate limit CoinGecko juga (banyak request berturut-turut).
- **Cache TTL**
  - `klines_cache`: TTL 4h = 300s, 1d = 600s. Logic `get_cached_klines` / `set_cached_klines` benar.
  - Cache hanya bertambah (set), tidak ada eviction. Key = (symbol, interval); jumlah key terbatas oleh universe coin × 2 interval → **memory aman**.
- **Potensi Binance 429**
  - Setiap snapshot: 1× ticker + 2× klines per coin (cache reduce klines setelah warm). Tanpa 429 handling, saat limit kena semua klines return `[]` → fallback ke CoinGecko untuk setiap coin → beban API tinggi dan indikator bisa seragam/lemah.

### 3.2 Snapshot Engine

**File:** `engine/market/market_snapshot_engine.py`

- **Konsistensi snapshot**
  - `update_market_snapshot()` menulis `market_snapshot["data"] = collected` lalu `market_snapshot["timestamp"] = datetime.utcnow()`. Pembaca bisa dapat `data` baru dengan `timestamp` lama jika read di antara dua baris itu. **Race kecil**, dampak hanya ketidaksesuaian singkat data vs timestamp.
- **Race condition**
  - Snapshot di-update di executor (blocking), dibaca dari main thread (command). Tanpa lock, read dan write bisa bersamaan. Karena assign adalah replace dict, reader dapat dict lama atau baru (utuh), bukan dict setengah tertulis. **Tidak corrupt**, hanya possible stale vs fresh.
- **Data None/corrupt**
  - `validate_market_data` menolak data tanpa price/trend/rsi valid. Coin yang gagal tidak masuk `collected`; snapshot hanya berisi data yang lulus validasi. **Data di snapshot tidak corrupt**.
- **Timestamp**
  - `market_snapshot["timestamp"]` di-set ke `datetime.utcnow()` hanya jika `collected` tidak kosong. Jika semua coin gagal, timestamp tidak di-update (tetap lama). `get_snapshot_timestamp_str()` handle `ts is None` → "—". **Aman**.
- **Blocking retry**
  - Retry failed coins setelah `time.sleep(RETRY_DELAY_SEC)` (30 detik). Selama itu event loop terblok. **Performance/UX warning**.

### 3.3 Detector Layer

**File:** `engine/detectors/*.py`, `engine/market/market_radar_pro_analyzer.py`

- **btc_bottom_detector**
  - **Tidak ada di codebase.** Di `market_radar_pro_analyzer.py` tidak ada import atau pemanggilan `detect_btc_bottom`. Dokumen/spec menyebut "BTC Bottom Detector" tetapi file `btc_bottom_detector.py` tidak ditemukan.
- **Input validation**
  - Semua detector memakai `.get()` dan cek `market_data`/`btc_data` dict; ada try/except. **Tidak ada KeyError** saat key optional.
- **Label conflict**
  - Di `generate_radar_pro()` urutan: default label → crash_risk → altseason → whale_accumulation → liquidation. **Label terakhir menang.** Jika beberapa detector true (mis. crash_risk + liquidation), hanya liquidation yang tampil. Ini design (prioritas), bukan bug; tapi prioritas tidak didokumentasikan.

### 3.4 Trading Brain

**File:** `engine/brain/trading_brain.py`

- **Risk reward**
  - `_risk_reward(entry, sl, tp1)` aman: cek None dan division by zero; return `None` jika invalid.
- **SL/TP validity**
  - Jika `support == 0`: `sl = support * 0.99` → `sl = 0`. Jika `resistance == 0`: `tp1 = resistance` → `tp1 = 0`. Kontrak mengharapkan nilai valid; **nilai 0 bisa lolos** dan merusak interpretasi entry/SL/TP.
- **Smart Trend Filter**
  - Logic MIXED/UNKNOWN → NO SETUP dan allow_long/allow_short sesuai alignment sudah benar.
- **Setup invalid**
  - Untuk NO SETUP, return dengan sl/tp1/tp2 None dan risk_reward None. Untuk setup valid, TP di-cap ±8%. Satu-satunya edge case adalah **support/resistance = 0** seperti di atas.

### 3.5 Opportunity System

**File:** `engine/trading/opportunity_scanner.py`, `engine/brain/opportunity_ranker.py`

- **Duplicate opportunity**
  - Input dari `market_data_dict` adalah symbol → data; satu symbol satu entry. Scanner tidak menghasilkan duplikat (coin, setup) dalam satu run.
- **Ranking & score**
  - `rank_opportunities` memodifikasi list in-place (menambah `score`), lalu sort dan return top 3. Formula: `(rr*40)*(confidence*0.4) + alignment_bonus - risk_penalty`. **Konsisten**.
  - Jika exception, fallback ke `opportunities[:3]` tanpa score; **tidak crash**.

### 3.6 Auto Alert System

**File:** `engine/alerts/auto_alert_engine.py`

- **Spam protection**
  - Cooldown 10 menit per (coin, setup); logic benar.
- **Memory growth `_last_alerts`**
  - Hanya `_last_alerts[key] = now` (set/update). **Tidak ada penghapusan key.** Setiap pasangan (coin, setup) yang pernah trigger alert masuk dict selamanya. Untuk universe tetap (~15 coin × ~3 setup) hanya puluhan key; jika universe dinamis dan sering berubah, key bisa menumpuk. **Unbounded growth** dalam teori.
- **Cooldown**
  - Hanya membandingkan `(now - last) < ALERT_COOLDOWN_SEC`. **Benar**.
- **Alert duplication**
  - Dalam satu run `process_auto_alerts`, tiap (coin, setup) maksimal sekali masuk `to_send` karena setelah add kita set `_last_alerts[key] = now`. Tidak ada duplikat dalam satu batch.

### 3.7 Telegram Bot

**File:** `interfaces/telegram_bot.py`

- **Snapshot scheduler**
  - `snapshot_job` setiap 60s; panggil `update_market_snapshot()` di executor, lalu `scan_opportunities()` + `process_auto_alerts()`. **Sesuai spesifikasi**.
- **Command handler**
  - Handlers pakai try/except dan reply_text fallback; tidak ada API langsung ke exchange. Data dari snapshot/engine. **Aman**.
- **Exception safety**
  - `_error_handler` global ada; per-command ada try/except. Auto alert send failure di-log dan tidak menjatuhkan job.
- **Telegram send failure**
  - `context.bot.send_message` di-wrap try/except; failure hanya warning log. **Aman**.

---

## 4. PERFORMANCE ISSUE

### 4.1 API request per snapshot cycle

- **Per coin:** `market_signal(symbol)` memanggil:
  - 1× Binance ticker (price)
  - 2× Binance klines (4h, 1d) — dikurangi oleh klines cache
  - 0–1× CoinGecko market_chart (jika klines kosong)
  - 1× `market_radar(fear, dominance)` — **market_radar dipanggil per coin**, padahal input hanya fear + dominance (sama untuk semua). Jadi N × (get_large_transactions, get_funding_rate, stablecoin_inflow, get_open_interest, dll).
- **Konsekuensi:** Untuk 15 coin: 15 ticker + 30 klines (atau lebih sedikit jika cache hit) + 15× panggilan market_radar. **market_radar seharusnya sekali per cycle**, bukan per coin.
- **Rate limit**
  - Binance: tanpa 429 handling dan backoff, risiko 429 naik saat cache cold atau universe besar.
  - CoinGecko: dipanggil banyak jika Binance gagal; bisa kena rate limit.

### 4.2 Memory

- **Klines cache:** Bounded (symbol × interval).
- **Snapshot:** Satu dict per coin; bounded.
- **Auto alert `_last_alerts`:** Unbounded jika (coin, setup) baru terus bertambah; dalam praktik kecil.

### 4.3 CPU

- Snapshot jalan di executor; blocking 30s retry bisa membuat job berikutnya tertunda. Rata-rata CPU untuk indikator (MA, RSI, dll) wajar untuk ukuran data saat ini.

---

## 5. RECOMMENDED FIX

### Prioritas tinggi

1. **Pindahkan market_radar keluar dari loop per symbol**  
   Panggil `market_radar(fear, dominance)` **sekali** per snapshot cycle di `update_market_snapshot()` (atau di `market_signal` hanya sekali dan hasilnya di-reuse), lalu pass hasil radar ke setiap `market_signal` atau simpan di level snapshot. Ini mengurangi puluhan panggilan API (Blockchair, funding, OI, dll) per cycle.

2. **Handle Binance 429**  
   Di `_get_binance_klines` (dan bila perlu ticker): deteksi `r.status_code == 429`, log warning, optional backoff (e.g. sleep 60s) dan retry sekali, atau langsung fallback ke CoinGecko tanpa retry berlebihan. Hindari N request CoinGecko bersamaan saat 429.

3. **Validasi SL/TP di TradingBrain**  
   Setelah hitung sl/tp1/tp2 dari support/resistance, jika `sl is not None and sl <= 0` atau `tp1 is not None and tp1 <= 0` (untuk long), treat sebagai invalid setup dan return NO SETUP atau gunakan fallback (mis. price ± persentase).

### Prioritas menengah

4. **Batas ukuran `_last_alerts`**  
   Misalnya: evict key yang lebih lama dari 24 jam, atau batasi maksimal 200 key (FIFO). Atau tetap unbounded dengan dokumentasi bahwa universe harus tetap/terbatas.

5. **Snapshot race**  
   Update atomik: `new_snapshot = {"data": collected, "timestamp": datetime.utcnow()}; market_snapshot.update(new_snapshot)` atau assign sekali ke `market_snapshot` dari objek baru, agar pembaca tidak pernah melihat data baru + timestamp lama.

6. **Retry snapshot tidak blocking**  
   Ganti `time.sleep(RETRY_DELAY_SEC)` dengan penjadwalan retry di cycle berikutnya atau job terpisah, agar executor tidak block 30 detik.

### Prioritas rendah

7. **Dokumentasi prioritas label radar**  
   Di `market_radar_pro_analyzer` atau docs: tulis urutan prioritas detector (liquidation > whale_accumulation > altseason > crash_risk > default) agar maintainer paham.

8. **Buat btc_bottom_detector atau hapus dari spec**  
   Jika fitur "BTC Bottom Forming" diinginkan, tambah `engine/detectors/btc_bottom_detector.py` dan integrasikan ke `generate_radar_pro()`. Jika tidak, hapus dari dokumentasi/spec.

9. **Optional: CoinGecko retry dengan backoff**  
   Untuk `get_coin_market_chart`, pada failure (atau 429) lakukan 1–2 retry dengan exponential backoff agar transient error tidak langsung fallback kosong.

---

## Ringkasan singkat

- **Critical:** Tidak ada.
- **Warning:** 429 tidak di-handle, market_radar per coin, race kecil snapshot, SL/TP = 0, memory `_last_alerts` unbounded, btc_bottom_detector hilang.
- **Performance:** Panggilan API berlebihan karena market_radar per symbol; retry 30s blocking.
- **Rekomendasi utama:** Satu panggilan market_radar per cycle; handle 429; validasi SL/TP; evict atau batasi `_last_alerts`; perbaiki race dan blocking retry jika memungkinkan.
