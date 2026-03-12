# ALIZA AI — System Context

**Dokumen konteks sistem untuk AI dan pengembang.**  
Mendokumentasikan tujuan, arsitektur, pipeline, dan komponen utama project AlizaAI agar dapat dipahami dan diperluas dengan konsisten.

---

## 1. TUJUAN SISTEM

**Aliza** adalah **AI Trading Assistant** untuk pasar crypto yang:

- **Menganalisis market** — harga, indikator (RSI, MA), sentiment (Fear & Greed), aktivitas whale, funding, open interest.
- **Menghasilkan trade setup** — entry, stop loss (SL), take profit (TP1, TP2) berdasarkan trend dan level teknikal.
- **Menghitung risk reward (RR)** — rasio reward/risk per setup.
- **Mengirim signal ke Telegram** — rekomendasi setup, alert posisi, dan laporan market.
- **Tidak melakukan auto trading** — eksekusi order tetap oleh user; Aliza hanya memberi analisis dan saran.

Sistem dirancang untuk **assist**, bukan **execute**.

---

## 2. ARSITEKTUR SISTEM

Struktur utama project:

```
aliza-ai/
├── api/           # REST API (FastAPI): dashboard, auth, market, chat
├── core/          # AI core: agent, RAG, knowledge base, tools, skill loader
├── engine/        # Trading & market engine (lihat bagian 3)
├── interfaces/   # User-facing: Telegram bot, market bot
├── scripts/      # Runner & utilitas: run_dashboard.py, dll.
├── dashboard/     # Web dashboard (HTML + Tailwind)
├── docs/          # Dokumentasi (termasuk dokumen ini)
├── data/          # SQLite DB (aliza.db), lock file
├── memory/        # User memory, document registry
├── project/      # Script project (cleanup, dll.)
└── skills_custom/ # Custom skills (contoh: weather)
```

