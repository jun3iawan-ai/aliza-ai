# Audit Read-Only: Kondisi Global vs Konteks Market vs Prediksi Market vs Skor Quant

**Tipe:** Audit read-only murni. Tidak ada perubahan kode/commit/restart di task ini — termasuk temuan bug, TIDAK diperbaiki, hanya dilaporkan.
**Tanggal:** 2026-09-18
**Lokasi kode yang diaudit:**
- `interfaces/telegram_bot.py` — handler `marketstate_command` (2178-2201), `market_context_command` (2314-2357), `predict` (2084-2112), `quant_command` (2117-2173); keyboard `_market_submenu_keyboard()` (460-472), `_analysis_submenu_keyboard()` (497-507); routing tombol (632-792)
- `engine/market/market_intelligence.py` (`analyze_market_environment`, seluruh file, 59 baris)
- `engine/market/market_context_engine.py` (`calculate_market_score`, `format_context_for_brief`, seluruh file, 234 baris)
- `engine/prediction/prediction_engine.py` (`generate_market_prediction`, seluruh file)
- `engine/prediction/bias_score_engine.py` (`calculate_market_bias`, seluruh file)
- `engine/prediction/probability_engine.py` (`calculate_probabilities`, seluruh file)
- `engine/intelligence/market_intelligence_engine.py` (`generate_market_intelligence`, seluruh file)
- `engine/intelligence/market_regime_detector.py`, `whale_flow_analyzer.py`, `altseason_model.py` (seluruh file, masing-masing di bawah 70 baris)
- `engine/intelligence/market_state_engine.py` (seluruh file, 106 baris) — ternyata terkait erat, lihat bagian 4
- `engine/market/market_radar.py` (`market_radar`, `bull_probability` via `market_ai_predictor.py`), `engine/detectors/smart_money_tracker.py` (`stablecoin_inflow`) — untuk konfirmasi ulang bug backlog #5
- `engine/market/global_market_cache.py` (fear&greed/dominance fallback, sudah diaudit sebelumnya di Radar Pro)

---

## Ringkasan Eksekutif

1. **Koreksi posisi menu**: `🌐 Kondisi Global` **BUKAN** bagian dari submenu Analisis. Ia ada di submenu **📊 Market** (`_market_submenu_keyboard()`), sebaris dengan Radar Market/Radar Pro. Yang benar-benar berdekatan di submenu **📈 Analisis** (`_analysis_submenu_keyboard()`) hanya 3 tombol: `🎯 Konteks Market`, `🔮 Prediksi Market`, `📊 Skor Quant` (plus `🔎 Penjelasan AI` dan `📊 Performance` yang di luar lingkup task ini). Nama tombol persis: **"🎯 Konteks Market"** (bukan "📊 Konteks Market") dan **"📊 Skor Quant"** (bukan "📐 Skor Quant") — draf di deskripsi task sudah agak usang.
2. **Temuan paling penting**: `/predict` (`🔮 Prediksi Market`) dan `/quant` (`📊 Skor Quant`) **berbagi mesin skor yang identik** — keduanya memanggil `calculate_market_bias(snapshot)` dari `bias_score_engine.py` (persis pola yang sama seperti `/radar` & `/radarpro` berbagi `generate_radar_pro()`). `/predict` mengonversi skor itu jadi probabilitas 0-100% via `probability_engine.py`; `/quant` menampilkan skor mentahnya langsung + label kekuatan STRONG/MEDIUM/WEAK. Dua tombol, dua tampilan berbeda, **satu otak yang sama**.
3. **Bug tie-break "BEARISH palsu"**: baik `/predict` maupun `/quant` memakai pola `if bull > bear: BULLISH else: BEARISH` — saat skor benar-benar seri (paling umum 0 vs 0, artinya *tidak ada sinyal apapun* terdeteksi), KEDUANYA melabeli kondisi netral itu sebagai **"BEARISH"**, bukan "NEUTRAL" — padahal `generate_market_prediction()` sendiri sudah punya default `"bias": "NEUTRAL"` di awal yang justru tidak pernah tercapai lewat perhitungan nyata. Dikonfirmasi lewat reproduksi langsung (bagian 4).
4. **Konfirmasi ulang bug backlog #5 (`stablecoin_flow`)**: bug lama (total circulating supply dipakai seolah "flow") **masih ada, belum diperbaiki** — plus ditemukan **bug tambahan yang belum pernah dilaporkan**: perbandingan string `stablecoin_flow == "HIGH"` di `bull_probability()` tidak akan pernah cocok, karena `stablecoin_inflow()` mengembalikan `"HIGH INFLOW"` (bukan `"HIGH"`) — jadi komponen ini mati total (selalu 0 poin). **Tapi, koreksi penting terhadap asumsi backlog**: pencemaran ini **TIDAK LAGI mengalir ke `/predict`** pada kode saat ini. `/predict` sekarang memakai `bias_score_engine.py` (tidak menyentuh `stablecoin_flow`/`bull_probability` sama sekali). Field `bull_probability` yang tercemar itu HANYA dikonsumsi oleh `market_state_engine.py` dan `market_report_formatter.py` — dan KEDUANYA ternyata **dead code**: di-import di `telegram_bot.py` tapi tidak pernah dipanggil dari command manapun. Jadi bug-nya nyata dan aktif dihitung tiap 60 detik (buang-buang compute), tapi **tidak sampai ke user manapun saat ini** lewat command apapun yang diaudit di sini.
5. **Fallback diam-diam ditemukan lagi**: `market_context_command` (`/market_context`) membaca `fear_greed`/`btc_dominance` dari `get_global_market_data()` tapi **tidak pernah mengecek** `fear_greed_status`/`btc_dominance_status` (flag "ok"/"failed" yang sudah ada persis untuk keperluan ini, sama seperti temuan di audit Radar Pro) — kalau API gagal dan fallback ke 50.0, skor komponen Fear&Greed/BTC Dominance tetap dihitung dan disatukan ke `total_score` seolah data asli, tanpa indikasi ke user.
6. Tidak ditemukan pola bug "label default dipasang lalu tidak pernah dibatalkan" (seperti kasus Crash Risk Radar Pro) di keempat fitur ini — arsitektur skoringnya aditif/independen, bukan cascade if/elif berlapis dengan detector susulan.

