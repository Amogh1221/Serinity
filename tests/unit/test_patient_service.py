import pytest
from services.patient_service import PatientService
from persistence.sqlite_memory_store import SQLiteProfileStore, SQLiteSessionStore
from tests.mocks import MockLLMProvider

def test_create_new_session(profile_store: SQLiteProfileStore, session_store: SQLiteSessionStore, mock_llm_provider: MockLLMProvider):
    service = PatientService(profile_store, session_store, mock_llm_provider)
    
    # Create an anonymous session
    session_id, opening_msg, patient_id = service.create_new_session()
    
    assert session_id is not None
    assert patient_id is not None
    assert opening_msg == "Mocked response from LLM1"
    
    messages = session_store.get_all_messages(session_id)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    
def test_generate_session_summary(profile_store: SQLiteProfileStore, session_store: SQLiteSessionStore, mock_llm_provider: MockLLMProvider):
    service = PatientService(profile_store, session_store, mock_llm_provider)
    
    session_id, _, patient_id = service.create_new_session()
    
    # Add a user message to trigger summary generation
    session_store.append_message(session_id, "user", "I feel sad today.")
    
    # Generate summary
    service.generate_session_summary(session_id, patient_id)
    
    # Check that summary was saved
    # _get_rolling_summary is technically protected but we can check via get_patient_sessions
    sessions = profile_store.get_patient_sessions(patient_id)
    assert len(sessions) == 1
    assert sessions[0]["rolling_summary"] == "Mocked session summary"
    
def test_sweep_abandoned_sessions(profile_store: SQLiteProfileStore, session_store: SQLiteSessionStore, mock_llm_provider: MockLLMProvider):
    service = PatientService(profile_store, session_store, mock_llm_provider)
    
    session_id, _, patient_id = service.create_new_session()
    session_store.append_message(session_id, "user", "Hello")
    
    # Manually update last_active_at to be older than timeout
    with session_store._get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET last_active_at = datetime('now', '-40 minutes') WHERE session_id = ?",
            (session_id,)
        )
        
    service.sweep_abandoned_sessions(timeout_minutes=30)
    
    # Session should now be inactive and summarized
    active_session = session_store.get_active_session(patient_id)
    assert active_session is None
    
    sessions = profile_store.get_patient_sessions(patient_id)
    assert sessions[0]["is_active"] == 0
    assert sessions[0]["rolling_summary"] == "Mocked session summary"
