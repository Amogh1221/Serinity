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
        resolved_patient_id = self.session_store.get_patient_id(session_id)

        recap = self.profile_store.build_profile_recap(resolved_patient_id) if resolved_patient_id else None
        opening_context = self.llm_provider.generate_opening_context(recap)
        llm1_response   = self.llm_provider.psychiatrist_response(opening_context)

        self.session_store.append_message(session_id, "assistant", llm1_response.assistant_message)

        patient_info = self.profile_store.get_patient(resolved_patient_id) if resolved_patient_id else None
        user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
        session_number = self.session_store.get_session_count(resolved_patient_id) if resolved_patient_id else 1
        log = get_logger(session_id, user_name, session_number)
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
        Asynchronously generates and saves a clinical summary of the session and updates the profile via LLM3.
        """
        patient_id = self.session_store.get_patient_id(session_id) or default_patient_id

        history = self.session_store.get_working_context(session_id)
        summary = "No conversation occurred."
        if len(history) > 1 and patient_id:
            try:
                old_profile = self.profile_store.get_patient_profile(patient_id)
                llm3_output = self.llm_provider.generate_end_of_session_profile(old_profile, history)
                summary = llm3_output.session_summary
                self.profile_store.update_patient_profile(patient_id, llm3_output)
                self.profile_store.update_long_term_memory(patient_id, llm3_output)
            except Exception as e:
                summary = f"Summary generation failed: {e}"

        self.session_store.save_session_summary(session_id, summary)

        patient_info = self.profile_store.get_patient(patient_id) if patient_id else None
        user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
        
        session_number = self.session_store.get_session_count(patient_id) if patient_id else 1
        log = get_logger(session_id, user_name, session_number)
        if 'llm3_output' in locals():
            log.llm3_output(llm3_output)
        else:
            log._write_jsonl("session_summary", {"summary": summary})
        close_logger(session_id)

    def sweep_abandoned_sessions(self, timeout_minutes: int = 30) -> None:
        """
        Finds sessions inactive for `timeout_minutes` and generates summaries for them, then closes them.
        """
        abandoned_ids = self.session_store.get_abandoned_sessions(timeout_minutes)
        for session_id in abandoned_ids:
            try:
                print(f"[PatientService] Sweeping abandoned session {session_id}...")
                self.generate_session_summary(session_id)
                self.end_session(session_id)
            except Exception as e:
                print(f"[PatientService] Failed to sweep session {session_id}: {e}")
