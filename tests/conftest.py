import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# ── 1. Set env vars BEFORE any app module is imported ──────────────────────
os.environ["CLOUD_MODE"]                      = "false"
os.environ["JWT_SECRET_KEY"]                  = "supersecretkey"
os.environ["JWT_ALGORITHM"]                   = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
# Remove cloud-service keys so providers that guard on them stay dormant
os.environ.pop("PINECONE_API_KEY", None)
os.environ.pop("GROQ_API_KEY",    None)
os.environ.pop("HF_TOKEN",        None)

# ── 2. Patch heavy infrastructure during module import only ────────────────
#    We temporarily patch during import of `main` to avoid network/model downloads,
#    then revert so unit test files (e.g. test_chroma_provider, test_safety_filters)
#    can test the real classes and methods.
with patch("providers.chroma_provider.ChromaVectorStore.__init__", return_value=None), \
     patch("providers.speech_to_text_provider.SenseVoiceSTTProvider._init_stt", return_value=None), \
     patch("providers.safety.bert.BertRiskSignal.__init__", return_value=None):
    from main import app                                                    # noqa: E402
    from api.dependencies import (                                          # noqa: E402
        get_profile_store, get_session_store, get_user_store,
        get_llm_provider, get_stt_provider, get_vector_store
    )
from persistence.sqlite_memory_store import SQLiteProfileStore, SQLiteSessionStore  # noqa: E402
from persistence.user_store import SQLiteUserStore                      # noqa: E402
from tests.mocks import MockLLMProvider, MockSTTProvider, MockVectorStore  # noqa: E402


# ── 4. Per-test fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_path():
    """Isolated SQLite file per test; cleaned up after."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture(scope="function")
def profile_store(db_path):
    return SQLiteProfileStore(db_path=db_path)


@pytest.fixture(scope="function")
def session_store(db_path):
    return SQLiteSessionStore(db_path=db_path, working_memory_turns=20)


@pytest.fixture(scope="function")
def user_store(db_path):
    return SQLiteUserStore(db_path=db_path)


@pytest.fixture(scope="function")
def mock_llm_provider():
    return MockLLMProvider()


@pytest.fixture(scope="function")
def mock_stt_provider():
    return MockSTTProvider()


@pytest.fixture(scope="function")
def mock_vector_store():
    return MockVectorStore()


@pytest.fixture(scope="function")
def client(
    profile_store,
    session_store,
    user_store,
    mock_llm_provider,
    mock_stt_provider,
    mock_vector_store,
):
    """TestClient with all infra dependencies overridden by in-memory mocks."""
    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_session_store] = lambda: session_store
    app.dependency_overrides[get_user_store]    = lambda: user_store
    app.dependency_overrides[get_llm_provider]  = lambda: mock_llm_provider
    app.dependency_overrides[get_stt_provider]  = lambda: mock_stt_provider
    app.dependency_overrides[get_vector_store]  = lambda: mock_vector_store

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
