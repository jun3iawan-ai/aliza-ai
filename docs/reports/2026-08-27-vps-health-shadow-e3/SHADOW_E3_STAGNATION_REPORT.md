# Investigasi Stagnasi shadow_e3 (candidates=0 sejak ~18 Agustus 2026)

**Tanggal investigasi:** 2026-08-27
**Sifat:** Investigasi READ-ONLY MURNI — tidak ada kode, `.env`, atau konfigurasi yang diubah; tidak ada service yang di-restart. Satu-satunya perubahan adalah dua salinan laporan ini.
**Rujukan:** `VPS_HEALTH_REPORT_2.md` (§6.2), `BIG_MOVE_REAL_1H_FIX_REPORT.md`.

---

## Ringkasan eksekutif

**Kesimpulan: B — KONDISI/MEKANISME PASAR, BUKAN BUG/REGRESI KODE.**

`shadow_e3` berhenti menghasilkan kandidat sejak sinyal terakhirnya (`BTC OVERBOUGHT REJECTION SHORT`, 2026-08-18 00:05:34 UTC) karena market_regime global (dihitung dari data BTC) telah berpindah ke **`TREND`** (BTC dalam uptrend kuat berkelanjutan — RSI 4h sempat mencapai ~94 pada 21 Agustus). Dalam kondisi regime `TREND`, filter strategi bawaan sistem (`engine/strategy/strategy_regime_map.py`) **tidak mengizinkan** kedua satu-satunya setup yang pernah dihasilkan `shadow_e3` sepanjang sejarahnya — `OVERSOLD BOUNCE` dan `OVERBOUGHT REJECTION` — kecuali regime adalah `RANGE` (keduanya) atau `DOWNTREND` (khusus `OVERBOUGHT REJECTION`). Mekanisme ini sudah ada di kode **jauh sebelum** `shadow_e3` dibuat dan **tidak berubah sama sekali** sejak deploy `shadow_e3` (21 Juli 2026) hingga sekarang — dikonfirmasi lewat `git log` per-file dan lewat nihilnya exception/traceback di seluruh log yang tersedia (20–27 Agustus). Reproduksi manual langsung terhadap data pasar live pada 27 Agustus 2026 mengonfirmasi mekanisme ini bekerja persis seperti dijelaskan.

Tidak ditemukan bug, exception tersembunyi, atau perubahan kode yang menjelaskan berhentinya kandidat. Namun ditemukan **karakteristik struktural penting** dari `shadow_e3` yang sebelumnya tidak terdokumentasi: strategi ini secara desain **hanya bisa aktif saat regime pasar `RANGE`/`DOWNTREND`**, sehingga akan selalu senyap total selama pasar trending kuat — berapa pun lama itu berlangsung. Ini punya implikasi langsung untuk jadwal evaluasi promosi 1 September (lihat Rekomendasi).

---

## 1. Logika lengkap `engine/shadow/e3_shadow.py`

File: `/opt/aliza-ai/engine/shadow/e3_shadow.py` (158 baris, tidak berubah sejak commit `bff3128`, 25 Juli 2026 — lihat §2).

Alur `collect_shadow_signals(snapshot)` (baris 136–146) per coin dalam `snapshot["data"]` (watchlist tetap 21 coin, `engine/market/market_universe.py:15-21`):

1. `enabled()` (baris 31–32) — modul off total kalau `SHADOW_E3_ENABLED` bukan truthy. **Terverifikasi ON** di `.env` (lihat `VPS_HEALTH_REPORT_2.md` §8).
2. `_closed_4h_klines(symbol)` (baris 50–92) — fetch langsung `GET https://api.binance.com/api/v3/klines` interval `4h` limit `100`, cache in-memory TTL 900 detik, buang candle yang belum closed. Early-return `[]` (list kosong, **tanpa exception**) jika HTTP status ≠ 200 (log `WARNING`, baris 66) atau request gagal (log `WARNING`, baris 70) — **nihil kejadian ini di log 20–27 Agustus** (lihat §3).
3. `build_shadow_signal(symbol, market_data, rows)` (baris 95–133) — **daftar lengkap semua early-return**:
   - baris 97: `market_data` bukan dict, atau `len(rows) < 15` → `None`.
   - baris 101: `atr = average_true_range(rows, 14)[-1]`; jika `None` atau `<=0` → `None`.
   - baris 105–109: `TradingBrain().analyze(data)` dibungkus `try/except Exception` generik → log `WARNING` lalu `None` bila exception. **Nihil kejadian ini di log** (lihat §3) — jalur ini tidak pernah gagal secara exception.
   - baris 110: `signal` falsy atau `signal["setup"] in (None, "NO SETUP")` → `None`. **Inilah gerbang yang, berdasarkan reproduksi §5, terpicu untuk 100% coin di 100% siklus sejak 18 Agustus.**
   - baris 115: `side` bukan `LONG`/`SHORT`, atau `entry <= 0` → `None`.
   - baris 117–120: **filter jarak-ke-support ≤1% — HANYA berlaku untuk setup `OVERSOLD BOUNCE`** (`entry > support * 1.01` → `None`). Setup lain (termasuk `OVERBOUGHT REJECTION`) **tidak** difilter jarak di level file ini.
