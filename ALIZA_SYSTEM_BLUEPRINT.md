# ALIZA AI --- SYSTEM BLUEPRINT

## 1. System Vision

AlizaAI adalah platform AI modular yang dapat berkembang menjadi:

-   AI Assistant Platform
-   Document Intelligence System
-   Crypto Market Intelligence Platform
-   Multi‑Agent AI System
-   SaaS AI Infrastructure

Tujuan utama adalah membangun **AI platform mandiri seperti mini
ChatGPT + AI tools ecosystem**.

------------------------------------------------------------------------

## 2. High Level Architecture

Client Layer (Web / Telegram / Future Apps)\
↓\
Nginx Reverse Proxy\
↓\
FastAPI Backend\
↓\
AI Core Engine\
↓\
Memory System \| RAG Engine \| Intelligence Engine\
↓\
PostgreSQL \| Vector Store \| Market Analyzer

------------------------------------------------------------------------

## 3. Client Layer

Interface pengguna:

-   Web Chat UI
-   Telegram Bot
-   WhatsApp (planned)

Frontend stack:

-   HTML
-   CSS
-   JavaScript

API utama:

POST /api/chat

------------------------------------------------------------------------

## 4. Backend Layer

Framework backend:

-   Python
-   FastAPI

Fungsi utama:

-   API routing
-   AI orchestration
-   database communication
-   tool execution

Server berjalan menggunakan:

Uvicorn + systemd service

Service aktif:

-   aliza-api
-   aliza-telegram
-   nginx

------------------------------------------------------------------------

## 5. AI Core Engine

File utama:

core/agent.py

Fungsi:

-   reasoning
-   skill selection
-   tool execution
-   response generation

Pipeline:

User Message\
→ Agent Reasoning\
→ Skill Selection\
→ Tool Execution\
→ Response Generation

------------------------------------------------------------------------

## 6. Skill System

Skill system memungkinkan AI menjalankan berbagai fungsi.

Contoh skill:

-   document_search
-   weather
-   crypto_analysis
-   system_tools

File terkait:

core/skill_loader.py\
core/tools.py

------------------------------------------------------------------------

## 7. Tool Router

Tool Router menentukan tool yang tepat untuk task tertentu.

File:

core/tool_router.py

Contoh tool:

-   search_document
-   calculate
-   crypto_data
-   system_info

------------------------------------------------------------------------

## 8. RAG Document System

RAG digunakan untuk knowledge retrieval.

Pipeline:

Upload Document\
→ Text Extraction\
→ Embedding\
→ Vector Storage\
→ Semantic Search\
→ AI Response

Folder:

knowledge/\
vector_store/

File utama:

core/rag_engine.py\
engine/document_analyzer.py

------------------------------------------------------------------------

## 9. Memory System

Memory menyimpan interaksi pengguna.

Database:

PostgreSQL

Tables utama:

-   users
-   chats
-   usage
-   documents

Digunakan untuk:

-   chat history
-   user context
-   usage tracking

------------------------------------------------------------------------

## 10. Crypto Intelligence Engine

Komponen ini menganalisis kondisi market crypto.

File:

engine/market_analyzer.py

Endpoint API:

GET /api/market/btc

Data yang dianalisis:

-   BTC price
-   RSI
-   MA50
-   MA200
-   Fear & Greed
-   BTC dominance
-   market cycle
-   market score

AI Intelligence:

-   market prediction
-   bottom probability
-   crash probability
-   altseason probability
-   whale activity

Data source:

-   CoinGecko API
-   Alternative.me Fear & Greed

##  ---

## 10.1 ALIZA MARKET RADAR

Market Radar adalah modul lanjutan dari Crypto Intelligence Engine
yang bertugas melakukan monitoring kondisi market secara real-time.

File utama:

engine/market_radar.py

Fungsi utama modul ini:

• market risk monitoring
• whale activity tracking
• bottom detection
• crash detection
• altseason detection

---

Market Radar Pipeline

Market Data Sources
↓
Market Analyzer
↓
Market Radar Engine
↓
AI Trading Brain
↓
API Response / Alert System

---

Market Radar Components

BTC Bottom Detector

Mendeteksi kemungkinan market bottom menggunakan kombinasi:

• RSI
• Fear & Greed Index
• BTC dominance
• market cycle
• whale activity

---

Crash Detection Engine

Menganalisis kemungkinan crash menggunakan:

• overbought RSI
• extreme greed sentiment
• BTC dominance drop
• trend reversal

---

Altseason Detector

