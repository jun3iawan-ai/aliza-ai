# ALIZA AI — PROJECT GUIDE

## 1. Project Overview

AlizaAI adalah platform AI assistant yang dapat berjalan di berbagai channel:

* Web Chat
* Telegram Bot
* WhatsApp (planned)

Tujuan project adalah membuat **AI platform mandiri** seperti mini ChatGPT yang dapat:

* menjawab pertanyaan
* membaca dokumen
* menyimpan chat history
* melacak penggunaan AI

---

# 2. Infrastructure

Server Environment

* VPS Ubuntu
* Nginx Reverse Proxy
* HTTPS (Let's Encrypt)
* Domain

Production URL:

https://juniawan.web.id

---

# 3. Backend Stack

Backend menggunakan:

* Python
* FastAPI
* SQLite Database
* Custom AI Engine

API Server berjalan di:

```
http://127.0.0.1:8000
```

Nginx melakukan reverse proxy untuk domain.

---

# 4. API Routing

Frontend menggunakan endpoint:

```
POST /api/chat
```

Nginx menerjemahkan ke:

```
POST /chat
```

FastAPI Endpoint:

```
@app.post("/chat")
```

Example request:

```
curl -X POST https://juniawan.web.id/api/chat \
-H "Content-Type: application/json" \
-d '{"message":"halo"}'
```

Example response:

```
{
 "answer": "Halo! Bagaimana kabarmu?"
}
```

---

# 5. Project Structure

```
aliza-ai
│
├── api
│   ├── auth.py
│   └── server.py
│
├── core
│   ├── agent.py
│   ├── database.py
│   ├── rag_engine.py
│   ├── tools.py
│   └── skill_loader.py
│
├── engine
│   ├── aliza_engine.py
│   └── document_analyzer.py
│
├── interfaces
│   └── telegram_bot.py
│
├── memory
│
├── knowledge
│
├── web
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── config
│   └── agent.yaml
│
├── data
│   └── aliza.db
│
└── main.py
```

---

# 6. Current Features

AI Core

* AI chat engine
* conversation memory
* skill system
* tool router

Document AI

* upload PDF
* extract text
* RAG search

Interfaces

* Web Chat
* Telegram Bot

System

* database
* usage tracking
* admin API

Deployment

* VPS server
* domain
* HTTPS
* nginx reverse proxy

---

# 7. Database Tables

users

```
id
username
password
role
```

chats

```
id
user_id
message
response
timestamp
```

usage

```
id
user_id
tokens
timestamp
```

documents

```
id
filename
upload_date
```

---

# 8. Admin API

Admin endpoints:

```
GET /admin/stats
GET /admin/users
```

Stats response example:

```
{
 "total_users": 5,
 "total_chats": 230,
 "total_tokens": 12400,
 "documents": 12
}
```

---

# 9. Git Repository

Repository:

https://github.com/jun3iawan-ai/aliza-ai

Git digunakan untuk:

* version control
* deployment history
* backup project

---

# 10. Development Stages

## Stage 1 (COMPLETED)

* AI engine
* Telegram bot
* document analyzer

## Stage 2 (COMPLETED)

* Web chat UI
* FastAPI API
* VPS deployment
* HTTPS domain

## Stage 3 (CURRENT)

Target features:

* user login system
* admin dashboard UI
* usage analytics

---

# 11. Next Development Tasks

Stage 3 development plan:

1. Web Login system
2. Admin dashboard
3. Usage statistics UI
4. Chat history per user
5. Streaming AI responses

---

# 12. Long Term Roadmap

Future features:

* WhatsApp integration
* vector database
* conversation history UI
* multi-user AI platform
* AI agent system
* SaaS deployment

---

# 13. Important Notes

* API endpoint FastAPI: `/chat`
* Nginx endpoint public: `/api/chat`
* Frontend uses `fetch("/api/chat")`
* Database: SQLite

---

# 14. How to Continue Development

When starting a new ChatGPT conversation, provide this context:

```
I am developing an AI platform called AlizaAI.
Use the context from ALIZA_PROJECT_GUIDE.md
Continue development from Stage 3.
```

This ensures the AI understands the project structure correctly.