4. Kalau lolos semua: SL = `entry ∓ 1×ATR14(4h)`, TP = `entry ± 3×ATR14(4h)`, `risk_reward=3.0`, `source="shadow_e3"` (baris 121–133) — sesuai deskripsi eksperimen di health report.

**Dependency langsung:**
- ATR: `engine.market.features.average_true_range` (`/opt/aliza-ai/engine/market/features.py:58-78`, Wilder ATR).
- Setup/side/entry: `engine.brain.trading_brain.TradingBrain.analyze()` (`/opt/aliza-ai/engine/brain/trading_brain.py`) — **gerbang sesungguhnya**, lihat §4.
- `market_data` per coin: dihasilkan oleh `engine.market.market_analyzer.market_signal()` (`/opt/aliza-ai/engine/market/market_analyzer.py:269-504`), dipanggil dari `market_snapshot_engine.update_market_snapshot()` per siklus `snapshot_job` (tiap 1 menit, `interfaces/telegram_bot.py:7448-7550`), lalu `_run_shadow_e3(snapshot, chat_id)` dipanggil di baris 7550 setiap siklus.

---

## 2. Riwayat commit sejak 21 Juli 2026 — tidak ada regresi kode di jalur ini

`git log --oneline --since="2026-07-21"` untuk setiap file dependency:

| File | Commit sejak 21 Juli | Tanggal | Relevansi |
|---|---|---|---|
| `engine/shadow/e3_shadow.py` | `bff3128` fix: add persisted cooldown to shadow_e3 dispatch, stop SUI spam | 2026-07-25 07:37 | Hanya menambah cooldown dispatch Telegram (`_shadow_signal_allowed`/`_record_shadow_cooldown` di `interfaces/telegram_bot.py`), **tidak menyentuh logika candidate generation** (`build_shadow_signal`/`collect_shadow_signals`). Ini terjadi sebelum periode produktif 24 Jul–18 Agu, jadi bukan penyebab drop-off. |
| `engine/market/features.py` | tidak ada | — | Tidak berubah sejak `63cace6` (21 Juli, sebelum `shadow_e3` dibuat). |
| `engine/brain/trading_brain.py` | tidak ada relevan | — | Commit `5d54ddb`/`b7cb149` bertanggal 21 Juli **08:42–08:49**, yaitu **sebelum** `shadow_e3` bahkan dibuat (`fe7c18e` pukul 12:36 di hari yang sama). Tidak ada commit setelahnya. |
| `engine/strategy/strategy_engine.py`, `strategy_filter.py`, `strategy_regime_map.py` | tidak ada | — | Nihil histori commit sejak 21 Juli sama sekali (file lebih lama, tidak tersentuh). |
| `engine/intelligence/market_regime_detector.py`, `market_intelligence_engine.py` | tidak ada relevan | — | Idem. |
| `engine/market/multi_timeframe_analyzer.py`, `risk_manager.py` | `5d54ddb` saja | 2026-07-21 08:49 | Sebelum `shadow_e3` ada. |

**Kesimpulan bagian ini:** seluruh rantai kode yang menentukan apakah `shadow_e3` menghasilkan kandidat (`e3_shadow.py` → `TradingBrain.analyze()` → `strategy_engine.filter_setup()` → `strategy_regime_map.STRATEGY_MAP` → `market_regime_detector.detect_market_regime()`) **tidak mengalami satu pun perubahan** antara commit yang men-deploy `shadow_e3` (21 Juli) dan hari ini (27 Agustus). Ini menyingkirkan kemungkinan regresi kode sebagai penyebab.

