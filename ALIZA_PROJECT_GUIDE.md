# ALIZA AI — PROJECT GUIDE

# 1. Project Overview

AlizaAI adalah platform AI assistant yang berjalan di berbagai channel:

• Web Chat
• Telegram Bot
• WhatsApp (planned)

Tujuan project adalah membuat **AI platform mandiri seperti mini ChatGPT** yang dapat:

• menjawab pertanyaan
• membaca dokumen
• menyimpan chat history
• melacak penggunaan AI
• memiliki memory pengguna

---

# 2. Infrastructure

Server Environment

• VPS Ubuntu
• Nginx Reverse Proxy
• HTTPS (Let's Encrypt)
• Domain publik

Production URL:

https://juniawan.web.id

API internal berjalan di:

http://127.0.0.1:8000

---

# 3. Backend Stack

Backend menggunakan:

• Python
• FastAPI
• PostgreSQL Database
• Custom AI Engine
• RAG Document System

Server berjalan menggunakan:

Uvicorn + Systemd service

Service aktif:

aliza-api
aliza-telegram
nginx

---

# 4. API Routing

Frontend menggunakan endpoint:

POST /api/chat

FastAPI endpoint:

POST /api/chat

Example request:

curl -X POST https://juniawan.web.id/api/chat 
-H "Content-Type: application/json" 
-d '{"message":"halo"}'

Example response:

{
"answer": "Halo! Apa yang bisa saya bantu?",
"tokens": 10,
"channel": "web"
}

---

# 5. Project Structure

aliza-ai

api
├── auth.py
└── server.py

core
├── agent.py
├── database.py
├── rag_engine.py
├── skill_loader.py
├── tool_router.py
└── tools.py

engine
├── aliza_engine.py
└── document_analyzer.py

interfaces
└── telegram_bot.py

memory

knowledge
├── documents
├── uploads
└── vector_store

web
├── index.html
├── app.js
└── style.css

config
└── agent.yaml

data

logs

main.py

---

# 6. Current Features

AI Core

• AI chat engine
• conversation memory
• skill system
• tool router

Document AI

• upload document
• extract document text
• RAG search

Interfaces

• Web Chat
• Telegram Bot

System

• PostgreSQL database
• usage tracking
• admin API

Deployment

• VPS production server
• HTTPS domain
• nginx reverse proxy
• systemd services

---

# 7. Database Tables

users

id
username
password
role
created_at

chats

id
user_id
channel
message
response
timestamp

usage

id
user_id
tokens
timestamp

documents

id
filename
upload_date

---

# 8. Admin API

Admin endpoints:

GET /admin/stats
GET /admin/users

Example response:

{
"total_users": 5,
"total_chats": 230,
"total_tokens": 12400,
"documents": 12
}

---

# 9. Git Repository

Repository:

https://github.com/jun3iawan-ai/aliza-ai

Git digunakan untuk:

• version control
• backup project
• deployment history

---

# 10. Deployment Services

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

---

# 11. Development Stages

Stage 1 (COMPLETED)

• AI engine
• Telegram bot
• document analyzer

Stage 2 (COMPLETED)

• Web chat UI
• FastAPI API
• VPS deployment
• HTTPS domain

Stage 3 (CURRENT)

Target:

• user login system
• admin dashboard UI
• usage analytics
• chat history per user

---

# 12. Next Development Tasks

Stage 3 tasks:

1. Web login system
2. Admin dashboard UI
3. Usage statistics UI
4. Chat history per user
5. Streaming AI responses

---

# 13. Long Term Roadmap

Future features:

• WhatsApp integration
• Vector database
• conversation history UI
• multi-user AI platform
• AI agent system
• SaaS deployment

---

# 14. Important Notes

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

---

# 15. Continue Development

When starting a new ChatGPT conversation, provide this context:

I am developing an AI platform called AlizaAI.
Use the context from ALIZA_PROJECT_GUIDE.md.
Continue development from Stage 3.

This ensures the AI understands the project correctly.
