from core.ports import LLM1Output, LLM2Output, LLM3Output

class FallbackLLMProvider:
    """
    Composite LLM Provider that loops through a list of other providers.
    If a provider throws an exception (e.g. rate limit / 429), it tries the next.
    Returns safe fallback strings if all providers fail.
    """
    def __init__(self, providers: list):
        self.providers = providers

    def generate_opening_context(self, profile_recap: str | None) -> list:
        # This doesn't call an LLM directly, so we just use the first provider's logic
        return self.providers[0].generate_opening_context(profile_recap)

    def psychiatrist_response(self, context: list, patient_info: dict = None) -> LLM1Output:
        for provider in self.providers:
            try:
                return provider.psychiatrist_response(context, patient_info)
            except Exception as e:
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for LLM1: {e}")
                continue
        
        # All failed
        print("[FallbackRouter] ALL providers failed for LLM1!")
        return LLM1Output(
            assistant_message="I'm here, and I'm listening. Please take your time. && Would you like to tell me more about what's on your mind?",
            intent="CONTINUE",
            risk_flag=False,
            clinical_summary=None
        )

    def internal_reasoning(self, context: list) -> LLM2Output:
        for provider in self.providers:
            try:
                return provider.internal_reasoning(context)
            except Exception as e:
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for LLM2: {e}")
                continue

        # All failed
        print("[FallbackRouter] ALL providers failed for LLM2!")
        return LLM2Output(
            assistant_message="I'm here, taking everything in. Please go on.",
            emotional_themes=[],
            thinking_patterns=[],
            behavioral_patterns=[],
            interpersonal_dynamics=[],
            stressors=[],
            unclear_areas=[],
            risk_assessment="Unable to complete risk assessment due to analysis error.",
            protective_factors=[]
        )

    def psychiatrist_query_response(self, context: list, retrieved_context: str) -> str:
        for provider in self.providers:
            try:
                return provider.psychiatrist_query_response(context, retrieved_context)
            except Exception as e:
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for Query: {e}")
                continue

        return "I hear you, and we will find a way through this together. Let's keep exploring what might help."

    def generate_end_of_session_profile(self, old_profile: dict, session_history: list, patient_info: dict = None) -> LLM3Output:
        for provider in self.providers:
            try:
                return provider.generate_end_of_session_profile(old_profile, session_history, patient_info)
            except Exception as e:
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for LLM3: {e}")
                continue

        return LLM3Output(
            session_summary="Error generating session summary.",
            update_profile=False,
            emotional_themes=[],
            thinking_patterns=[],
            behavioral_patterns=[],
            interpersonal_dynamics=[],
            stressors=[],
            unclear_areas=[],
            risk_assessment="Error.",
            protective_factors=[]
        )

    def summarize_history(self, turns: list) -> str:
        for provider in self.providers:
            try:
                return provider.summarize_history(turns)
            except Exception as e:
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for Summarize: {e}")
                continue

        return "[Summary unavailable]"
