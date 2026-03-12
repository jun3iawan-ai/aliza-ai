from engine.brain.aliza_engine import ask_aliza
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

    try:

        # =========================
        # HANDLE EXCEL FILE
        # =========================

        if path.lower().endswith((".xlsx", ".xls")):

            df = pd.read_excel(path)

            # batasi agar tidak terlalu panjang
            text = df.head(100).to_string()

        # =========================
        # HANDLE FILE LAIN (PDF, DOCX, TXT)
        # =========================

        else:

            documents = load_file(path)

            if not documents:
                return "Dokumen tidak dapat dibaca."

            contents = []

            for doc in documents:
                contents.append(doc.page_content)

            text = "\n".join(contents)

    except Exception as e:

        return f"Gagal membaca dokumen: {str(e)}"

    # =========================
    # VALIDASI ISI
    # =========================

    if not text.strip():
        return "Isi dokumen kosong atau tidak dapat dibaca."

    # =========================
    # BATASI TEXT AGAR AI TIDAK KELEBIHAN TOKEN
    # =========================

    MAX_LENGTH = 5000
    text = text[:MAX_LENGTH]

    # =========================
    # PROMPT KE ALIZA
    # =========================

    prompt = f"""
Berikut isi dokumen:

{text}

Tolong buat ringkasan dokumen tersebut dalam bahasa Indonesia yang jelas dan terstruktur.
"""

    result = ask_aliza(prompt)

    return result