---

## 1. Alur Kode Masing-Masing (dikonfirmasi ulang, bukan asumsi)

### 1.1 `🌐 Kondisi Global` → `/marketstate` → `marketstate_command` (`telegram_bot.py:2178-2201`)

```python
snapshot = get_market_snapshot()
intel = analyze_market_environment(snapshot)   # engine/market/market_intelligence.py
phase = intel.get("market_phase")
trend = intel.get("btc_trend")
rsi = intel.get("btc_rsi")
crash = intel.get("crash_warning")
```

`analyze_market_environment()` (`engine/market/market_intelligence.py:11-58`) **hanya membaca `snapshot["data"]["BTC"]`** — tidak ada coin lain, tidak ada fear&greed/dominance/makro. Logikanya:
- `market_phase`: `rsi<35` → `ACCUMULATION`; `rsi>70` → `OVERBOUGHT`; `trend BULLISH` → `BULL TREND`; `trend BEARISH` → `BEAR TREND`; selain itu `NEUTRAL`.
- `crash_warning`: `True` jika `price < support * 0.97`.

**Catatan penting**: meskipun namanya "Kondisi Global", fitur ini murni teknikal BTC (single-coin), tidak melibatkan data makro/global sama sekali. Nama tombol berpotensi menyesatkan ekspektasi user.

### 1.2 `🎯 Konteks Market` → `/market_context` → `market_context_command` (`telegram_bot.py:2314-2357`)

```python
result = calculate_market_score()   # engine/market/market_context_engine.py
```

`calculate_market_score()` (`market_context_engine.py:54-189`) menghitung **5 komponen berbobot** yang dijumlah jadi skor 0-100 (lihat bagian 2 untuk rincian formula). Ini **satu-satunya** dari keempat fitur yang benar-benar menggabungkan data makroekonomi (CPI, Fed funds rate dari `macro_monitor.py`) dan funding rate rata-rata lintas 5 coin (`BTC, ETH, BNB, SOL, XRP`). Fungsi ini juga dipakai ulang oleh Morning Brief & Evening Summary (`format_context_for_brief()`, dipanggil di `telegram_bot.py:5664` dan `5797`) — reuse yang bersih, bukan duplikasi bermasalah.

