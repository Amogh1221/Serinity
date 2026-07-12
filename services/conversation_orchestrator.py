from typing import Optional
from core.ports import LLMProvider, VectorStore, SessionStore, ProfileStore, AnalysisJobStore, LLM1Output
from core.schemas import ChatResult
from services.risk_assessment_service import RiskAssessmentService
from core.logger import get_logger

class ConversationOrchestrator:
    """
    Central coordinator for the application's core logic.
    Implements a 'Sync Fast-Path, Async Slow-Path' architecture to decouple 
    immediate conversational responses (LLM1) from deep psychological analysis (LLM2).
    """
    def __init__(
        self,
        llm_provider: LLMProvider,
        vector_store: VectorStore,
        session_store: SessionStore,
        profile_store: ProfileStore,
        job_store: AnalysisJobStore,
        risk_service: RiskAssessmentService
    ):
        self.llm_provider = llm_provider
        self.vector_store = vector_store
        self.session_store = session_store
        self.profile_store = profile_store
        self.job_store = job_store
        self.risk_service = risk_service

    def _format_list(self, items: list) -> str:
        if not items:
            return "None identified yet"
        return "\n  • " + "\n  • ".join(items)

    def handle_message(self, session_id: str, message: str, emotion: Optional[str], default_patient_id: Optional[str]) -> ChatResult:
        patient_id = self.profile_store.get_patient_id(session_id) or default_patient_id
        patient_info = self.profile_store.get_patient(patient_id) if patient_id else None
        user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
        
        log = get_logger(session_id, user_name)
        
        emotion = (emotion or "").lower().strip()
        user_message = message
        if emotion and emotion not in ("neutral", "unknown", ""):
            user_message = f"[vocal tone: {emotion}] {user_message}"
            
        log.user_message(message, emotion=emotion or None)
        
        self.session_store.append_message(session_id, "user", user_message)
        
        history = self.session_store.get_working_context(session_id, llm_engine=self.llm_provider)
        
        llm1_response = self.llm_provider.psychiatrist_response(history)
        log.llm1_decision(llm1_response)
        
        base_risk = self.risk_service.assess(message, llm1_response, None)
        
        intent = llm1_response.intent
        if base_risk and intent != "ANALYZE":
            intent = "ANALYZE"
            
        self.session_store.append_message(session_id, "assistant", llm1_response.assistant_message)
        log.assistant_reply(llm1_response.assistant_message, risk_injected=base_risk)
        
        chat_result = ChatResult(
            assistant_message=llm1_response.assistant_message,
            intent=intent,
            risk_flagged=base_risk,
            job_id=None
        )
        
        if intent == "ANALYZE" and patient_id:
            job_id = self.job_store.queue_analysis_job(session_id, patient_id)
            chat_result.job_id = job_id
            
        return chat_result

    def run_background_analysis(self, job_id: str, session_id: str, patient_id: str):
        """
        Executes the heavy LLM2 pattern analysis asynchronously.
        Uses the AnalysisJobStore to ensure only one analysis runs per patient at a time.
        """
        if not self.job_store.acquire_analysis_job(job_id, patient_id):
            print(f"[Orchestrator] Job {job_id} for {patient_id} could not be acquired (likely concurrent analysis in progress).")
            return
            
        log = get_logger(session_id, "Background Task")
        try:
            history = self.session_store.get_working_context(session_id, llm_engine=self.llm_provider)
            retrieval_query = "\n".join(
                msg["content"]
                for msg in history[-10:]
                if msg.get("role") == "user"
            )
            query_source = "user_messages_fallback"
            
            log.analyze_triggered(retrieval_query, query_source)
            retrieved_context = self.vector_store.retrieve(retrieval_query)
            log.retrieved_context(retrieved_context)
            
            llm2_input = history[-10:] + [{
                "role": "user",
                "content": (
                    f"Clinical Context for Analysis:\n{retrieved_context}\n\n"
                    "Please perform pattern analysis across all eight domains."
                )
            }]
            llm2_response = self.llm_provider.internal_reasoning(llm2_input)
            log.llm2_output(llm2_response)
            
            self.profile_store.update_patient_profile(patient_id, llm2_response)
            self.job_store.complete_analysis_job(job_id)
            print(f"[Orchestrator] Background analysis completed for patient {patient_id}.")
            
        except Exception as e:
            print(f"[Orchestrator] Background analysis failed: {e}")
            self.job_store.fail_analysis_job(job_id)
