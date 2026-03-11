# ALIZA AI --- PROJECT GUIDE

# 1. Project Overview

AlizaAI adalah platform AI assistant yang berjalan di berbagai channel:

• Web Chat\
• Telegram Bot\
• WhatsApp (planned)

Tujuan project adalah membuat **AI platform mandiri seperti mini
ChatGPT** yang dapat:

• menjawab pertanyaan\
• membaca dokumen\
• menyimpan chat history\
• melacak penggunaan AI\
• memiliki memory pengguna\
• menyediakan **AI Market Intelligence**

AlizaAI dikembangkan sebagai platform AI modular yang dapat diperluas
menjadi:

• AI assistant platform\
• AI document analysis system\
• AI crypto market intelligence platform

------------------------------------------------------------------------

# 2. Infrastructure

Server Environment

• VPS Ubuntu\
• Nginx Reverse Proxy\
• HTTPS (Let's Encrypt)\
• Domain publik

Production URL:

https://juniawan.web.id

Internal API:

http://127.0.0.1:8000

Server menggunakan arsitektur:

Client → Nginx → FastAPI → AI Engine

------------------------------------------------------------------------

# 3. Backend Stack

Backend menggunakan:

• Python\
• FastAPI\
• PostgreSQL Database\
• Custom AI Engine\
• RAG Document System\
• Market Intelligence Engine

Server berjalan menggunakan:

Uvicorn + Systemd service

Service aktif:

aliza-api\
aliza-telegram\
nginx

------------------------------------------------------------------------

# 4. API Routing

Frontend menggunakan endpoint:

POST /api/chat

FastAPI endpoint:

POST /api/chat

Example request:

curl -X POST https://juniawan.web.id/api/chat\
-H "Content-Type: application/json"\
-d '{"message":"halo"}'

Example response:

{ "answer": "Halo! Apa yang bisa saya bantu?", "tokens": 10, "channel":
"web" }

------------------------------------------------------------------------

# 5. Crypto Intelligence API

AlizaAI juga memiliki **Market Intelligence Engine**.

Endpoint:

GET /api/market/btc

Example response:

{ "price": 70203.76, "rsi": 42.73, "fear_greed": 13, "dominance": 56.92,
"trend": "BEARISH", "cycle_phase": "BEAR", "market_score": 65, "signal":
"HOLD", "bottom_probability": 70, "crash_probability": 0,
"altseason_probability": 0, "whale_activity": "ACCUMULATING" }

Crypto dashboard tersedia di:

https://juniawan.web.id/btc

------------------------------------------------------------------------

# 6. Project Structure

aliza-ai

api ├── auth.py └── server.py

core ├── agent.py ├── database.py ├── rag_engine.py ├── skill_loader.py
├── tool_router.py └── tools.py

engine ├── aliza_engine.py ├── document_analyzer.py └──
market_analyzer.py

interfaces └── telegram_bot.py

memory

knowledge ├── documents ├── uploads └── vector_store

web ├── index.html ├── app.js ├── style.css └── btc ├── index.html ├──
btc.js └── btc.css

config └── agent.yaml

data

logs

main.py

------------------------------------------------------------------------

# 7. Current Features

AI Core

• AI chat engine\
• conversation memory\
• skill system\
• tool router

Document AI

• upload document\
• extract document text\
• RAG search

Interfaces

• Web Chat\
• Telegram Bot

Market Intelligence

• BTC market analyzer\
• AI market prediction\
• market cycle detection\
• whale activity detection\
• crash probability detection\
• altseason indicator

System

• PostgreSQL database\
• usage tracking\
• admin API

Deployment

• VPS production server\
• HTTPS domain\
• nginx reverse proxy\
• systemd services

# 7.1 ALIZA MARKET RADAR (NEXT MODULE)

Next major upgrade untuk AlizaAI adalah modul ALIZA MARKET RADAR.

Modul ini akan memperluas Crypto Intelligence Engine menjadi sistem
monitoring market yang lebih advanced.

Fungsi utama:

• BTC bottom detector
• crash alert system
• altseason detector
• whale transaction tracker
• AI trade signal notifier

Tujuan modul ini adalah membuat Aliza mampu memberikan AI-driven
crypto intelligence secara real-time.

ALIZA MARKET RADAR FEATURES

BTC Bottom Detector

AI akan menganalisis kemungkinan market bottom berdasarkan:

• RSI oversold
• extreme fear sentiment
• BTC dominance
• market cycle
• whale accumulation

Output:

bottom_probability

Crash Alert System

Sistem mendeteksi potensi crash berdasarkan:

• overbought RSI
• extreme greed sentiment
• market structure breakdown
• BTC dominance drop

Output:

crash_alert
crash_probability

Altseason Detector

Mendeteksi kemungkinan dimulainya altcoin season menggunakan:

• BTC dominance drop
• market cycle shift
• trend reversal

Output:

altseason_probability

Whale Tracker

Mendeteksi aktivitas whale melalui:

• large BTC transactions
• exchange inflow/outflow

Output:

whale_activity

Telegram Trade Signal

Sistem dapat mengirim alert otomatis ke Telegram jika:

• BTC bottom probability tinggi
• crash probability meningkat
• strong trading setup terdeteksi

Contoh alert:

BTC MARKET RADAR

Bottom probability: 78%
Trend: BEARISH
Whale activity: ACCUMULATING

Possible accumulation zone detected.

------------------------------------------------------------------------

# 8. Database Tables

users

id\
username\
password\
role\
created_at

chats

id\
user_id\
channel\
message\
response\
timestamp

usage

id\
user_id\
tokens\
timestamp

documents

id\
filename\
upload_date

------------------------------------------------------------------------

# 9. Admin API

Admin endpoints:

GET /admin/stats\
GET /admin/users

Example response:

{ "total_users": 5, "total_chats": 230, "total_tokens": 12400,
"documents": 12 }

------------------------------------------------------------------------

# 10. Git Repository

Repository:

https://github.com/jun3iawan-ai/aliza-ai

Git digunakan untuk:

• version control\
• backup project\
• deployment history

------------------------------------------------------------------------

# 11. Deployment Services

Server services:

aliza-api

Menjalankan FastAPI server.

systemctl status aliza-api

aliza-telegram

Menjalankan Telegram bot.

systemctl status aliza-telegram

nginx

Reverse proxy dan HTTPS.

systemctl status nginx

------------------------------------------------------------------------

# 12. Development Stages

Stage 1 (COMPLETED)

• AI engine\
• Telegram bot\
• document analyzer

Stage 2 (COMPLETED)

• Web chat UI\
• FastAPI API\
• VPS deployment\
• HTTPS domain

Stage 3 (COMPLETED)

• Crypto market intelligence engine\
• BTC dashboard\
• AI market analyzer

Stage 4 (CURRENT)

Target:

• user login system\
• admin dashboard UI\
• usage analytics\
• chat history per user

------------------------------------------------------------------------

# 13. Next Development Tasks

Stage 4 tasks:

1.  Web login system\
2.  Admin dashboard UI\
3.  Usage statistics UI\
4.  Chat history per user\
5.  Streaming AI responses

------------------------------------------------------------------------

# 14. Long Term Roadmap

Future features:

• WhatsApp integration\
• Vector database upgrade\
• conversation history UI\
• multi-user AI platform\
• AI agent system\
• SaaS deployment\
• multi-asset crypto intelligence

------------------------------------------------------------------------

# 15. Important Notes

Frontend endpoint:

/api/chat

Backend endpoint:

/api/chat

Frontend uses:

fetch("/api/chat")

Database:

PostgreSQL

Production domain:

https://juniawan.web.id

------------------------------------------------------------------------

# 16. Continue Development

When starting a new ChatGPT conversation, provide this context:

I am developing an AI platform called AlizaAI. Use the context from
ALIZA_PROJECT_GUIDE.md. Continue development from the latest stage.

This ensures the AI understands the project correctly.

# 17. Next Intelligence Upgrades

Setelah sistem Aliza stabil di production server, upgrade berikutnya akan difokuskan pada peningkatan stabilitas dan kecerdasan market engine.

1. Market Engine Error Guard

Market Engine akan ditingkatkan dengan error guard system untuk mencegah crash ketika data API tidak tersedia atau bernilai None.

Tujuan:

• mencegah error runtime
• meningkatkan stabilitas bot
• memastikan API market selalu merespon

Contoh kasus yang diperbaiki:

'>' not supported between instances of 'NoneType' and 'int'

Dengan sistem ini, market engine akan menggunakan:

fallback data

safe comparison

exception guard

2. Bot Lock System

Bot Lock System akan ditambahkan untuk memastikan hanya satu instance Telegram bot yang dapat berjalan.

Tujuan:

• mencegah multiple polling instance
• mencegah error Telegram 409 Conflict
• menjaga stabilitas sistem bot

Sistem ini akan menggunakan:

lock file

process verification

startup guard

3. Market Cache Engine

Market engine akan menggunakan cache system untuk mengurangi beban CPU server.

Manfaat:

• mengurangi request API berulang
• menurunkan penggunaan CPU dari ±25% menjadi ±3%
• meningkatkan respons API market

Cache akan diterapkan pada:

BTC price data

dominance data

fear & greed index

market radar

4. Global Market Brain

Upgrade terbesar berikutnya adalah membangun ALIZA GLOBAL MARKET BRAIN.

Sistem ini akan membuat Aliza mampu membaca kondisi makro global yang mempengaruhi crypto market.

Data yang akan dianalisis:

• DXY (US Dollar Index)
• S&P500
• NASDAQ
• Interest Rate
• Global Liquidity
• Crypto Market Cap

Dengan sistem ini, Aliza akan berkembang menjadi:

AI Macro + Crypto Intelligence System

yang setara dengan tools yang digunakan oleh hedge fund.
