import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Mock environment variables before importing app
os.environ["CLOUD_MODE"] = "false"
os.environ["JWT_SECRET_KEY"] = "supersecretkey"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"

from main import app
from api.dependencies import (
    get_profile_store, get_session_store, get_user_store,
    get_llm_provider, get_stt_provider, get_vector_store
)
from persistence.sqlite_memory_store import SQLiteProfileStore, SQLiteSessionStore
from persistence.user_store import SQLiteUserStore
from tests.mocks import MockLLMProvider, MockSTTProvider, MockVectorStore

@pytest.fixture(scope="function")
def db_path():
    # Use a temporary file for the database to ensure a clean state per test
    # and allow the SQLite store to connect multiple times to the same DB during a test
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    os.unlink(path)

@pytest.fixture(scope="function")
def profile_store(db_path):
    store = SQLiteProfileStore(db_path=db_path)
    return store

@pytest.fixture(scope="function")
def session_store(db_path):
    store = SQLiteSessionStore(db_path=db_path, working_memory_turns=20)
    return store

@pytest.fixture(scope="function")
def user_store(db_path):
    store = SQLiteUserStore(db_path=db_path)
    return store

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
def client(profile_store, session_store, user_store, mock_llm_provider, mock_stt_provider, mock_vector_store):
    app.dependency_overrides[get_profile_store] = lambda: profile_store
    app.dependency_overrides[get_session_store] = lambda: session_store
    app.dependency_overrides[get_user_store] = lambda: user_store
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm_provider
    app.dependency_overrides[get_stt_provider] = lambda: mock_stt_provider
    app.dependency_overrides[get_vector_store] = lambda: mock_vector_store
    
    with TestClient(app) as c:
        yield c
        
    app.dependency_overrides.clear()
