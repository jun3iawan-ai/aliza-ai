# ALIZA AI — ARCHITECTURE MAP

## USER INTERFACE

User
├── Telegram Bot (`interfaces/telegram_bot.py`)
└── Dashboard API (`api/server.py` + `api/dashboard_api.py`)

---

## MARKET DATA FLOW

External APIs
(CoinGecko, Binance, Fear & Greed)

↓
market_analyzer

↓
market_radar

↓
TradingBrain

↓
market_snapshot_engine

---

## MARKET SNAPSHOT

`snapshot_job` memanggil `update_market_snapshot()` setiap 60 detik.

Opportunity scanner membaca snapshot tervalidasi. Snapshot stale/invalid menghentikan scan tanpa fallback ke market cache.

Sebagian command/checker khusus memiliki upstream call langsung dengan timeout dan error handling.

---

## TRADING SYSTEM

TradingBrain
↓
Opportunity Scanner
↓
Production Signal Scanner (`scan_for_signals`)
↓
Unified Gateway (risk + dedup + dispatch)
↓
Telegram
↓
Signal Tracker (record setelah dispatch sukses)

Trade Manager
↓
SQLite `trades`

---

## INTELLIGENCE SYSTEM

Predictive AI
Quant Market Model
Market Intelligence
Whale Detector
Crash Detector
Altseason Detector

---

## STORAGE

`data/aliza.db`

Tables:

`trades` — ditulis oleh `engine/trading/trade_manager.py`

`signal_tracking` — schema/migrasi dan row ditulis oleh `engine/trading/signal_tracker.py`

`data/user_config.db` adalah database terpisah untuk konfigurasi user.

---

## DASHBOARD API

`api/dashboard_api.py` menyediakan:

- `/api/dashboard/market`
- `/api/dashboard/quant`
- `/api/dashboard/predict`
- `/api/dashboard/signals`
- `/api/dashboard/portfolio`

<!-- Diverifikasi akurat per 2026-07-21, commit f38ab55 -->
