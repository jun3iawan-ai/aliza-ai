from engine.aliza_engine import ask_aliza
from core.rag_engine import load_file
from memory.active_document import get_active_document


def analyze_document():

    path = get_active_document()

    if not path:
        return "Tidak ada dokumen yang aktif."

    documents = load_file(path)

    if not documents:
        return "Dokumen tidak dapat dibaca."

    text = ""

    for doc in documents:
        text += doc.page_content + "\n"

    prompt = f"""
Berikut isi dokumen berikut:

{text[:5000]}

Tolong buat ringkasan dokumen tersebut dalam bahasa Indonesia yang jelas.
"""

    result = ask_aliza(prompt)

    return result