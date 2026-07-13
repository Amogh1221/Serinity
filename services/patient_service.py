from typing import Optional, Tuple
from core.ports import ProfileStore, SessionStore, LLMProvider
from core.logger import get_logger, close_logger

class PatientService:
    """
    Service responsible for managing the high-level lifecycle of patient sessions.
    Handles session initialization, profile recap generation, and session termination/summarization.
    """
    def __init__(self, profile_store: ProfileStore, session_store: SessionStore, llm_provider: LLMProvider):
        self.profile_store = profile_store
        self.session_store = session_store
        self.llm_provider = llm_provider

    def create_new_session(self, default_patient_id: Optional[str] = None) -> Tuple[str, str, str]:
        session_id = self.session_store.create_session(patient_id=default_patient_id)
        resolved_patient_id = self.profile_store.get_patient_id(session_id)

        recap = self.profile_store.build_profile_recap(resolved_patient_id) if resolved_patient_id else None
        opening_context = self.llm_provider.generate_opening_context(recap)
        llm1_response   = self.llm_provider.psychiatrist_response(opening_context)

        self.session_store.append_message(session_id, "assistant", llm1_response.assistant_message)

        patient_info = self.profile_store.get_patient(resolved_patient_id) if resolved_patient_id else None
        user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
        
        log = get_logger(session_id, user_name)
        log.session_start(resolved_patient_id)
        log.assistant_reply(llm1_response.assistant_message, risk_injected=False)

        return session_id, llm1_response.assistant_message, resolved_patient_id

    def end_session(self, session_id: str, default_patient_id: Optional[str] = None) -> None:
        """
        Synchronously ends the session.
        Immediate teardown logic goes here.
        """
        self.session_store.end_session(session_id)

    def reset_patient_data(self, patient_id: str) -> None:
        """
        Resets the patient's data, including sessions, messages, and profile.
        """
        self.profile_store.reset_patient_data(patient_id)

    def delete_patient(self, patient_id: str) -> None:
        """
        Deletes a patient and all their associated data completely.
        """
        self.profile_store.delete_patient(patient_id)

    def generate_session_summary(self, session_id: str, default_patient_id: Optional[str] = None) -> None:
        """
        Asynchronously generates and saves a clinical summary of the session.
        """
        patient_id = self.profile_store.get_patient_id(session_id) or default_patient_id

        history = self.session_store.get_working_context(session_id)
        summary = "No conversation occurred."
        if len(history) > 1:
            try:
                summary = self.llm_provider.summarize_history(history)
            except Exception as e:
                summary = f"Summary generation failed: {e}"

        if patient_id:
            self.session_store.save_session_summary(session_id, summary)

        patient_info = self.profile_store.get_patient(patient_id) if patient_id else None
        user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
        
        log = get_logger(session_id, user_name)
        log._write_jsonl("session_summary", {"summary": summary})
        close_logger(session_id)
