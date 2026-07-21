from typing import Optional, Dict, Any, List
from core.ports import LLMProvider, LLM1Output, LLM2Output, LLM3Output, STTProvider, VectorStore

class MockLLMProvider:
    def generate_opening_context(self, profile_recap: Optional[str]) -> list:
        return [{"role": "system", "content": "Mocked opening context"}]

    def psychiatrist_response(
        self, context: list, patient_info: dict = None, medium_term_memory: str | None = None
    ) -> LLM1Output:
        return LLM1Output(
            assistant_message="Mocked response from LLM1",
            intent="CONTINUE",
            risk_flag=False,
            clinical_summary=None,
            search_query=None
        )

    def internal_reasoning(
        self, context: list, stable_prefix: str | None = None
    ) -> LLM2Output:
        return LLM2Output(
            assistant_message="Mocked response from LLM2",
            emotional_themes=["theme1"],
            thinking_patterns=["pattern1"],
            behavioral_patterns=["behavior1"],
            interpersonal_dynamics=["dynamic1"],
            stressors=["stressor1"],
            unclear_areas=["unclear1"],
            risk_assessment="No safety concerns identified",
            protective_factors=["factor1"]
        )
        
    def psychiatrist_query_response(self, context: list, retrieved_context: str) -> str:
        return "Mocked query response"
        
    def generate_end_of_session_profile(self, old_profile: dict, session_history: list, patient_info: dict = None) -> LLM3Output:
        return LLM3Output(
            session_summary="Mocked session summary",
            update_profile=True,
            emotional_themes=["theme1"],
            thinking_patterns=["pattern1"],
            behavioral_patterns=["behavior1"],
            interpersonal_dynamics=["dynamic1"],
            stressors=["stressor1"],
            unclear_areas=["unclear1"],
            risk_assessment="No safety concerns identified",
            protective_factors=["factor1"],
            updated_primary_concern=None
        )

class MockSTTProvider:
    def transcribe(self, audio_bytes: bytes) -> Dict[str, Any]:
        return {
            "text": "Mocked transcribed text",
            "emotion": "neutral",
            "event": None
        }

class MockVectorStore:
    def retrieve(self, query: str, k: int = 8) -> str:
        return "Mocked retrieved clinical context"
