import pytest
from unittest.mock import MagicMock, patch
from providers.chroma_provider import ChromaVectorStore


class TestChromaVectorStore:
    """Tests for ChromaVectorStore, mocking ChromaDB, OllamaEmbeddings, and BM25."""

    @patch("providers.chroma_provider.OllamaEmbeddings")
    @patch("providers.chroma_provider.Chroma")
    def test_init_empty_collection(self, MockChroma, MockEmbeddings):
        """If collection is empty, ensemble_retriever is set to None and no BM25 index is built."""
        mock_chroma_instance = MockChroma.return_value
        # Mock count = 0
        mock_chroma_instance._collection.count.return_value = 0

        store = ChromaVectorStore(
            host="http://localhost:11434",
            embedding_model="nomic-embed-text",
            persist_dir="./fake_chroma_db",
            collection_name="test-knowledge"
        )

        assert store.ensemble_retriever is None
        mock_chroma_instance.get.assert_not_called()

    @patch("providers.chroma_provider.OllamaEmbeddings")
    @patch("providers.chroma_provider.Chroma")
    @patch("os.path.exists", return_value=False)
    @patch("providers.chroma_provider.BM25Retriever.from_texts")
    @patch("providers.chroma_provider.EnsembleRetriever")
    @patch("builtins.open")
    @patch("pickle.dump")
    def test_init_builds_bm25_from_scratch(self, mock_dump, mock_open, MockEnsemble, MockBM25, mock_exists, MockChroma, MockEmbeddings):
        """If collection has documents and no cache exists, it pulls docs from Chroma and builds BM25 cache."""
        mock_chroma_instance = MockChroma.return_value
        mock_chroma_instance._collection.count.return_value = 10
        
        # Mock batch fetching: first call returns 10 docs, second returns 0
        mock_chroma_instance.get.side_effect = [
            {"documents": ["Doc 1", "Doc 2"]},
            {"documents": []}
        ]

        store = ChromaVectorStore(
            host="http://localhost:11434",
            embedding_model="nomic-embed-text",
            persist_dir="./fake_chroma_db",
            collection_name="test-knowledge"
        )

        # Verified it pulled from Chroma
        assert mock_chroma_instance.get.call_count == 2
        # Verified it built BM25
        MockBM25.assert_called_once_with(["Doc 1", "Doc 2"])
        # Verified it cached to pickle
        mock_open.assert_called_once()
        mock_dump.assert_called_once()
        # Verified ensemble was created
        MockEnsemble.assert_called_once()
        assert store.ensemble_retriever == MockEnsemble.return_value

    @patch("providers.chroma_provider.OllamaEmbeddings")
    @patch("providers.chroma_provider.Chroma")
    def test_retrieve_with_ensemble(self, MockChroma, MockEmbeddings):
        """Retrieve uses the ensemble retriever if it is available."""
        mock_chroma_instance = MockChroma.return_value
        mock_chroma_instance._collection.count.return_value = 0 # Forces ensemble to None initially
        
        store = ChromaVectorStore("host", "emb", "dir", "col")
        
        # Inject fake ensemble
        mock_ensemble = MagicMock()
        fake_doc1 = MagicMock()
        fake_doc1.page_content = "retrieved text 1"
        fake_doc2 = MagicMock()
        fake_doc2.page_content = "retrieved text 2"
        mock_ensemble.invoke.return_value = [fake_doc1, fake_doc2]
        
        store.ensemble_retriever = mock_ensemble

        result = store.retrieve("Anxiety criteria", k=2)
        
        assert result == "retrieved text 1\n\nretrieved text 2"
        mock_ensemble.invoke.assert_called_once_with("Anxiety criteria")

    @patch("providers.chroma_provider.OllamaEmbeddings")
    @patch("providers.chroma_provider.Chroma")
    def test_retrieve_without_ensemble_falls_back_to_mmr(self, MockChroma, MockEmbeddings):
        """If ensemble is None, it uses ChromaDB MMR search."""
        mock_chroma_instance = MockChroma.return_value
        mock_chroma_instance._collection.count.return_value = 0
        
        store = ChromaVectorStore("host", "emb", "dir", "col")
        assert store.ensemble_retriever is None
        
        mock_chroma_instance._collection.count.return_value = 10
        fake_doc1 = MagicMock()
        fake_doc1.page_content = "fallback text 1"
        mock_chroma_instance.max_marginal_relevance_search.return_value = [fake_doc1]

        result = store.retrieve("Anxiety", k=1)
        
        assert result == "fallback text 1"
        mock_chroma_instance.max_marginal_relevance_search.assert_called_once_with(
            "Anxiety", k=1, fetch_k=10, lambda_mult=0.7
        )

    @patch("providers.chroma_provider.OllamaEmbeddings")
    @patch("providers.chroma_provider.Chroma")
    def test_retrieve_handles_exception_and_falls_back(self, MockChroma, MockEmbeddings):
        """Retrieve falls back to similarity search on MMR exception."""
        mock_chroma_instance = MockChroma.return_value
        mock_chroma_instance._collection.count.return_value = 0
        
        store = ChromaVectorStore("host", "emb", "dir", "col")
        mock_chroma_instance._collection.count.return_value = 10
        mock_chroma_instance.max_marginal_relevance_search.side_effect = Exception("MMR Failed")
        
        fake_doc = MagicMock()
        fake_doc.page_content = "similarity text"
        mock_chroma_instance.similarity_search.return_value = [fake_doc]

        result = store.retrieve("Anxiety", k=1)
        assert result == "similarity text"
        mock_chroma_instance.similarity_search.assert_called_once_with("Anxiety", k=1)
