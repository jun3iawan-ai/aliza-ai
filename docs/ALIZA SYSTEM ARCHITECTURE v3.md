# ALIZA AI — System Architecture

Version: v3  
System: AlizaAI Trading Intelligence Platform

---

## 1. Tujuan Sistem

**Aliza** adalah **AI Trading Assistant** untuk crypto market yang:

- menganalisis kondisi market
- menghasilkan trade setup (entry, SL, TP)
- menghitung risk reward
- memberikan sinyal trading
- memonitor posisi
- mengirim alert ke Telegram

**Aliza TIDAK melakukan auto trading.**

---

## 2. High-Level Architecture

```
User (Telegram / Web)
        ↓
Telegram Bot / Web Dashboard
        ↓
API Layer (FastAPI)
        ↓
Engine (Market + Trading)
        ↓
Market Cache → Market Analyzer → Market Radar → Trading Brain
        ↓
Trade Manager / Opportunity Scanner / Portfolio / Monitor / Guardian
        ↓
External APIs (CoinGecko, Fear & Greed, dll.)
```

---

## 3. Struktur Repository

```
aliza-ai/
├── api/           # FastAPI: server, dashboard API, auth
├── core/          # AI core: agent, RAG, knowledge base, tools
├── engine/        # Trading & market engine
├── interfaces/    # Telegram bot, market bot
├── scripts/       # run_dashboard.py, deploy, server-monitor
├── dashboard/     # Dashboard HTML (dilayani FastAPI)
├── web/           # Web UI (index, btc, app.js, style.css)
├── data/          # SQLite aliza.db, lock file
├── docs/          # Dokumentasi
├── memory/        # User memory, document registry
├── knowledge/     # documents, uploads, vector_store
└── config/        # agent.yaml
```

---

## 4. Engine Structure

```
engine/
├── brain/         trading_brain, ai_trade_guardian, aliza_engine
├── market/        market_analyzer, market_radar, market_report_formatter,
│                  radar_analyzer, market_universe
├── detectors/     crash_detector, whale_tracker, altseason_detector,
│                  liquidation_monitor, smart_money_tracker
├── intelligence/  crypto_intelligence, market_ai_predictor, document_analyzer
├── trading/       opportunity_scanner, trade_manager, trade_monitor,
│                  position_manager, portfolio_engine
├── monitoring/    market_monitor
└── utils/         market_cache, market_cache_updater
```

---

## 5. Market Analysis Pipeline

```
market_cache (engine/utils/market_cache.py)
    → get_market_data(symbol) / get_all_market_data()
    → market_analyzer.market_signal(symbol)  (engine/market/market_analyzer.py)
        → market_radar  (engine/market/market_radar.py)
        → trading_brain.analyze()  (engine/brain/trading_brain.py)
            → trade_setup (setup, entry, sl, tp1, tp2, risk_reward, confidence, risk_quality)
```

- **market_cache:** Menghindari spam API; menyimpan data sementara (60s).
- **market_analyzer:** Fetch harga, sentiment, dominance; hitung MA, RSI, S/R; panggil market_radar dan trading_brain.
- **market_radar:** Sinyal makro (funding, whale, liquidation risk, cycle phase, market risk).
- **trading_brain:** Menghasilkan setup dan level entry/SL/TP dari trend, RSI, S/R.

---

## 6. Trading System

| Komponen | File | Fungsi |
|----------|------|--------|
| Trade Manager | engine/trading/trade_manager.py | Menyimpan trade di SQLite (create, get, close). Tabel `trades` di `data/aliza.db`. |
| Opportunity Scanner | engine/trading/opportunity_scanner.py | Mencari peluang trading dari cache; filter RR; ranking; dipakai `/setfutures`. |
| Portfolio Engine | engine/trading/portfolio_engine.py | Menghitung PnL posisi aktif. |
| Position Manager | engine/trading/position_manager.py | Saran manajemen posisi (partial profit, trail SL, break even). |
| Trade Monitor | engine/trading/trade_monitor.py | Mendeteksi TP/SL hit; auto close + alert. |
| AI Trade Guardian | engine/brain/ai_trade_guardian.py | Alert keamanan posisi ke Telegram (background job). |

---

## 7. Telegram Bot

**File:** `interfaces/telegram_bot.py`

**Command:** `/start`, `/market`, `/radar`, `/setfutures`, `/entry`, `/close`, `/portfolio`, `/status`, `/testalert`, `/marketdebug` (dan `/radarpro`, `/predict`, `/quant` di code).

**Background jobs:**

- trade_guardian_job (60s)
- crash_detector_job (180s)
- whale_tracker_job (180s)
- altseason_detector_job (300s)

---

## 8. Database

- **SQLite,** path: `data/aliza.db`
- **Tabel:** `trades` (id, coin, setup, entry, stop_loss, tp1, tp2, status, created_at)
- **init_trade_db()** dipanggil saat startup bot.

---

## 9. Market Cache

**File:** `engine/utils/market_cache.py`

- Mengurangi request API berulang; menyimpan market data sementara.
- Cache 60 detik; `get_market_data(symbol)`, `get_all_market_data()`.

---

## 10. Dashboard API

Endpoint:

- `/api/dashboard/market` — Data market BTC
- `/api/dashboard/predict` — Probabilitas prediksi
- `/api/dashboard/quant` — Skor dan bias market
- `/api/dashboard/signals` — Daftar opportunity
- `/api/dashboard/portfolio` — Posisi aktif

---

## 11. Dashboard Server

- **Script:** `scripts/run_dashboard.py`
- **Port:** 8001 (env: `ALIZA_DASHBOARD_PORT`)
- Menjalankan FastAPI (uvicorn) untuk dashboard dan API.

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

## 15. AI Trading Workflow

```
Market Data (external API)
    → Market Cache
    → Market Analyzer
    → Market Radar
    → Trading Brain → trade_setup
    → Opportunity Scanner
    → Trade Entry (user) / Signal
    → Trade Manager (persist)
    → Portfolio Engine / Position Manager
    → Trade Monitor (TP/SL)
    → AI Trade Guardian (alert)
```

---

End of document