| Folder | Peran |
|--------|--------|
| **api/** | FastAPI server: dashboard API (`/api/dashboard/*`), auth, market, chat. Menyajikan dashboard HTML di `/` dan health di `/health`. |
| **core/** | Agent AI (CrewAI), RAG, knowledge base, tool router, skill loader. Dipakai untuk fitur chat/assistant. |
| **engine/** | Inti trading: analisis market, radar, trading brain, opportunity scanner, trade manager, signal engine, intelligence (quant, predictive, radar pro). |
| **interfaces/** | Telegram bot (`telegram_bot.py`), market bot (`market_bot.py`). Entry point untuk user. |
| **scripts/** | Script standalone: `run_dashboard.py` (uvicorn dengan port dari env). |
| **dashboard/** | Frontend dashboard web: `index.html` (panel market, quant, predict, signals, portfolio, BTC chart). |

---

## 3. ENGINE STRUCTURE

Semua logika market dan trading terkonsentrasi di **engine/**:

```
engine/
├── brain/           # Keputusan trading & AI assistant
├── market/          # Analisis market & radar
├── detectors/       # Deteksi event: whale, crash, altseason, liquidation
├── intelligence/   # Model intelijen: predictive, quant, radar pro, market intel
├── trading/        # Trade lifecycle: manager, scanner, portfolio, signal, decision AI
├── monitoring/     # Monitoring market & notifikasi
└── utils/          # Cache market & updater
```

### 3.1 engine/brain/

| Modul | Fungsi |
|-------|--------|
| **trading_brain.py** | `TradingBrain.analyze(market_data)` — dari price, RSI, trend, S/R menghasilkan **setup** (PULLBACK LONG, SHORT CONTINUATION, OVERSOLD BOUNCE, dll.) dan **entry, sl, tp1, tp2, risk_reward, confidence, risk_quality**. |
| **ai_trade_guardian.py** | `analyze_trades()` — baca posisi aktif, hitung PnL, map ke status alert (SECURE_PROFIT, PARTIAL_PROFIT, BREAK_EVEN, RISK_WARNING, CLOSE_WARNING), kirim saran ke Telegram (dipakai job). |
| **aliza_engine.py** | `ask_aliza(user_input)` — integrasi ke CrewAI/agent untuk chat/assistant. |

### 3.2 engine/market/

| Modul | Fungsi |
|-------|--------|
| **market_analyzer.py** | Fetch harga (CoinGecko), Fear & Greed, dominance; hitung MA, RSI, S/R; panggil **market_radar** dan **TradingBrain**; expose `market_signal(symbol)`, `btc_signal()`, `multi_market_scan()`. |
| **market_radar.py** | `market_radar(fear, dominance)` — sinyal makro: funding, whale, OI, liquidation risk, cycle phase, bull probability, market risk score. |
| **market_universe.py** | `MAJOR_COINS` — daftar symbol yang dianalisis. |
| **market_report_formatter.py** | Format output analisis untuk tampilan/Telegram. |
| **radar_analyzer.py** | `market_radar_report()`, `classify_trend()` — report multi-market dari scan. |
| **market_radar_pro.py** | (di market/) Versi lain radar; ada juga di intelligence/. |

### 3.3 engine/detectors/

| Modul | Fungsi |
|-------|--------|
| **crash_detector.py** | `detect_market_crash()` — skor probabilitas crash dari risk score, stablecoin flow, funding, liquidation, whale; kirim alert. |
| **whale_tracker.py** | `detect_whale_activity()` — deteksi whale buy/sell dari whale_activity + stablecoin flow. |
| **altseason_detector.py** | `detect_altseason()` — skor altseason dari dominance, cycle, phase, stablecoin. |
| **liquidation_monitor.py** | Open interest, level OI, `liquidation_risk()`. |
| **smart_money_tracker.py** | `stablecoin_inflow()`, `smart_money_score()`. |
| **whale_signal_engine.py** | `scan_whale_signals()` — rule accumulation/distribution dari trend, RSI, whale_activity; `format_whale_alert()`. |

### 3.4 engine/intelligence/

| Modul | Fungsi |
|-------|--------|
| **crypto_intelligence.py** | Funding rate, analisis funding, altseason index/status. |
| **market_ai_predictor.py** | `market_phase()`, `bull_probability()`, `market_risk_score()`. |
| **market_intelligence.py** | `scan_market_intelligence()` — alert: BTC bottom zone, crash risk, altseason potential, market cycle. |
| **market_radar_pro.py** | `calculate_market_probabilities()` — bottom/crash/bull/altseason probability; `format_radar_report()`. |
| **predictive_market_ai.py** | `calculate_market_predictions()` — breakout, reversal, crash probability; `format_prediction_report()`. |
| **quant_market_model.py** | `calculate_market_score()` — skor 0–100 + market_bias (BULLISH/NEUTRAL/BEARISH/HIGH RISK); `format_quant_report()`. |
| **document_analyzer.py** | `analyze_document()` — baca dokumen aktif, panggil AI untuk ringkasan. |

### 3.5 engine/trading/

| Modul | Fungsi |
|-------|--------|
| **trade_manager.py** | CRUD posisi: `init_trade_db()`, `create_trade()`, `get_active_trades()`, `close_trade()`. DB SQLite `data/aliza.db`. |
| **opportunity_scanner.py** | `scan_opportunities()` — dari `get_all_market_data()` filter setup dengan RR ≥ 1.3, sort by RR, return list; `opportunity_report()` untuk teks top 3. |
| **signal_engine.py** | Auto signal: `scan_for_signals()` — filter RR ≥ 3, confidence ≥ 70, smart filter (BTC context, trend alignment), anti-spam 30 menit; `format_signal_message()`; dipakai job Telegram. |
| **trade_decision_ai.py** | `evaluate_trade(signal)` — skor kualitas trade dari RR, confidence, trend alignment, market risk, whale; return score + status (HIGH QUALITY / GOOD / MODERATE / AVOID). |
| **portfolio_engine.py** | `get_price()`, `calculate_pnl()`, `portfolio_report()` — laporan posisi + PnL (pakai cache + fallback Binance). |
| **position_manager.py** | `analyze_positions()` — rekomendasi partial profit, trail SL, break even dari PnL. |
| **trade_monitor.py** | `check_trades()` — cek TP/SL posisi aktif, auto close + alert. |

### 3.6 engine/monitoring/

| Modul | Fungsi |
|-------|--------|
| **market_monitor.py** | `monitor_market()`, `send_telegram()`, `format_message()` — monitoring kondisi market dan notifikasi. |

### 3.7 engine/utils/

| Modul | Fungsi |
|-------|--------|
| **market_cache.py** | `get_market_data(symbol)`, `get_all_market_data()` — cache in-memory (CACHE_TIME 60s), delegasi ke `market_signal()`. Mengurangi spam ke API eksternal. |
| **market_cache_updater.py** | `update_market_cache()` — refresh cache untuk semua MAJOR_COINS (bisa dijadwalkan). |

---

## 4. MARKET ANALYSIS PIPELINE

Alur data untuk satu symbol (contoh BTC):

```
1. market_cache.get_market_data(symbol)
   └── Jika cache valid (≤ 60s) → return cached
   └── Else ↓

2. market_analyzer.market_signal(symbol)
   ├── Fetch: price (CoinGecko), fear_greed, dominance
   ├── Hitung: MA50, MA200, RSI, support, resistance, trend
   ├── market_radar(fear, dominance)
   │   ├── crypto_intelligence (funding, altseason)
   │   ├── smart_money_tracker, liquidation_monitor
   │   └── market_ai_predictor (phase, bull prob, risk score)
   │   → radar dict (cycle_phase, whale_activity, funding_status, liquidation_risk, dll.)
   └── TradingBrain().analyze(market_data)
       → trade_setup: { setup, entry, sl, tp1, tp2, risk_reward, confidence, risk_quality }

3. market_data + trade_setup di-cache dan dikembalikan ke pemanggil.
```

Ringkas: **market_cache** → **market_analyzer** (yang di dalam memanggil **market_radar** dan **trading_brain**) → keluaran **trade_setup** melekat pada objek market per symbol.

---

## 5. TRADING SYSTEM

| Komponen | Peran |
|----------|--------|
| **trade_manager** | Satu-satunya persistence posisi: create/get/close di SQLite. Tabel `trades`: coin, setup, entry, stop_loss, tp1, tp2, status, created_at. |
| **opportunity_scanner** | Baca `get_all_market_data()`, filter kandidat dengan `trade_setup` dan RR ≥ 1.3, sort by RR, return list (dan `opportunity_report()` untuk teks). Dipakai command `/setfutures`. |
| **portfolio_engine** | Tampilkan posisi aktif: `get_active_trades()` + harga (cache/Binance), hitung PnL per posisi, format laporan. Dipakai `/portfolio`. |
| **position_manager** | Analisis PnL posisi; rekomendasi (partial profit, trail SL, break even). Bisa dipakai job atau command. |
| **trade_monitor** | Loop posisi aktif, bandingkan harga ke TP1/SL; jika kena, panggil `close_trade()` dan generate alert. |
| **ai_trade_guardian** | Loop posisi aktif, hitung PnL, map ke level alert (secure profit, partial, break even, risk warning, close warning); kirim saran ke Telegram (job), dengan memory agar tidak spam. |

Arah posisi (LONG/SHORT) disimpulkan dari field **setup** (mis. "PULLBACK LONG", "SHORT CONTINUATION") di semua modul yang butuh direction.

---

## 6. TELEGRAM BOT

**File:** `interfaces/telegram_bot.py`

### 6.1 Command handler

- **Market:** `/market [COIN]`, `/radar`, `/radarpro`, `/setfutures`
- **Trading:** `/entry COIN`, `/close COIN`, `/portfolio`
- **Intelijen:** `/predict`, `/quant`
- **System:** `/status`, `/testalert`, `/marketdebug`
- **Start:** `/start` — set `context.bot_data["chat_id"]` untuk pengiriman alert/job.

Command memanggil engine (market_cache, trade_manager, opportunity_scanner, portfolio_engine, market_radar_pro, predictive_market_ai, quant_market_model, dll.) dan membalas dengan format teks (Bahasa Indonesia).

### 6.2 Background jobs (job_queue.run_repeating)

| Job | Interval | First | Fungsi |
|-----|----------|-------|--------|
| trade_guardian_job | 60s | 30s | `analyze_trades()` → kirim alert saran PnL |
| crash_detector_job | 180s | 60s | `detect_market_crash()` → alert crash |
| whale_tracker_job | 180s | 90s | `detect_whale_activity()` → alert whale |
| altseason_detector_job | 300s | 120s | `detect_altseason()` → alert altseason |
| signal_engine_job | 300s | 120s | `scan_for_signals()` → kirim auto signal (RR≥3, confidence≥70) |
| whale_signal_job | 600s | 180s | `scan_whale_signals()` → kirim whale alert |
| market_intelligence_job | 900s | 300s | `scan_market_intelligence()` → kirim intel (bottom, crash, altseason, cycle) |

Semua job mengirim ke `context.bot_data.get("chat_id")` (di-set saat user `/start`).

### 6.3 Alert system

- Alert berasal dari job di atas + logic di engine (guardian, detector, signal_engine, whale_signal, market_intelligence).
- Format pesan konsisten (emoji + teks Bahasa Indonesia).
- Anti-spam: signal_engine pakai LAST_SIGNAL + 30 menit; guardian pakai ALERT_MEMORY per posisi.

### 6.4 Lain-lain

- Single-instance lock (PID file `data/telegram_bot.lock`) agar hanya satu proses bot.
- Startup: `init_trade_db()` agar tabel trades siap.

---

## 7. DASHBOARD API

**Base URL (contoh):** `http://SERVER_IP:8001` (port dari `ALIZA_DASHBOARD_PORT`, default 8001).

| Endpoint | Method | Fungsi |
|----------|--------|--------|
| `/` | GET | Dashboard HTML (`dashboard/index.html`) |
| `/health` | GET | Health check: `{ "status": "ok", "service": "AlizaAI Dashboard", "engine": "running" }` |
| `/market` | GET | Data market BTC (sederhana): `get_market_data("BTC")` |
| **/api/dashboard/market** | GET | Data market BTC (Market Radar) — objek penuh dari cache. |
| **/api/dashboard/quant** | GET | `calculate_market_score()` — market_score, market_bias, konteks. |
| **/api/dashboard/predict** | GET | `calculate_market_predictions()` — breakout/reversal/crash probability. |
| **/api/dashboard/signals** | GET | `scan_opportunities()` — list opportunity (coin, setup, entry, sl, tp1, tp2, rr, …). |
| **/api/dashboard/portfolio** | GET | Posisi aktif: list `{ coin, setup, entry, stop_loss, tp1, tp2 }`. |

