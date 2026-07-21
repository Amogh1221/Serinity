import os
import json
from huggingface_hub import InferenceClient
from core.ports import LLM1Output, LLM2Output, LLM3Output
from core.prompts import LLM1_SYSTEM_PROMPT, LLM2_SYSTEM_PROMPT, LLM3_SYSTEM_PROMPT


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


class HuggingFaceLLMProvider:
    """
    Concrete implementation of the LLMProvider protocol using the HuggingFace
    Serverless Inference API (api-inference.huggingface.co).

    Requires HF_TOKEN set as a Space Secret. Models used:
      LLM1 / LLM3 : meta-llama/Llama-3.1-8B-Instruct  (fast, free tier)
      LLM2         : meta-llama/Llama-3.3-70B-Instruct (deep analysis)

    NOTE: HF Inference API does NOT support prompt caching, so the
    stable_prefix and medium_term_memory params are merged into regular
    system messages instead.
    """

    def __init__(self, model1: str, model2: str):
        token = os.environ.get("HF_TOKEN")
        if not token:
            raise RuntimeError(
                "HF_TOKEN is not set. Add it as a Space Secret on HuggingFace."
            )
        self.model1 = model1
        self.model2 = model2
        # Single client — the model is passed per-call so one client is enough
        self.client = InferenceClient(api_key=token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_stable_system(
        self, patient_info: dict | None, medium_term_memory: str | None
    ) -> str | None:
        """Build the demographics + MTM system block (replaces Groq's cache_control)."""
        parts = []
        if patient_info:
            parts.append(
                f"PATIENT DEMOGRAPHICS:\n"
                f"- Name: {patient_info.get('name', 'Unknown')}\n"
                f"- Age: {patient_info.get('age', 'Unknown')}\n"
                f"- Gender: {patient_info.get('gender', 'Unknown')}\n"
                f"- Nationality: {patient_info.get('nationality', 'Unknown')}\n"
                f"- Primary Concern: {patient_info.get('primary_concern', 'Unknown')}"
            )
        if medium_term_memory:
            parts.append(
                f"PATIENT MEDIUM-TERM MEMORY (prior sessions & patterns — do not quote verbatim):\n"
                f"{medium_term_memory}"
            )
        return "\n\n".join(parts) if parts else None

    def _call(self, model: str, messages: list, temperature: float, max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    # ------------------------------------------------------------------
    # Schema repair helpers — HF models sometimes omit fields from the
    # JSON schema. We inject sensible defaults before Pydantic validates.
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_llm1(raw: str) -> LLM1Output:
        d = json.loads(raw)
        d.setdefault("intent", "CONTINUE")
        d.setdefault("risk_flag", False)
        d.setdefault("clinical_summary", None)
        d.setdefault("search_query", None)
        return LLM1Output.model_validate(d)

    @staticmethod
    def _parse_llm2(raw: str) -> LLM2Output:
        d = json.loads(raw)
        d.setdefault("assistant_message", "I'm here with you. Please continue.")
        d.setdefault("emotional_themes", [])
        d.setdefault("thinking_patterns", [])
        d.setdefault("behavioral_patterns", [])
        d.setdefault("interpersonal_dynamics", [])
        d.setdefault("stressors", [])
        d.setdefault("unclear_areas", [])
        d.setdefault("risk_assessment", "No immediate risk identified.")
        d.setdefault("protective_factors", [])
        return LLM2Output.model_validate(d)

    @staticmethod
    def _parse_llm3(raw: str) -> LLM3Output:
        d = json.loads(raw)
        d.setdefault("session_summary", "Session completed.")
        d.setdefault("update_profile", True)
        d.setdefault("emotional_themes", [])
        d.setdefault("thinking_patterns", [])
        d.setdefault("behavioral_patterns", [])
        d.setdefault("interpersonal_dynamics", [])
        d.setdefault("stressors", [])
        d.setdefault("unclear_areas", [])
        d.setdefault("risk_assessment", "No immediate risk identified.")
        d.setdefault("protective_factors", [])
        d.setdefault("updated_primary_concern", None)
        return LLM3Output.model_validate(d)

    def generate_opening_context(self, profile_recap: str | None) -> list:
        if profile_recap:
            return [
                {
                    "role": "user",
                    "content": (
                        f"{profile_recap}\n\n"
                        "Start the psychiatric session. Greet the patient warmly, "
                        "briefly acknowledge continuity if it feels right, then use && "
                        "to add an open question at the end — e.g. "
                        "'Welcome back, it's good to see you. && How have things been for you since we last spoke?'"
                    ),
                }
            ]
        else:
            return [
                {
                    "role": "user",
                    "content": (
                        "Start the psychiatric session. Greet the patient warmly and naturally, "
                        "then use && to add an open question at the end — e.g. "
                        "'Hello, I'm Dr. Aiden. I'm here to listen. && What brings you here today?'"
                    ),
                }
            ]

    def psychiatrist_response(
        self,
        context: list,
        patient_info: dict = None,
        medium_term_memory: str | None = None,
    ) -> LLM1Output:
        try:
            messages = [_msg("system", LLM1_SYSTEM_PROMPT)]
            stable = self._build_stable_system(patient_info, medium_term_memory)
            if stable:
                messages.append(_msg("system", stable))
            for m in context:
                messages.append(_msg(m["role"], m["content"]))

            raw = self._call(self.model1, messages, temperature=0.6, max_tokens=1024)
            return self._parse_llm1(raw)
        except Exception as e:
            print(f"[HF LLM1 ERROR] {e}")
            raise e

    def internal_reasoning(
        self,
        context: list,
        stable_prefix: str | None = None,
    ) -> LLM2Output:
        try:
            messages = [_msg("system", LLM2_SYSTEM_PROMPT)]
            # stable_prefix = demographics + profile recap (built by orchestrator)
            if stable_prefix:
                messages.append(_msg("user", stable_prefix))
            for m in context:
                messages.append(_msg(m["role"], m["content"]))

            raw = self._call(self.model2, messages, temperature=0.1, max_tokens=1024)
            return self._parse_llm2(raw)
        except Exception as e:
            print(f"[HF LLM2 ERROR] {e}")
            raise e

    def psychiatrist_query_response(self, context: list, retrieved_context: str) -> str:
        try:
            sys_prompt = (
                "You are a compassionate AI psychiatrist. The patient has asked for advice. "
                "Synthesize a thoughtful response using the following clinical guidelines:\n\n"
                f"{retrieved_context}\n\n"
                "Keep your response empathetic, natural, and under 4 sentences. Do not use markdown."
            )
            messages = [_msg("system", sys_prompt)]
            for m in context:
                messages.append(_msg(m["role"], m["content"]))

            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                temperature=0.5,
                max_tokens=512,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[HF QUERY ERROR] {e}")
            raise e

    def generate_end_of_session_profile(
        self, old_profile: dict, session_history: list, patient_info: dict = None
    ) -> LLM3Output:
        try:
            messages = [_msg("system", LLM3_SYSTEM_PROMPT)]
            if patient_info:
                demographics = (
                    f"PATIENT DEMOGRAPHICS:\n"
                    f"- Name: {patient_info.get('name', 'Unknown')}\n"
                    f"- Age: {patient_info.get('age', 'Unknown')}\n"
                    f"- Gender: {patient_info.get('gender', 'Unknown')}\n"
                    f"- Nationality: {patient_info.get('nationality', 'Unknown')}\n"
                    f"- Primary Concern: {patient_info.get('primary_concern', 'Unknown')}"
                )
                messages.append(_msg("system", demographics))

            formatted_history = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in session_history
            )
            user_prompt = (
                f"EXISTING PROFILE:\n{old_profile}\n\n"
                f"RECENT SESSION TRANSCRIPT:\n{formatted_history}\n\n"
                "Please generate the 100-200 word session_summary and the merged, deduplicated clinical profile."
            )
            messages.append(_msg("user", user_prompt))

            raw = self._call(self.model1, messages, temperature=0.2, max_tokens=1500)
            return self._parse_llm3(raw)
        except Exception as e:
            print(f"[HF LLM3 ERROR] {e}")
            raise e

    def summarize_history(self, turns: list) -> str:
        if not turns:
            return ""
        try:
            formatted = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in turns
            )
            messages = [
                _msg(
                    "system",
                    "You are a clinical note-taker. Summarize the following "
                    "patient-psychiatrist conversation excerpt in 3-5 sentences, "
                    "third-person clinical register. Capture key symptoms, "
                    "themes, and any safety concerns. Be concise.",
                ),
                _msg("user", formatted),
            ]
            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                temperature=0.3,
                max_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[HF SUMMARIZE ERROR] {e}")
            raise e