**Commit "big-move real 1h fix"** (`9dc9782`, di-merge `2c283f9`, 5 Agustus 2026): hanya mengubah `engine/market/market_snapshot_engine.py` (field `price_change_1h` untuk BIG MOVE ALERT) dan menambah test baru. **Tidak menyentuh** `_closed_4h_klines()` milik `e3_shadow.py` (fungsi terpisah, cache terpisah, endpoint yang sama tapi request independen) maupun `market_analyzer.market_signal()` (path ATR/RSI/support/trend E3 yang sesungguhnya dipakai). Verifikasi: `git show 9dc9782 --stat` hanya menyentuh `engine/market/market_snapshot_engine.py` dan `tests/test_big_move_real_1h_change.py` (dikonfirmasi juga oleh laporan asli, §1 "Scope merge: tepat dua berkas").

**Gate `data_coverage`/`insufficient_4h`/`insufficient_1d`** (Fase 1d, commit `86dfcb0`/`6831ad0`, 21 Juli 10:07–10:09, **sebelum** `shadow_e3` dibuat): gate ini murni observability — dipakai untuk menentukan `trend_4h`/`trend_1d`/`alignment` di `market_analyzer.market_signal()` (baris 353–370). Reproduksi live (§5) menunjukkan gate ini berjalan normal — `data_coverage.reason == "ok"` untuk semua 6 coin yang diuji, `klines_4h=99`/`klines_1d=99` (dari limit 100), bukan `insufficient_*`. Gate ini **tidak** dalam kondisi gagal diam-diam.

---

## 3. Log mentah — cakupan aktual dan pola

**Cakupan log yang benar-benar terbaca (diverifikasi langsung, bukan asumsi):**

| Sumber | Rentang tanggal terverifikasi |
|---|---|
| `journalctl -u aliza-telegram` | 2026-08-23 09:01 WIB → sekarang (boot journal ini saja; retensi pendek, sudah dicatat di health report) |
| `/opt/aliza-ai/logs/aliza.log.7.gz` (file tertua yang ada) | **2026-08-20 00:00:08 → 2026-08-20 23:59:53** (baris pertama/terakhir dicek langsung) |
| `aliza.log.6.gz` … `aliza.log.1` | 2026-08-21 → 2026-08-26, satu file per hari |
| `aliza.log` (aktif) | 2026-08-27 00:00:12 → 08:17:17 (saat investigasi) |

**Tidak ada log yang mencakup 18–19 Agustus 2026** (hari sinyal terakhir tercatat) — file tertua yang tersisa (`aliza.log.7.gz`) mulai 20 Agustus. Rotasi harian menyimpan 8 hari (`aliza.log` + `.1` + `.2.gz`…`.7.gz`), jadi jendela 18–19 Agustus sudah terhapus rotasi sebelum audit ini dijalankan. **Ini adalah keterbatasan nyata**: transisi persis dari "menghasilkan kandidat" ke "candidates=0" tidak bisa dilihat di log — hanya bisa diverifikasi *state-nya sudah 0 sejak 20 Agustus* dan *tetap 0 hingga sekarang*.

**Pola dalam jendela yang tersedia (20–27 Agustus, dihitung langsung per file):**

```
grep -o "shadow_e3 candidates=[0-9]*" <tiap file> | sort | uniq -c
aliza.log.7.gz (20 Agu): 1433 baris "candidates=0" — 0 baris "candidates=N>0"
aliza.log.6.gz (21 Agu): 1432 baris "candidates=0"
aliza.log.5.gz (22 Agu): 1436 baris "candidates=0"
aliza.log.4.gz (23 Agu): 1436 baris "candidates=0"
aliza.log.3.gz (24 Agu): 1436 baris "candidates=0"
aliza.log.2.gz (25 Agu): 1436 baris "candidates=0"
aliza.log.1    (26 Agu): 1435 baris "candidates=0"
aliza.log      (27 Agu, parsial): 496 baris "candidates=0"
```

