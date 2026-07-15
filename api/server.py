import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

from core.database import conn, cursor
from api.auth import router as auth_router
from api.dashboard_api import router as dashboard_router
from api.security import validate_jwt_configuration

from fastapi import APIRouter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_jwt_configuration()
    yield

# =========================
# INIT FASTAPI
# =========================

app = FastAPI(
    title="Aliza Dashboard API",
    version="1.0",
    lifespan=lifespan,
)


# =========================
# REGISTER AUTH ROUTER
# =========================

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard_router)


# =========================
# MARKET ROUTER
# =========================

market_router = APIRouter()


@market_router.get("/btc")
def btc_market():
    from engine.market.market_analyzer import btc_signal

    return btc_signal()


app.include_router(market_router, prefix="/api/market", tags=["market"])


# =========================
# REQUEST MODEL
# =========================

class ChatRequest(BaseModel):
    """Fleksibel: isi salah satu dari message atau prompt."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    message: Optional[str] = Field(default=None, description="Pesan pengguna")
    prompt: Optional[str] = Field(default=None, description="Alias untuk message")
    user_id: Optional[int] = None
    channel: str = "web"


# =========================
# DASHBOARD (ALIZA TRADING DASHBOARD)
# =========================

_DASHBOARD_HTML = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"

@app.get("/")
def dashboard():
    """Serve Trading Dashboard. Port dikonfigurasi via ALIZA_DASHBOARD_PORT (default 8001)."""
    if _DASHBOARD_HTML.exists():
        return FileResponse(_DASHBOARD_HTML)
    return {"message": "AlizaAI API running", "dashboard": "dashboard/index.html not found"}


# =========================
# HEALTH CHECK
# =========================

@app.get("/health")
def health():
    """Health check untuk monitoring dan load balancer."""
    return {
        "status": "ok",
        "service": "AlizaAI Dashboard",
        "engine": "running"
    }


# =========================
# MARKET TEST ROUTE
# =========================

@app.get("/market")
def market():
    """Data market BTC (test/simple endpoint)."""
    from engine.utils.market_cache import get_market_data

    return get_market_data("BTC") or {}


# =========================
# CHAT ENDPOINT
# =========================

def _chat_text(req: ChatRequest) -> str:
    parts = []
    if req.message is not None and str(req.message).strip():
        parts.append(str(req.message).strip())
    if req.prompt is not None and str(req.prompt).strip():
        parts.append(str(req.prompt).strip())
    return parts[0] if parts else ""


_FALLBACK_REPLY = (
    "Maaf, Aliza tidak dapat memproses permintaan saat ini. Silakan coba lagi dalam beberapa saat."
)


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    Chat dengan Aliza. Tidak mengembalikan 500: error AI/DB ditangani dan di-log.
    """
    try:
        from engine.brain.aliza_engine import ask_aliza

        channel = (req.channel or "web").strip() or "web"
        message = _chat_text(req)

        if not message:
            raise HTTPException(
                status_code=400,
                detail="message atau prompt tidak boleh kosong",
            )

        user_id = req.user_id

        try:
            answer = ask_aliza(message)
            if not answer or not str(answer).strip():
                answer = _FALLBACK_REPLY
            else:
                answer = str(answer).strip()
        except Exception as e:
            logger.exception("ask_aliza failed: %s", e)
            answer = _FALLBACK_REPLY

        tokens = len(message.split()) + len(str(answer).split())

        try:
            cursor.execute(
                """
                INSERT INTO chats (user_id, channel, message, response)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, channel, message, answer),
            )
            cursor.execute(
                """
                INSERT INTO usage (user_id, tokens)
                VALUES (%s, %s)
                """,
                (user_id, tokens),
            )
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning("chat persist skipped (db): %s", e)

        return {
            "reply": answer,
            "answer": answer,
            "tokens": tokens,
            "channel": channel,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("chat endpoint error: %s", e)
        return {
            "reply": _FALLBACK_REPLY,
            "answer": _FALLBACK_REPLY,
            "tokens": 0,
            "channel": getattr(req, "channel", None) or "web",
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
