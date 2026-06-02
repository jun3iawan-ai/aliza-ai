"""
API ringan untuk integrasi eksternal (mis. backend Node.js) pada endpoint /v1/generate-response.

Dashboard utama dan /api/chat ada di api/server.py (proses/port terpisah).

**DEPRECATED (2026-04-16):** Endpoint ``/v1/generate-response`` tetap didukung untuk klien lama,
namun **client baru** harus memakai ``POST /api/chat`` di ``api/server.py`` (migration: lihat
``docs/instructions/intent-routing.md`` §6.3). Timeline: monitoring 30 hari → remove jika tidak ada traffic.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from engine.brain.aliza_engine import ask_aliza

logger = logging.getLogger(__name__)

app = FastAPI()

_DEPRECATED_HEADERS = {
    "X-Deprecated": "true",
    "X-Deprecated-Endpoint": "/v1/generate-response",
    "X-Migration-Hint": "Use POST /api/chat on api/server.py",
}

# Selaras dengan fallback di api/server.py (/api/chat) bila output LLM kosong
_FALLBACK_REPLY = (
    "Maaf, Aliza tidak dapat memproses permintaan saat ini. Silakan coba lagi dalam beberapa saat."
)
_ERROR_GENERIC = "Maaf, terjadi kesalahan saat memproses permintaan. Silakan coba lagi nanti."


class Request(BaseModel):
    user_message: str


@app.post("/v1/generate-response")
async def generate_response(req: Request):
    """
    Generate respons Aliza via ask_aliza (satu sumber kebenaran untuk routing intent).

    **Deprecated:** gunakan ``POST /api/chat`` di ``api/server.py`` untuk integrasi baru.

    Perilaku search / math / chat selaras dengan POST /api/chat di api/server.py.

    Perbedaan dengan /api/chat (disengaja):
    - Tanpa persist PostgreSQL (chats, usage, tokens) — cocok untuk integrasi stateless.
    - Schema respons: hanya ``answer`` sukses, atau ``answer`` + ``error`` saat gagal validasi/eksekusi.
    - Aplikasi FastAPI terpisah; biasanya dijalankan pada host/port berbeda dari dashboard API.

    Rekomendasi ke depan: pertimbangkan satu gateway FastAPI dengan route namespaced jika
    duplikasi app tidak lagi dibutuhkan; jangan hapus endpoint ini tanpa jadwal deprecation ke klien.
    """
    logger.warning(
        "DEPRECATED: /v1/generate-response called — migrate to POST /api/chat (api/server.py)"
    )
    try:
        user = (req.user_message or "").strip()
        if not user:
            return JSONResponse(
                content={"answer": None, "error": "Pesan tidak boleh kosong"},
                headers=_DEPRECATED_HEADERS,
            )

        result = await asyncio.to_thread(ask_aliza, user)
        answer = str(result).strip() if result is not None else ""
        if not answer:
            answer = _FALLBACK_REPLY

        return JSONResponse(content={"answer": answer}, headers=_DEPRECATED_HEADERS)
    except Exception:
        logger.exception("/v1/generate-response failed")
        return JSONResponse(
            content={"answer": None, "error": _ERROR_GENERIC},
            headers=_DEPRECATED_HEADERS,
        )