Total **11 340 baris berturut-turut**, **100% candidates=0**, tanpa satu pun pengecualian, selaras dengan `shadow_e3 recorded=0` (baris `interfaces/telegram_bot.py:7441`) yang hitungannya identik per file — mengonfirmasi tidak ada kandidat yang "hilang" karena cooldown dispatch (kandidat tetap direkam ke DB dengan `dispatch_status=COOLDOWN` walau dispatch Telegram ditahan; baris `record_signal(shadow)` dipanggil untuk setiap kandidat terlepas dari status dispatch — lihat `interfaces/telegram_bot.py:7422-1440`).

**Exception/traceback terkait `shadow_e3`/`e3_shadow`:** **NIHIL** di seluruh 8 file log yang tersedia. Grep untuk `"shadow_e3 kline"`, `"shadow_e3 TradingBrain"`, `"shadow_e3 dispatch failed"`, `"shadow_e3 runtime error"` — semuanya 0 kemunculan. Format log (`"shadow_e3 candidates=%d"`, sumber: `e3_shadow.py:145`) identik di semua file — **kode tidak berubah, formatnya juga tidak berubah**, hanya nilainya yang konstan 0.

**Contoh baris lama (candidates=N>0) tidak tersedia di log** (di luar jendela retensi), tapi tercermin di database `signal_tracking` (lihat §5.3) — sinyal terakhir dengan hasil non-nol adalah baris DB `id=119`, `BTC OVERBOUGHT REJECTION SHORT`, `signal_time=2026-08-18T00:05:34.932034+00:00`.

---

## 4. Mekanisme gerbang sesungguhnya — `TradingBrain.analyze()` + filter regime

Reproduksi (§5) menunjukkan bahwa `TradingBrain().analyze()` mengembalikan `setup="NO SETUP"` (atau `None` outright) untuk semua coin di semua siklus sejak ±18 Agustus. Membaca lengkap `/opt/aliza-ai/engine/brain/trading_brain.py`, ada **empat gerbang berlapis** sebelum setup apa pun bisa lolos ke `e3_shadow.py`:

1. **Gerbang alignment** (baris 122–136): jika `trend_alignment` (dihitung `engine/market/multi_timeframe_analyzer.py` dari MA 4h & 1d) adalah `MIXED`/`UNKNOWN`/`None` → langsung `NO SETUP`, **RSI tidak pernah dicek**.
2. **Gerbang RSI ekstrem** (baris 148–179): hanya `rsi<30` → `OVERSOLD BOUNCE`, `rsi>70` → `OVERBOUGHT REJECTION`; RSI netral + trend `SIDEWAYS` → tetap `NO SETUP` (tidak ada cabang untuk kondisi ini).
3. **Gerbang arah vs alignment** (baris 138–140, 182–191, `reject_reason="direction_blocked"`): `OVERBOUGHT REJECTION` (short) hanya diizinkan jika alignment `STRONG_BEARISH`/`BEARISH`/`PARTIAL` — **diblokir jika alignment `STRONG_BULLISH`/`BULLISH`**. Sebaliknya untuk `OVERSOLD BOUNCE` (long) vs alignment bearish. Ini berarti RSI ekstrem yang muncul justru *karena* tren sedang kuat searah, secara struktural memblokir setup pembalikan arah yang bersangkutan.
4. **Gerbang regime strategi** (baris 256–265, memanggil `engine.strategy.strategy_engine.filter_setup()` → `engine.strategy.strategy_filter.is_strategy_allowed()` → `engine.strategy.strategy_regime_map.STRATEGY_MAP`):

   ```python
   # /opt/aliza-ai/engine/strategy/strategy_regime_map.py
   STRATEGY_MAP = {
       "TREND": ["PULLBACK LONG", "PULLBACK SHORT", "MOMENTUM LONG", "MOMENTUM SHORT", "BREAKOUT LONG"],
       "RANGE": ["OVERSOLD BOUNCE", "OVERBOUGHT REJECTION"],
       "DOWNTREND": ["PULLBACK SHORT", "OVERBOUGHT REJECTION"],
       "VOLATILE": [],
   }
   ```

   **`OVERSOLD BOUNCE` dan `OVERBOUGHT REJECTION` — satu-satunya dua setup yang PERNAH tercatat dari `shadow_e3` sepanjang sejarah (28/28 baris DB, lihat §5.3) — hanya diizinkan saat regime `RANGE` (keduanya) atau `DOWNTREND` (khusus `OVERBOUGHT REJECTION`).** Saat regime `TREND`, **keduanya diblokir total**, apa pun RSI/alignment per-coin.

