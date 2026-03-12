# ALIZA AI — Project Guide

Dokumentasi utama project AlizaAI. Diperbarui sesuai kondisi repository saat ini.

---

## 1. Tujuan Aliza

**Aliza** adalah **AI Trading Assistant** untuk crypto market yang:

- menganalisis kondisi market
- menghasilkan trade setup (entry, SL, TP)
- menghitung risk reward
- memberikan sinyal trading
- memonitor posisi
- mengirim alert ke Telegram

**Aliza TIDAK melakukan auto trading.** Eksekusi order tetap dilakukan oleh user.

---

## 2. Struktur Repository

```
aliza-ai/
├── api/           # REST API (FastAPI): server, dashboard API, auth
├── core/          # AI core: agent, RAG, knowledge base, tools, skill loader
├── engine/        # Trading & market engine (lihat bagian 4)
├── interfaces/    # Telegram bot, market bot
├── scripts/       # run_dashboard.py, deploy, server-monitor
├── dashboard/     # Web dashboard (HTML) dilayani oleh FastAPI
├── web/           # Web UI (index.html, btc/, app.js, style.css)
├── data/          # SQLite (aliza.db), lock file
├── docs/          # Dokumentasi
├── memory/        # User memory, document registry
├── knowledge/     # documents, uploads, vector_store
├── config/        # agent.yaml
├── project/       # Script project
└── skills_custom/ # Custom skills
```

