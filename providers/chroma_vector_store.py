import os
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

class ChromaVectorStore:
    """
    Concrete implementation of the VectorStore protocol using ChromaDB.
    Handles semantic embedding generation and max-marginal relevance (MMR) retrieval 
    for pulling clinical context during background analysis.
    """
    def __init__(self, host: str, embedding_model: str, persist_dir: str, collection_name: str):
        self.embeddings = OllamaEmbeddings(
            model=embedding_model,
            base_url=host,
        )

        self.vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=persist_dir,
        )
        count = self.vectorstore._collection.count()
        if count == 0:
            print(
                "[RAG WARNING] ChromaDB collection is empty. "
                "Run `python built_vectorDB.py` to populate it before starting a session."
            )
        else:
            print(f"[RAG] Loaded {count:,} documents from ChromaDB ({collection_name}).")

    def retrieve(self, query: str) -> str:
        if not query or not query.strip():
            return ""

        try:
            count = self.vectorstore._collection.count()
            if count == 0:
                return ""

            actual_fetch_k = min(30, count)
            actual_k = min(8, actual_fetch_k)

            results = self.vectorstore.max_marginal_relevance_search(
                query,
                k=actual_k,
                fetch_k=actual_fetch_k,
                lambda_mult=0.7,
            )
            return "\n\n".join([doc.page_content for doc in results])

        except Exception as e:
            print(f"[RAG ERROR] MMR search failed: {e}. Attempting similarity fallback.")
            try:
                results = self.vectorstore.similarity_search(query, k=8)
                return "\n\n".join([doc.page_content for doc in results])
            except Exception as e2:
                print(f"[RAG ERROR] Similarity fallback also failed: {e2}")
                return ""