5. **`market_regime` dihitung market-wide dari BTC saja** (`engine/intelligence/market_intelligence_engine.py:50-54` → `engine/intelligence/market_regime_detector.py:11-65`):
   ```python
   if trend == "BULLISH" and rsi > 60: return {"market_regime": "TREND"}
   ...
   if trend == "BULLISH": return {"market_regime": "TREND"}  # fallback
   ```
   Selama BTC (bukan altcoin manapun) berstatus `trend="BULLISH"` (indikator MA klasik, `market_analyzer.py:372-382`), regime GLOBAL langsung `TREND` — memblokir `OVERSOLD BOUNCE`/`OVERBOUGHT REJECTION` untuk **seluruh 21 coin watchlist sekaligus**, terlepas dari RSI masing-masing altcoin.

---

## 5. Reproduksi manual (read-only, live, 27 Agustus 2026)

Script sementara ditulis di `/tmp/claude-1000/.../scratchpad/` (di luar `/opt/aliza-ai`), memanggil fungsi produksi asli (`market_analyzer.market_signal()`, `e3_shadow._closed_4h_klines()`, `features.average_true_range()`/`calculate_rsi_series()`, `TradingBrain().analyze()`) dengan instrumentasi tambahan di memori. **Dihapus setelah selesai**, tidak ada file yang ditinggalkan di `/opt/aliza-ai`, tidak ada service yang disentuh.

### 5.1 Jalur end-to-end untuk 6 coin (BTC, ETHFI, PEPE, SUI, ARB, TAO) — kondisi live saat ini

Semua 6 coin: `market_signal()` mengembalikan data valid (`data_coverage.reason="ok"`, `klines_4h=99`, `klines_1d=99`), `_closed_4h_klines()` mengembalikan 99 baris (>15, syarat terpenuhi), ATR14(4h) terhitung valid (>0) untuk semua. **Tidak ada exception di jalur mana pun.** Titik gagal seragam: `TradingBrain().analyze()` mengembalikan `NO SETUP` (atau `None`) untuk keenamnya — RSI saat pengujian berkisar netral 46,7–59,6 (BTC 59,55; ETHFI 48,6; PEPE 50,43; SUI 46,67; ARB 46,8; TAO 54,6), tidak ada yang <30 atau >70, dan/atau `trend_alignment` `PARTIAL`/`MIXED`.

### 5.2 Rekonstruksi RSI historis (4h, ~11–16 hari terakhir dari data yang sama yang sudah terambil)

Menggunakan candle 4h yang sama yang sudah difetch (bukan panggilan API historis baru terpisah), RSI direkonstruksi per-candle dengan formula Wilder yang identik dengan produksi (`calculate_rsi_series`, `features.py:35-55`). Hasil kunci:

- **BTC** mengalami RSI ekstrem (>70) pada **33 dari ~70 candle 4h terakhir**, memuncak hingga **RSI 94,23 pada 21 Agustus 15:59 UTC** — bertepatan persis dengan `trend_4h=BULLISH`, `trend_1d=BULLISH`, `alignment=STRONG_BULLISH`. Dalam kondisi ini, `OVERBOUGHT REJECTION` (short) diblokir oleh gerbang arah (§4.3) — bukan karena RSI tidak ekstrem, tapi karena arahnya berlawanan dengan tren kuat yang sedang berlangsung.
- Ringkasan 8 coin (RSI ekstrem vs berapa yang lolos gerbang arah individual):

  | Coin | Candle RSI ekstrem (≈11 hari) | Diblokir gerbang alignment/arah | Lolos gerbang arah |
  |---|---:|---:|---:|
  | BTC | 33 | 29 | 4 |
  | ETH | 23 | 21 | 2 |
  | PEPE | 27 | 22 | 5 |
  | SOL | 25 | 11 | 14 |
  | SUI | 15 | 4 | 11 |
  | ARB | 17 | 2 | 15 |
  | TAO | 12 | 2 | 10 |
  | ETHFI | 15 | 5 | 10 |

  Untuk BTC/ETH/PEPE, mayoritas RSI ekstrem memang diblokir gerbang arah (tren sangat kuat searah RSI). Tapi untuk SOL/SUI/ARB/TAO/ETHFI, **banyak candle RSI ekstrem yang justru lolos gerbang alignment/arah** — namun tetap nihil di DB. Ini konsisten dengan **gerbang regime market-wide (§4.4-4.5)**: karena `market_regime` dihitung HANYA dari BTC, selama BTC ber-`trend=BULLISH` (yang terkonfirmasi live saat ini, §5.1: `detect_market_regime({"trend":"BULLISH","rsi":59.55}) → {"market_regime": "TREND"}`), regime global `TREND` memblokir `OVERSOLD BOUNCE`/`OVERBOUGHT REJECTION` untuk SEMUA coin sekaligus — termasuk altcoin yang RSI-nya sendiri sudah lolos gerbang arah individual. Ini menjelaskan mengapa candidates=0 terjadi serentak di 21 coin, bukan hanya di BTC.

