import os
from langchain_pinecone import PineconeVectorStore as LangchainPinecone
from langchain_ollama import OllamaEmbeddings
from pinecone import Pinecone

class PineconeVectorStore:
    """
    Concrete implementation of the VectorStore protocol using Pinecone.
    Handles semantic embedding generation and retrieval for pulling clinical context.
    """
    def __init__(self, host: str, embedding_model: str, index_name: str, api_key: str):
        self.embeddings = OllamaEmbeddings(
            model=embedding_model,
            base_url=host,
        )
        
        # Initialize the Pinecone SDK client
        self.pc = Pinecone(api_key=api_key)
        
        # We assume the index already exists. 
        # If it doesn't, this will throw an error when accessed.
        self.index = self.pc.Index(index_name)

        self.vectorstore = LangchainPinecone(
            index=self.index,
            embedding=self.embeddings,
            text_key="text" # The default text metadata key used by langchain
        )
        
        # Note: Pinecone doesn't naturally support local BM25/hybrid search 
        # in the exact same way as local Chroma without serverless Pinecone BM25 integrations.
        # We will use pure semantic search (Max Marginal Relevance or Similarity).

    def retrieve(self, query: str, k: int = 8) -> str:
        if not query or not query.strip():
            return ""

        try:
            # First try Max Marginal Relevance search for diverse results
            results = self.vectorstore.max_marginal_relevance_search(
                query,
                k=k,
                fetch_k=max(20, k * 3),
                lambda_mult=0.7,
            )
            return "\n\n".join([doc.page_content for doc in results])
        except Exception as e:
            print(f"[RAG ERROR] MMR search failed in Pinecone: {e}. Attempting standard similarity fallback.")
            try:
                results = self.vectorstore.similarity_search(query, k=k)
                return "\n\n".join([doc.page_content for doc in results])
            except Exception as e2:
                print(f"[RAG ERROR] Similarity fallback also failed in Pinecone: {e2}")
                return ""
