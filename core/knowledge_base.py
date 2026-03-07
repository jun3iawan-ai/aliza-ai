import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

documents = []
embeddings = []

index = None


def load_documents():

    folder = "knowledge/documents"

    if not os.path.exists(folder):
        return

    for file in os.listdir(folder):

        if file.endswith(".pdf"):

            reader = PdfReader(os.path.join(folder, file))

            text = ""

            for page in reader.pages:
                text += page.extract_text() or ""

            documents.append(text)


def build_index():

    global index

    if not documents:
        return

    for doc in documents:

        emb = model.encode(doc)

        embeddings.append(emb)

    dimension = len(embeddings[0])

    index = faiss.IndexFlatL2(dimension)

    index.add(np.array(embeddings))


def search_knowledge(query):

    if index is None:
        return "Knowledge base belum dimuat."

    q_emb = model.encode(query)

    D, I = index.search(np.array([q_emb]), k=1)

    return documents[I[0][0]]