### 5.3 Data historis `signal_tracking` (database, bukan log)

```
SELECT source, count(*) FROM signal_tracking GROUP BY source;
  shadow_e3: 28 baris (llm=79, deterministic=17, legacy=10)

SELECT date(signal_time), count(*) FROM signal_tracking WHERE source='shadow_e3' GROUP BY 1;
  2026-07-24|2  2026-07-25|4  2026-07-27|3  2026-07-30|3  2026-08-04|1  2026-08-05|5
  2026-08-06|1 2026-08-07|1  2026-08-09|1  2026-08-13|1  2026-08-14|2  2026-08-15|1
  2026-08-16|1 2026-08-17|1  2026-08-18|1  -- NIHIL setelah ini --
```

**Setup yang PERNAH tercatat, sepanjang 28 baris: hanya `OVERSOLD BOUNCE` dan `OVERBOUGHT REJECTION`** — tidak pernah `PULLBACK LONG`/`PULLBACK SHORT`, konsisten dengan `STRATEGY_MAP["RANGE"]`/`["DOWNTREND"]` yang membatasi kedua setup itu jadi satu-satunya yang bisa lolos. Baris terakhir: `id=119, BTC, OVERBOUGHT REJECTION, SHORT, entry=64482.34, signal_time=2026-08-18T00:05:34 UTC`. Pola sebelumnya juga menunjukkan **ETHFI** menghasilkan `OVERBOUGHT REJECTION SHORT` berulang pada entry yang terus naik (13→14→15→16 Agustus: 0,429 → 0,4831 → 0,5148) — indikasi ETHFI sendiri sedang trending naik kuat menjelang pergeseran regime, konsisten dengan cerita "pasar mulai trending" tepat sebelum 18 Agustus.

---

## 6. Kondisi pasar sebagai penjelasan alternatif (data harga)

`backtest/data/*.csv` (mis. `BTCUSDT_4h.csv`) **hanya mencakup hingga ~20-21 Juli 2026** (timestamp terakhir `1784577600000` ms ≈ 21 Juli) — dataset one-time yang difetch bersamaan dengan pembuatan backtester Fase 2/3, **tidak diperbarui berkelanjutan**. Dataset ini **tidak mencakup** jendela 14 Agustus–sekarang yang relevan untuk investigasi, sehingga tidak dipakai sebagai bukti kuantitatif utama (sesuai instruksi, tidak ada panggilan API eksternal baru khusus untuk mengisi kekosongan data historis ini). Bukti kuantitatif kondisi pasar pada §5.2 diperoleh dari data yang sama yang sudah diambil oleh reproduksi §5 (candle 4h Binance, dipakai untuk merekonstruksi ATR/RSI historis), bukan dataset backtest terpisah.

---

## 7. Kesimpulan formal

### B. KONDISI PASAR / MEKANISME DESAIN SISTEM — BUKAN BUG