### 1.3 `🔮 Prediksi Market` → `/predict` → `predict()` (`telegram_bot.py:2084-2112`)

```python
snapshot = get_market_snapshot()
prediction = generate_market_prediction(snapshot)   # engine/prediction/prediction_engine.py
bull_p = prediction.get("bullish_probability", 50)
bear_p = prediction.get("bearish_probability", 50)
bias = prediction.get("bias", "NEUTRAL")
confidence = prediction.get("confidence", "LOW")
```

Ada **fallback legacy** (`elif predict_market and format_prediction_report:`) yang mengimpor `engine.intelligence.predictive_market_ai` — **modul ini TIDAK ADA di repo** (`ModuleNotFoundError` dikonfirmasi langsung). Fallback ini aman (tidak crash — baik `predict_market` maupun `format_prediction_report` sama-sama `None` dari blok `except ImportError`, jadi jatuh ke pesan `"Modul prediksi belum tersedia."`), tapi merupakan **dead code** — persis pola `market_radar_pro.py` yang ditemukan di audit sebelumnya.

`generate_market_prediction()` (`prediction_engine.py:21-71`):
```python
bias_out = calculate_market_bias(snapshot)          # <-- SAMA PERSIS dipakai /quant
bull_s, bear_s = bias_out["bullish_score"], bias_out["bearish_score"]
prob_out = calculate_probabilities(bull_s, bear_s)   # probability_engine.py
bull_p, bear_p = prob_out["bullish_probability"], prob_out["bearish_probability"]
bias = "BULLISH" if bull_p > bear_p else "BEARISH"
confidence = "HIGH" if (bull_p>70 or bear_p>70) else "MEDIUM" if (bull_p>55 or bear_p>55) else "LOW"
```

### 1.4 `📊 Skor Quant` → `/quant` → `quant_command()` (`telegram_bot.py:2117-2173`)

```python
scores = calculate_market_bias(snapshot)   # <-- FUNGSI YANG SAMA PERSIS dipakai /predict
bullish_score, bearish_score = scores["bullish_score"], scores["bearish_score"]
bias = "BULLISH" if bullish_score > bearish_score else "BEARISH"
ratio = bullish_score / (bullish_score + bearish_score)   # kalau total > 0
strength = "STRONG" if ratio>0.7 else "MEDIUM" if ratio>0.55 else "WEAK"
mi = snapshot.get("market_intelligence") or {}   # dict yang SAMA dipakai calculate_market_bias
```

Juga ada fallback legacy (`if calculate_market_bias is None: ... _quant_market_score ...`) yang mengimpor `engine.intelligence.quant_market_model` — **modul ini juga TIDAK ADA** (`ModuleNotFoundError` dikonfirmasi). Fallback ini punya **bug tambahan**: baris impor `from engine.intelligence.quant_market_model import ... format_quant_report as _quant_format_report` mem-alias nama jadi `_quant_format_report`, tapi kode fallback di `quant_command` memanggil nama **`format_quant_report`** (tanpa underscore/alias) yang **tidak pernah ter-assign** kecuali lewat blok `except ImportError: format_quant_report = None`. Kalau modul itu SEANDAINYA ada dan berhasil di-import, baris `if _quant_market_score and format_quant_report:` akan meledak `NameError`. Untungnya modulnya memang tidak ada, jadi kedua kondisi (`_quant_market_score is None`) membuat cabang ini tidak pernah tereksekusi sampai baris yang buggy — **landmine yang saat ini aman karena "dilindungi" oleh bug lain (modul hilang)**.

### 1.5 Kesimpulan bagian 1 — independensi vs berbagi

| Pasangan | Berbagi fungsi inti? |
|---|---|
| `/marketstate` vs 3 lainnya | Independen sepenuhnya — satu-satunya yang membaca snapshot BTC mentah langsung tanpa lewat engine skor manapun. |
| `/market_context` vs 3 lainnya | Independen — `calculate_market_score()` tidak dipanggil oleh & tidak memanggil tiga fungsi lainnya. |
| **`/predict` vs `/quant`** | **BERBAGI `calculate_market_bias()` dari `bias_score_engine.py`** — persis skenario `/radar`+`/radarpro` yang berbagi `generate_radar_pro()`. Lihat bagian 3 untuk analisis dampak. |

