import os
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever

class ChromaVectorStore:
    """
    Concrete implementation of the VectorStore protocol using ChromaDB.
    Handles semantic embedding generation and hybrid retrieval (BM25 + MMR)
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
                "Run `python build_vectorDB.py` to populate it before starting a session."
            )
            self.ensemble_retriever = None
        else:
            print("[RAG] Building BM25 index for Hybrid Retrieval...")
            import pickle
            bm25_cache_path = os.path.join(persist_dir, "bm25_index.pkl")
            
            bm25_retriever = None
            if os.path.exists(bm25_cache_path):
                print("[RAG] Loading BM25 index from local cache...")
                try:
                    with open(bm25_cache_path, "rb") as f:
                        bm25_retriever = pickle.load(f)
                except Exception as e:
                    print(f"[RAG] Failed to load BM25 cache: {e}. Rebuilding...")
                    bm25_retriever = None

            if bm25_retriever is None:
                print("[RAG] Building BM25 index from ChromaDB (this may take a moment for large databases)...")
                # Extract all stored documents in batches to avoid SQLite 'too many SQL variables' error
                documents = []
                batch_size = 5000
                offset = 0
                while True:
                    batch = self.vectorstore.get(limit=batch_size, offset=offset)
                    batch_docs = batch.get("documents", [])
                    if not batch_docs:
                        break
                    documents.extend(batch_docs)
                    offset += batch_size
                
                if documents:
                    bm25_retriever = BM25Retriever.from_texts(documents)
                    bm25_retriever.k = min(8, len(documents))
                    
                    # Save to cache for future restarts
                    try:
                        with open(bm25_cache_path, "wb") as f:
                            pickle.dump(bm25_retriever, f)
                        print("[RAG] BM25 index cached successfully.")
                    except Exception as e:
                        print(f"[RAG WARNING] Failed to cache BM25 index: {e}")
            
            if bm25_retriever:
                # 2. Semantic Retriever (Chroma MMR)
                mmr_retriever = self.vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs={
                        "k": bm25_retriever.k,
                        "fetch_k": min(30, len(documents)),
                        "lambda_mult": 0.7
                    }
                )
                
                # 3. Hybrid Ensemble (50% Lexical, 50% Semantic)
                self.ensemble_retriever = EnsembleRetriever(
                    retrievers=[bm25_retriever, mmr_retriever],
                    weights=[0.5, 0.5]
                )
            else:
                self.ensemble_retriever = None

    def retrieve(self, query: str) -> str:
        if not query or not query.strip():
            return ""

        try:
            if self.ensemble_retriever:
                results = self.ensemble_retriever.invoke(query)
                # EnsembleRetriever returns a list of Document objects
                # We limit the final combined output to the top 8 matches
                return "\n\n".join([doc.page_content for doc in results[:8]])
            
            # Fallback if ensemble isn't ready (e.g. empty DB)
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
            print(f"[RAG ERROR] Hybrid search failed: {e}. Attempting similarity fallback.")
            try:
                results = self.vectorstore.similarity_search(query, k=8)
                return "\n\n".join([doc.page_content for doc in results])
            except Exception as e2:
                print(f"[RAG ERROR] Similarity fallback also failed: {e2}")
                return ""
