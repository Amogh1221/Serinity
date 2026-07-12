"""
rag_engine.py — Serinity local RAG engine.

Changes from cloud version:
  - Pinecone + HuggingFaceEndpointEmbeddings → ChromaDB + OllamaEmbeddings
  - retrieve() signature kept identical so main.py requires no changes
  - MMR search preserved; fallback to plain similarity if MMR unavailable
  - Embedding model: nomic-embed-text via Ollama (generate once, persist)

NOTE: Run built_vectorDB.py once before starting the app to populate
      the local ChromaDB. The engine will fail gracefully if the DB is
      empty and log a clear message.
"""

import os
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

load_dotenv()

OLLAMA_HOST          = os.getenv("OLLAMA_HOST",           "http://localhost:11434")
EMBEDDING_MODEL      = os.getenv("EMBEDDING_MODEL",       "nomic-embed-text")
CHROMA_PERSIST_DIR   = os.getenv("CHROMA_PERSIST_DIR",    "./chroma_db")
CHROMA_COLLECTION    = os.getenv("CHROMA_COLLECTION_NAME","mhcva-knowledge")


class RAGEngine:
    def __init__(self):
        self.embeddings = OllamaEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=OLLAMA_HOST,
        )

        # Load the persisted ChromaDB collection.
        # If built_vectorDB.py hasn't been run yet the collection will be empty;
        # retrieve() will return an empty string in that case.
        self.vectorstore = Chroma(
            collection_name=CHROMA_COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )
        count = self.vectorstore._collection.count()
        if count == 0:
            print(
                "[RAG WARNING] ChromaDB collection is empty. "
                "Run `python built_vectorDB.py` to populate it before starting a session."
            )
        else:
            print(f"[RAG] Loaded {count:,} documents from ChromaDB ({CHROMA_COLLECTION}).")

    def retrieve(self, query: str, k: int = 8, fetch_k: int = 30, lambda_mult: float = 0.7) -> str:
        """
        Retrieve diverse clinical context using Maximal Marginal Relevance (MMR).
        Signature is identical to the old Pinecone version — main.py doesn't
        need to change how it calls this method.

        Args:
            query:       The retrieval query (clinical_summary when available,
                         or concatenated recent user messages as fallback).
            k:           Number of documents to return.
            fetch_k:     Candidate pool size before MMR diversity re-ranking.
            lambda_mult: MMR diversity trade-off (0=max diversity, 1=max relevance).

        Returns:
            Joined page_content strings, separated by double newlines.
        """
        if not query or not query.strip():
            return ""

        try:
            # Check if there are enough docs for the requested fetch_k
            count = self.vectorstore._collection.count()
            if count == 0:
                return ""

            actual_fetch_k = min(fetch_k, count)
            actual_k = min(k, actual_fetch_k)

            results = self.vectorstore.max_marginal_relevance_search(
                query,
                k=actual_k,
                fetch_k=actual_fetch_k,
                lambda_mult=lambda_mult,
            )
            return "\n\n".join([doc.page_content for doc in results])

        except Exception as e:
            print(f"[RAG ERROR] MMR search failed: {e}. Attempting similarity fallback.")
            try:
                results = self.vectorstore.similarity_search(query, k=k)
                return "\n\n".join([doc.page_content for doc in results])
            except Exception as e2:
                print(f"[RAG ERROR] Similarity fallback also failed: {e2}")
                return ""


# Module-level singleton imported by main.py
rag_engine = RAGEngine()