---

## 2. Tabel Perbandingan Sisi-Berdampingan

| Aspek | 🌐 Kondisi Global (`/marketstate`) | 🎯 Konteks Market (`/market_context`) | 🔮 Prediksi Market (`/predict`) | 📊 Skor Quant (`/quant`) |
|---|---|---|---|---|
| **Command & handler** | `/marketstate` → `marketstate_command` | `/market_context` → `market_context_command` | `/predict` → `predict` | `/quant` → `quant_command` |
| **Lokasi menu** | Submenu **📊 Market** | Submenu **📈 Analisis** | Submenu **📈 Analisis** | Submenu **📈 Analisis** |
| **Sumber data mentah** | `snapshot["data"]["BTC"]` saja (price, rsi, trend, support) | `get_global_market_data()` (fear&greed, BTC dominance), `get_all_funding_data()` (funding rate 5 coin), `get_macro_data()` (CPI/Fed, FRED), `scan_for_signals()` (scan seluruh watchlist) | `snapshot["data"]["BTC"]` (trend, rsi) + `snapshot["market_intelligence"]` (regime, whale_pressure, altseason_probability — dihitung dari BTC + seluruh watchlist) | **Identik dengan `/predict`**: `calculate_market_bias(snapshot)` memakai sumber yang sama persis |
| **Scope** | Per-coin (BTC saja) | Global murni (makro + funding lintas-coin + sinyal lintas-watchlist) | Campuran: BTC-sentris + 1 komponen lintas-watchlist (altseason) | Sama seperti `/predict` (campuran BTC + lintas-watchlist), ditambah tampilan trend/RSI BTC mentah |
| **Metrik/komponen** | `market_phase`, `btc_trend`, `btc_rsi`, `crash_warning` (price vs support) | 5 komponen berbobot: Fear&Greed (nilai 0-20), BTC Dominance (0-15), Funding Rate avg (0-25), Makro CPI/Fed (0-25), Technical signal (0-15) | `bullish_score`/`bearish_score` (dari `calculate_market_bias`) → `bullish_probability`/`bearish_probability` (0-100%, dibatasi 15-85%) | `bullish_score`/`bearish_score` mentah (skala poin, bukan %) + `market_regime`, `whale_pressure`, `altseason_probability`, BTC trend/RSI |
| **Formula scoring/probabilitas** | Tidak ada skor gabungan — murni if/elif kategorisasi | **Ya, eksplisit**: total = jumlah 5 skor komponen (maks 20+15+25+25+15=100). Threshold: ≤30 Bearish, ≤45 Weak, ≤55 Neutral, ≤70 Bullish, >70 Strong Bullish (`_label_for_score`) | **Ya**: `bias_score_engine` — trend ±30, rsi>60/<40 ±10, regime TREND/DOWNTREND ±10, whale BUYING/SELLING ±10, altseason>60 +10 (bullish only) → lalu `probability_engine` konversi rasio jadi %, dibatasi 15-85% | **Formula skor identik dengan `/predict`** (fungsi yang sama), tapi TIDAK dikonversi ke probabilitas — dipakai langsung sebagai rasio untuk label kekuatan STRONG(>70%)/MEDIUM(>55%)/WEAK |
| **Format output** | 4 baris: BTC Trend, BTC RSI, Market Phase, Crash Warning (YES/NO) | Skor total /100 + label + emoji, breakdown 5 komponen dengan nilai mentah, ringkasan saran, timestamp | Bullish/Bearish Probability (%), Short-term Bias, Confidence, timestamp snapshot | Bullish/Bearish Score (poin mentah), Market Bias, Market Strength, breakdown Trend/RSI/Regime/Whale/Altseason, timestamp snapshot |
| **Pertanyaan yang dijawab** | "Bagaimana kondisi teknikal BTC saat ini — apakah oversold/overbought/trending, dan apakah harga sedang mendekati crash dari support?" | "Secara keseluruhan (makro + sentimen + funding + sinyal), apakah kondisi pasar mendukung entry baru sekarang?" | "Berapa persen kemungkinan pasar bullish vs bearish jangka pendek, dan seberapa yakin sistem?" | "Seberapa kuat bias pasar saat ini (dalam skor mentah), dan apa saja komponen individualnya (regime, whale, altseason)?" |

