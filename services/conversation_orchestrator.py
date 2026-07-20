"""
Conversation Orchestrator Service
Coordinates the conversation logic, manages LLM calls, and interfaces with the risk assessment service.
"""

import time
from typing import Optional
from core.ports import LLMProvider, VectorStore, SessionStore, ProfileStore, LLM1Output
from core.schemas import ChatResult
from services.risk_assessment_service import RiskAssessmentService
from core.logger import get_logger, serinity_logger

class ConversationOrchestrator:
    """
    Central coordinator for the application's core logic.
    Implements a 'Sync 3-Pipeline' architecture.
    """
    def __init__(
        self,
        llm_provider: LLMProvider,
        vector_store: VectorStore,
        session_store: SessionStore,
        profile_store: ProfileStore,
        risk_service: RiskAssessmentService
    ):
        self.llm_provider = llm_provider
        self.vector_store = vector_store
        self.session_store = session_store
        self.profile_store = profile_store
        self.risk_service = risk_service

    def _format_list(self, items: list) -> str:
        if not items:
            return "None identified yet"
        return "\n  • " + "\n  • ".join(items)

    def handle_message(self, session_id: str, message: str, emotion: Optional[str], default_patient_id: Optional[str]) -> ChatResult:
        start_time = time.time()
        
        patient_id = self.session_store.get_patient_id(session_id) or default_patient_id
        patient_info = self.profile_store.get_patient(patient_id) if patient_id else None
        user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
        
        session_number = self.session_store.get_session_count(patient_id) if patient_id else 1
        log = get_logger(session_id, user_name, session_number)
        
        emotion = (emotion or "").lower().strip()
        user_message = message
        if emotion and emotion not in ("neutral", "unknown", ""):
            user_message = f"[vocal tone: {emotion}] {user_message}"
            
        log.user_message(message, emotion=emotion or None)
        
        self.session_store.append_message(session_id, "user", user_message)
        
        history = self.session_store.get_working_context(session_id, llm_engine=self.llm_provider)
        
        try:
            llm1_response = self.llm_provider.psychiatrist_response(history, patient_info)
            log.llm1_decision(llm1_response)
            
            base_risk = self.risk_service.assess(message, llm1_response, None)
            
            intent = llm1_response.intent
            if base_risk and intent != "ANALYZE":
                intent = "ANALYZE"
                
            final_message = llm1_response.assistant_message

            # Sync fast-path for user queries
            if intent == "QUERY" and llm1_response.search_query:
                retrieved_context = self.vector_store.retrieve(llm1_response.search_query, k=5)
                log.analyze_triggered(llm1_response.search_query, "query")
                log.retrieved_context(retrieved_context)
                final_message = self.llm_provider.psychiatrist_query_response(history, retrieved_context)
                
            # Synchronous execution of LLM2 pipeline
            if intent == "ANALYZE" and patient_id:
                llm2_message = self._run_sync_analysis(session_id, patient_id, llm1_response.clinical_summary, llm1_response.assistant_message)
                if llm2_message:
                    final_message = llm2_message

            self.session_store.append_message(session_id, "assistant", final_message)
            latency_ms = int((time.time() - start_time) * 1000)
            log.assistant_reply(final_message, risk_injected=base_risk, latency_ms=latency_ms)
            
            chat_result = ChatResult(
                assistant_message=final_message,
                intent=intent,
                risk_flagged=base_risk,
                job_id=None,
                clinical_summary=llm1_response.clinical_summary
            )
                
            return chat_result
        except Exception as e:
            log.error("handle_message_failed", e)
            serinity_logger.error(f"Error in handle_message: {str(e)}")
            fallback_message = "I'm having a little trouble connecting my thoughts right now. Could you repeat that?"
            self.session_store.append_message(session_id, "assistant", fallback_message)
            return ChatResult(
                assistant_message=fallback_message,
                intent="UNKNOWN",
                risk_flagged=False,
                job_id=None,
                clinical_summary=None
            )

    def _run_sync_analysis(self, session_id: str, patient_id: str, clinical_summary: Optional[str] = None, llm1_draft: Optional[str] = None) -> Optional[str]:
        """
        Executes the heavy LLM2 pattern analysis synchronously and returns the LLM2 generated response.
        """
        session_number = self.session_store.get_session_count(patient_id) if patient_id else 1
        log = get_logger(session_id, "Sync Analysis Task", session_number)
        try:
            history = self.session_store.get_working_context(session_id, llm_engine=self.llm_provider)
            if clinical_summary and clinical_summary.strip():
                retrieval_query = clinical_summary
                query_source = "clinical_summary"
            else:
                retrieval_query = "\n".join(
                    msg["content"]
                    for msg in history[-10:]
                    if msg.get("role") == "user"
                )
                query_source = "user_messages_fallback"
            
            log.analyze_triggered(retrieval_query, query_source)
            retrieved_context = self.vector_store.retrieve(retrieval_query)
            log.retrieved_context(retrieved_context)
            
            existing_profile_recap = self.profile_store.build_profile_recap(patient_id) or "No previous clinical profile exists for this patient."
            
            patient_info = self.profile_store.get_patient(patient_id) if patient_id else None
            demographics = ""
            if patient_info:
                demographics = (
                    f"PATIENT DEMOGRAPHICS:\n"
                    f"- Name: {patient_info.get('name', 'Unknown')}\n"
                    f"- Age: {patient_info.get('age', 'Unknown')}\n"
                    f"- Gender: {patient_info.get('gender', 'Unknown')}\n"
                    f"- Nationality: {patient_info.get('nationality', 'Unknown')}\n"
                    f"- Primary Concern: {patient_info.get('primary_concern', 'Unknown')}\n\n"
                )
            
            context_prompt = (
                f"{demographics}"
                f"Existing Clinical Profile:\n{existing_profile_recap}\n\n"
            )
            if clinical_summary and clinical_summary.strip():
                context_prompt += f"Current Session Clinical Summary:\n{clinical_summary}\n\n"
                
            context_prompt += (
                f"Retrieved Clinical Reference (Sims' Symptoms in the Mind):\n{retrieved_context}\n\n"
            )

            if llm1_draft:
                context_prompt += (
                    f"Intern's Draft Response:\n{llm1_draft}\n\n"
                )

            context_prompt += (
                "Please perform pattern analysis across all eight domains. Evaluate how the user is behaving now (based on the current session messages and summary) compared to their existing profile, and output the updated patterns. "
                "You must also review the Intern's Draft Response, refine and amplify it using your deeper clinical insights, and provide the final polished conversational response."
            )
            
            llm2_input = history[-10:] + [{
                "role": "user",
                "content": context_prompt
            }]
            llm2_response = self.llm_provider.internal_reasoning(llm2_input)
            log.llm2_output(llm2_response)
            
            self.profile_store.update_long_term_memory(patient_id, llm2_response)
            serinity_logger.info(f"Synchronous analysis completed for patient {patient_id}.")
            return llm2_response.assistant_message
            
        except Exception as e:
            log.error("sync_analysis_failed", e)
            serinity_logger.error(f"Synchronous analysis failed: {e}")
            return None