Bukti penyangkal bug/regresi:
- Nihil perubahan kode di seluruh rantai dependency (`e3_shadow.py`, `features.py`, `trading_brain.py`, `strategy_engine.py`, `strategy_filter.py`, `strategy_regime_map.py`, `market_regime_detector.py`, `multi_timeframe_analyzer.py`) sejak sebelum `shadow_e3` dibuat (21 Juli 2026) hingga sekarang.
- Nihil exception/traceback terkait `shadow_e3` di 8 file log yang tersedia (20–27 Agustus, >11.000 siklus).
- Reproduksi live (27 Agustus) menjalankan seluruh pipeline tanpa error, sampai ke titik gagal yang sama persis dan bisa dijelaskan sepenuhnya oleh logika filter yang memang sudah ada.

Mekanisme penjelas:
- `shadow_e3` secara struktural hanya pernah menghasilkan 2 dari 4 kemungkinan setup TradingBrain (`OVERSOLD BOUNCE`, `OVERBOUGHT REJECTION`) — keduanya hanya diizinkan oleh `strategy_regime_map.py` saat `market_regime` global (dihitung dari BTC saja) adalah `RANGE`/`DOWNTREND`.
- BTC memasuki tren bullish kuat berkelanjutan sekitar pertengahan/akhir Agustus (RSI 4h terverifikasi mencapai puncak 94,23 pada 21 Agustus), mengubah `market_regime` menjadi `TREND` — yang dikonfirmasi live masih berlaku hari ini (27 Agustus, `trend=BULLISH → regime=TREND`).
- Selama regime `TREND` bertahan, `shadow_e3` **akan selalu** `candidates=0` di semua coin sekaligus, apa pun RSI altcoin individual — ini bukan kegagalan, melainkan cara sistem memang dirancang bekerja.

### C-catatan (bukan blocker kesimpulan): satu keterbatasan data
Log 18–19 Agustus (hari transisi persis) sudah terhapus rotasi (retensi 8 hari) sebelum audit ini — transisi pastinya tidak bisa dilihat langsung di log, hanya state "sudah 0 sejak 20 Agustus, konsisten hingga sekarang" yang terverifikasi. Ini tidak mengubah kesimpulan B (mekanisme regime yang menyebabkannya sudah terbukti valid dan tidak berubah), tapi tanggal pasti pergeseran regime (18 vs 19 vs 20 Agustus) tidak bisa dipastikan presisi jam-nya.

---

## 8. Rekomendasi

1. **Perpanjang jendela evaluasi promosi shadow_e3 — SANGAT DISARANKAN, terlepas dari kesimpulan A/B/C.** Target `≥60 outcome` atau `1 September 2026` sudah tidak realistis: 28 sinyal terkumpul dalam ~25 hari efektif (24 Juli–18 Agustus), lalu 9+ hari nihil murni karena regime `TREND` yang menurut desain `strategy_regime_map.py` memang mematikan strategi ini. Karena regime `TREND` bisa bertahan berminggu-minggu (tidak ada jaminan durasi), disarankan **evaluasi berbasis jumlah outcome tercapai (≥60), bukan tanggal kalender** — atau, jika tanggal tetap dipakai, jadwal 1 September perlu ditunda tanpa batas pasti sampai regime kembali `RANGE`/`DOWNTREND` cukup lama untuk mengumpulkan sampel tambahan.
2. **Evaluasi win rate 10,7% dan expectancy −1,06%/trade tetap jadi perhatian terpisah** — closed sample (28 baris) ini murni dari periode `RANGE`/`DOWNTREND`, jadi tidak tercemar oleh masalah regime saat ini, tapi ukuran sampel masih kecil untuk kesimpulan statistik kuat.
3. **Pertimbangkan menambah observability**: `build_shadow_signal()` tidak membedakan alasan gagal (rows<15 vs ATR≤0 vs NO SETUP vs filter support) dalam log — hanya agregat `candidates=%d`. Menambah counter per-alasan (tanpa mengubah perilaku) akan membuat investigasi berikutnya jauh lebih cepat, dan akan langsung memperjelas apakah stagnasi disebabkan regime (seperti temuan investigasi ini) atau sebab lain di masa depan. (Tidak diimplementasikan di sini sesuai batasan read-only investigasi ini.)
4. **Dokumentasikan keterbatasan `shadow_e3` sebagai strategi khusus regime `RANGE`/`DOWNTREND`** di checklist promosi (`SHADOW_PROMOTION_CHECKLIST_REPORT.md`) — sebelumnya tidak disebutkan eksplisit bahwa filter regime membatasi eksperimen ini hanya pada 2 dari 4 kondisi pasar.