---

## 3. Tumpang Tindih / Redundansi

**Kesimpulan: 3 dari 4 fitur benar-benar mengukur hal berbeda dan saling melengkapi. Tapi `/predict` dan `/quant` adalah kasus tumpang-tindih signifikan yang sama persis polanya dengan `/radar` vs `/radarpro`.**

- **`/marketstate` vs yang lain**: unik — satu-satunya yang scope-nya benar-benar sempit (BTC only, tanpa skor gabungan). Tidak tumpang tindih dengan yang lain, tapi *namanya* ("Kondisi Global") menyesatkan karena isinya tidak ada unsur global sama sekali (bandingkan dengan `/market_context` yang justru benar-benar global). Ini murni masalah penamaan/UX, bukan bug logika.
- **`/market_context` vs yang lain**: unik — satu-satunya dengan data makroekonomi asli (CPI/Fed) dan funding rate multi-coin. Tidak ada fungsi lain yang menghitung ulang hal yang sama.
- **`/predict` vs `/quant` — TUMPANG TINDIH SIGNIFIKAN**: keduanya memanggil `calculate_market_bias(snapshot)` yang **persis sama**, menghasilkan `bullish_score`/`bearish_score` yang **identik** untuk snapshot yang sama. Bedanya murni presentasi:
  - `/predict` mengonversi ke persentase probabilitas (0-100%, dibatasi 15-85%) dan menyebutnya "Bullish/Bearish Probability" + "Confidence".
  - `/quant` menampilkan skor mentahnya (skala poin arbitrer, bisa 0-70 untuk bullish, 0-60 untuk bearish) dan menyebutnya "Bullish/Bearish Score" + "Market Strength" (STRONG/MEDIUM/WEAK).
  
  User yang menekan kedua tombol untuk snapshot yang sama akan melihat **dua angka dan dua skala berbeda** (persentase vs skor mentah) yang sebenarnya berasal dari **satu perhitungan yang identik** — berpotensi membuat user mengira ini dua "pendapat" independen sistem (semacam validasi silang), padahal secara matematis keduanya cuma dua cara menampilkan angka yang sama. Ini persis pola `/radar` vs `/radarpro` yang ditemukan di audit sebelumnya (berbagi `generate_radar_pro()`), hanya di domain berbeda.
  - **Verifikasi arah bias**: dicek dengan kombinasi skor realistis (`calculate_market_bias` hanya pernah menghasilkan kelipatan 10 karena semua increment-nya 30/10/10/10/10) — arah BULLISH/BEARISH antara `/predict` dan `/quant` **selalu konsisten satu sama lain** untuk skor tidak seri (diverifikasi dengan 19 kombinasi realistis, 0 perbedaan arah). Jadi bukan risiko "kontradiksi", tapi tetap risiko "dua tombol, satu jawaban, tampak seperti dua insight independen".

---

## 4. Kualitas Data

### 4.1 Fallback diam-diam — ditemukan lagi, pola sama dengan Info Coin & Radar Pro

`market_context_command` → `calculate_market_score()` (`market_context_engine.py:62-99`):
```python
g = get_global_market_data() or {}
fg = _safe_float(g.get("fear_greed"))
if fg is None:
    failed_components += 1
else:
    ... # skor dihitung dari fg
```

`get_global_market_data()` (`global_market_cache.py`, sudah diaudit di laporan Radar Pro) **tidak pernah mengembalikan `None`** untuk `fear_greed`/`btc_dominance` — saat API gagal, ia diam-diam fallback ke `50.0` dan hanya membedakannya lewat field terpisah `fear_greed_status`/`btc_dominance_status` ("ok"/"failed"). **`market_context_engine.py` tidak pernah membaca field status ini** — jadi `fg` praktis TIDAK PERNAH `None` (selalu ada angka, entah asli atau fallback 50.0), dan cabang `if fg is None: failed_components += 1` nyaris tidak pernah ke-trigger oleh kegagalan API sungguhan. Efeknya: skor komponen Fear&Greed (dan BTC Dominance) tetap dihitung dari nilai 50.0 seolah itu data pasar asli, ikut disatukan ke `total_score`/100 yang ditampilkan ke user, tanpa indikasi apapun bahwa datanya mungkin fallback.

