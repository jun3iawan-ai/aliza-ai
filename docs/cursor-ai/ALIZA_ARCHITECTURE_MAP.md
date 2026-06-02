# ALIZA AI — ARCHITECTURE MAP

## USER INTERFACE

User
↓
Telegram Bot
↓
Dashboard API

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
trade_setup

---

## MARKET SNAPSHOT

market_snapshot_engine

Stores validated market data every 60 seconds.

Telegram commands use snapshot instead of API calls.

---

## TRADING SYSTEM

TradingBrain
↓
Opportunity Scanner
↓
Signal Engine

Trade Manager
↓
SQLite database

Position Manager
↓
Telegram alerts

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

SQLite
data/aliza.db

Tables:

trades