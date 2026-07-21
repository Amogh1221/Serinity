from core.ports import LLM1Output, LLM2Output, LLM3Output


def _is_rate_limit(exc: Exception) -> bool:
    """Return True if the exception looks like a quota / rate-limit error."""
    msg = str(exc).lower()
    return any(k in msg for k in (
        "429", "rate limit", "ratelimit", "too many requests",
        "quota", "exceeded", "tokens exhausted", "credits"
    ))


class FallbackLLMProvider:
    """
    Composite LLM Provider that loops through a list of other providers.
    If a provider throws an exception (e.g. rate limit / 429), it tries the next.

    For LLM1 and LLM2 calls:
      - If all providers fail with a rate-limit/quota error, the exception is
        re-raised so the route can return HTTP 429 and the frontend shows a popup.
      - If all providers fail for any other reason, a safe fallback string is returned.

    For non-conversational calls (query, LLM3, summarize), the fallback string is
    always returned to avoid breaking secondary features.
    """
    def __init__(self, providers: list):
        self.providers = providers

    def generate_opening_context(self, profile_recap: str | None) -> list:
        return self.providers[0].generate_opening_context(profile_recap)

    def psychiatrist_response(
        self, context: list, patient_info: dict = None, medium_term_memory: str | None = None
    ) -> LLM1Output:
        last_error = None
        for provider in self.providers:
            try:
                return provider.psychiatrist_response(context, patient_info, medium_term_memory)
            except Exception as e:
                last_error = e
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for LLM1: {e}")
                continue

        # Surface rate-limit errors so the frontend can show a popup
        if last_error and _is_rate_limit(last_error):
            print("[FallbackRouter] Rate limit detected — re-raising for LLM1.")
            raise RuntimeError(f"Tokens Exhausted: {last_error}") from last_error

        print("[FallbackRouter] ALL providers failed for LLM1!")
        return LLM1Output(
            assistant_message="I'm here, and I'm listening. Please take your time. && Would you like to tell me more about what's on your mind?",
            intent="CONTINUE",
            risk_flag=False,
            clinical_summary=None
        )

    def internal_reasoning(
        self, context: list, stable_prefix: str | None = None
    ) -> LLM2Output:
        last_error = None
        for provider in self.providers:
            try:
                return provider.internal_reasoning(context, stable_prefix)
            except Exception as e:
                last_error = e
                print(f"[FallbackRouter] Provider {type(provider).__name__} failed for LLM2: {e}")
                continue

        # Surface rate-limit errors so the orchestrator can propagate them
        if last_error and _is_rate_limit(last_error):
            print("[FallbackRouter] Rate limit detected — re-raising for LLM2.")
            raise RuntimeError(f"Tokens Exhausted: {last_error}") from last_error

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

    def generate_end_of_session_profile(
        self, old_profile: dict, session_history: list, patient_info: dict = None
    ) -> LLM3Output:
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
