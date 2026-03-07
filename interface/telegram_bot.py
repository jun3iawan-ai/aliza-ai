from engine.aliza_engine import ask_aliza
from memory.active_document import get_active_document
from core.rag_engine import load_file


def analyze_document():

    path = get_active_document()

    if not path:
        return "Tidak ada dokumen aktif."

    docs = load_file(path)

    if not docs:
        return "Dokumen tidak dapat dibaca."

    context = ""

    for d in docs[:5]:
        context += d.page_content + "\n\n"

    prompt = f"""
Berikut isi dokumen berikut:

{context}

Tolong buat ringkasan dokumen tersebut dalam bahasa Indonesia yang jelas.
"""

    return ask_aliza(prompt)