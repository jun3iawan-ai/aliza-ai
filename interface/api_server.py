from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import shutil
import os

from engine.aliza_engine import ask_aliza
from core.rag_engine import add_document_to_vector_store
from engine.document_analyzer import analyze_document

app = FastAPI(title="AlizaAI API")

app.mount("/web", StaticFiles(directory="web"), name="web")


class ChatRequest(BaseModel):
    message: str
    user_id: str | None = None


UPLOAD_FOLDER = "knowledge/uploads/original_files"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.get("/")
def root():
    return {"status": "AlizaAI API running"}


@app.get("/dashboard")
def dashboard():
    return FileResponse("web/index.html")


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

        save_path = os.path.join(UPLOAD_FOLDER, file.filename)

        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        add_document_to_vector_store(save_path)

        summary = analyze_document()

        return {
            "status": "success",
            "summary": summary
        }

    except Exception as e:

        return {"error": str(e)}