| Folder | Peran |
|--------|--------|
| **api/** | FastAPI server, dashboard API (`/api/dashboard/*`), auth. Route `/` menyajikan dashboard, `/health` untuk health check. |
| **core/** | Agent AI, RAG, knowledge base, tool router, skill loader. |
| **engine/** | Inti trading: analisis market, radar, trading brain, detector, intelligence, trade manager, opportunity scanner, signal engine, dll. |
| **interfaces/** | Telegram bot (`telegram_bot.py`), market bot (`market_bot.py`). |
| **scripts/** | `run_dashboard.py` (menjalankan dashboard di port 8001), deploy, server-monitor. |
| **dashboard/** | File HTML dashboard yang dilayani oleh FastAPI. |
| **web/** | Web UI (index, btc, app.js, style.css). |
| **data/** | Database SQLite `aliza.db`, file lock bot. |
| **docs/** | Dokumentasi project. |

---

## 3. Engine Structure

```
engine/
├── brain/           # Keputusan trading & AI assistant
│   ├── trading_brain.py
│   ├── ai_trade_guardian.py
│   └── aliza_engine.py
├── market/          # Analisis market & radar
│   ├── market_analyzer.py
│   ├── market_radar.py
│   ├── market_report_formatter.py
│   ├── radar_analyzer.py
│   └── market_universe.py
├── detectors/       # Deteksi event market
│   ├── crash_detector.py
│   ├── whale_tracker.py
│   ├── altseason_detector.py
│   ├── liquidation_monitor.py
│   └── smart_money_tracker.py
├── intelligence/    # Model intelijen
│   ├── crypto_intelligence.py
│   ├── market_ai_predictor.py
│   └── document_analyzer.py
├── trading/         # Trade lifecycle
│   ├── opportunity_scanner.py
│   ├── trade_manager.py
│   ├── trade_monitor.py
│   ├── position_manager.py
│   └── portfolio_engine.py
├── monitoring/      # Monitoring market
│   └── market_monitor.py
└── utils/           # Cache & utilitas
    ├── market_cache.py
    └── market_cache_updater.py
```

Modul tambahan di repository (mis. `signal_engine.py`, `trade_decision_ai.py`, `whale_signal_engine.py`, `market_intelligence.py`, `market_radar_pro.py`, `predictive_market_ai.py`, `quant_market_model.py`) mendukung auto signal, evaluasi trade, dan laporan intelijen; rincian ada di `docs/ALIZA_SYSTEM_CONTEXT.md`.

---

## 4. Market Analysis Pipeline

Alur data analisis market:

```
market_cache (get_market_data / get_all_market_data)
    → market_analyzer (market_signal)
        → market_radar (sinyal makro: funding, whale, risk, phase)
        → trading_brain (setup, entry, sl, tp, rr, confidence)
            → trade_setup
```

- **market_cache** (`engine/utils/market_cache.py`): cache in-memory, mengurangi spam API, refresh per 60 detik.
- **market_analyzer** (`engine/market/market_analyzer.py`): fetch harga, Fear & Greed, dominance; hitung MA, RSI, S/R; panggil market_radar dan trading_brain.
- **market_radar**: funding, whale, open interest, liquidation risk, cycle phase, market risk score.
- **trading_brain**: dari trend, RSI, S/R menghasilkan **setup** (PULLBACK LONG, SHORT CONTINUATION, OVERSOLD BOUNCE, dll.) dan **entry, sl, tp1, tp2, risk_reward, confidence, risk_quality**.

---

## 5. Trading System

| Modul | Fungsi |
|-------|--------|
| **trade_manager** | Menyimpan dan mengelola trade di SQLite (`data/aliza.db`, tabel `trades`). `create_trade()`, `get_active_trades()`, `close_trade()`, `init_trade_db()`. |
| **opportunity_scanner** | Mencari peluang trading dari `get_all_market_data()`, filter RR ≥ 1.3, sort by RR, return daftar opportunity. Dipakai command `/setfutures`. |
| **portfolio_engine** | Menghitung PnL posisi aktif (harga dari cache/Binance), format laporan portfolio. |
| **position_manager** | Memberi saran manajemen posisi (partial profit, trail SL, break even) berdasarkan PnL. |
| **trade_monitor** | Mendeteksi TP/SL hit; jika harga mencapai TP atau SL, panggil `close_trade()` dan kirim alert. |
| **ai_trade_guardian** | Menganalisis posisi aktif, hitung PnL, map ke status (SECURE_PROFIT, PARTIAL_PROFIT, RISK_WARNING, dll.), memberi alert keamanan posisi ke Telegram (background job). |

---

## 6. Telegram Bot

**File:** `interfaces/telegram_bot.py`

### Command handler

| Command | Fungsi |
|---------|--------|
| `/start` | Set chat_id untuk penerima alert; sambutan. |
| `/market` | Data market (default BTC atau coin yang diberikan). |
| `/radar` | Laporan market radar. |
| `/setfutures` | Daftar opportunity terbaik dari opportunity_scanner. |
| `/entry` | Buka posisi (coin, setup, entry, sl, tp1, tp2). |
| `/close` | Tutup posisi untuk coin. |
| `/portfolio` | Tampilkan posisi aktif. |
| `/status` | Status sistem (engine, cache, trade monitor, jumlah posisi, coins). |
| `/testalert` | Kirim test alert. |
| `/marketdebug` | Debug output market_signal. |

Command tambahan yang ada di code: `/radarpro`, `/predict`, `/quant` (laporan radar pro, prediksi, quant model).

### Background jobs

| Job | Interval | Fungsi |
|-----|----------|--------|
| trade_guardian_job | 60s | ai_trade_guardian: analisis posisi, alert keamanan. |
| crash_detector_job | 180s | crash_detector: alert risiko crash. |
| whale_tracker_job | 180s | whale_tracker: alert aktivitas whale. |
| altseason_detector_job | 300s | altseason_detector: alert potensi altseason. |

Job lain di code: signal_engine_job, whale_signal_job, market_intelligence_job (auto signal, whale signal, market intelligence).

---

## 7. Database

- **Engine:** SQLite  
- **Path:** `data/aliza.db`  
- **Tabel:** `trades`  
  - Kolom: `id`, `coin`, `setup`, `entry`, `stop_loss`, `tp1`, `tp2`, `status`, `created_at`.  
- Inisialisasi: `init_trade_db()` dipanggil saat startup Telegram bot.

---

## 8. Market Cache

**File:** `engine/utils/market_cache.py`

- **Fungsi:** Menghindari spam API; menyimpan market data sementara (in-memory).
- **CACHE_TIME:** 60 detik.
- **get_market_data(symbol):** Return cache jika masih valid; jika tidak, panggil `market_signal(symbol)` lalu simpan ke cache.
- **get_all_market_data():** Loop MAJOR_COINS, isi cache untuk semua coin.

---

## 9. Dashboard API

Endpoint yang tersedia (prefix `/api/dashboard`):

| Endpoint | Fungsi |
|----------|--------|
| `/api/dashboard/market` | Data market BTC (Market Radar). |
| `/api/dashboard/predict` | Probabilitas prediksi market (predictive_market_ai). |
| `/api/dashboard/quant` | Skor dan bias market (quant_market_model). |
| `/api/dashboard/signals` | Daftar opportunity (opportunity_scanner). |
| `/api/dashboard/portfolio` | Posisi aktif (coin, setup, entry, stop_loss, tp1, tp2). |

---

## 10. Dashboard Server

- **Script:** `scripts/run_dashboard.py`
- **Port default:** 8001 (konfigurasi via env `ALIZA_DASHBOARD_PORT`).
- Menjalankan FastAPI (uvicorn) dengan app `api.server:app`, host `0.0.0.0`.
- Cara jalankan: `python scripts/run_dashboard.py` (dari root project).

---

## 11. Deployment

- **Telegram Bot:** Dijalankan sebagai systemd service (`aliza-telegram.service`). Entry point: `interfaces/telegram_bot.py`.
- **Dashboard:** Dijalankan dengan `scripts/run_dashboard.py` (bisa dijadwalkan atau di-wrap systemd).

---

## 12. Market Universe

Coin yang dianalisis didefinisikan di:

**File:** `engine/market/market_universe.py`  
**Variabel:** `MAJOR_COINS`

Contoh isi: BTC, ETH, BNB, SOL, XRP, ADA, DOGE, AVAX, TRX, TON, LINK, DOT, LTC, APT, ATOM (daftar lengkap ada di file).

---

## 13. Output Trade Setup

Format **trade_setup** (dari trading_brain / opportunity):

| Field | Keterangan |
|-------|------------|
| coin | Symbol (BTC, ETH, …) |
| setup | Nama setup (PULLBACK LONG, SHORT CONTINUATION, OVERSOLD BOUNCE, dll.) |
| entry | Harga entry |
| sl | Stop loss |
| tp1 | Take profit 1 |
| tp2 | Take profit 2 |
| risk_reward | Rasio risk reward |
| confidence | Skor kepercayaan |
| risk_quality | EXCELLENT / GOOD / MEDIUM / POOR |

---

## 14. Dokumentasi Terkait

- **docs/ALIZA_SYSTEM_CONTEXT.md** — Konteks sistem lengkap untuk AI dan developer (pipeline, endpoint, format data).
- **docs/ALIZA SYSTEM ARCHITECTURE v3.md** — Arsitektur sistem.
- **docs/ALIZA_SYSTEM_MAP.md** — Peta modul dan alur.

---

End of document.