Dashboard front-end memanggil `/api/dashboard/*` dan menampilkan di panel (Market Radar, Market Score, Predictive AI, Trading Signals, Portfolio, BTC Live Chart iframe).

---

## 8. DATABASE

- **Engine:** SQLite.
- **Path:** `data/aliza.db` (relatif terhadap CWD saat proses jalan; sebaiknya dijalankan dari root project).
- **Tabel:** `trades`
  - Kolom: `id`, `coin`, `setup`, `entry`, `stop_loss`, `tp1`, `tp2`, `status` ('OPEN'/'CLOSED'), `created_at`.
  - **trade_manager** satu-satunya modul yang menulis/membaca tabel ini; yang lain memakai `get_active_trades()`, `create_trade()`, `close_trade()`.
- Inisialisasi: `init_trade_db()` (CREATE TABLE IF NOT EXISTS) dipanggil saat startup Telegram bot.

---

## 9. MARKET CACHE

**File:** `engine/utils/market_cache.py`

- **Fungsi:** Menghindari spam ke API eksternal (CoinGecko, Fear & Greed, dll.) dengan cache in-memory per symbol.
- **CACHE_TIME:** 60 detik.
- **get_market_data(symbol):** Jika ada cache dan belum kadaluarsa → return cache; else panggil `market_signal(symbol)`, simpan ke cache, return.
- **get_all_market_data():** Loop `MAJOR_COINS`, panggil `get_market_data(coin)` untuk setiap coin (sehingga cache terisi untuk semua).
- **Update interval:** Cache hanya di-refresh on-demand saat data diminta setelah 60s. Optional: `market_cache_updater.update_market_cache()` bisa dijadwalkan terpisah.