**Nuansa penting (lebih baik dari beberapa kasus lama)**: nilai MENTAH tetap ditampilkan transparan ke user lewat `fg_label`/`dom_label` di `market_context_command` (`"—" if fg_val is None else f"{fg_val:.1f}"`) — tapi karena `fg_val` yang diterima nyaris tidak pernah `None` (root cause di atas), label "—" ini praktis tidak pernah muncul walau datanya sebenarnya fallback. Jadi transparansi yang dirancang di level tampilan gagal berfungsi karena root cause-nya (status flag tidak dicek) sama seperti di Radar Pro.

**Dampak turunan ke `/predict` dan `/quant` juga**: `calculate_altseason_probability()` (dipakai `market_intelligence_engine.py` yang mengisi `snapshot["market_intelligence"]`, dikonsumsi `bias_score_engine.calculate_market_bias()` — dipakai `/predict` DAN `/quant`) membaca `btc_data.get("dominance")`, yang nilainya berasal dari `global_data["btc_dominance"]` yang disalin ke setiap coin oleh `market_analyzer.py:412,478` — **sumber yang SAMA** dengan yang dipakai `/market_context`. Jadi kalau BTC dominance API gagal, fallback 50.0 yang sama ini ikut mencemari komponen altseason di `/predict` dan `/quant` juga, secara diam-diam, tanpa disclosure.

### 4.2 Nilai global disalin sebagai per-coin — TIDAK ditemukan sebagai bug baru di 4 fitur ini

Berbeda dari kasus Radar Pro, keempat fitur ini secara sadar hanya beroperasi di scope BTC-tunggal atau agregat-seluruh-watchlist (bukan iterasi per-coin yang menampilkan label seolah spesifik per-coin). `analyze_whale_flow(btc_data)`, `detect_market_regime(btc_data)` memang membaca field yang secara arsitektur global (`whale_activity`, `market_risk_score` — sama seperti temuan Radar Pro), tapi di sini dipakai secara sadar sebagai sinyal BTC/global, tidak diklaim seolah spesifik ke altcoin tertentu. **Tidak ada instans baru dari bug "atribusi salah ke coin tertentu".**

### 4.3 Konfirmasi ulang bug backlog #5 `stablecoin_flow` — MASIH ADA, plus 1 bug baru, TAPI sudah tidak mencemari `/predict`

`engine/detectors/smart_money_tracker.py:10-49` (`stablecoin_inflow()`): **dikonfirmasi masih menjumlahkan total circulating supply stablecoin** dari DefiLlama (`peggedAssets[].circulating.peggedUSD`) dan mengklasifikasikannya sebagai `"HIGH INFLOW"`/`"NORMAL"`/`"LOW"` berdasarkan level absolut (>150B / >100B / else) — **bukan delta/arus sesungguhnya** (tidak ada perbandingan dengan periode sebelumnya). Bug lama, belum diperbaiki, sesuai keputusan yang berlaku.

