import os
import json
from groq import Groq
from core.ports import LLM1Output, LLM2Output, LLM3Output
from core.prompts import LLM1_SYSTEM_PROMPT, LLM2_SYSTEM_PROMPT, LLM3_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Groq prompt-caching helpers
#
# Groq (beta) caches any prefix up to the LAST message that contains a
# cache_control marker. Multiple markers create cascading cache levels.
#
# Cache levels we exploit:
#   Level 1 (all calls): system prompt — constant across all patients/sessions
#   Level 2 (LLM1+LLM2): demographics + medium-term memory — constant within
#     a session; only changes when LLM2 fires and updates long_term_memory
#   Level 3 (dynamic): conversation history + RAG context — changes every turn
# ---------------------------------------------------------------------------

def _cached_msg(role: str, content: str) -> dict:
    """Message with Groq beta cache_control breakpoint."""
    return {
        "role": role,
        "content": [
            {
                "type": "text",
                "text": content,
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }


def _msg(role: str, content: str) -> dict:
    """Plain message (no cache marker)."""
    return {"role": role, "content": content}


class GroqLLMProvider:
    """
    Concrete implementation of the LLMProvider protocol using the Groq API.

    Prompt caching strategy (Groq beta cache_control):

    LLM1 psychiatrist_response — two cache levels:
      [1] system, cached  LLM1_SYSTEM_PROMPT           (~700 tokens, never changes)
      [2] system, cached  demographics + medium-term    (~200-400 tokens, stable per session)
          memory (long_term_memory recap)
      [3] dynamic         conversation history          (changes every turn)

    LLM2 internal_reasoning — two cache levels:
      [1] system, cached  LLM2_SYSTEM_PROMPT           (~600 tokens, never changes)
      [2] user,   cached  demographics + profile_recap  (~200-400 tokens, stable between
          (medium-term memory)                          LLM2 calls within a session)
      [3] dynamic         history[-6:] + analysis ctx   (changes every turn)

    Savings estimate vs. baseline (no caching):
      - LLM1: ~1,000-1,100 cached tokens per turn after warm-up
      - LLM2: ~1,200-1,400 cached tokens per ANALYZE call
    """
    def __init__(self, model1: str, model2: str):
        self.model1 = model1
        self.model2 = model2
        self.client = Groq()

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
        """
        LLM1 fast path. Message order:
          [1] system, CACHED  LLM1_SYSTEM_PROMPT         (constant)
          [2] system, CACHED  demographics + MTM recap    (stable within session)
          [3] dynamic         conversation history        (changes every turn)

        `medium_term_memory` is the long_term_memory recap string built by
        the orchestrator from profile_store. It is constant between LLM2 updates.
        """
        try:
            # Level 1: constant system prompt — cached across all patients
            messages = [_cached_msg("system", LLM1_SYSTEM_PROMPT)]

            # Level 2: stable patient context — cached within a session
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
            if medium_term_memory:
                stable_parts.append(
                    f"PATIENT MEDIUM-TERM MEMORY (prior sessions & patterns — do not quote verbatim):\n"
                    f"{medium_term_memory}"
                )
            if stable_parts:
                messages.append(_cached_msg("system", "\n\n".join(stable_parts)))

            # Level 3: dynamic conversation history
            for m in context:
                messages.append(_msg(m["role"], m["content"]))

            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.6,
                max_completion_tokens=1024,
            )
            raw = response.choices[0].message.content
            return LLM1Output.model_validate_json(raw)
        except Exception as e:
            print(f"[Groq LLM1 ERROR] {e}")
            raise e

    def internal_reasoning(
        self,
        context: list,
        stable_prefix: str | None = None,
    ) -> LLM2Output:
        """
        LLM2 analysis path. Message order:
          [1] system, CACHED  LLM2_SYSTEM_PROMPT         (constant)
          [2] user,   CACHED  stable_prefix              (demographics + profile_recap,
                                                          stable between LLM2 calls)
          [3] dynamic         history[-6:] + analysis ctx (changes every ANALYZE trigger)

        `stable_prefix` is built by the orchestrator and contains demographics +
        medium-term memory (profile_recap). It is constant for the lifetime of a
        session between LLM2 updates — giving a solid cache hit on the 70b model.
        """
        try:
            # Level 1: constant system prompt
            messages = [_cached_msg("system", LLM2_SYSTEM_PROMPT)]

            # Level 2: stable patient context (demographics + profile recap)
            if stable_prefix:
                messages.append(_cached_msg("user", stable_prefix))

            # Level 3: dynamic history + analysis context
            for m in context:
                messages.append(_msg(m["role"], m["content"]))

            response = self.client.chat.completions.create(
                model=self.model2,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_completion_tokens=1024,
            )
            raw = response.choices[0].message.content
            return LLM2Output.model_validate_json(raw)
        except Exception as e:
            print(f"[Groq LLM2 ERROR] {e}")
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
                max_completion_tokens=512,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Groq QUERY ERROR] {e}")
            raise e

    def generate_end_of_session_profile(
        self, old_profile: dict, session_history: list, patient_info: dict = None
    ) -> LLM3Output:
        try:
            # Level 1: constant system prompt — cached across all patients
            messages = [_cached_msg("system", LLM3_SYSTEM_PROMPT)]

            # Level 2: patient demographics — small, per-patient, no cache needed
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

            # Level 3: dynamic content — old profile + session transcript
            formatted_history = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in session_history
            )
            user_prompt = (
                f"EXISTING PROFILE:\n{old_profile}\n\n"
                f"RECENT SESSION TRANSCRIPT:\n{formatted_history}\n\n"
                "Please generate the 100-200 word session_summary and the merged, deduplicated clinical profile."
            )
            messages.append(_msg("user", user_prompt))

            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_completion_tokens=1500,
            )
            raw = response.choices[0].message.content
            return LLM3Output.model_validate_json(raw)
        except Exception as e:
            print(f"[Groq LLM3 ERROR] {e}")
            raise e


    def summarize_history(self, turns: list) -> str:
        if not turns:
            return ""
        try:
            formatted = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in turns
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a clinical note-taker. Summarize the following "
                        "patient-psychiatrist conversation excerpt in 3-5 sentences, "
                        "third-person clinical register. Capture key symptoms, "
                        "themes, and any safety concerns. Be concise."
                    ),
                },
                {"role": "user", "content": formatted},
            ]
            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                temperature=0.3,
                max_completion_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Groq SUMMARIZE ERROR] {e}")
            raise e
