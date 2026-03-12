# ALIZA AI — System Map

Version: 2.0  
Type: AI Trading Assistant

Dokumentasi peta sistem sesuai kondisi repository saat ini.

---

## 1. Tujuan Sistem

**Aliza** adalah AI Trading Assistant untuk crypto market yang:

- menganalisis kondisi market
- menghasilkan trade setup (entry, SL, TP)
- menghitung risk reward
- memberikan sinyal trading
- memonitor posisi
- mengirim alert ke Telegram

Aliza **tidak melakukan auto trading**.

---

## 2. Alur Utama (Core Flow)

```
Market Data (external API)
    ↓
Market Cache (engine/utils/market_cache.py)
    ↓
Market Analyzer (engine/market/market_analyzer.py)
    ↓
Market Radar + Trading Brain
    ↓
trade_setup (setup, entry, sl, tp1, tp2, risk_reward, confidence)
    ↓
Opportunity Scanner / Signal Engine / Trade Manager
    ↓
Telegram / Dashboard API
```

---

## 3. Struktur Project

```
aliza-ai/
├── api/           # FastAPI: server, dashboard API, auth
├── core/          # AI core: agent, RAG, knowledge base, tools, skill loader
├── engine/        # Trading & market engine
├── interfaces/    # Telegram bot, market bot
├── scripts/       # run_dashboard.py, deploy, server-monitor
├── dashboard/     # Dashboard HTML (dilayani FastAPI)
├── web/           # Web UI (index.html, btc/, app.js, style.css)
├── data/          # SQLite aliza.db, lock file
├── docs/          # Dokumentasi
├── memory/        # User memory, document registry
├── knowledge/     # documents, uploads, vector_store
└── config/        # agent.yaml
```

---

## 4. Engine Structure

### brain/

| File | Fungsi |
|------|--------|
| trading_brain.py | Menghasilkan setup, entry, sl, tp1, tp2, risk_reward, confidence, risk_quality dari trend, RSI, S/R. |
| ai_trade_guardian.py | Analisis posisi aktif, PnL, alert keamanan ke Telegram. |
| aliza_engine.py | Integrasi AI assistant (chat). |

### market/

| File | Fungsi |
|------|--------|
| market_analyzer.py | market_signal(symbol), btc_signal(); fetch harga, Fear & Greed, dominance; MA, RSI, S/R; panggil market_radar dan trading_brain. |
| market_radar.py | Sinyal makro: funding, whale, OI, liquidation risk, cycle phase, market risk. |
| market_report_formatter.py | Format output analisis. |
| radar_analyzer.py | Report multi-market, classify_trend. |
| market_universe.py | MAJOR_COINS — daftar coin yang dianalisis. |

### detectors/

| File | Fungsi |
|------|--------|
| crash_detector.py | Deteksi risiko crash; alert. |
| whale_tracker.py | Deteksi aktivitas whale. |
| altseason_detector.py | Deteksi potensi altseason. |
| liquidation_monitor.py | Open interest, liquidation risk. |
| smart_money_tracker.py | Smart money / stablecoin flow. |

### intelligence/

| File | Fungsi |
|------|--------|
| crypto_intelligence.py | Funding rate, altseason index. |
| market_ai_predictor.py | Phase, bull probability, market risk score. |
| document_analyzer.py | Analisis dokumen dengan AI. |

### trading/

| File | Fungsi |
|------|--------|
| opportunity_scanner.py | Cari peluang trading; filter RR; dipakai /setfutures. |
| trade_manager.py | CRUD posisi di SQLite (data/aliza.db, tabel trades). |
| trade_monitor.py | Deteksi TP/SL hit; auto close + alert. |
| position_manager.py | Saran manajemen posisi (partial, trail, break even). |
| portfolio_engine.py | Hitung PnL; laporan portfolio. |

### monitoring/

| File | Fungsi |
|------|--------|
| market_monitor.py | Monitor kondisi market; notifikasi. |

### utils/

| File | Fungsi |
|------|--------|
| market_cache.py | Cache market data; hindari spam API; CACHE_TIME 60s. |
| market_cache_updater.py | Update cache untuk semua MAJOR_COINS. |

---

## 5. Market Analysis Pipeline

```
market_cache (get_market_data / get_all_market_data)
    → market_analyzer (market_signal)
        → market_radar
        → trading_brain
            → trade_setup
```

---

## 6. Trading System

| Modul | Fungsi |
|-------|--------|
| trade_manager | Menyimpan trade di SQLite (create_trade, get_active_trades, close_trade). |
| opportunity_scanner | Mencari peluang trading; ranking RR. |
| portfolio_engine | Menghitung PnL. |
| position_manager | Saran manajemen posisi. |
| trade_monitor | Mendeteksi TP/SL hit. |
| ai_trade_guardian | Alert keamanan posisi ke Telegram. |

---

## 7. Telegram Bot

**File:** `interfaces/telegram_bot.py`

**Command:** /start, /market, /radar, /setfutures, /entry, /close, /portfolio, /status, /testalert, /marketdebug (dan /radarpro, /predict, /quant).

**Background jobs:** trade_guardian_job, crash_detector_job, whale_tracker_job, altseason_detector_job (dan signal_engine_job, whale_signal_job, market_intelligence_job).

---

## 8. Database

- **SQLite:** `data/aliza.db`
- **Tabel:** `trades` (id, coin, setup, entry, stop_loss, tp1, tp2, status, created_at)
- **init_trade_db()** dipanggil saat startup bot.

---

## 9. Market Cache

**File:** `engine/utils/market_cache.py`

- Menghindari spam API; menyimpan market data sementara (60s).
- `get_market_data(symbol)`, `get_all_market_data()`.

---

## 10. Dashboard API

| Endpoint | Fungsi |
|----------|--------|
| /api/dashboard/market | Data market BTC |
| /api/dashboard/predict | Probabilitas prediksi |
| /api/dashboard/quant | Skor dan bias market |
| /api/dashboard/signals | Daftar opportunity |
| /api/dashboard/portfolio | Posisi aktif |

---

## 11. Dashboard Server

- **Script:** `scripts/run_dashboard.py`
- **Port:** 8001 (env: ALIZA_DASHBOARD_PORT)

---

## 12. Deployment

- **Telegram Bot:** systemd service `aliza-telegram.service`
- **Dashboard:** `python scripts/run_dashboard.py`

---

## 13. Market Universe

**File:** `engine/market/market_universe.py`  
**Variabel:** `MAJOR_COINS` — daftar coin yang dianalisis (BTC, ETH, BNB, SOL, …).

---

## 14. Output Trade Setup

Format: **coin**, **setup**, **entry**, **sl**, **tp1**, **tp2**, **risk_reward**, **confidence**, **risk_quality**.

---

End of System Map
