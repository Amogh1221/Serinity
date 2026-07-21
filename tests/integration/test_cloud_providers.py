import os
import pytest
from dotenv import load_dotenv

# Load real environment variables for integration tests (unlike conftest.py)
load_dotenv(override=True)

@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="GROQ_API_KEY not set")
def test_groq_llm_provider():
    """
    Tests the real Groq API to ensure the cloud LLM provider is working correctly.
    This will actually consume API credits and requires internet access.
    """
    from providers.llms.groq_llm_provider import GroqLLMProvider
    
    # Initialize with standard fast models
    provider = GroqLLMProvider(
        model1=os.getenv("GROQ_LLM1_MODEL", "llama-3.1-8b-instant"), 
        model2=os.getenv("GROQ_LLM2_MODEL", "llama-3.3-70b-versatile")
    )
    
    # 1. Test basic context generation (Fast, offline)
    context = provider.generate_opening_context(None)
    assert len(context) > 0
    
    # 2. Test actual LLM1 API call
    # We send a very short, benign message to keep token usage low
    response = provider.psychiatrist_response(
        context=[{"role": "user", "content": "Hi, I just wanted to say hello."}]
    )
    
    # Verify the response successfully parsed into our Pydantic model
    assert response is not None
    assert hasattr(response, "assistant_message")
    assert len(response.assistant_message) > 0
    assert response.intent in ["CONTINUE", "QUERY", "ANALYZE"]


@pytest.mark.skipif(not os.getenv("HF_TOKEN"), reason="HF_TOKEN not set")
def test_huggingface_llm_provider():
    """
    Tests the real HuggingFace Serverless Inference API.
    Requires HF_TOKEN and a network connection. Consumes free-tier quota.
    """
    from providers.llms.huggingface_llm_provider import HuggingFaceLLMProvider

    model1 = os.getenv("HF_LLM1_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    model2 = os.getenv("HF_LLM2_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
    provider = HuggingFaceLLMProvider(model1=model1, model2=model2)

    # 1. Opening context generation (offline — no API call)
    context = provider.generate_opening_context(None)
    assert len(context) > 0

    # 2. LLM1 live API call — send a short benign message
    from huggingface_hub.errors import HfHubHTTPError
    try:
        response = provider.psychiatrist_response(
            context=[{"role": "user", "content": "Hi, I just wanted to say hello."}]
        )
        assert response is not None
        assert hasattr(response, "assistant_message")
        assert len(response.assistant_message) > 0
        assert response.intent in ["CONTINUE", "QUERY", "ANALYZE"]
    except HfHubHTTPError as e:
        if "402" in str(e) or "429" in str(e):
            pytest.skip(f"HF API credits depleted or rate limit hit: {e}")
        else:
            raise e
@pytest.mark.skipif(
    not os.getenv("PINECONE_API_KEY"),
    reason="PINECONE_API_KEY not set — skipping Pinecone integration test"
)
def test_pinecone_provider():
    """Tests writing, retrieving, and deleting a document in Pinecone."""
    from providers.pinecone_provider import PineconeVectorStore
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    index = os.getenv("PINECONE_INDEX_NAME", "serinity-knowledge")
    api_key = os.getenv("PINECONE_API_KEY")

    provider = PineconeVectorStore(host, model, index, api_key)

    import uuid
    import time
    test_id = str(uuid.uuid4())
    test_text = f"Integration test document for Serinity: {test_id}"

    try:
        # Write to Pinecone
        provider.vectorstore.add_texts(texts=[test_text], ids=[test_id])

        # Pinecone is eventually consistent — wait for propagation
        time.sleep(5)

        # Retrieve and verify the document is findable
        retrieved = provider.retrieve(test_text, k=1)
        assert retrieved, "Expected at least one result from Pinecone"
        assert test_id in retrieved or test_text[:30] in retrieved, (
            f"Expected test document to appear in retrieved context, got: {retrieved[:200]}"
        )
    finally:
        # Clean up
        try:
            provider.vectorstore.delete(ids=[test_id])
        except Exception:
            pass  # Best-effort cleanup


@pytest.mark.skipif(not os.getenv("BETTERSTACK_SOURCE_TOKEN"), reason="BETTERSTACK_SOURCE_TOKEN not set")
def test_betterstack_logging():
    """Tests sending a very small log payload to BetterStack."""
    try:
        from logtail import LogtailHandler
        import logging
        token = os.getenv("BETTERSTACK_SOURCE_TOKEN")
        handler = LogtailHandler(source_token=token)
        
        test_logger = logging.getLogger("integration_test_logger")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.INFO)
        
        test_logger.info("Integration test log from Serinity", extra={"test_id": "1234"})
        
        # Flush ensures the log is sent before the test exits
        if hasattr(handler, 'flush'):
            handler.flush()
    except ImportError:
        pytest.skip("logtail-python not installed")


def test_real_sqlite_database():
    """Tests writing and deleting from the actual disk SQLite DB instead of memory."""
    from persistence.user_store import SQLiteUserStore
    import uuid
    import tempfile
    
    # We use a temporary file but on disk, not :memory:, to simulate real I/O
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    try:
        store = SQLiteUserStore(db_path=path)
        test_username = f"integration_user_{uuid.uuid4().hex[:8]}"
        
        # Write
        user_id = store.create_user(test_username, f"{test_username}@example.com", "fakehash")
        assert user_id is not None
        
        # Read
        user = store.get_user_by_id(user_id)
        assert user["username"] == test_username
        
        # Delete
        with store._get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            
        deleted_user = store.get_user_by_id(user_id)
        assert deleted_user is None
    finally:
        os.unlink(path)
