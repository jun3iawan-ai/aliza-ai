from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import shutil
import os

from engine.aliza_engine import ask_aliza
from core.rag_engine import add_document_to_vector_store
from engine.document_analyzer import analyze_document

# =========================
# FASTAPI INIT
# =========================

app = FastAPI(title="AlizaAI API")

# folder web dashboard
app.mount("/web", StaticFiles(directory="web"), name="web")

# =========================
# REQUEST MODEL
# =========================

class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None


# =========================
# FOLDER CONFIG
# =========================

UPLOAD_FOLDER = "knowledge/uploads/original_files"
ACTIVE_FOLDER = "active_document"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ACTIVE_FOLDER, exist_ok=True)


# =========================
# ROOT
# =========================

@app.get("/")
def root():
    return {"status": "AlizaAI API running"}


# =========================
# DASHBOARD PAGE
# =========================

@app.get("/dashboard")
def dashboard():
    return FileResponse("web/index.html")


# =========================
# CHAT ENDPOINT
# =========================

@app.post("/chat")
def chat(req: ChatRequest):

    try:

        response = ask_aliza(req.message)

        return {"response": response}

    except Exception as e:

        return {"error": str(e)}


# =========================
# UPLOAD DOCUMENT
# =========================

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):

    try:

        # simpan file ke folder upload
        save_path = os.path.join(UPLOAD_FOLDER, file.filename)

        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print("File diterima:", file.filename)
        print("Disimpan ke:", save_path)

        # =========================
        # SET ACTIVE DOCUMENT
        # =========================

        # hapus active document lama
        for f in os.listdir(ACTIVE_FOLDER):
            os.remove(os.path.join(ACTIVE_FOLDER, f))

        # copy file baru ke active_document
        active_path = os.path.join(ACTIVE_FOLDER, file.filename)
        shutil.copy(save_path, active_path)

        print("Active document:", active_path)

        # =========================
        # MASUKKAN KE VECTOR STORE
        # =========================

        add_document_to_vector_store(save_path)

        # =========================
        # ANALISIS DOKUMEN
        # =========================

        summary = analyze_document()

        return {
            "status": "success",
            "summary": summary
        }

    except Exception as e:

        print("ERROR:", e)

        return {"error": str(e)}