Semua konsumen data market (scanner, signal engine, dashboard API, detector, dll.) sebaiknya memakai **get_market_data** / **get_all_market_data** agar memanfaatkan cache yang sama.

---

## 10. AUTO SIGNAL ENGINE

**File:** `engine/trading/signal_engine.py`

- **Tujuan:** Mengirim signal trading otomatis ke Telegram (tanpa command `/setfutures`) dengan filter kualitas.
- **Alur:**
  1. `scan_for_signals()` — data dari `get_all_market_data()`.
  2. Filter: **risk_reward ≥ 3**, **confidence ≥ 70**.
  3. Smart filter: konteks BTC (`get_btc_context()`); jika `market_risk == "HIGH"` skip semua; trend alignment (BEARISH skip LONG, BULLISH skip SHORT); SIDEWAYS kurangi confidence 10.
  4. Pilih 1 signal dengan RR tertinggi.
  5. Evaluasi: `evaluate_trade(signal)` → trade_score, trade_status; dilampirkan ke signal untuk ditampilkan di pesan.
  6. Anti-spam: jika coin yang sama sudah dikirim dalam 30 menit (LAST_SIGNAL, LAST_SIGNAL_TIME), tidak kirim lagi.
- **Format pesan:** `format_signal_message(signal)` — judul, coin/setup, entry/SL/TP, RR/confidence, Trade Score/Status, Market Context, footer.
- **Trigger:** Job Telegram `signal_engine_job` setiap 300s (first 120s).

