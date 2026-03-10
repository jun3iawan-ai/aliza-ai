from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from engine.aliza_engine import ask_aliza
from engine.market_analyzer import btc_signal

from core.database import conn, cursor
from api.auth import router as auth_router

from fastapi import APIRouter


# =========================
# INIT FASTAPI
# =========================

app = FastAPI(
    title="AlizaAI API",
    version="1.0"
)


# =========================
# REGISTER AUTH ROUTER
# =========================

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


# =========================
# MARKET ROUTER
# =========================

market_router = APIRouter()


@market_router.get("/btc")
def btc_market():
    return btc_signal()


app.include_router(market_router, prefix="/api/market", tags=["market"])


# =========================
# REQUEST MODEL
# =========================

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[int] = None
    channel: str = "web"


# =========================
# HOME
# =========================

@app.get("/")
def home():
    return {"message": "AlizaAI API running"}


# =========================
# CHAT ENDPOINT
# =========================

@app.post("/api/chat")
def chat(req: ChatRequest):

    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message kosong")

    user_id = req.user_id or 1
    channel = req.channel

    try:
        answer = ask_aliza(message)
    except Exception as e:
        answer = f"AI error: {str(e)}"

    cursor.execute(
        """
        INSERT INTO chats (user_id, message, response)
        VALUES (%s, %s, %s)
        """,
        (user_id, message, answer)
    )

    tokens = len(message.split()) + len(answer.split())

    cursor.execute(
        """
        INSERT INTO usage (user_id, tokens)
        VALUES (%s, %s)
        """,
        (user_id, tokens)
    )

    conn.commit()

    return {
        "answer": answer,
        "tokens": tokens,
        "channel": channel
    }


# =========================
# ADMIN STATS
# =========================

@app.get("/admin/stats")
def admin_stats():

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM chats")
    chats = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(tokens),0) FROM usage")
    tokens = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM documents")
    documents = cursor.fetchone()[0]

    return {
        "total_users": users,
        "total_chats": chats,
        "total_tokens": tokens,
        "documents": documents
    }


# =========================
# ADMIN USERS
# =========================

@app.get("/admin/users")
def admin_users():

    cursor.execute("SELECT id, username, role FROM users")

    rows = cursor.fetchall()

    users = [
        {
            "id": r["id"],
            "username": r["username"],
            "role": r["role"]
        }
        for r in rows
    ]

    return users