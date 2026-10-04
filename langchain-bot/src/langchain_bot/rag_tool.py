from pathlib import Path

from langchain_core.tools import tool
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()


_vector_store = None

def load_policy_documents():
    root = Path(__file__).resolve().parent.parent.parent
    policies_dir = root / "policies"

    documents = []

    for file_path in policies_dir.glob("*.txt"):
        docs = TextLoader(
            str(file_path),
            encoding="utf-8"
        ).load()

        for doc in docs:
            doc.metadata["source"] = file_path.name

        documents.extend(docs)

    return documents

def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150
    )

    return splitter.split_documents(documents)

def get_vector_store():
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    root = Path(__file__).resolve().parent.parent.parent
    persist_dir = root / "chroma_db"

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small"
    )

    if persist_dir.exists() and any(persist_dir.iterdir()):
        print("Loading existing ChromaDB...")
        _vector_store = Chroma(
            persist_directory=str(persist_dir),
            embedding_function=embeddings
        )
        print("Loaded existing ChromaDB.")
    else:
        print("Loading policy documents...")
        documents = load_policy_documents()

        print("Splitting policy documents...")
        chunks = split_documents(documents)

        print("Creating ChromaDB...")
        _vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=str(persist_dir)
        )

        print("ChromaDB created and loaded.")

    return _vector_store

@tool
def search_policies(query: str) -> str:
    """Search policies and FAQs only. Do not use this tool for user orders."""
    vector_store = get_vector_store()

    docs = vector_store.similarity_search(query, k=4)

    results = []

    for doc in docs:
        source = doc.metadata.get("source", "Unknown")
        results.append(
            f"Source: {source}\n{doc.page_content}"
        )

    return "\n\n---\n\n".join(results)

def initialize_vector_store():
    get_vector_store()


__all__ = [
    "search_policies",
    "initialize_vector_store",
]