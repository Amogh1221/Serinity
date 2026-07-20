import pytest
from unittest.mock import MagicMock
from services.conversation_orchestrator import ConversationOrchestrator
from core.ports import LLM1Output
from core.schemas import ChatResult

def test_handle_message_intent_continue(mocker):
    # Mock dependencies
    llm_mock = MagicMock()
    llm_mock.psychiatrist_response.return_value = LLM1Output(
        intent="CONTINUE",
        assistant_message="Tell me more about that.",
        clinical_summary="Patient feels sad."
    )
    
    vec_mock = MagicMock()
    
    session_mock = MagicMock()
    session_mock.get_patient_id.return_value = "pat_123"
    session_mock.get_session_count.return_value = 1
    session_mock.get_working_context.return_value = []
    
    profile_mock = MagicMock()
    profile_mock.get_patient.return_value = {"name": "Test", "id": "pat_123"}
    
    risk_mock = MagicMock()
    risk_mock.assess.return_value = False
    
    orchestrator = ConversationOrchestrator(
        llm_provider=llm_mock,
        vector_store=vec_mock,
        session_store=session_mock,
        profile_store=profile_mock,
        risk_service=risk_mock
    )
    
    # Run
    result = orchestrator.handle_message("sess_1", "I am sad", "sad", "pat_123")
    
    # Assert
    assert result.intent == "CONTINUE"
    assert result.assistant_message == "Tell me more about that."
    assert result.risk_flagged is False
    session_mock.append_message.assert_any_call("sess_1", "user", "[vocal tone: sad] I am sad")
    session_mock.append_message.assert_any_call("sess_1", "assistant", "Tell me more about that.")
    vec_mock.retrieve.assert_not_called()

def test_handle_message_intent_query(mocker):
    llm_mock = MagicMock()
    llm_mock.psychiatrist_response.return_value = LLM1Output(
        intent="QUERY",
        assistant_message="Let me think.",
        clinical_summary="Patient is anxious.",
        search_query="Anxiety symptoms"
    )
    llm_mock.psychiatrist_query_response.return_value = "According to literature, this is anxiety."
    
    vec_mock = MagicMock()
    vec_mock.retrieve.return_value = ["Textbook entry on anxiety"]
    
    session_mock = MagicMock()
    session_mock.get_patient_id.return_value = None
    profile_mock = MagicMock()
    profile_mock.get_patient.return_value = None
    risk_mock = MagicMock()
    risk_mock.assess.return_value = False
    
    orchestrator = ConversationOrchestrator(
        llm_mock, vec_mock, session_mock, profile_mock, risk_mock
    )
    
    result = orchestrator.handle_message("sess_2", "I feel anxious", None, None)
    
    assert result.intent == "QUERY"
    assert result.assistant_message == "According to literature, this is anxiety."
    vec_mock.retrieve.assert_called_once_with("Anxiety symptoms", k=5)
    llm_mock.psychiatrist_query_response.assert_called_once()

def test_handle_message_intent_analyze(mocker):
    llm_mock = MagicMock()
    llm_mock.psychiatrist_response.return_value = LLM1Output(
        intent="ANALYZE",
        assistant_message="I see a pattern.",
        clinical_summary="Patient discussed trauma."
    )
    
    # Mock the _run_sync_analysis which uses LLM2
    mocker.patch.object(ConversationOrchestrator, '_run_sync_analysis', return_value="Deep analysis output.")
    
    vec_mock = MagicMock()
    session_mock = MagicMock()
    session_mock.get_patient_id.return_value = "pat_123"
    profile_mock = MagicMock()
    profile_mock.get_patient.return_value = {"name": "Test", "id": "pat_123"}
    risk_mock = MagicMock()
    risk_mock.assess.return_value = False
    
    orchestrator = ConversationOrchestrator(
        llm_mock, vec_mock, session_mock, profile_mock, risk_mock
    )
    
    result = orchestrator.handle_message("sess_3", "Lots of trauma", None, "pat_123")
    
    assert result.intent == "ANALYZE"
    assert result.assistant_message == "Deep analysis output."
    orchestrator._run_sync_analysis.assert_called_once()

def test_handle_message_risk_override(mocker):
    llm_mock = MagicMock()
    llm_mock.psychiatrist_response.return_value = LLM1Output(
        intent="CONTINUE",
        assistant_message="Let's talk.",
        clinical_summary="Patient mentioned harm."
    )
    mocker.patch.object(ConversationOrchestrator, '_run_sync_analysis', return_value="Safety protocol initiated.")
    
    vec_mock = MagicMock()
    session_mock = MagicMock()
    session_mock.get_patient_id.return_value = "pat_123"
    profile_mock = MagicMock()
    profile_mock.get_patient.return_value = {"name": "Test", "id": "pat_123"}
    
    risk_mock = MagicMock()
    risk_mock.assess.return_value = True # Flagged risk!
    
    orchestrator = ConversationOrchestrator(
        llm_mock, vec_mock, session_mock, profile_mock, risk_mock
    )
    
    result = orchestrator.handle_message("sess_4", "I want to hurt myself", None, "pat_123")
    
    # Risk override should force intent to ANALYZE
    assert result.intent == "ANALYZE"
    assert result.risk_flagged is True
    assert result.assistant_message == "Safety protocol initiated."
