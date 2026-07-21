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

        # Build medium-term memory once — constant within a session, stable between LLM2 updates.
        # Passed to LLM1 as a cached context block and reused in LLM2 via _run_sync_analysis.
        medium_term_memory: Optional[str] = None
        if patient_id:
            medium_term_memory = self.profile_store.build_profile_recap(patient_id)

        try:
            llm1_response = self.llm_provider.psychiatrist_response(
                history, patient_info, medium_term_memory=medium_term_memory
            )
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
                llm2_message = self._run_sync_analysis(
                    session_id, patient_id,
                    llm1_response.clinical_summary,
                    llm1_response.assistant_message,
                    medium_term_memory=medium_term_memory,
                )
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
            # Rate-limit / quota errors must bubble up so the route can return 429
            # and the frontend shows the "Tokens Exhausted" popup.
            err_msg = str(e).lower()
            if any(k in err_msg for k in ("tokens exhausted", "429", "rate limit", "quota", "exceeded")):
                raise
            fallback_message = "I'm having a little trouble connecting my thoughts right now. Could you repeat that?"
            self.session_store.append_message(session_id, "assistant", fallback_message)
            return ChatResult(
                assistant_message=fallback_message,
                intent="UNKNOWN",
                risk_flagged=False,
                job_id=None,
                clinical_summary=None
            )

    def _run_sync_analysis(
        self,
        session_id: str,
        patient_id: str,
        clinical_summary: Optional[str] = None,
        llm1_draft: Optional[str] = None,
        medium_term_memory: Optional[str] = None,
    ) -> Optional[str]:
        """
        Executes the heavy LLM2 pattern analysis synchronously.

        Groq caching layers:
          [1] system, cached  LLM2_SYSTEM_PROMPT        (constant — provider handles this)
          [2] user,   cached  stable_prefix             (demographics + medium-term memory;
                                                         constant between LLM2 calls)
          [3] dynamic         history[-6:] + context    (RAG + session summary + draft)

        `medium_term_memory` is passed in from handle_message (already fetched once)
        to avoid a redundant DB round-trip.
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
            
            patient_info = self.profile_store.get_patient(patient_id) if patient_id else None

            # --- Build stable_prefix (cached at the provider) ---
            # Contains demographics + medium-term memory. These are constant between
            # LLM2 calls, so Groq can serve them from cache after the first warm-up.
            stable_parts = []
            if patient_info:
                stable_parts.append(
                    f"PATIENT DEMOGRAPHICS:\n"
                    f"- Name: {patient_info.get('name', 'Unknown')}\n"
                    f"- Age: {patient_info.get('age', 'Unknown')}\n"
                    f"- Gender: {patient_info.get('gender', 'Unknown')}\n"
                    f"- Nationality: {patient_info.get('nationality', 'Unknown')}\n"
                    f"- Primary Concern: {patient_info.get('primary_concern', 'Unknown')}"
                )
            mtm = medium_term_memory or self.profile_store.build_profile_recap(patient_id)
            if mtm:
                stable_parts.append(
                    f"PATIENT MEDIUM-TERM MEMORY (prior sessions & profile — do not quote verbatim):\n"
                    f"{mtm}"
                )
            stable_prefix = "\n\n".join(stable_parts) if stable_parts else None

            # --- Build dynamic context_prompt (only the changing parts) ---
            # Demographics + MTM are now in stable_prefix (cached), so we only
            # include the truly dynamic content here.
            context_parts = []
            if clinical_summary and clinical_summary.strip():
                context_parts.append(f"Current Session Clinical Summary:\n{clinical_summary}")
            context_parts.append(
                f"Retrieved Clinical Reference (Sims' Symptoms in the Mind):\n{retrieved_context}"
            )
            if llm1_draft:
                context_parts.append(f"Intern's Draft Response:\n{llm1_draft}")
            context_parts.append(
                "Please perform pattern analysis across all eight domains. Evaluate how the user "
                "is behaving now (based on the current session messages and summary) compared to "
                "their existing profile, and output the updated patterns. You must also review the "
                "Intern's Draft Response, refine and amplify it using your deeper clinical insights, "
                "and provide the final polished conversational response."
            )
            context_prompt = "\n\n".join(context_parts)

            # history[-6:] reduces TPM by ~35% vs [-10:]; profile_recap + rolling
            # summary already carry the earlier context, so quality loss is negligible.
            llm2_input = history[-6:] + [{"role": "user", "content": context_prompt}]
            llm2_response = self.llm_provider.internal_reasoning(llm2_input, stable_prefix=stable_prefix)
            log.llm2_output(llm2_response)

            self.profile_store.update_long_term_memory(patient_id, llm2_response)
            serinity_logger.info(f"Synchronous analysis completed for patient {patient_id}.")
            return llm2_response.assistant_message
            
        except Exception as e:
            log.error("sync_analysis_failed", e)
            serinity_logger.error(f"Synchronous analysis failed: {e}")
            return None