Menentukan kemungkinan dimulainya altcoin season dengan analisis:

• BTC dominance trend
• market cycle shift

---

Whale Activity Tracker

Melacak transaksi besar pada blockchain untuk mendeteksi aktivitas
akumulasi whale.

---

Alert System

Market Radar dapat mengirim alert melalui:

• Telegram Bot
• Web Dashboard
• API endpoint

Contoh alert:

BTC MARKET RADAR ALERT

Crash probability: HIGH
Whale activity: DISTRIBUTING
Trend: BULLISH

Potential market reversal detected.

---

## 10.2 ALIZA GLOBAL MARKET BRAIN

Global Market Brain adalah modul macro intelligence layer yang membaca kondisi pasar global yang mempengaruhi crypto market.

Modul ini memperluas kemampuan Aliza dari crypto market intelligence menjadi macro + crypto intelligence system.

File utama yang akan digunakan:

engine/global_market_brain.py
Global Market Brain Pipeline
Global Market Data Sources
↓
Macro Analyzer
↓
Global Market Brain
↓
Market Radar
↓
AI Trading Brain
↓
API Response / Alert System
Global Data Sources

Global Market Brain akan membaca berbagai indikator makro ekonomi global:

• DXY (US Dollar Index)
• S&P500 Index
• NASDAQ Index
• Global Interest Rate
• Global Liquidity Index
• Total Crypto Market Capitalization

Data ini akan digunakan untuk menentukan macro market environment.

Macro Intelligence Analysis

Global Market Brain akan menghasilkan analisis seperti:

• Risk-On / Risk-Off Environment
• Global Liquidity Expansion / Contraction
• Macro Volatility Risk
• Crypto Market Expansion Probability

Example Output

Contoh output dari modul Global Market Brain:

GLOBAL MARKET INTELLIGENCE

DXY: BULLISH
S&P500: WEAK
NASDAQ: BEARISH
Liquidity: TIGHT

Macro Environment:
RISK OFF

Impact on Crypto:
HIGH VOLATILITY
Role in Aliza Architecture

Global Market Brain akan menjadi lapisan analisis makro yang memberikan konteks tambahan kepada:

• Market Radar
• Trading Brain
• Alert System

Dengan adanya layer ini, Aliza dapat memahami:

• hubungan antara market global dan crypto
• kondisi likuiditas global
• fase siklus pasar yang lebih besar

Dampak terhadap sistem Aliza

Setelah modul ini selesai, kemampuan Aliza akan berkembang dari:

Crypto Market Analyzer
↓
Crypto Intelligence Platform
↓
Macro + Crypto Intelligence System

yang mendekati kemampuan market intelligence tools yang digunakan oleh hedge fund dan trading desk profesional.

## 11. Crypto Intelligence Dashboard

Dashboard web tersedia di:

https://juniawan.web.id/btc

Frontend files:

web/btc/index.html\
web/btc/btc.css\
web/btc/btc.js

Dashboard menampilkan:

-   BTC price
-   RSI
-   Fear & Greed
-   BTC dominance
-   Market score
-   Trend
-   Cycle phase
-   AI prediction
-   Bottom probability
-   Crash probability
-   Altseason probability
-   Whale activity
-   TradingView chart
-   AI analysis

------------------------------------------------------------------------

## 12. Deployment Architecture

Server environment:

VPS Ubuntu

Web server:

Nginx

Backend API:

FastAPI

Internal API:

http://127.0.0.1:8000

Public domain:

https://juniawan.web.id

------------------------------------------------------------------------

## 13. Security Layer

Current security:

-   HTTPS (Let's Encrypt)

Future security improvements:

-   JWT authentication
-   role‑based access control
-   API rate limiting

------------------------------------------------------------------------

## 14. Scaling Plan

Saat sistem berkembang, arsitektur dapat diperluas menjadi:

Load Balancer\
Multiple API Servers\
Redis Cache\
Vector Database\
Worker Queue

------------------------------------------------------------------------

## 15. Future Expansion

Fitur masa depan:

-   Multi‑agent AI
-   Auto research agent
-   Trading intelligence AI
-   AI SaaS platform
-   Enterprise AI assistant

------------------------------------------------------------------------

## 16. Development Philosophy

AlizaAI dibangun dengan prinsip:

-   modular architecture
-   AI‑first design
-   scalable infrastructure
-   multi‑channel interface
-   tool‑based intelligence

Tujuan akhirnya adalah membangun **AI ecosystem platform** yang dapat
berkembang menjadi AI startup‑scale system.
