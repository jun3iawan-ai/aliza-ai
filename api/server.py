from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

from engine.aliza_engine import ask_aliza
from core.database import conn, cursor

from api.auth import router as auth_router


app = FastAPI(
    title="AlizaAI API",
    version="1.0"
)

# =========================
# REGISTER AUTH ROUTER
# =========================

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


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

    # =========================
    # AI RESPONSE
    # =========================

    answer = ask_aliza(message)

    # =========================
    # SAVE CHAT HISTORY
    # =========================

    cursor.execute(
        """
        INSERT INTO chats (user_id, message, response)
        VALUES (?, ?, ?)
        """,
        (user_id, message, answer)
    )

    # =========================
    # USAGE TRACKING
    # =========================

    tokens = len(message.split()) + len(answer.split())

    cursor.execute(
        """
        INSERT INTO usage (user_id, tokens)
        VALUES (?, ?)
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

    users = cursor.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    chats = cursor.execute(
        "SELECT COUNT(*) FROM chats"
    ).fetchone()[0]

    tokens = cursor.execute(
        "SELECT COALESCE(SUM(tokens),0) FROM usage"
    ).fetchone()[0]

    documents = cursor.execute(
        "SELECT COUNT(*) FROM documents"
    ).fetchone()[0]

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

    rows = cursor.execute(
        "SELECT id, username, role FROM users"
    ).fetchall()

    users = [
        {
            "id": r[0],
            "username": r[1],
            "role": r[2]
        }
        for r in rows
    ]

    return users