---

## 11. DEPLOYMENT

- **Telegram Bot**
  - Jalan sebagai proses panjang (polling).
  - Bisa dijadikan service systemd, contoh nama: **aliza-telegram.service**.
  - Command: `python interfaces/telegram_bot.py` (dari root project, atau dengan PYTHONPATH/script yang set root).

- **Dashboard**
  - **Script:** `scripts/run_dashboard.py`
  - Port dari env: **ALIZA_DASHBOARD_PORT** (default **8001**).
  - Command: `python scripts/run_dashboard.py` (script sudah menambah ROOT_DIR ke `sys.path`).
  - Server: Uvicorn, app `api.server:app`, host `0.0.0.0`.
  - Akses: `http://SERVER_IP:8001` (atau port yang dikonfigurasi).

---

## 12. MARKET UNIVERSE

**File:** `engine/market/market_universe.py`

**MAJOR_COINS** — daftar symbol yang dianalisis (urutan tetap):

```text
BTC, ETH, BNB, SOL, XRP, ADA, DOGE, AVAX, TRX, TON, LINK, DOT, LTC, APT, ATOM
```

Semua scan multi-coin (opportunity_scanner, signal_engine, detector, dashboard) memakai list ini. Harga dan mapping ke exchange/API (mis. CoinGecko id) ada di **market_analyzer** (COINGECKO_IDS, dll.).

---

## 13. OUTPUT FORMAT

### Trade setup (dari TradingBrain / opportunity)

Struktur **trade_setup** atau item opportunity/signal:

| Field | Tipe | Keterangan |
|-------|------|-------------|
| **coin** | str | Symbol, e.g. "BTC", "ETH" |
| **setup** | str | E.g. "PULLBACK LONG", "SHORT CONTINUATION", "OVERSOLD BOUNCE" |
| **entry** | float | Harga entry |
| **sl** | float | Stop loss |
| **tp1** | float | Take profit 1 |
| **tp2** | float | Take profit 2 |
| **risk_reward** / **rr** | float | Reward/risk ratio |
| **confidence** | int | Skor kepercayaan (0–85+) |
| **risk_quality** | str | "EXCELLENT" / "GOOD" / "MEDIUM" / "POOR" |

Optional (setelah evaluasi/konteks): **trade_score**, **trade_status**, **btc_trend**, **market_risk**.

### Posisi aktif (get_active_trades)

Setiap baris: tuple `(coin, setup, entry, stop_loss, tp1, tp2)`.  
**Direction** tidak disimpan; disimpulkan dari **setup** (e.g. "LONG" in setup → LONG).

---

## 14. TUJUAN KE DEPAN

- **Dashboard trading terminal** — pengembangan dashboard web menjadi terminal trading lengkap (bukan hanya baca): tampilan posisi real-time, konfirmasi entry/close, integrasi notifikasi, dan (opsional) koneksi ke exchange untuk eksekusi yang tetap under user control.

---

**Akhir dokumen.**  
Untuk menambah fitur atau mengintegrasikan AI lain, gunakan dokumen ini sebagai referensi arsitektur dan kontrak data (cache, trade_manager, format trade_setup, endpoint dashboard).
