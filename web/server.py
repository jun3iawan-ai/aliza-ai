from fastapi import FastAPI
from pydantic import BaseModel

from engine.aliza_engine import ask_aliza
from core.database import conn, cursor

app = FastAPI()


# =========================
# REQUEST MODEL
# =========================

class ChatRequest(BaseModel):
    message: str
    user_id: int = 1
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

@app.post("/chat")
def chat(req: ChatRequest):

    # AI response
    answer = ask_aliza(req.message)

    # =========================
    # SAVE CHAT HISTORY
    # =========================

    cursor.execute(
        """
        INSERT INTO chats (user_id, channel, message, response)
        VALUES (?, ?, ?, ?)
        """,
        (req.user_id, req.channel, req.message, answer)
    )

    # =========================
    # USAGE TRACKING
    # =========================

    tokens = len(req.message.split()) + len(answer.split())

    cursor.execute(
        """
        INSERT INTO usage (user_id, tokens, endpoint)
        VALUES (?, ?, ?)
        """,
        (req.user_id, tokens, "chat")
    )

    conn.commit()

    return {"answer": answer}


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
        "SELECT SUM(tokens) FROM usage"
    ).fetchone()[0] or 0

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
# USER LIST (ADMIN)
# =========================

@app.get("/admin/users")
def admin_users():

    rows = cursor.execute(
        "SELECT id, username, role, created_at FROM users"
    ).fetchall()

    users = []

    for r in rows:
        users.append(dict(r))

    return users