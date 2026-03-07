import os

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredExcelLoader,
    UnstructuredWordDocumentLoader
)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever

from sentence_transformers import SentenceTransformer
from langchain.embeddings.base import Embeddings


# =========================
# EMBEDDING MODEL
# =========================

class SentenceTransformerEmbeddings(Embeddings):

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed_documents(self, texts):
        return self.model.encode(texts).tolist()

    def embed_query(self, text):
        return self.model.encode([text])[0].tolist()


embedding = SentenceTransformerEmbeddings()


# =========================
# DOCUMENT LOADER
# =========================

def load_file(file_path):

    ext = os.path.splitext(file_path)[1].lower()

    try:

        if ext == ".pdf":
            loader = PyPDFLoader(file_path)

        elif ext == ".txt":
            loader = TextLoader(file_path, encoding="utf-8")

        elif ext == ".xlsx":
            loader = UnstructuredExcelLoader(file_path)

        elif ext == ".docx":
            loader = UnstructuredWordDocumentLoader(file_path)

        else:
            return []

        return loader.load()

    except Exception as e:

        print(f"Gagal memuat dokumen {file_path}: {e}")
        return []


# =========================
# LOAD DOCUMENTS
# =========================

def load_documents():

    documents = []

    folder = "knowledge/documents"

    if not os.path.exists(folder):
        return documents

    for file in os.listdir(folder):

        path = os.path.join(folder, file)

        documents.extend(load_file(path))

    return documents


# =========================
# BUILD VECTOR STORE
# =========================

def build_vector_store():

    docs = load_documents()

    if not docs:
        print("Tidak ada dokumen untuk diproses.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    chunks = splitter.split_documents(docs)

    vector_store = FAISS.from_documents(chunks, embedding)

    os.makedirs("knowledge/vector_store", exist_ok=True)

    vector_store.save_local("knowledge/vector_store")

    print("Vector store berhasil dibuat.")


# =========================
# LOAD VECTOR STORE
# =========================

def load_vector_store():

    path = "knowledge/vector_store"

    if not os.path.exists(os.path.join(path, "index.faiss")):
        build_vector_store()

    return FAISS.load_local(
        path,
        embedding,
        allow_dangerous_deserialization=True
    )


# =========================
# VECTOR SEARCH
# =========================

def vector_search(query):

    vector_store = load_vector_store()

    results = vector_store.similarity_search(query, k=3)

    context = ""

    for r in results:

        source = r.metadata.get("source", "dokumen")

        context += f"[Sumber: {os.path.basename(source)}]\n"
        context += r.page_content + "\n\n"

    return context


# =========================
# KEYWORD SEARCH
# =========================

def keyword_search(query):

    docs = load_documents()

    if not docs:
        return ""

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    chunks = splitter.split_documents(docs)

    retriever = BM25Retriever.from_documents(chunks)
    retriever.k = 3

    results = retriever.get_relevant_documents(query)

    context = ""

    for r in results:

        source = r.metadata.get("source", "dokumen")

        context += f"[Sumber: {os.path.basename(source)}]\n"
        context += r.page_content + "\n\n"

    return context


# =========================
# HYBRID SEARCH
# =========================

def search_knowledge(query):

    vector_results = vector_search(query)
    keyword_results = keyword_search(query)

    context = ""

    context += "=== Vector Search Result ===\n"
    context += vector_results

    context += "\n=== Keyword Search Result ===\n"
    context += keyword_results

    return context


# =========================
# ADD DOCUMENT TO VECTOR STORE
# =========================

def add_document_to_vector_store(file_path):

    documents = load_file(file_path)

    if not documents:
        print("Dokumen kosong atau tidak dapat dibaca.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    chunks = splitter.split_documents(documents)

    vector_store_path = "knowledge/vector_store"

    os.makedirs(vector_store_path, exist_ok=True)

    index_path = os.path.join(vector_store_path, "index.faiss")

    if os.path.exists(index_path):

        vector_store = FAISS.load_local(
            vector_store_path,
            embedding,
            allow_dangerous_deserialization=True
        )

        vector_store.add_documents(chunks)

    else:

        vector_store = FAISS.from_documents(chunks, embedding)

    vector_store.save_local(vector_store_path)

    print("Dokumen berhasil ditambahkan ke vector database.")