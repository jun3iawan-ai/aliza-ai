from engine.aliza_engine import ask_aliza
from core.rag_engine import load_file
from memory.active_document import get_active_document

import pandas as pd
import os


def analyze_document():

    path = get_active_document()

    if not path:
        return "Tidak ada dokumen yang aktif."

    if not os.path.exists(path):
        return "File dokumen tidak ditemukan."

    text = ""

    # =========================
    # HANDLE EXCEL FILE
    # =========================

    if path.lower().endswith(".xlsx") or path.lower().endswith(".xls"):

        try:
            df = pd.read_excel(path)
            text = df.to_string()

        except Exception as e:
            return f"Gagal membaca file Excel: {str(e)}"

    # =========================
    # HANDLE FILE LAIN (PDF, DOCX, TXT)
    # =========================

    else:

        documents = load_file(path)

        if not documents:
            return "Dokumen tidak dapat dibaca."

        for doc in documents:
            text += doc.page_content + "\n"

    if not text.strip():
        return "Isi dokumen kosong atau tidak dapat dibaca."

    # =========================
    # PROMPT KE ALIZA
    # =========================

    prompt = f"""
Berikut isi dokumen berikut:

{text[:5000]}

Tolong buat ringkasan dokumen tersebut dalam bahasa Indonesia yang jelas.
"""

    result = ask_aliza(prompt)

    return result