**Bug baru yang ditemukan** — `engine/intelligence/market_ai_predictor.py:44`:
```python
if stablecoin_flow == "HIGH":
    score += 20
```
`stablecoin_inflow()` tidak pernah mengembalikan string `"HIGH"` — hanya `"HIGH INFLOW"`, `"NORMAL"`, `"LOW"`, atau `"UNKNOWN"`. Perbandingan string ini **tidak akan pernah cocok**, jadi komponen +20 untuk stablecoin flow di `bull_probability()` (fungsi di `market_radar.py`'s pipeline, BUKAN yang dipakai `/predict`) **selalu 0, mati total** — bug independen di atas bug konseptual yang sudah diketahui.

**Koreksi terhadap asumsi task**: field `bull_probability` yang tercemar dua bug ini ditelusuri sampai ke pemakainya — hanya dipakai oleh:
- `market_state_engine.py:76` (`calculate_market_state()`) — **fungsi ini sendiri punya 2 impor internal yang modulnya TIDAK ADA** (`engine.intelligence.predictive_market_ai`, `engine.intelligence.quant_market_model` — sama-sama `ModuleNotFoundError` dikonfirmasi), jadi bahkan jika dipanggil, sebagian besar outputnya sudah netral-default duluan sebelum sempat memakai `bull_probability` yang tercemar.
- `market_report_formatter.py` (`format_market_report()`).

**Kedua fungsi ini di-import di `telegram_bot.py` (baris 78, 144-146) TAPI TIDAK PERNAH DIPANGGIL dari command manapun** — dikonfirmasi lewat pencarian pemanggilan `format_market_report(` dan `format_market_state_report(`/`calculate_market_state(` di seluruh `telegram_bot.py`: nihil. Jadi **bug `stablecoin_flow`/`bull_probability` nyata dan aktif dihitung setiap siklus snapshot (60 detik) — tapi saat ini TIDAK sampai ke user manapun** lewat command Telegram apapun, termasuk `/predict` yang disebut di backlog lama. Kemungkinan `/predict` sudah direfactor ke `bias_score_engine.py` (yang bersih dari stablecoin_flow) setelah backlog #5 dicatat, tanpa catatan itu diperbarui.

Ini menambah bukti pola sistemik: modul-modul lama (`market_radar_pro.py`, `engine.intelligence.predictive_market_ai`, `engine.intelligence.quant_market_model`, `market_state_engine.py`, `market_report_formatter.py`) tetap ada di repo dalam kondisi setengah-hidup (di-import tapi tidak dipanggil, atau memanggil modul yang sudah tidak ada) — konsisten dengan temuan `market_radar_pro.py` di audit sebelumnya.

### 4.4 Sticky/default label tidak pernah direset — TIDAK ditemukan pola Crash-Risk di sini, TAPI ada temuan terkait: "BEARISH palsu" saat skor seri

Diperiksa struktur logika keempatnya: `analyze_market_environment` (if/elif murni, tidak ada cascade detector susulan), `calculate_market_score` (komponen aditif independen, tidak saling menimpa), `calculate_market_bias` (aditif independen, tidak ada default awal yang bisa "nyangkut"). **Tidak ada instans pola "default dipasang duluan, detector susulan cuma menegaskan tidak pernah membatalkan"** seperti kasus Crash Risk Radar Pro.

**Namun ditemukan bug lain yang sepadan dampaknya** — di `prediction_engine.py:56-59` dan `quant_command` (`telegram_bot.py:2135`):
```python
bias = "BULLISH" if bull_p > bear_p else "BEARISH"    # /predict
bias = "BULLISH" if bullish_score > bearish_score else "BEARISH"   # /quant
```

Tidak ada cabang `NEUTRAL`. Saat skor benar-benar seri (paling umum **0 vs 0** — artinya trend SIDEWAYS, RSI netral 40-60, regime RANGE, whale NEUTRAL, altseason≤60 — kondisi pasar yang genuinely datar/tanpa sinyal), keduanya jatuh ke cabang `else` dan melabeli kondisi netral itu sebagai **"BEARISH"**. Dikonfirmasi lewat reproduksi langsung:
```
scores=(0,0)   probs=(50%,50%)  predict=BEARISH  quant=BEARISH
```

Ironisnya, `generate_market_prediction()` sendiri sudah menyiapkan default `"bias": "NEUTRAL"` di awal fungsi (`prediction_engine.py:38`) — tapi default ini hanya tercapai kalau `calculate_market_bias`/`calculate_probabilities` gagal total (exception/modul hilang), **bukan** untuk kasus market yang genuinely netral hasil perhitungan normal. Jadi kata "NEUTRAL" ada di kode tapi secara praktis tidak pernah muncul dari perhitungan nyata — hanya dari kegagalan sistem.

**Mitigasi parsial yang sudah ada** (bukan alasan untuk mengabaikan): `/predict` tetap menampilkan angka 50%/50% eksplisit dan `Confidence: LOW`; `/quant` menampilkan `Market Strength: WEAK` untuk kasus total=0. Jadi user yang membaca angka pendukungnya masih bisa menyimpulkan "ini sebenarnya netral", tapi kata "Bias: BEARISH" / "Market Bias: BEARISH" sendiri tetap salah arah secara harfiah.

**Verifikasi tambahan**: diuji juga apakah `/predict` dan `/quant` bisa **saling bertentangan arah** (bukan cuma keduanya sama-sama salah) — hasil: **tidak**, untuk seluruh kombinasi skor realistis (kelipatan 10, sesuai cara `bias_score_engine` menghitung), arah BULLISH/BEARISH keduanya selalu konsisten satu sama lain. Jadi risikonya "kompak salah bareng" pada kasus seri, bukan "user melihat dua kesimpulan berlawanan".

---

## 5. Rekomendasi (urutan dampak, tanpa perbaikan — sesuai lingkup task)

1. **[Dampak sedang-tinggi, UX]** `/predict` vs `/quant` menampilkan angka dari mesin skor yang identik (`calculate_market_bias`) dengan dua skala berbeda (probabilitas % vs skor mentah) tanpa penjelasan ke user bahwa keduanya berasal dari perhitungan yang sama — berpotensi membuat user mengira ini dua sinyal independen. Layak dipertimbangkan: satukan presentasi, atau minimal beri catatan di salah satu pesan bahwa angkanya berasal dari model yang sama.
2. **[Dampak sedang]** Bias "BEARISH" palsu saat skor benar-benar seri (paling sering 0 vs 0, kondisi pasar genuinely netral) di `/predict` DAN `/quant` — kata "NEUTRAL" sudah ada di desain (`prediction_engine.py`) tapi tidak pernah dipakai untuk kasus ini. Berpotensi bikin user parno di saat market sebenarnya datar-datar saja.
3. **[Dampak sedang, transparansi data]** `market_context_command` tidak mengecek `fear_greed_status`/`btc_dominance_status` sebelum menghitung skor — pola yang sama persis dengan temuan Radar Pro, kali ini mencemari skor 0-100 yang ditampilkan sebagai "Total: X/100" ke user tanpa disclosure saat data sebenarnya fallback.
4. **[Dampak rendah saat ini, tapi berbahaya kalau diaktifkan]** Bug ganda `stablecoin_flow`/`bull_probability` (supply-bukan-flow + string mismatch `"HIGH"` vs `"HIGH INFLOW"`) masih aktif dihitung tiap 60 detik tapi untungnya tidak mencapai user manapun saat ini (konsumen satu-satunya, `market_state_engine.py` & `market_report_formatter.py`, adalah dead code). **Risiko laten**: kalau suatu saat ada yang menyambungkan `format_market_report`/`format_market_state_report` ke command baru tanpa sadar bug ini masih ada, bug lama akan langsung aktif lagi ditambah bug barunya.
5. **[Dampak rendah, code hygiene]** Tiga modul legacy dengan import yang sudah rusak/tidak ada: `engine.intelligence.predictive_market_ai` (fallback `/predict`), `engine.intelligence.quant_market_model` (fallback `/quant`, dipakai juga oleh `market_state_engine.py`) — konsisten dengan pola `market_radar_pro.py` di audit sebelumnya. Kandidat pembersihan, bukan bug aktif.
6. **[Dampak rendah, cuma bisa muncul kalau bug #5 "diperbaiki setengah"]** Alias `format_quant_report`/`_quant_format_report` yang salah nama di `telegram_bot.py:166` — landmine `NameError` yang saat ini aman karena dilindungi bug lain (modul `quant_market_model` tidak ada). Kalau modul itu suatu saat dibuat ulang tanpa memperbaiki baris ini, `/quant` bisa crash di jalur fallback.
7. **[Dampak sangat rendah, UX/penamaan]** `🌐 Kondisi Global` isinya murni BTC-teknikal (tidak ada unsur global), sementara `🎯 Konteks Market` yang justru berisi data global (makro, funding, fear&greed). Nama kedua tombol ini bertukar posisi secara konseptual — berpotensi membingungkan user yang menebak isi fitur dari namanya.

**Tidak semua ditemukan bermasalah** — `/market_context` sendiri (di luar isu fallback #3) adalah desain paling matang dari keempatnya: formula eksplisit, breakdown transparan per komponen, dan dipakai ulang secara bersih oleh Morning Brief/Evening Summary tanpa duplikasi logika.
